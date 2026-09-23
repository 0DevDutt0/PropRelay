"""Unit tests for VoiceSession orchestrator, state transitions, and latency tracking."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from livekit.agents.metrics import base as metrics_base
from livekit.agents.voice import events as voice_events

from proprelay.agent.session import (
    LatencyTracker,
    VoiceSession,
    VoiceSessionConfig,
    VoiceState,
)
from proprelay.events.schemas import EventType


@pytest.fixture
def mock_pipeline() -> dict[str, MagicMock]:
    stt_mock = MagicMock()
    vad_mock = MagicMock()
    llm_mock = MagicMock()
    tts_mock = MagicMock()
    tools_mock = MagicMock()
    publisher_mock = MagicMock()
    publisher_mock.publish = AsyncMock()

    return {
        "stt": stt_mock,
        "vad": vad_mock,
        "llm": llm_mock,
        "tts": tts_mock,
        "tools": tools_mock,
        "publisher": publisher_mock,
    }


def test_session_config_defaults() -> None:
    config = VoiceSessionConfig.from_env()
    assert config.stt_model == "base.en"
    assert config.ollama_model == "qwen2.5:7b"
    assert config.kokoro_voice == "af_alloy"
    assert config.turn_detection_version == "v1-mini"
    assert config.enable_preemptive_generation is True
    assert "PropRelay" in config.welcome_message


def test_latency_tracker_reconstruction() -> None:
    tracker = LatencyTracker()

    # 1. End of utterance
    eou = metrics_base.EOUMetrics(
        timestamp=100.0,
        end_of_utterance_delay=0.35,
        transcription_delay=0.1,
        on_user_turn_completed_delay=0.05,
    )
    assert tracker.record_metrics(eou) is None

    # 2. STT
    stt_m = metrics_base.STTMetrics(
        label="stt",
        request_id="req-1",
        timestamp=100.35,
        duration=0.12,
        audio_duration=1.5,
        streamed=False,
    )
    assert tracker.record_metrics(stt_m) is None

    # 3. LLM
    llm_m = metrics_base.LLMMetrics(
        label="llm",
        request_id="req-2",
        timestamp=100.47,
        duration=0.45,
        ttft=0.08,
        cancelled=False,
        completion_tokens=20,
        prompt_tokens=50,
        prompt_cached_tokens=0,
        cache_creation_tokens=0,
        reasoning_tokens=0,
        total_tokens=70,
        tokens_per_second=40.0,
    )
    assert tracker.record_metrics(llm_m) is None

    # 4. TTS (non-streamed terminal metric)
    tts_m = metrics_base.TTSMetrics(
        label="tts",
        request_id="req-3",
        timestamp=100.92,
        ttfb=0.09,
        duration=0.25,
        audio_duration=2.0,
        streamed=False,
        cancelled=False,
        characters_count=50,
        input_tokens=0,
        output_tokens=0,
        connection_reused=True,
    )
    summary = tracker.record_metrics(tts_m)
    assert summary is not None
    assert summary["t_turn_eou_ms"] == 350.0
    assert summary["t_stt_ms"] == 120.0
    assert summary["t_llm_ttft_ms"] == 80.0
    assert summary["t_tts_ttfb_ms"] == 90.0
    assert summary["t_total_reconstructed_ms"] == 640.0


@pytest.mark.asyncio
async def test_session_state_changes(mock_pipeline: dict[str, MagicMock]) -> None:
    config = VoiceSessionConfig(session_id="test-session-1")
    session = VoiceSession(
        config=config,
        agent_tools=mock_pipeline["tools"],
        event_publisher=mock_pipeline["publisher"],
        stt_instance=mock_pipeline["stt"],
        vad_instance=mock_pipeline["vad"],
        llm_instance=mock_pipeline["llm"],
        tts_instance=mock_pipeline["tts"],
    )

    assert session.state == VoiceState.DISCONNECTED

    await session._set_state(VoiceState.LISTENING)
    assert session.state.value == VoiceState.LISTENING.value

    # Verify event emission
    mock_pipeline["publisher"].publish.assert_called_once()
    event = mock_pipeline["publisher"].publish.call_args[0][0]
    assert event.event_type == EventType.VOICE_STATE_CHANGED.value
    assert event.payload["new_state"] == VoiceState.LISTENING.value


@pytest.mark.asyncio
async def test_session_tool_execution_state(mock_pipeline: dict[str, MagicMock]) -> None:
    config = VoiceSessionConfig(session_id="test-session-2")
    session = VoiceSession(
        config=config,
        agent_tools=mock_pipeline["tools"],
        event_publisher=mock_pipeline["publisher"],
        stt_instance=mock_pipeline["stt"],
        vad_instance=mock_pipeline["vad"],
        llm_instance=mock_pipeline["llm"],
        tts_instance=mock_pipeline["tts"],
    )

    # Simulate tool start
    from livekit.agents import llm

    func_call = llm.FunctionCall(
        call_id="call-1",
        name="search_properties",
        arguments="{}",
    )
    tool_start_ev = voice_events.ToolExecutionUpdatedEvent(
        update=voice_events.ToolCallStarted(function_call=func_call)
    )
    session._session.emit("tool_execution_updated", tool_start_ev)
    await asyncio.sleep(0.05)
    assert session.state.value == VoiceState.TOOL_EXECUTING.value

    # Simulate tool end
    tool_end_ev = voice_events.ToolExecutionUpdatedEvent(
        update=voice_events.ToolCallEnded(id="1", call_id="c1", status="done")
    )
    session._session.emit("tool_execution_updated", tool_end_ev)
    await asyncio.sleep(0.05)
    assert session.state.value == VoiceState.THINKING.value


@pytest.mark.asyncio
async def test_session_user_transcription_event(mock_pipeline: dict[str, MagicMock]) -> None:
    config = VoiceSessionConfig(session_id="test-session-3")
    session = VoiceSession(
        config=config,
        agent_tools=mock_pipeline["tools"],
        event_publisher=mock_pipeline["publisher"],
        stt_instance=mock_pipeline["stt"],
        vad_instance=mock_pipeline["vad"],
        llm_instance=mock_pipeline["llm"],
        tts_instance=mock_pipeline["tts"],
    )

    tr_ev = voice_events.UserInputTranscribedEvent(
        transcript="Find apartments in Downtown",
        is_final=True,
    )
    session._session.emit("user_input_transcribed", tr_ev)
    await asyncio.sleep(0.05)

    mock_pipeline["publisher"].publish.assert_called()
    calls = mock_pipeline["publisher"].publish.call_args_list
    events = [c[0][0] for c in calls if c[0][0].event_type == EventType.VOICE_TRANSCRIPT_USER.value]
    assert len(events) == 1
    assert events[0].payload["transcript"] == "Find apartments in Downtown"
    assert events[0].payload["is_final"] is True
