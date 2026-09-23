"""Integration test for full LiveKit voice session turn with STT, LLM, tools, and TTS."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
import urllib.request
from typing import Any

import httpx
import numpy as np
import pytest
import soundfile as sf
from livekit import rtc


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_voice_turn_e2e() -> None:
    """Verify end-to-end voice turn against local LiveKit and running worker."""
    # Pre-check services
    async with httpx.AsyncClient(timeout=1.5) as client:
        try:
            await client.get("http://127.0.0.1:7880")
            res_kk = await client.get("http://127.0.0.1:8880/health")
            res_api = await client.get("http://127.0.0.1:8000/api/health")
            if res_kk.status_code != 200 or res_api.status_code != 200:
                pytest.skip("Services not fully ready")
        except Exception as e:
            pytest.skip(f"Local services offline: {e}")

    # 1. Request token
    room_name = f"pytest-turn-{int(time.time())}"
    token_req = urllib.request.Request(
        "http://127.0.0.1:8000/api/token",
        data=json.dumps({"room_name": room_name, "participant_name": "PytestCaller"}).encode(
            "utf-8"
        ),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(token_req) as resp:
        token_data = json.loads(resp.read().decode())

    token = token_data["token"]
    url = token_data["url"]

    # 2. Connect client room
    room = rtc.Room()
    received_events: list[dict[str, Any]] = []
    agent_greeting_done = asyncio.Event()
    agent_responded = asyncio.Event()

    @room.on("data_received")
    def on_data_received(data_packet: rtc.DataPacket) -> None:
        try:
            payload = json.loads(data_packet.data.decode("utf-8"))
            ev_type = payload.get("event_type") or payload.get("type")
            received_events.append(payload)

            if ev_type == "voice.state.changed":
                p = payload.get("payload", {})
                if p.get("old_state") == "SPEAKING" and p.get("new_state") == "LISTENING":
                    agent_greeting_done.set()

            if ev_type == "voice.transcript.agent":
                t = payload.get("payload", {}).get("transcript", "")
                if "PropRelay" not in t:
                    agent_responded.set()
        except Exception:
            pass

    await room.connect(url, token)

    # 3. Publish mic track
    source = rtc.AudioSource(sample_rate=24000, num_channels=1)
    track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
    options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    await room.local_participant.publish_track(track, options)

    # Wait for greeting
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(agent_greeting_done.wait(), timeout=12.0)

    await asyncio.sleep(0.5)

    # 4. Stream speech from test_input.wav if exists, else synthesize
    wav_path = "scratch/test_input.wav"
    if not os.path.exists(wav_path):
        pytest.skip("scratch/test_input.wav not present")

    wav_data, sample_rate = sf.read(wav_path, dtype="int16")
    chunk_size = sample_rate // 50  # 20ms

    for i in range(0, len(wav_data), chunk_size):
        chunk = wav_data[i : i + chunk_size]
        if len(chunk) < chunk_size:
            chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
        frame = rtc.AudioFrame(
            data=chunk.tobytes(),
            sample_rate=sample_rate,
            num_channels=1,
            samples_per_channel=chunk_size,
        )
        await source.capture_frame(frame)
        await asyncio.sleep(0.019)

    # Silence
    silence_chunk = np.zeros(chunk_size, dtype=np.int16)
    for _ in range(50):
        frame = rtc.AudioFrame(
            data=silence_chunk.tobytes(),
            sample_rate=sample_rate,
            num_channels=1,
            samples_per_channel=chunk_size,
        )
        await source.capture_frame(frame)
        await asyncio.sleep(0.019)

    # Wait for response
    try:
        await asyncio.wait_for(agent_responded.wait(), timeout=25.0)
    except TimeoutError:
        pytest.fail("Agent did not respond to user speech within 25 seconds")

    await room.disconnect()

    # Assertions
    event_types = [ev.get("event_type") or ev.get("type") for ev in received_events]
    assert "voice.transcript.user" in event_types
    assert "property.search.completed" in event_types
    assert "voice.transcript.agent" in event_types
