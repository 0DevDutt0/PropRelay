"""LiveKit AgentServer worker entrypoint for PropRelay Voice Agent."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import AgentServer, JobContext, cli

from proprelay.agent.session import VoiceSession, VoiceSessionConfig
from proprelay.agent.tools import AgentTools
from proprelay.domain.clock import SystemClock
from proprelay.domain.policy import BookingPolicyService
from proprelay.domain.repositories import (
    InMemoryBookingRepository,
    InMemoryLeadRepository,
    InMemoryPropertyRepository,
    InMemoryShowingRepository,
)
from proprelay.events.broadcaster import CompositeEventPublisher, LiveKitEventBroadcaster
from proprelay.events.journal import EventJournal

load_dotenv()
logger = logging.getLogger("proprelay.agent.worker")

server = AgentServer()


def _init_domain_stack() -> tuple[AgentTools, EventJournal]:
    """Initialize domain repositories from JSON fixtures and construct AgentTools."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    listings_path = repo_root / "data" / "listings.json"
    showings_path = repo_root / "data" / "showings.json"
    events_path = repo_root / "data" / "events.jsonl"

    clock = SystemClock()
    property_repo = (
        InMemoryPropertyRepository.from_json_file(listings_path)
        if listings_path.exists()
        else InMemoryPropertyRepository()
    )
    showing_repo = (
        InMemoryShowingRepository.from_json_file(showings_path)
        if showings_path.exists()
        else InMemoryShowingRepository()
    )
    booking_repo = InMemoryBookingRepository()
    lead_repo = InMemoryLeadRepository()

    policy_service = BookingPolicyService(
        property_repo=property_repo,
        showing_repo=showing_repo,
        booking_repo=booking_repo,
        clock=clock,
    )
    journal = EventJournal(file_path=events_path)

    tools = AgentTools(
        property_repo=property_repo,
        showing_repo=showing_repo,
        booking_repo=booking_repo,
        lead_repo=lead_repo,
        booking_policy=policy_service,
        event_publisher=journal,
        clock=clock,
    )
    return tools, journal


@server.rtc_session(agent_name=os.getenv("LIVEKIT_AGENT_NAME", "proprelay"))
async def voice_entrypoint(ctx: JobContext) -> None:
    """Entrypoint called when a LiveKit room job is dispatched to this worker."""
    logger.info("Connecting to LiveKit room for job %s...", ctx.job.id)
    await ctx.connect()
    logger.info("Connected to room '%s'", ctx.room.name)

    # 1. Initialize domain tools and journal
    tools, journal = _init_domain_stack()

    # 2. Wire LiveKit WebRTC data channel event broadcast
    broadcaster = LiveKitEventBroadcaster(room=ctx.room)
    composite_publisher = CompositeEventPublisher([journal, broadcaster])
    tools._publisher = composite_publisher

    # 3. Wait for human participant to join room
    logger.info("Waiting for participant in room '%s'...", ctx.room.name)
    participant = await ctx.wait_for_participant()
    logger.info("Participant joined: %s (%s)", participant.identity, participant.name)

    # 4. Create and start VoiceSession
    config = VoiceSessionConfig.from_env()
    session = VoiceSession(
        config=config,
        agent_tools=tools,
        event_publisher=composite_publisher,
    )

    ctx.add_shutdown_callback(session.aclose)
    await session.start(room=ctx.room, participant=participant)


def main() -> None:
    """Run LiveKit agent worker via CLI runner."""
    cli.run_app(server)


if __name__ == "__main__":
    main()
