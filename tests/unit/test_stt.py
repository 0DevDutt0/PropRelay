"""Unit tests for FasterWhisperSTT adapter."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
from livekit import rtc
from livekit.agents import stt
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from proprelay.stt.faster_whisper import FasterWhisperSTT, _detect_default_device


class MockSegment:
    def __init__(self, text: str, start: float, end: float, avg_logprob: float = -0.2) -> None:
        self.text = text
        self.start = start
        self.end = end
        self.avg_logprob = avg_logprob


class MockTranscriptionInfo:
    def __init__(self, duration: float = 2.5, language: str = "en") -> None:
        self.duration = duration
        self.language = language


@pytest.fixture
def mock_whisper_model() -> MagicMock:
    model = MagicMock()
    segments = [
        MockSegment("find a two bedroom", 0.0, 1.2),
        MockSegment("under three thousand dollars", 1.2, 2.5),
    ]
    info = MockTranscriptionInfo(duration=2.5, language="en")
    model.transcribe.return_value = (segments, info)
    return model


def test_device_detection() -> None:
    device = _detect_default_device()
    assert device in ("cuda", "cpu")


def test_stt_initialization() -> None:
    stt_adapter = FasterWhisperSTT(
        model="small.en",
        device="cpu",
        compute_type="int8",
        language="en",
        beam_size=2,
    )
    assert stt_adapter.model == "small.en"
    assert stt_adapter.provider == "faster-whisper"
    assert not stt_adapter.capabilities.streaming


def test_convert_buffer_to_float32_16k_mono() -> None:
    stt_adapter = FasterWhisperSTT(device="cpu", compute_type="int8")

    # 16000 samples of 16kHz mono int16 audio
    raw_samples = (np.sin(np.linspace(0, 100, 16000)) * 10000).astype(np.int16)
    frame = rtc.AudioFrame(
        data=raw_samples.tobytes(),
        sample_rate=16000,
        num_channels=1,
        samples_per_channel=16000,
    )

    audio_float32 = stt_adapter._convert_buffer_to_float32_16k(frame)
    assert isinstance(audio_float32, np.ndarray)
    assert audio_float32.dtype == np.float32
    assert len(audio_float32) == 16000
    assert np.max(np.abs(audio_float32)) <= 1.0


def test_convert_buffer_stereo_to_mono() -> None:
    stt_adapter = FasterWhisperSTT(device="cpu", compute_type="int8")

    # Stereo audio (2 channels, 1000 samples per channel)
    raw_samples = np.ones(2000, dtype=np.int16) * 16384
    frame = rtc.AudioFrame(
        data=raw_samples.tobytes(),
        sample_rate=16000,
        num_channels=2,
        samples_per_channel=1000,
    )

    audio_float32 = stt_adapter._convert_buffer_to_float32_16k(frame)
    assert len(audio_float32) == 1000
    assert np.isclose(audio_float32[0], 0.5, atol=1e-3)


def test_convert_buffer_resampling() -> None:
    stt_adapter = FasterWhisperSTT(device="cpu", compute_type="int8")

    # 48kHz audio resampled to 16kHz
    raw_samples = np.zeros(48000, dtype=np.int16)
    frame = rtc.AudioFrame(
        data=raw_samples.tobytes(),
        sample_rate=48000,
        num_channels=1,
        samples_per_channel=48000,
    )

    audio_float32 = stt_adapter._convert_buffer_to_float32_16k(frame)
    # 48000 samples at 48kHz resampled to 16kHz is ~16000 samples
    assert abs(len(audio_float32) - 16000) < 500


@pytest.mark.asyncio
async def test_recognize_impl_success(mock_whisper_model: MagicMock) -> None:
    stt_adapter = FasterWhisperSTT(
        device="cpu",
        compute_type="int8",
        model_instance=mock_whisper_model,
    )

    raw_samples = np.zeros(16000, dtype=np.int16)
    frame = rtc.AudioFrame(
        data=raw_samples.tobytes(),
        sample_rate=16000,
        num_channels=1,
        samples_per_channel=16000,
    )

    event = await stt_adapter._recognize_impl(
        frame,
        conn_options=DEFAULT_API_CONNECT_OPTIONS,
    )

    assert event.type == stt.SpeechEventType.FINAL_TRANSCRIPT
    assert len(event.alternatives) == 1
    alt = event.alternatives[0]
    assert alt.text == "find a two bedroom under three thousand dollars"
    assert alt.language == "en"
    assert alt.start_time == 0.0
    assert alt.end_time == 2.5
    assert alt.confidence > 0.0


@pytest.mark.asyncio
async def test_recognize_impl_empty_audio() -> None:
    stt_adapter = FasterWhisperSTT(device="cpu", compute_type="int8")
    frame = rtc.AudioFrame(
        data=b"",
        sample_rate=16000,
        num_channels=1,
        samples_per_channel=0,
    )

    event = await stt_adapter._recognize_impl(
        frame,
        conn_options=DEFAULT_API_CONNECT_OPTIONS,
    )

    assert event.type == stt.SpeechEventType.FINAL_TRANSCRIPT
    assert len(event.alternatives) == 0


def test_prewarm_with_mock_model(mock_whisper_model: MagicMock) -> None:
    stt_adapter = FasterWhisperSTT(
        device="cpu",
        compute_type="int8",
        model_instance=mock_whisper_model,
    )
    stt_adapter.prewarm()
    mock_whisper_model.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_aclose_cleanup(mock_whisper_model: MagicMock) -> None:
    stt_adapter = FasterWhisperSTT(
        device="cpu",
        compute_type="int8",
        model_instance=mock_whisper_model,
    )
    await stt_adapter.aclose()
    assert stt_adapter._model is None
    assert len(stt_adapter._resampler_cache) == 0


@pytest.mark.asyncio
async def test_stream_creation(mock_whisper_model: MagicMock) -> None:
    mock_vad = MagicMock()
    mock_vad_stream = MagicMock()
    mock_vad.stream.return_value = mock_vad_stream

    stt_adapter = FasterWhisperSTT(
        device="cpu",
        compute_type="int8",
        vad=mock_vad,
        model_instance=mock_whisper_model,
    )

    stream = stt_adapter.stream()
    assert isinstance(stream, stt.RecognizeStream)
    await stream.aclose()
