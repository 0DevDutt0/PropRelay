"""Unit tests for PropRelay Local Kokoro TTS server."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

from proprelay.tts.server import KokoroEngine, create_tts_app


@pytest.fixture
def mock_kokoro_engine() -> KokoroEngine:
    engine = KokoroEngine(model_path="dummy.onnx", voices_path="dummy.bin")
    mock_kokoro = MagicMock()
    # 0.5s of 24kHz audio
    samples = (np.sin(np.linspace(0, 50, 12000)) * 0.5).astype(np.float32)
    mock_kokoro.create.return_value = (samples, 24000)
    engine._kokoro = mock_kokoro
    engine._is_loaded = True
    return engine


def test_health_endpoint() -> None:
    app = create_tts_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "kokoro-tts"
    assert "model_loaded" in data


def test_models_endpoint() -> None:
    app = create_tts_app()
    client = TestClient(app)
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) >= 1
    assert data["data"][0]["id"] == "kokoro"


def test_voices_endpoint() -> None:
    app = create_tts_app()
    client = TestClient(app)
    response = client.get("/v1/voices")
    assert response.status_code == 200
    data = response.json()
    assert "af_alloy" in data["voices"]
    assert "am_adam" in data["voices"]


def test_generate_speech_fallback_mode() -> None:
    # Uses un-loaded engine (synthetic mode)
    engine = KokoroEngine(model_path="nonexistent.onnx", voices_path="nonexistent.bin")
    app = create_tts_app(engine)
    client = TestClient(app)

    response = client.post(
        "/v1/audio/speech",
        json={
            "model": "kokoro",
            "input": "Hello, welcome to PropRelay leasing concierge.",
            "voice": "af_alloy",
            "response_format": "wav",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert len(response.content) > 1000
    # Check WAV header
    assert response.content[:4] == b"RIFF"
    assert response.content[8:12] == b"WAVE"


def test_generate_speech_with_mock_model(mock_kokoro_engine: KokoroEngine) -> None:
    app = create_tts_app(mock_kokoro_engine)
    client = TestClient(app)

    response = client.post(
        "/v1/audio/speech",
        json={
            "model": "kokoro",
            "input": "We have two apartments available.",
            "voice": "af_bella",
            "speed": 1.1,
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert len(response.content) > 1000

    mock_kokoro_engine._kokoro.create.assert_called_once_with(
        "We have two apartments available.",
        voice="af_bella",
        speed=1.1,
        lang="en-us",
    )


def test_generate_speech_empty_input_rejected() -> None:
    app = create_tts_app()
    client = TestClient(app)

    response = client.post(
        "/v1/audio/speech",
        json={
            "model": "kokoro",
            "input": "   ",
        },
    )
    assert response.status_code == 400
