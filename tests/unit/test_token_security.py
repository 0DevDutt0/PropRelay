"""Security audit test suite for LiveKit token issuance, bounded TTL, and claims."""

from __future__ import annotations

import time

import jwt
import pytest
from livekit.api import TokenVerifier

from proprelay.auth.tokens import LiveKitTokenService, TokenConfig


@pytest.fixture
def token_service() -> LiveKitTokenService:
    config = TokenConfig(
        api_key="test-key-security-audit",
        api_secret="test-secret-audit-key-32chars-min!",
        default_ttl_seconds=3600,
    )
    return LiveKitTokenService(config)


def test_valid_token_claims_and_minimal_permissions(token_service: LiveKitTokenService) -> None:
    """Verify that a valid token contains minimal participant grants and zero admin permissions."""
    token = token_service.generate_token(
        identity="user-sec-01",
        room_name="room-prop-101",
        participant_name="Renter Alice",
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
    )
    claims = token_service.verify_token(token)

    assert claims.identity == "user-sec-01"
    assert claims.video is not None
    assert claims.video.room == "room-prop-101"
    assert claims.video.can_publish is True
    assert claims.video.can_subscribe is True
    assert claims.video.can_publish_data is True
    # Minimal permission verification: Ensure caller is NOT granted room admin or recording privileges
    assert not claims.video.room_admin
    assert not claims.video.room_record


def test_expired_token_rejected(token_service: LiveKitTokenService) -> None:
    """Verify that a token with expired TTL fails verification."""
    # Issue a token with 1 second TTL
    short_token = token_service.generate_token(
        identity="user-expiring",
        room_name="room-expiring",
        ttl_seconds=1,
    )
    # Wait for token expiration
    time.sleep(1.5)

    with pytest.raises(Exception) as exc_info:
        token_service.verify_token(short_token)
    # TokenVerifier or PyJWT raises expired error
    assert "expired" in str(exc_info.value).lower() or "signature" in str(exc_info.value).lower()


def test_wrong_secret_signature_rejected(token_service: LiveKitTokenService) -> None:
    """Verify that tokens signed with a different secret are rejected immediately."""
    token = token_service.generate_token(
        identity="user-forgery",
        room_name="room-target",
    )

    tampered_verifier = TokenVerifier(
        api_key="test-key-security-audit",
        api_secret="attacker-forged-secret-different-key!",
    )
    with pytest.raises((jwt.PyJWTError, ValueError)):
        tampered_verifier.verify(token)


def test_wrong_room_access_prevented(token_service: LiveKitTokenService) -> None:
    """Verify that token claims bind strictly to the assigned room."""
    token = token_service.generate_token(
        identity="user-room-isolation",
        room_name="room-authorized",
    )
    claims = token_service.verify_token(token)
    assert claims.video is not None
    assert claims.video.room == "room-authorized"
    assert claims.video.room != "room-unauthorized-other-tenant"


def test_insufficient_permissions_custom_grant(token_service: LiveKitTokenService) -> None:
    """Verify that publish permissions can be explicitly restricted (listen-only grant)."""
    listen_only_token = token_service.generate_token(
        identity="listener-only-user",
        room_name="room-broadcast",
        can_publish=False,
        can_subscribe=True,
        can_publish_data=False,
    )
    claims = token_service.verify_token(listen_only_token)
    assert claims.video is not None
    assert claims.video.can_publish is False
    assert claims.video.can_subscribe is True
    assert claims.video.can_publish_data is False


def test_empty_identity_rejected(token_service: LiveKitTokenService) -> None:
    """Verify that empty identities or room names are rejected at generation boundary."""
    with pytest.raises(ValueError, match="Identity cannot be empty"):
        token_service.generate_token(identity="   ", room_name="room-test")

    with pytest.raises(ValueError, match="Room name cannot be empty"):
        token_service.generate_token(identity="valid-user", room_name="   ")
