"""Integration smoke tests probing local voice stack services (opt-in / non-blocking)."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_local_endpoint() -> None:
    """Check if local Ollama runtime is reachable on localhost:11434."""
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            resp = await client.get("http://127.0.0.1:11434/api/tags")
            assert resp.status_code == 200
            data = resp.json()
            models = [m.get("name") for m in data.get("models", [])]
            # Print available models for diagnostic inspection
            print("Found Ollama models:", models)
        except Exception as e:
            pytest.skip(f"Ollama is not currently running locally: {e}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_livekit_local_endpoint() -> None:
    """Check if local LiveKit server is listening on port 7880."""
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            resp = await client.get("http://127.0.0.1:7880")
            assert resp.status_code in (200, 404)
        except Exception as e:
            pytest.skip(f"LiveKit server is not currently running: {e}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kokoro_local_endpoint() -> None:
    """Check if local Kokoro TTS server is listening on port 8880."""
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            resp = await client.get("http://127.0.0.1:8880/health")
            assert resp.status_code == 200
        except Exception as e:
            pytest.skip(f"Kokoro TTS server is not currently running: {e}")
