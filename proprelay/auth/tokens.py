"""Server-side LiveKit token generation and verification service."""

from __future__ import annotations

import datetime
import os

from livekit.api import AccessToken, TokenVerifier, VideoGrants
from livekit.api.access_token import Claims
from pydantic import BaseModel, ConfigDict, Field


class TokenConfig(BaseModel):
    """Configuration credentials for LiveKit token signing."""

    model_config = ConfigDict(frozen=True)

    api_key: str = Field(..., description="LiveKit API Key")
    api_secret: str = Field(..., description="LiveKit API Secret (kept strictly server-side)")
    default_ttl_seconds: int = Field(default=3600, gt=0, description="Default token expiration")

    @classmethod
    def from_env(cls) -> TokenConfig:
        """Instantiate configuration from environment variables."""
        api_key = os.getenv("LIVEKIT_API_KEY", "devkey")
        api_secret = os.getenv("LIVEKIT_API_SECRET", "secret")
        ttl = int(os.getenv("TOKEN_TTL_SECONDS", "3600"))
        return cls(api_key=api_key, api_secret=api_secret, default_ttl_seconds=ttl)


class LiveKitTokenService:
    """Manages creation and verification of short-lived WebRTC participant tokens."""

    def __init__(self, config: TokenConfig | None = None) -> None:
        self.config = config or TokenConfig.from_env()

    def generate_token(
        self,
        identity: str,
        room_name: str,
        participant_name: str | None = None,
        ttl_seconds: int | None = None,
        can_publish: bool = True,
        can_subscribe: bool = True,
        can_publish_data: bool = True,
    ) -> str:
        """Create a cryptographically signed JWT granting access to a LiveKit room."""
        if not identity.strip():
            raise ValueError("Identity cannot be empty")
        if not room_name.strip():
            raise ValueError("Room name cannot be empty")

        ttl = datetime.timedelta(seconds=ttl_seconds or self.config.default_ttl_seconds)

        grants = VideoGrants(
            room_join=True,
            room=room_name.strip(),
            can_publish=can_publish,
            can_subscribe=can_subscribe,
            can_publish_data=can_publish_data,
        )

        token = (
            AccessToken(self.config.api_key, self.config.api_secret)
            .with_identity(identity.strip())
            .with_grants(grants)
            .with_ttl(ttl)
        )

        if participant_name:
            token = token.with_name(participant_name.strip())

        return token.to_jwt()

    def verify_token(self, token: str, leeway_seconds: int = 0) -> Claims:
        """Verify signature and return claim grants for an existing token with strict expiration checking."""
        verifier = TokenVerifier(
            self.config.api_key,
            self.config.api_secret,
            leeway=datetime.timedelta(seconds=leeway_seconds),
        )
        return verifier.verify(token)
