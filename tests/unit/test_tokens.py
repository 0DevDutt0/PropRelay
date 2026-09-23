"""Unit tests verifying LiveKit server-side token generation and claims."""

from __future__ import annotations

import pytest

from proprelay.auth.tokens import LiveKitTokenService, TokenConfig


def test_token_generation_and_verification() -> None:
    config = TokenConfig(
        api_key="test-key-1234567890123456789012",
        api_secret="test-secret-1234567890123456789012",
        default_ttl_seconds=1800,
    )
    service = LiveKitTokenService(config)

    token = service.generate_token(
        identity="renter-user-1",
        room_name="proprelay-room-101",
        participant_name="Jane Doe",
        can_publish=True,
        can_subscribe=True,
    )
    assert isinstance(token, str)
    assert len(token) > 50

    # Verify signature and claims
    claims = service.verify_token(token)
    assert claims.identity == "renter-user-1"
    assert claims.video is not None
    assert claims.video.room == "proprelay-room-101"
    assert claims.video.can_publish is True
    assert claims.video.can_subscribe is True


def test_token_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVEKIT_API_KEY", "env-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "env-secret")
    monkeypatch.setenv("TOKEN_TTL_SECONDS", "7200")

    cfg = TokenConfig.from_env()
    assert cfg.api_key == "env-key"
    assert cfg.api_secret == "env-secret"
    assert cfg.default_ttl_seconds == 7200


def test_token_empty_identity_rejected() -> None:
    service = LiveKitTokenService(TokenConfig(api_key="key", api_secret="sec"))
    with pytest.raises(ValueError, match="Identity cannot be empty"):
        service.generate_token(identity="   ", room_name="room-1")


def test_token_empty_room_rejected() -> None:
    service = LiveKitTokenService(TokenConfig(api_key="key", api_secret="sec"))
    with pytest.raises(ValueError, match="Room name cannot be empty"):
        service.generate_token(identity="user-1", room_name="   ")
