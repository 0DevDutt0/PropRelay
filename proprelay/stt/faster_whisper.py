"""Local Speech-to-Text (STT) adapter wrapping faster-whisper (CTranslate2)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, cast

import numpy as np
from livekit import rtc
from livekit.agents import stt, utils
from livekit.agents.types import (
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    APIConnectOptions,
    NotGivenOr,
)
from livekit.agents.vad import VAD

from proprelay.testing.failure_injection import (
    FailureMode,
    InjectedSTTError,
    should_inject_failure,
)

logger = logging.getLogger(__name__)


def _detect_default_device() -> str:
    """Detect default compute device based on CTranslate2 CUDA availability."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


class FasterWhisperSTT(stt.STT[stt.SpeechEvent]):
    """Local Speech-to-Text implementation wrapping faster-whisper on NVIDIA CUDA or CPU.

    Subclasses LiveKit's `stt.STT` and provides:
    - Zero cloud cost local inference via CTranslate2.
    - Automatic audio buffer conversion from PCM int16 frames to 16kHz float32.
    - Seamless stream adaptation via LiveKit's StreamAdapter and Silero VAD.
    - Lazy model loading and prewarming to prevent conversational cold starts.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        language: str = "en",
        beam_size: int = 1,
        vad: VAD | None = None,
        model_instance: Any | None = None,
    ) -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=False,
                interim_results=False,
            )
        )
        self._model_name = model or os.getenv("PROPRELAY_STT_MODEL", "base.en")
        self._device = device or os.getenv("PROPRELAY_STT_DEVICE", _detect_default_device())

        if compute_type:
            self._compute_type = compute_type
        elif self._device == "cuda":
            self._compute_type = os.getenv("PROPRELAY_STT_COMPUTE_TYPE", "float16")
        else:
            self._compute_type = os.getenv("PROPRELAY_STT_COMPUTE_TYPE", "int8")

        self._language = language or os.getenv("PROPRELAY_STT_LANGUAGE", "en")
        self._beam_size = beam_size
        self._vad = vad
        self._model = model_instance
        self._resampler_cache: dict[int, rtc.AudioResampler] = {}
        self._lock = asyncio.Lock()

    @property
    def model(self) -> str:
        return self._model_name or "base.en"

    @property
    def provider(self) -> str:
        return "faster-whisper"

    def _ensure_model(self) -> Any:
        """Lazily load faster-whisper model on first transcription request."""
        if self._model is not None:
            return self._model

        from faster_whisper import WhisperModel

        logger.info(
            "Loading faster-whisper model '%s' on device '%s' (%s)",
            self._model_name,
            self._device,
            self._compute_type,
        )
        try:
            self._model = WhisperModel(
                model_size_or_path=self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )
        except Exception as e:
            logger.warning(
                "Failed to initialize faster-whisper on device '%s' (%s): %s. Falling back to cpu.",
                self._device,
                self._compute_type,
                e,
            )
            self._device = "cpu"
            self._compute_type = "int8"
            self._model = WhisperModel(
                model_size_or_path=self._model_name,
                device="cpu",
                compute_type="int8",
            )

        return self._model

    def _convert_buffer_to_float32_16k(self, buffer: utils.AudioBuffer) -> np.ndarray[Any, Any]:
        """Convert an incoming AudioBuffer into a 1D float32 16kHz numpy array."""
        frame = utils.merge_frames(buffer) if isinstance(buffer, list) else buffer

        if frame.sample_rate != 16000:
            if frame.sample_rate not in self._resampler_cache:
                self._resampler_cache[frame.sample_rate] = rtc.AudioResampler(
                    input_rate=frame.sample_rate,
                    output_rate=16000,
                    num_channels=1,
                )
            resampled = self._resampler_cache[frame.sample_rate].push(frame)
            if len(resampled) > 0:
                frame = utils.merge_frames(resampled)

        pcm_data = np.frombuffer(frame.data, dtype=np.int16)
        if frame.num_channels > 1:
            pcm_data = pcm_data.reshape(-1, frame.num_channels).mean(axis=1).astype(np.int16)

        return (pcm_data.astype(np.float32) / 32768.0).astype(np.float32)

    async def _recognize_impl(
        self,
        buffer: utils.AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        """Transcribe an audio buffer utterance using local faster-whisper."""
        if should_inject_failure(FailureMode.STT):
            logger.warning("Injected synthetic STT failure triggered")
            raise InjectedSTTError("Injected synthetic faster-whisper transcription error")

        audio_data = self._convert_buffer_to_float32_16k(buffer)
        if len(audio_data) == 0:
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[],
            )

        target_lang = (
            language if (language is not NOT_GIVEN and language is not None) else self._language
        )

        model = self._ensure_model()

        def _transcribe() -> tuple[list[Any], Any]:
            segments_gen, info = model.transcribe(
                audio_data,
                language=target_lang,
                beam_size=self._beam_size,
                condition_on_previous_text=False,
            )
            return list(segments_gen), info

        start_time = time.perf_counter()
        segments, info = await asyncio.to_thread(_transcribe)
        duration = time.perf_counter() - start_time

        transcript_parts = [s.text.strip() for s in segments if s.text and s.text.strip()]
        full_text = " ".join(transcript_parts).strip()

        logger.debug(
            "faster-whisper transcribed %d segments (%.2fs) in %.3fs: '%s'",
            len(segments),
            getattr(info, "duration", 0.0),
            duration,
            full_text,
        )

        detected_lang = getattr(info, "language", target_lang) or "en"
        confidence = 1.0
        if segments:
            # Average avg_logprob if available
            logprobs = [s.avg_logprob for s in segments if hasattr(s, "avg_logprob")]
            if logprobs:
                confidence = float(np.exp(np.mean(logprobs)))

        alternatives = []
        if full_text:
            alternatives.append(
                stt.SpeechData(
                    language=cast(Any, detected_lang),
                    text=full_text,
                    confidence=confidence,
                    start_time=segments[0].start if segments else 0.0,
                    end_time=segments[-1].end if segments else 0.0,
                )
            )

        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=alternatives,
        )

    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.RecognizeStream:
        """Create a streaming recognizer by wrapping this STT in LiveKit's StreamAdapter."""
        vad = self._vad
        if vad is None:
            from livekit.plugins import silero

            vad = silero.VAD.load()

        adapter = stt.StreamAdapter(stt=self, vad=vad)
        return adapter.stream(language=language, conn_options=conn_options)

    def prewarm(self) -> None:
        """Pre-warm CTranslate2 execution engine with a tiny silent audio tensor."""
        try:
            model = self._ensure_model()
            logger.info("Pre-warming faster-whisper STT on %s...", self._device)
            silence = np.zeros(1600, dtype=np.float32)  # 100ms
            model.transcribe(silence, language=self._language, beam_size=1)
            logger.info("faster-whisper STT pre-warmed successfully.")
        except Exception as e:
            logger.warning("faster-whisper STT prewarm encountered error (non-fatal): %s", e)

    async def aclose(self) -> None:
        """Clean up model resources."""
        self._model = None
        self._resampler_cache.clear()
