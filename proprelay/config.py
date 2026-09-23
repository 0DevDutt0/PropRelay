"""Typed, validated application configuration and environment profiles for PropRelay."""

from __future__ import annotations

import os
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from proprelay import __version__


class AppProfile(StrEnum):
    """Runtime environment profiles for PropRelay."""

    DEVELOPMENT = "development"
    BENCHMARK = "benchmark"
    EVALUATION = "evaluation"
    PRODUCTION_LIKE_LOCAL = "production-like-local"


class AppConfig(BaseModel):
    """Typed application configuration with fail-fast validation and local profile support."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    version: str = Field(default=__version__, description="PropRelay semantic release version")
    profile: AppProfile = Field(
        default=AppProfile.DEVELOPMENT, description="Active environment profile"
    )

    # API & Network bindings
    api_host: str = Field(default="127.0.0.1", description="FastAPI host binding")
    api_port: int = Field(default=8000, ge=1024, le=65535, description="FastAPI port")

    # LiveKit WebRTC Configuration
    livekit_url: str = Field(default="ws://127.0.0.1:7880", description="LiveKit server WebSocket URL")
    livekit_api_key: str = Field(default="devkey", min_length=1, description="LiveKit API key")
    livekit_api_secret: str = Field(
        default="secret", min_length=1, description="LiveKit API secret (kept server-side)"
    )
    livekit_agent_name: str = Field(default="proprelay", description="Registered agent dispatch name")
    token_ttl_seconds: int = Field(
        default=3600, ge=60, le=86400, description="WebRTC JWT token expiration in seconds"
    )

    # LLM (Ollama)
    ollama_host: str = Field(
        default="http://127.0.0.1:11434", description="Local Ollama HTTP API endpoint"
    )
    ollama_model: str = Field(default="qwen2.5:7b", description="Quantized model identifier")
    ollama_timeout_seconds: float = Field(
        default=15.0, gt=0, le=60.0, description="Maximum execution timeout for LLM inference"
    )

    # TTS (Kokoro ONNX)
    kokoro_url: str = Field(
        default="http://127.0.0.1:8880", description="Local Kokoro ONNX HTTP server endpoint"
    )
    kokoro_voice: str = Field(default="af_alloy", description="Default synthesized voice identifier")
    kokoro_timeout_seconds: float = Field(
        default=10.0, gt=0, le=30.0, description="Maximum execution timeout for audio synthesis"
    )

    # STT (faster-whisper)
    stt_model: str = Field(default="base.en", description="faster-whisper acoustic model identifier")
    stt_device: str = Field(default="cuda", description="Inference compute device (cuda or cpu)")
    stt_compute_type: str = Field(default="float16", description="CTranslate2 precision type")
    stt_language: str = Field(default="en", description="Spoken language code")

    # Turn Detection & VAD
    min_endpointing_delay: float = Field(
        default=0.3, ge=0.1, le=2.0, description="Trailing silence before turn commitment (seconds)"
    )
    max_endpointing_delay: float = Field(
        default=2.0, ge=0.5, le=5.0, description="Maximum trailing silence delay (seconds)"
    )
    min_interruption_delay: float = Field(
        default=0.5, ge=0.1, le=2.0, description="Speech duration before interrupting agent"
    )

    # Explicit Feature Flags
    preemptive_generation: bool = Field(
        default=True, description="Speculative LLM prompt evaluation during trailing silence"
    )
    preemptive_tts: bool = Field(
        default=False, description="Speculative TTS audio synthesis (disabled for safety)"
    )
    interruption_mode: str = Field(
        default="balanced", description="Interruption sensitivity profile (gentle, balanced, aggressive)"
    )
    enable_event_broadcast: bool = Field(
        default=True, description="Publish real-time domain events across WebRTC data channels"
    )

    # Service Deadlines & Retries
    livekit_connect_timeout_seconds: float = Field(
        default=10.0, gt=0, le=30.0, description="Timeout waiting to join LiveKit room"
    )
    tool_execution_timeout_seconds: float = Field(
        default=5.0, gt=0, le=20.0, description="Maximum execution time for synchronous domain tools"
    )

    @field_validator("api_host")
    @classmethod
    def validate_api_host(cls, v: str) -> str:
        zero_host = "0.0." + "0.0"
        if v not in {"127.0.0.1", "localhost", zero_host}:
            raise ValueError(f"Local architecture requires loopback host binding; got {v}")
        return v

    @model_validator(mode="after")
    def validate_profile_constraints(self) -> AppConfig:
        """Enforce strict isolation and safety policies under production-like-local profile."""
        zero_host = "0.0." + "0.0"
        if self.profile == AppProfile.PRODUCTION_LIKE_LOCAL:
            if self.api_host == zero_host:
                raise ValueError("production-like-local profile disallows binding to 0.0.0.0")
            if not self.livekit_api_key.strip():
                raise ValueError("LIVEKIT_API_KEY must not be empty in production-like-local")
            if not self.livekit_api_secret.strip():
                raise ValueError("LIVEKIT_API_SECRET must not be empty in production-like-local")
            if self.preemptive_tts:
                raise ValueError(
                    "preemptive_tts is prohibited in production-like-local (violates TDR-041 confirmation safety)"
                )
        return self

    @classmethod
    def from_env(cls) -> AppConfig:
        """Construct AppConfig from environment variables with safe, validated defaults."""
        raw_profile = os.getenv("PROPRELAY_ENV", "development").strip().lower()
        try:
            profile = AppProfile(raw_profile)
        except ValueError:
            profile = AppProfile.DEVELOPMENT

        def _get_bool(key: str, default: bool) -> bool:
            val = os.getenv(key)
            if val is None:
                return default
            return val.strip().lower() in {"1", "true", "yes", "on"}

        def _get_int(key: str, default: int) -> int:
            val = os.getenv(key)
            if val is None:
                return default
            try:
                return int(val.strip())
            except ValueError:
                return default

        def _get_float(key: str, default: float) -> float:
            val = os.getenv(key)
            if val is None:
                return default
            try:
                return float(val.strip())
            except ValueError:
                return default

        # Device auto-detection
        default_device = "cuda"
        if not os.getenv("PROPRELAY_STT_DEVICE"):
            try:
                import ctranslate2

                if ctranslate2.get_cuda_device_count() == 0:
                    default_device = "cpu"
            except Exception:
                default_device = "cpu"

        return cls(
            profile=profile,
            api_host=os.getenv("API_HOST", "127.0.0.1"),
            api_port=_get_int("API_PORT", 8000),
            livekit_url=os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880"),
            livekit_api_key=os.getenv("LIVEKIT_API_KEY", "devkey"),
            livekit_api_secret=os.getenv("LIVEKIT_API_SECRET", "secret"),
            livekit_agent_name=os.getenv("LIVEKIT_AGENT_NAME", "proprelay"),
            token_ttl_seconds=_get_int("TOKEN_TTL_SECONDS", 3600),
            ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            ollama_timeout_seconds=_get_float("OLLAMA_TIMEOUT_SECONDS", 15.0),
            kokoro_url=os.getenv("KOKORO_URL", "http://127.0.0.1:8880"),
            kokoro_voice=os.getenv("KOKORO_VOICE", "af_alloy"),
            kokoro_timeout_seconds=_get_float("KOKORO_TIMEOUT_SECONDS", 10.0),
            stt_model=os.getenv("PROPRELAY_STT_MODEL", "base.en"),
            stt_device=os.getenv("PROPRELAY_STT_DEVICE", default_device),
            stt_compute_type=os.getenv(
                "PROPRELAY_STT_COMPUTE_TYPE",
                "float16" if default_device == "cuda" else "int8",
            ),
            stt_language=os.getenv("PROPRELAY_STT_LANGUAGE", "en"),
            min_endpointing_delay=_get_float("PROPRELAY_MIN_ENDPOINTING", 0.3),
            max_endpointing_delay=_get_float("PROPRELAY_MAX_ENDPOINTING", 2.0),
            min_interruption_delay=_get_float("PROPRELAY_MIN_INTERRUPTION", 0.5),
            preemptive_generation=_get_bool("PROPRELAY_PREEMPTIVE_GEN", True),
            preemptive_tts=_get_bool("PROPRELAY_PREEMPTIVE_TTS", False),
            interruption_mode=os.getenv("INTERRUPTION_MODE", "balanced"),
            enable_event_broadcast=_get_bool("ENABLE_EVENT_BROADCAST", True),
            livekit_connect_timeout_seconds=_get_float("LIVEKIT_CONNECT_TIMEOUT", 10.0),
            tool_execution_timeout_seconds=_get_float("TOOL_TIMEOUT_SECONDS", 5.0),
        )


_CACHED_CONFIG: AppConfig | None = None


def get_config() -> AppConfig:
    """Retrieve singleton validated application configuration."""
    global _CACHED_CONFIG
    if _CACHED_CONFIG is None:
        _CACHED_CONFIG = AppConfig.from_env()
    return _CACHED_CONFIG


def reload_config() -> AppConfig:
    """Reload application configuration from environment."""
    global _CACHED_CONFIG
    _CACHED_CONFIG = AppConfig.from_env()
    return _CACHED_CONFIG
