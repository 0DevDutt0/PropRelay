"""LiveKit WebRTC Data Channel Event Broadcaster and Composite Publisher."""

from __future__ import annotations

import logging

from livekit import rtc

from proprelay.events.journal import IEventPublisher
from proprelay.events.schemas import DomainEvent
from proprelay.testing.failure_injection import (
    FailureMode,
    InjectedPublishError,
    should_inject_failure,
)

logger = logging.getLogger(__name__)

DEFAULT_EVENTS_TOPIC = "proprelay.events"


class LiveKitEventBroadcaster(IEventPublisher):
    """Publishes DomainEvents to connected WebRTC peers via LiveKit reliable data channel."""

    def __init__(
        self,
        room: rtc.Room,
        topic: str = DEFAULT_EVENTS_TOPIC,
    ) -> None:
        self.room = room
        self.topic = topic

    async def publish(self, event: DomainEvent) -> None:
        """Serialize and broadcast a DomainEvent envelope over WebRTC data channel."""
        if should_inject_failure(FailureMode.PUBLISH):
            logger.warning(
                "Injected failure: Dropping realtime broadcast packet for event %s",
                event.event_id,
            )
            raise InjectedPublishError(f"Simulated data packet drop for {event.event_id}")

        try:
            if not self.room.isconnected():
                logger.debug("Cannot broadcast event %s: room is not connected", event.event_id)
                return

            local_participant = self.room.local_participant
            if local_participant is None:
                logger.debug("Cannot broadcast event %s: no local participant", event.event_id)
                return

            payload = event.model_dump_json().encode("utf-8")
            await local_participant.publish_data(
                payload=payload,
                topic=self.topic,
                reliable=True,
            )
            logger.debug(
                "Broadcasted event %s [%s] to topic '%s'",
                event.event_id,
                event.event_type,
                self.topic,
            )
        except Exception as e:
            logger.warning(
                "Failed to broadcast event %s over data channel: %s",
                event.event_id,
                e,
            )


class CompositeEventPublisher(IEventPublisher):
    """Dispatches DomainEvents concurrently to multiple underlying event publishers."""

    def __init__(self, publishers: list[IEventPublisher]) -> None:
        self._publishers = [p for p in publishers if p is not None]

    async def publish(self, event: DomainEvent) -> None:
        """Publish event to all registered underlying publishers."""
        for publisher in self._publishers:
            try:
                await publisher.publish(event)
            except Exception as e:
                logger.warning(
                    "Publisher %s failed to publish event %s: %s",
                    type(publisher).__name__,
                    event.event_id,
                    e,
                )
