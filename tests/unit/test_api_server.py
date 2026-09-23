"""Unit tests for PropRelay API server (token issuing & health endpoints)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from proprelay.api.server import create_api_app
from proprelay.auth.tokens import LiveKitTokenService, TokenConfig


@pytest.fixture
def token_service() -> LiveKitTokenService:
    config = TokenConfig(api_key="testkey", api_secret="testsecret" * 4, default_ttl_seconds=3600)
    return LiveKitTokenService(config)


def test_request_token_default_payload(token_service: LiveKitTokenService) -> None:
    app = create_api_app(token_service)
    client = TestClient(app)

    response = client.post("/api/token", json={})
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["url"].startswith("ws://") or data["url"].startswith("wss://")
    assert data["room_name"].startswith("room-")
    assert data["identity"].startswith("user-")

    # Cryptographically verify the returned token
    claims = token_service.verify_token(data["token"])
    assert claims.video is not None
    assert claims.video.room == data["room_name"]
    assert claims.identity == data["identity"]
    assert claims.video.can_publish
    assert claims.video.can_subscribe
    assert claims.video.can_publish_data


def test_request_token_custom_payload(token_service: LiveKitTokenService) -> None:
    app = create_api_app(token_service)
    client = TestClient(app)

    response = client.post(
        "/api/token",
        json={
            "identity": "renter-alex-1",
            "name": "Alex Johnson",
            "room_name": "showing-suite-99",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["identity"] == "renter-alex-1"
    assert data["room_name"] == "showing-suite-99"

    claims = token_service.verify_token(data["token"])
    assert claims.identity == "renter-alex-1"
    assert claims.video is not None
    assert claims.video.room == "showing-suite-99"
    assert claims.name == "Alex Johnson"


def test_get_config(token_service: LiveKitTokenService) -> None:
    app = create_api_app(token_service)
    client = TestClient(app)

    response = client.get("/api/config")
    assert response.status_code == 200
    assert "livekit_url" in response.json()


def test_health_check_endpoint(token_service: LiveKitTokenService) -> None:
    app = create_api_app(token_service)
    client = TestClient(app)

    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "livekit" in data
    assert "ollama" in data
    assert "kokoro" in data
    assert "version" in data
    assert "profile" in data


def test_security_headers_present(token_service: LiveKitTokenService) -> None:
    app = create_api_app(token_service)
    client = TestClient(app)

    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "default-src" in response.headers.get("Content-Security-Policy", "")


def test_readiness_probe_endpoint(token_service: LiveKitTokenService) -> None:
    app = create_api_app(token_service)
    client = TestClient(app)

    response = client.get("/api/readiness")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "ready" in data
    assert "checks" in data
    assert "fixtures" in data["checks"]
    assert "storage" in data["checks"]


def test_oversized_payload_rejected(token_service: LiveKitTokenService) -> None:
    app = create_api_app(token_service)
    client = TestClient(app)

    # 70 KB payload exceeds 64 KB limit
    large_payload = {"name": "A" * 70000}
    response = client.post("/api/token", json=large_payload)
    assert response.status_code == 413
    assert "exceeds maximum allowed limit" in response.text
