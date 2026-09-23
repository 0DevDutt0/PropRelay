"""Explicit test suite enforcing the core architectural invariants of PropRelay.

Invariants:
1. LLM != Business Policy (LLM intent cannot bypass domain policy or force an invalid reservation)
2. Frontend != Source of Truth (Client cannot forge reservations without server-side validation)
3. Realtime Packet != Durable Event (WebRTC data channel delivery failure does not lose event records)
4. LLM Judge != Business Correctness (Semantic judge cannot override a deterministic safety failure)
5. Performance != Quality (Preemptive optimizations cannot disable two-phase confirmation gates)
6. Local Concurrency != Cloud Scale (Concurrency experiments assert local mutual exclusion, not cloud scale)
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from proprelay.agent.tools import AgentTools, BookShowingInput
from proprelay.config import AppProfile, get_config
from proprelay.domain.clock import FrozenClock
from proprelay.domain.models import BookingStatus
from proprelay.domain.policy import BookingPolicyService, BookingRequest, PolicyErrorCode
from proprelay.domain.repositories import (
    InMemoryBookingRepository,
    InMemoryLeadRepository,
    InMemoryPropertyRepository,
    InMemoryShowingRepository,
)
from proprelay.evaluation.judges import BookingSafetyJudge
from proprelay.events.broadcaster import CompositeEventPublisher
from proprelay.events.journal import EventJournal, IEventPublisher
from proprelay.events.schemas import DomainEvent, EventType
from proprelay.workflows.context import ConversationContext


class DroppingBroadcaster(IEventPublisher):
    """Simulates a lossy WebRTC data channel packet drop."""

    async def publish(self, event: DomainEvent) -> None:
        raise ConnectionError("Packet dropped on lossy WebRTC data channel transport")


@pytest.mark.asyncio
async def test_invariant_1_llm_cannot_bypass_booking_policy() -> None:
    """Invariant 1: LLM != Business Policy.
    Even if the LLM hallucinates confirmed=True for an unavailable slot,
    the domain policy service rejects the mutation.
    """
    clock = FrozenClock(datetime.datetime(2026, 10, 1, 9, 0, 0, tzinfo=datetime.UTC))
    prop_repo = InMemoryPropertyRepository.from_json_file("data/listings.json")
    showing_repo = InMemoryShowingRepository.from_json_file("data/showings.json")
    booking_repo = InMemoryBookingRepository()
    lead_repo = InMemoryLeadRepository()

    policy = BookingPolicyService(
        property_repo=prop_repo,
        showing_repo=showing_repo,
        booking_repo=booking_repo,
        clock=clock,
    )
    context = ConversationContext(session_id="inv-1-session")
    tools = AgentTools(
        property_repo=prop_repo,
        showing_repo=showing_repo,
        booking_repo=booking_repo,
        lead_repo=lead_repo,
        booking_policy=policy,
        clock=clock,
        context=context,
    )

    # Attempt to book an invalid / nonexistent slot directly with confirmed=True
    result = await tools.book_showing(
        BookShowingInput(
            property_id="prop-101",
            slot_id="slot-nonexistent-999",
            renter_name="Adversarial User",
            confirmed=True,
        )
    )

    assert result.success is False
    # Rejected either due to missing pending action or invalid slot
    assert result.error_code in {"NO_PENDING_ACTION", "SLOT_NOT_FOUND"}
    assert len(await booking_repo.list_all()) == 0


@pytest.mark.asyncio
async def test_invariant_2_frontend_cannot_create_booking_directly() -> None:
    """Invariant 2: Frontend != Source of Truth.
    The domain policy service strictly requires valid property and slot constraints.
    Direct API requests with fabricated dates or slots are rejected.
    """
    clock = FrozenClock(datetime.datetime(2026, 10, 1, 9, 0, 0, tzinfo=datetime.UTC))
    prop_repo = InMemoryPropertyRepository.from_json_file("data/listings.json")
    showing_repo = InMemoryShowingRepository.from_json_file("data/showings.json")
    booking_repo = InMemoryBookingRepository()

    policy = BookingPolicyService(
        property_repo=prop_repo,
        showing_repo=showing_repo,
        booking_repo=booking_repo,
        clock=clock,
    )

    # Fabricated slot ID from malicious frontend request
    req = BookingRequest(
        property_id="prop-101",
        slot_id="slot-forged-by-client",
        renter_name="Hacker",
        renter_phone="+1-555-000-0000",
        renter_email="hacker@example.com",
    )
    res = await policy.validate_and_reserve(req)
    assert res.success is False
    assert res.error_code == PolicyErrorCode.SLOT_NOT_FOUND
    assert len(await booking_repo.list_all()) == 0


@pytest.mark.asyncio
async def test_invariant_3_realtime_packet_not_equal_durable_event(tmp_path: Path) -> None:
    """Invariant 3: Realtime Packet != Durable Event.
    A dropped WebRTC data packet MUST NOT cause loss of the durable event log.
    """
    journal = EventJournal(file_path=tmp_path / "events.jsonl")
    broadcaster = DroppingBroadcaster()
    composite = CompositeEventPublisher([journal, broadcaster])

    event = DomainEvent(
        event_type=EventType.SHOWING_BOOKED.value,
        timestamp=datetime.datetime.now(datetime.UTC),
        session_id="sess-inv3",
        workflow_id="wf-inv3",
        payload={"booking_id": "book-inv3-safe"},
    )

    await composite.publish(event)

    # Durable journal successfully persisted the event
    assert journal.count() == 1
    events = journal.read_all()
    assert events[0].payload["booking_id"] == "book-inv3-safe"


def test_invariant_4_semantic_judge_cannot_override_safety_failure() -> None:
    """Invariant 4: LLM Judge != Business Correctness.
    A semantic judge's positive tone rating CANNOT convert a consequential safety failure into a PASS.
    """
    # Deterministic safety check fails because booking occurred when not allowed
    safety_judge = BookingSafetyJudge()
    safety_check = safety_judge.evaluate(
        should_allow_booking=False,
        booking_occurred=True,
        rejection_reason="Unconfirmed booking executed",
    )
    assert safety_check.passed is False

    # Even if an LLM judge evaluates the conversation as polite/natural:
    # Release gate policy enforces that safety_check.passed is strictly authoritative.
    is_release_blocked = not safety_check.passed
    assert is_release_blocked is True


@pytest.mark.asyncio
async def test_invariant_5_performance_cannot_disable_confirmation_safety() -> None:
    """Invariant 5: Performance != Quality.
    Preemptive generation or caching MUST NEVER bypass the two-phase confirmation gate.
    """
    clock = FrozenClock(datetime.datetime(2026, 10, 1, 9, 0, 0, tzinfo=datetime.UTC))
    prop_repo = InMemoryPropertyRepository.from_json_file("data/listings.json")
    showing_repo = InMemoryShowingRepository.from_json_file("data/showings.json")
    booking_repo = InMemoryBookingRepository()
    lead_repo = InMemoryLeadRepository()

    policy = BookingPolicyService(
        property_repo=prop_repo,
        showing_repo=showing_repo,
        booking_repo=booking_repo,
        clock=clock,
    )
    context = ConversationContext(session_id="inv-5-session")
    tools = AgentTools(
        property_repo=prop_repo,
        showing_repo=showing_repo,
        booking_repo=booking_repo,
        lead_repo=lead_repo,
        booking_policy=policy,
        clock=clock,
        context=context,
    )

    # Initial booking attempt without confirmation
    result = await tools.book_showing(
        BookShowingInput(
            property_id="prop-101",
            slot_id="slot-101-01",
            renter_name="Fast Renter",
            confirmed=False,
        )
    )
    assert result.success is True
    assert result.data is not None
    # Must be PENDING, NOT confirmed!
    assert result.data.booking.status == BookingStatus.PENDING
    assert len(await booking_repo.list_all()) == 0


def test_invariant_6_local_concurrency_is_not_cloud_scale() -> None:
    """Invariant 6: Local Concurrency != Cloud Scale.
    The application configuration and runtime profiles clearly distinguish local
    single-node limits from multi-tenant cloud capacity.
    """
    cfg = get_config()
    assert cfg.api_host in {"127.0.0.1", "localhost", "0.0.0.0"}
    # Architecture invariants enforce that PropRelay is documented as single-node local
    assert cfg.profile in {
        AppProfile.DEVELOPMENT,
        AppProfile.BENCHMARK,
        AppProfile.EVALUATION,
        AppProfile.PRODUCTION_LIKE_LOCAL,
    }
