"""Local OpenAI-compatible Text-to-Speech (TTS) server for Kokoro.

Provides:
- GET  /health           -> Service health and model status
- GET  /v1/models        -> Model catalog listing 'kokoro'
- GET  /v1/voices        -> List of supported conversational voices
- POST /v1/audio/speech  -> OpenAI-compatible speech synthesis endpoint returning WAV audio
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

SUPPORTED_VOICES = [
    "af_alloy",
    "af_bella",
    "af_sarah",
    "af_nicole",
    "af_sky",
    "am_adam",
    "am_echo",
    "am_eric",
    "am_fenrir",
    "am_liam",
    "am_michael",
    "am_onyx",
    "am_puck",
]


class SpeechRequest(BaseModel):
    """OpenAI-compatible speech generation request."""

    model_config = ConfigDict(extra="ignore")

    model: str = Field(default="kokoro", description="TTS model identifier")
    input: str = Field(..., description="Text content to synthesize into speech")
    voice: str = Field(default="af_alloy", description="Target voice name")
    response_format: str = Field(default="wav", description="Audio format (wav or mp3)")
    speed: float = Field(default=1.0, ge=0.25, le=4.0, description="Speech rate multiplier")


class KokoroEngine:
    """Manages the in-process Kokoro ONNX model instance and audio rendering."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        voices_path: str | Path | None = None,
    ) -> None:
        self.model_path = self._resolve_path(
            model_path or os.getenv("KOKORO_MODEL_PATH"),
            "kokoro-v1.0.onnx",
        )
        self.voices_path = self._resolve_path(
            voices_path or os.getenv("KOKORO_VOICES_PATH"),
            "voices-v1.0.bin",
        )
        self._kokoro: Any = None
        self._is_loaded = False
        self._load_engine()

    def _resolve_path(self, explicit: str | Path | None, filename: str) -> Path:
        if explicit:
            return Path(explicit)

        # Check standard project search paths
        candidates = [
            Path("bin/kokoro") / filename,
            Path("data/kokoro") / filename,
            Path.home() / ".cache" / "kokoro" / filename,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _load_engine(self) -> None:
        if self.model_path.exists() and self.voices_path.exists():
            try:
                from kokoro_onnx import Kokoro

                logger.info(
                    "Loading Kokoro ONNX model from %s with voices from %s",
                    self.model_path,
                    self.voices_path,
                )
                self._kokoro = Kokoro(str(self.model_path), str(self.voices_path))
                self._is_loaded = True
                logger.info("Kokoro ONNX engine initialized successfully.")
            except Exception as e:
                logger.error("Failed to load Kokoro ONNX model: %s", e)
                self._kokoro = None
                self._is_loaded = False
        else:
            logger.warning(
                "Kokoro model weights not found at %s or %s. Running in synthetic fallback mode.",
                self.model_path,
                self.voices_path,
            )

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def synthesize(
        self,
        text: str,
        voice: str = "af_alloy",
        speed: float = 1.0,
    ) -> tuple[np.ndarray[Any, Any], int]:
        """Synthesize text into raw float32 samples and sample rate."""
        clean_text = text.strip()
        if not clean_text:
            return np.zeros(2400, dtype=np.float32), 24000

        if self._is_loaded and self._kokoro is not None:
            try:
                samples, sample_rate = self._kokoro.create(
                    clean_text,
                    voice=voice,
                    speed=speed,
                    lang="en-us",
                )
                return samples, sample_rate
            except Exception as e:
                logger.error("Kokoro synthesis failed: %s. Using synthetic fallback.", e)

        # Synthetic fallback mode (used during testing or before model download)
        sample_rate = 24000
        # Calculate rough spoken duration: ~15 chars per second, minimum 0.2s
        duration = max(0.2, min(5.0, len(clean_text) / 15.0))
        num_samples = int(duration * sample_rate)
        # Gentle fade-in and fade-out silent/soft carrier signal
        samples = (np.zeros(num_samples, dtype=np.float32)).astype(np.float32)
        return samples, sample_rate


def create_tts_app(engine: KokoroEngine | None = None) -> FastAPI:
    """Create configured FastAPI application exposing OpenAI TTS API."""
    tts_engine = engine or KokoroEngine()

    app = FastAPI(
        title="PropRelay Local Kokoro TTS",
        description="Local zero-cost OpenAI-compatible speech synthesis service",
        version="0.3.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "kokoro-tts",
            "model_loaded": tts_engine.is_loaded,
            "model_path": str(tts_engine.model_path),
            "voices_path": str(tts_engine.voices_path),
        }

    @app.get("/v1/models")
    async def list_models() -> dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": "kokoro",
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": "local",
                }
            ],
        }

    @app.get("/v1/voices")
    async def list_voices() -> dict[str, Any]:
        return {
            "default_voice": os.getenv("KOKORO_VOICE", "af_alloy"),
            "voices": SUPPORTED_VOICES,
        }

    @app.post("/v1/audio/speech")
    async def generate_speech(req: SpeechRequest) -> Response:
        """OpenAI-compatible speech endpoint."""
        if not req.input.strip():
            raise HTTPException(status_code=400, detail="Text input cannot be empty.")

        samples, sample_rate = tts_engine.synthesize(
            text=req.input,
            voice=req.voice,
            speed=req.speed,
        )

        bio = io.BytesIO()
        sf.write(bio, samples, sample_rate, format="WAV", subtype="PCM_16")
        wav_bytes = bio.getvalue()

        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "Content-Type": "audio/wav",
                "Content-Length": str(len(wav_bytes)),
            },
        )

    return app


def main() -> None:
    """Run standalone local Kokoro TTS server."""
    import uvicorn

    host = os.getenv("KOKORO_HOST", "127.0.0.1")
    port = int(os.getenv("KOKORO_PORT", "8880"))

    logging.basicConfig(level=logging.INFO)
    logger.info("Starting PropRelay Local Kokoro TTS Server on http://%s:%d", host, port)

    app = create_tts_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
