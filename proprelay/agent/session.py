"""Realtime Voice Session Orchestrator for PropRelay Agent."""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import time
import uuid
from enum import StrEnum
from typing import Any, Literal, cast

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    TurnHandlingOptions,
    inference,
    llm,
    stt,
)
from livekit.agents.metrics import base as metrics_base
from livekit.agents.voice import events as voice_events
from livekit.plugins import openai, silero
from pydantic import BaseModel, ConfigDict, Field

from proprelay.agent.prompts import DEFAULT_AGENT_INSTRUCTIONS
from proprelay.agent.tools import AgentTools
from proprelay.agent.voice_tools import create_voice_tools
from proprelay.events.journal import IEventPublisher
from proprelay.events.schemas import DomainEvent, EventType
from proprelay.observability.store import (
    ErrorCode,
    MetricsStore,
    RuntimeState,
    SessionReportSummary,
    StructuredError,
    TurnMetric,
)
from proprelay.stt.faster_whisper import FasterWhisperSTT
from proprelay.workflows.context import ConversationContext
from proprelay.workflows.state import WorkflowState

logger = logging.getLogger(__name__)


class VoiceState(StrEnum):
    """Authoritative application voice runtime states."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    TOOL_EXECUTING = "TOOL_EXECUTING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    ERROR = "ERROR"


class VoiceSessionConfig(BaseModel):
    """Runtime configuration parameters for a PropRelay voice session."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(default_factory=lambda: f"sess-{uuid.uuid4().hex[:10]}")
    stt_model: str = Field(default="base.en")
    stt_device: str | None = Field(default=None)
    stt_compute_type: str | None = Field(default=None)
    ollama_model: str = Field(default="qwen2.5:7b")
    ollama_base_url: str = Field(default="http://127.0.0.1:11434/v1")
    kokoro_base_url: str = Field(default="http://127.0.0.1:8880/v1")
    kokoro_voice: str = Field(default="af_alloy")
    turn_detection_version: str = Field(default="v1-mini")
    turn_detection_unlikely_threshold: float | None = Field(default=None)
    turn_detection_backchannel_threshold: float | None = Field(default=None)
    endpointing_mode: Literal["fixed", "dynamic"] = Field(default="fixed")
    min_endpointing_delay: float = Field(default=0.5)
    max_endpointing_delay: float = Field(default=3.0)
    min_interruption_duration: float = Field(default=0.5)
    enable_preemptive_generation: bool = Field(default=True)
    enable_preemptive_tts: bool = Field(default=False)
    welcome_message: str = Field(
        default="Hi, I'm PropRelay. I can help you find a property or arrange a showing. What are you looking for?"
    )

    @classmethod
    def from_env(cls) -> VoiceSessionConfig:
        """Create configuration loaded from environment variables."""
        return cls(
            stt_model=os.getenv("PROPRELAY_STT_MODEL", "base.en"),
            stt_device=os.getenv("PROPRELAY_STT_DEVICE") or None,
            stt_compute_type=os.getenv("PROPRELAY_STT_COMPUTE_TYPE") or None,
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
            kokoro_base_url=os.getenv("KOKORO_BASE_URL", "http://127.0.0.1:8880/v1"),
            kokoro_voice=os.getenv("KOKORO_VOICE", "af_alloy"),
            turn_detection_version=os.getenv("PROPRELAY_TURN_DETECTION", "v1-mini"),
            turn_detection_unlikely_threshold=float(thresh)
            if (thresh := os.getenv("PROPRELAY_UNLIKELY_THRESHOLD"))
            else None,
            turn_detection_backchannel_threshold=float(backchannel)
            if (backchannel := os.getenv("PROPRELAY_BACKCHANNEL_THRESHOLD"))
            else None,
            endpointing_mode=cast(
                Literal["fixed", "dynamic"],
                os.getenv("PROPRELAY_ENDPOINTING_MODE", "fixed"),
            ),
            min_endpointing_delay=float(os.getenv("PROPRELAY_MIN_ENDPOINTING", "0.5")),
            max_endpointing_delay=float(os.getenv("PROPRELAY_MAX_ENDPOINTING", "3.0")),
            min_interruption_duration=float(os.getenv("PROPRELAY_MIN_INTERRUPTION", "0.5")),
            enable_preemptive_generation=os.getenv("PROPRELAY_PREEMPTIVE_GEN", "true").lower()
            == "true",
            enable_preemptive_tts=os.getenv("PROPRELAY_PREEMPTIVE_TTS", "false").lower() == "true",
            welcome_message=os.getenv(
                "PROPRELAY_WELCOME_MESSAGE",
                "Hi, I'm PropRelay. I can help you find a property or arrange a showing. What are you looking for?",
            ),
        )


class LatencyTracker:
    """Tracks latency components across speech, turn-taking, LLM, tools, and TTS."""

    def __init__(self) -> None:
        self.last_stt_duration: float = 0.0
        self.last_llm_ttft: float = 0.0
        self.last_llm_duration: float = 0.0
        self.last_tts_ttfb: float = 0.0
        self.last_tts_duration: float = 0.0
        self.last_eou_delay: float = 0.0
        self.interruption_count: int = 0
        self.last_turn_timestamp: float = time.time()

    def record_metrics(self, metric: metrics_base.AgentMetrics) -> dict[str, Any] | None:
        """Process incoming LiveKit AgentMetrics and return summary if turn completed."""
        if isinstance(metric, metrics_base.STTMetrics):
            self.last_stt_duration = metric.duration
        elif isinstance(metric, metrics_base.LLMMetrics):
            self.last_llm_ttft = metric.ttft
            self.last_llm_duration = metric.duration
        elif isinstance(metric, metrics_base.TTSMetrics):
            self.last_tts_ttfb = metric.ttfb
            self.last_tts_duration = metric.duration
        elif isinstance(metric, metrics_base.EOUMetrics):
            self.last_eou_delay = metric.end_of_utterance_delay
        elif isinstance(metric, metrics_base.InterruptionMetrics):
            self.interruption_count += metric.num_interruptions

        # When TTS completes, we produce an aggregated latency record
        if isinstance(metric, metrics_base.TTSMetrics) and not metric.streamed:
            reconstructed_total = (
                self.last_eou_delay
                + self.last_stt_duration
                + self.last_llm_ttft
                + self.last_tts_ttfb
            )
            return {
                "t_turn_eou_ms": round(self.last_eou_delay * 1000, 2),
                "t_stt_ms": round(self.last_stt_duration * 1000, 2),
                "t_llm_ttft_ms": round(self.last_llm_ttft * 1000, 2),
                "t_llm_total_ms": round(self.last_llm_duration * 1000, 2),
                "t_tts_ttfb_ms": round(self.last_tts_ttfb * 1000, 2),
                "t_tts_total_ms": round(self.last_tts_duration * 1000, 2),
                "t_total_reconstructed_ms": round(reconstructed_total * 1000, 2),
                "interruption_count": self.interruption_count,
            }
        return None


class VoiceSession:
    """Manages the full lifecycle of a PropRelay local voice session."""

    def __init__(
        self,
        config: VoiceSessionConfig,
        agent_tools: AgentTools,
        event_publisher: IEventPublisher | None = None,
        metrics_store: MetricsStore | None = None,
        *,
        stt_instance: Any | None = None,
        vad_instance: Any | None = None,
        llm_instance: Any | None = None,
        tts_instance: Any | None = None,
    ) -> None:
        self.config = config
        self._tools_service = agent_tools
        self._publisher = event_publisher
        self._metrics_store = metrics_store
        self._state = VoiceState.DISCONNECTED
        self._latency_tracker = LatencyTracker()
        self._lock = asyncio.Lock()
        self._session_start_time: float = time.time()

        # Structured conversational context
        self._context = ConversationContext(
            session_id=config.session_id,
            on_state_change=self._on_workflow_state_change,
        )
        self._tools_service.set_context(self._context)

        # Construct or use injected voice pipeline components
        self._vad = vad_instance or silero.VAD.load()

        if stt_instance is not None:
            self._stt = stt_instance
        else:
            local_stt = FasterWhisperSTT(
                model=config.stt_model,
                device=config.stt_device,
                compute_type=config.stt_compute_type,
            )
            self._stt = stt.StreamAdapter(stt=local_stt, vad=self._vad)

        self._llm = llm_instance or openai.LLM.with_ollama(
            model=config.ollama_model,
            base_url=config.ollama_base_url,
        )

        self._tts = tts_instance or openai.TTS(
            model="kokoro",
            voice=config.kokoro_voice,
            base_url=config.kokoro_base_url,
            api_key="not-needed",
            response_format="wav",
        )

        # Wire turn handling options
        turn_detector_kwargs: dict[str, Any] = {
            "version": config.turn_detection_version,
            "local_fallback": True,
        }
        if config.turn_detection_unlikely_threshold is not None:
            turn_detector_kwargs["unlikely_threshold"] = config.turn_detection_unlikely_threshold
        if config.turn_detection_backchannel_threshold is not None:
            turn_detector_kwargs["backchannel_threshold"] = (
                config.turn_detection_backchannel_threshold
            )

        turn_detector = inference.TurnDetector(**turn_detector_kwargs)
        self._turn_handling = TurnHandlingOptions(
            turn_detection=turn_detector,
            endpointing={
                "mode": config.endpointing_mode,
                "min_delay": config.min_endpointing_delay,
                "max_delay": config.max_endpointing_delay,
            },
            interruption={
                "enabled": True,
                "mode": "vad",
                "min_duration": config.min_interruption_duration,
                "resume_false_interruption": True,
            },
            preemptive_generation={
                "enabled": config.enable_preemptive_generation,
                "preemptive_tts": config.enable_preemptive_tts,
            },
        )

        # Register tools
        self._voice_tools = create_voice_tools(
            agent_tools=self._tools_service,
            session_id=config.session_id,
        )

        # Create Agent
        self._agent = Agent(
            instructions=DEFAULT_AGENT_INSTRUCTIONS,
            tools=cast(Any, self._voice_tools),
        )

        # Create AgentSession
        self._session: AgentSession[Any] = AgentSession(
            stt=self._stt,
            vad=self._vad,
            llm=self._llm,
            tts=self._tts,
            turn_handling=self._turn_handling,
        )

        self._register_event_handlers()

    @property
    def state(self) -> VoiceState:
        return self._state

    @property
    def session_id(self) -> str:
        return self.config.session_id

    @property
    def context(self) -> ConversationContext:
        return self._context

    def _on_workflow_state_change(self, old_state: WorkflowState, new_state: WorkflowState) -> None:
        """Publish workflow.state.changed domain event when workflow state transitions."""
        if self._publisher:
            payload: dict[str, Any] = {
                "old_state": old_state.value,
                "new_state": new_state.value,
                "workflow_type": self._context.workflow_type.value,
                "turn_id": str(self._context.current_turn),
            }
            if self._context.pending_action:
                payload["pending_action"] = self._context.pending_action.model_dump(mode="json")
            if self._context.selected_property:
                payload["selected_property"] = self._context.selected_property.model_dump(
                    mode="json"
                )
            event = DomainEvent(
                event_type=EventType.WORKFLOW_STATE_CHANGED.value,
                timestamp=datetime.datetime.now(datetime.UTC),
                session_id=self.config.session_id,
                workflow_id=self._context.workflow_id,
                turn_id=str(self._context.current_turn),
                payload=payload,
            )
            asyncio.create_task(self._publisher.publish(event))

    async def _set_state(self, new_state: VoiceState, extra: dict[str, Any] | None = None) -> None:
        async with self._lock:
            old_state = self._state
            self._state = new_state
            logger.info("Voice state: %s -> %s", old_state.value, new_state.value)

        if self._publisher:
            payload = {"old_state": old_state.value, "new_state": new_state.value}
            if extra:
                payload.update(extra)
            event = DomainEvent(
                event_type=EventType.VOICE_STATE_CHANGED.value,
                timestamp=datetime.datetime.now(datetime.UTC),
                session_id=self.config.session_id,
                workflow_id=self._context.workflow_id,
                turn_id=str(self._context.current_turn),
                payload=payload,
            )
            await self._publisher.publish(event)

    def _register_event_handlers(self) -> None:
        """Register listeners on AgentSession to drive state and observability."""

        @self._session.on("agent_state_changed")
        def _on_agent_state(ev: voice_events.AgentStateChangedEvent) -> None:
            state_map = {
                "listening": VoiceState.LISTENING,
                "thinking": VoiceState.THINKING,
                "speaking": VoiceState.SPEAKING,
                "idle": VoiceState.LISTENING,
                "initializing": VoiceState.CONNECTING,
            }
            mapped = state_map.get(ev.new_state)
            if mapped and mapped != self._state:
                asyncio.create_task(self._set_state(mapped))

        @self._session.on("tool_execution_updated")
        def _on_tool_exec(ev: voice_events.ToolExecutionUpdatedEvent) -> None:
            update = ev.update
            if isinstance(update, voice_events.ToolCallStarted):
                tool_name = (
                    update.function_call.name if hasattr(update, "function_call") else "tool"
                )
                asyncio.create_task(self._set_state(VoiceState.TOOL_EXECUTING, {"tool": tool_name}))
            elif isinstance(update, voice_events.ToolCallEnded):
                call_id = update.call_id if hasattr(update, "call_id") else ""
                asyncio.create_task(self._set_state(VoiceState.THINKING, {"call_id": call_id}))

        @self._session.on("user_input_transcribed")
        def _on_user_transcript(ev: voice_events.UserInputTranscribedEvent) -> None:
            if not ev.transcript.strip():
                return
            if ev.is_final:
                self._context.advance_turn()
            if self._publisher:
                event = DomainEvent(
                    event_type=EventType.VOICE_TRANSCRIPT_USER.value,
                    timestamp=datetime.datetime.now(datetime.UTC),
                    session_id=self.config.session_id,
                    workflow_id=self._context.workflow_id,
                    turn_id=str(self._context.current_turn),
                    payload={
                        "transcript": ev.transcript.strip(),
                        "is_final": ev.is_final,
                        "language": str(ev.language) if ev.language else "en",
                    },
                )
                asyncio.create_task(self._publisher.publish(event))

        @self._session.on("conversation_item_added")
        def _on_conversation_item(ev: voice_events.ConversationItemAddedEvent) -> None:
            item = ev.item
            if isinstance(item, llm.ChatMessage) and item.role == "assistant":
                text = item.text_content
                if text and text.strip() and self._publisher:
                    event = DomainEvent(
                        event_type=EventType.VOICE_TRANSCRIPT_AGENT.value,
                        timestamp=datetime.datetime.now(datetime.UTC),
                        session_id=self.config.session_id,
                        workflow_id=self._context.workflow_id,
                        turn_id=str(self._context.current_turn),
                        payload={"transcript": text.strip()},
                    )
                    asyncio.create_task(self._publisher.publish(event))

        @self._session.on("metrics_collected")
        def _on_metrics(ev: voice_events.MetricsCollectedEvent) -> None:
            summary = self._latency_tracker.record_metrics(ev.metrics)
            if summary:
                runtime_state = (
                    RuntimeState.COLD_START
                    if self._context.current_turn <= 1
                    else RuntimeState.WARM_RUNTIME
                )
                if self._metrics_store:
                    turn_metric = TurnMetric(
                        session_id=self.config.session_id,
                        workflow_id=self._context.workflow_id,
                        turn_id=str(self._context.current_turn),
                        runtime_state=runtime_state,
                        endpointing_ms=summary.get("t_turn_eou_ms"),
                        stt_ms=summary.get("t_stt_ms"),
                        llm_ttft_ms=summary.get("t_llm_ttft_ms"),
                        llm_total_ms=summary.get("t_llm_total_ms"),
                        tts_ttfb_ms=summary.get("t_tts_ttfb_ms"),
                        turn_total_ms=summary.get("t_total_reconstructed_ms"),
                    )
                    self._metrics_store.record_turn_metric(turn_metric)

                if self._publisher:
                    event = DomainEvent(
                        event_type=EventType.VOICE_LATENCY_METRICS.value,
                        timestamp=datetime.datetime.now(datetime.UTC),
                        session_id=self.config.session_id,
                        workflow_id=self._context.workflow_id,
                        turn_id=str(self._context.current_turn),
                        payload=summary,
                    )
                    asyncio.create_task(self._publisher.publish(event))

        @self._session.on("error")
        def _on_error(ev: voice_events.ErrorEvent) -> None:
            err_msg = str(ev.error)
            logger.error("AgentSession error: %s", err_msg)
            structured_err = StructuredError(
                error_code=ErrorCode.CONNECTION_ERROR,
                message=err_msg,
                session_id=self.config.session_id,
                workflow_id=self._context.workflow_id,
                turn_id=str(self._context.current_turn),
            )
            if self._metrics_store:
                self._metrics_store.record_error(structured_err)
            if self._publisher:
                err_event = DomainEvent(
                    event_type=EventType.SYSTEM_ERROR.value,
                    timestamp=datetime.datetime.now(datetime.UTC),
                    session_id=self.config.session_id,
                    workflow_id=self._context.workflow_id,
                    turn_id=str(self._context.current_turn),
                    payload=structured_err.model_dump(mode="json"),
                )
                asyncio.create_task(self._publisher.publish(err_event))
            asyncio.create_task(self._set_state(VoiceState.ERROR, {"error": err_msg}))

    async def start(
        self,
        room: rtc.Room,
        participant: rtc.RemoteParticipant | None = None,
    ) -> None:
        """Start the voice session inside the connected LiveKit room."""
        self._session_start_time = time.time()
        await self._set_state(VoiceState.CONNECTING)

        logger.info(
            "Starting VoiceSession %s in room '%s'...",
            self.config.session_id,
            room.name,
        )

        if self._publisher:
            start_event = DomainEvent(
                event_type=EventType.SESSION_STARTED.value,
                timestamp=datetime.datetime.now(datetime.UTC),
                session_id=self.config.session_id,
                workflow_id=self._context.workflow_id,
                payload={
                    "stt_model": self.config.stt_model,
                    "ollama_model": self.config.ollama_model,
                    "kokoro_voice": self.config.kokoro_voice,
                },
            )
            await self._publisher.publish(start_event)

        # Start LiveKit AgentSession
        await self._session.start(self._agent, room=room)

        # Speak short initial welcome
        if self.config.welcome_message:
            logger.info("Speaking welcome greeting: '%s'", self.config.welcome_message)
            self._session.say(self.config.welcome_message)

        await self._set_state(VoiceState.LISTENING)

    async def aclose(self) -> None:
        """Cleanly terminate voice session and release resources."""
        await self._set_state(VoiceState.DISCONNECTED)
        duration_ms = (time.time() - self._session_start_time) * 1000

        if self._metrics_store:
            report = SessionReportSummary(
                session_id=self.config.session_id,
                started_at=datetime.datetime.fromtimestamp(
                    self._session_start_time, tz=datetime.UTC
                ),
                completed_at=datetime.datetime.now(datetime.UTC),
                duration_ms=round(duration_ms, 2),
                total_turns=self._context.current_turn,
                total_tool_calls=self._tools_service.metrics.tool_calls_count,
                workflows_completed=1 if self._tools_service.metrics.workflow_completed else 0,
                workflows_abandoned=1 if self._tools_service.metrics.workflow_abandoned else 0,
                errors_count=1 if self._state == VoiceState.ERROR else 0,
            )
            self._metrics_store.record_session_report(report)

        if self._publisher:
            close_event = DomainEvent(
                event_type=EventType.SESSION_COMPLETED.value,
                timestamp=datetime.datetime.now(datetime.UTC),
                session_id=self.config.session_id,
                workflow_id=self._context.workflow_id,
                duration_ms=round(duration_ms, 2),
                payload={
                    "total_turns": self._context.current_turn,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            await self._publisher.publish(close_event)

        await self._session.aclose()
        if hasattr(self._stt, "aclose"):
            await self._stt.aclose()
