"""Unit tests for LiveKitEventBroadcaster and CompositeEventPublisher."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from proprelay.events.broadcaster import (
    CompositeEventPublisher,
    LiveKitEventBroadcaster,
)
from proprelay.events.schemas import DomainEvent, EventType


@pytest.fixture
def sample_event() -> DomainEvent:
    return DomainEvent(
        event_type=EventType.PROPERTY_SEARCH_COMPLETED.value,
        timestamp=datetime.datetime(2026, 9, 23, 10, 0, tzinfo=datetime.UTC),
        payload={"count": 2},
    )


@pytest.mark.asyncio
async def test_livekit_broadcaster_connected(sample_event: DomainEvent) -> None:
    room = MagicMock()
    room.isconnected.return_value = True
    local_participant = MagicMock()
    local_participant.publish_data = AsyncMock()
    room.local_participant = local_participant

    broadcaster = LiveKitEventBroadcaster(room, topic="test.events")
    await broadcaster.publish(sample_event)

    local_participant.publish_data.assert_called_once()
    call_kwargs = local_participant.publish_data.call_args[1]
    assert call_kwargs["topic"] == "test.events"
    assert call_kwargs["reliable"] is True
    assert b"property.search.completed" in call_kwargs["payload"]


@pytest.mark.asyncio
async def test_livekit_broadcaster_disconnected(sample_event: DomainEvent) -> None:
    room = MagicMock()
    room.isconnected.return_value = False
    local_participant = MagicMock()
    local_participant.publish_data = AsyncMock()
    room.local_participant = local_participant

    broadcaster = LiveKitEventBroadcaster(room)
    await broadcaster.publish(sample_event)

    local_participant.publish_data.assert_not_called()


@pytest.mark.asyncio
async def test_livekit_broadcaster_no_participant(sample_event: DomainEvent) -> None:
    room = MagicMock()
    room.isconnected.return_value = True
    room.local_participant = None

    broadcaster = LiveKitEventBroadcaster(room)
    await broadcaster.publish(sample_event)


@pytest.mark.asyncio
async def test_composite_publisher(sample_event: DomainEvent) -> None:
    pub1 = MagicMock()
    pub1.publish = AsyncMock()
    pub2 = MagicMock()
    pub2.publish = AsyncMock()

    composite = CompositeEventPublisher([pub1, pub2])
    await composite.publish(sample_event)

    pub1.publish.assert_called_once_with(sample_event)
    pub2.publish.assert_called_once_with(sample_event)


@pytest.mark.asyncio
async def test_composite_publisher_handles_subpublisher_failure(
    sample_event: DomainEvent,
) -> None:
    pub1 = MagicMock()
    pub1.publish = AsyncMock(side_effect=RuntimeError("Data channel closed"))
    pub2 = MagicMock()
    pub2.publish = AsyncMock()

    composite = CompositeEventPublisher([pub1, pub2])
    # Should not raise exception
    await composite.publish(sample_event)

    pub1.publish.assert_called_once()
    pub2.publish.assert_called_once()
