"""Unit tests verifying deterministic reschedule and cancellation operations and event ordering.

Guarantees:
- Deadlock-free sorted locking across slot mutations.
- Invariant enforcement: RENTER_MISMATCH, BOOKING_ALREADY_CANCELLED, RESCHEDULE_SAME_SLOT, etc.
- Slot release on cancellation and rescheduling.
- Event ordering and telemetry verification.
"""

from __future__ import annotations

import asyncio

import pytest

from proprelay.agent.tools import (
    AgentTools,
    BookShowingInput,
    CancelShowingInput,
    RescheduleShowingInput,
)
from proprelay.domain.clock import FrozenClock
from proprelay.domain.models import (
    Booking,
    BookingStatus,
    ShowingSlotStatus,
)
from proprelay.domain.policy import (
    BookingPolicyService,
    CancellationRequest,
    PolicyErrorCode,
    RescheduleRequest,
)
from proprelay.domain.repositories import (
    InMemoryBookingRepository,
    InMemoryShowingRepository,
)
from proprelay.events.journal import EventJournal
from proprelay.events.schemas import EventType
from proprelay.workflows.context import ConversationContext


@pytest.fixture
def workflow_context() -> ConversationContext:
    return ConversationContext(session_id="test-session-rc")


@pytest.mark.asyncio
async def test_policy_reschedule_success(
    booking_policy: BookingPolicyService,
    booking_repo: InMemoryBookingRepository,
    showing_repo: InMemoryShowingRepository,
    frozen_clock: FrozenClock,
) -> None:
    """Verify successful reschedule updates booking and swaps slot statuses."""
    # Seed an active booking on slot-test-01
    booking = Booking(
        booking_id="bk-test-01",
        slot_id="slot-test-01",
        property_id="test-prop-1",
        renter_name="John Doe",
        renter_phone="555-1234",
        renter_email="john@example.com",
        created_at=frozen_clock.now(),
        status=BookingStatus.CONFIRMED,
        idempotency_key="key-01",
    )
    await booking_repo.add(booking)
    # Mark old slot booked
    old_slot = await showing_repo.get_slot("slot-test-01")
    assert old_slot is not None
    await showing_repo.update_slot_status("slot-test-01", ShowingSlotStatus.BOOKED)

    # Reschedule to slot-test-02
    req = RescheduleRequest(
        booking_id="bk-test-01",
        new_slot_id="slot-test-02",
        renter_name="John Doe",
    )
    res = await booking_policy.validate_and_reschedule(req)
    assert res.success
    assert res.booking is not None
    assert res.booking.slot_id == "slot-test-02"
    assert res.booking.updated_at is not None

    # Check repository state
    saved_booking = await booking_repo.get_by_id("bk-test-01")
    assert saved_booking is not None
    assert saved_booking.slot_id == "slot-test-02"

    old_slot_after = await showing_repo.get_slot("slot-test-01")
    new_slot_after = await showing_repo.get_slot("slot-test-02")
    assert old_slot_after is not None and old_slot_after.status == ShowingSlotStatus.AVAILABLE
    assert new_slot_after is not None and new_slot_after.status == ShowingSlotStatus.BOOKED


@pytest.mark.asyncio
async def test_policy_reschedule_errors(
    booking_policy: BookingPolicyService,
    booking_repo: InMemoryBookingRepository,
    showing_repo: InMemoryShowingRepository,
    frozen_clock: FrozenClock,
) -> None:
    """Verify domain error codes on invalid reschedule attempts."""
    # Seed active booking on slot-test-01
    booking = Booking(
        booking_id="bk-err-01",
        slot_id="slot-test-01",
        property_id="test-prop-1",
        renter_name="Jane Smith",
        created_at=frozen_clock.now(),
        status=BookingStatus.CONFIRMED,
        idempotency_key="key-err-01",
    )
    await booking_repo.add(booking)
    await showing_repo.update_slot_status("slot-test-01", ShowingSlotStatus.BOOKED)

    # 1. Non-existent booking
    res = await booking_policy.validate_and_reschedule(
        RescheduleRequest(
            booking_id="bk-nonexistent", new_slot_id="slot-test-02", renter_name="Jane Smith"
        )
    )
    assert not res.success
    assert res.error_code == PolicyErrorCode.BOOKING_NOT_FOUND

    # 2. Renter mismatch
    res_mismatch = await booking_policy.validate_and_reschedule(
        RescheduleRequest(
            booking_id="bk-err-01", new_slot_id="slot-test-02", renter_name="Wrong Person"
        )
    )
    assert not res_mismatch.success
    assert res_mismatch.error_code == PolicyErrorCode.RENTER_MISMATCH

    # 3. Reschedule to same slot
    res_same = await booking_policy.validate_and_reschedule(
        RescheduleRequest(
            booking_id="bk-err-01", new_slot_id="slot-test-01", renter_name="Jane Smith"
        )
    )
    assert not res_same.success
    assert res_same.error_code == PolicyErrorCode.RESCHEDULE_SAME_SLOT

    # 4. Target slot already booked
    res_booked = await booking_policy.validate_and_reschedule(
        RescheduleRequest(
            booking_id="bk-err-01", new_slot_id="slot-test-booked", renter_name="Jane Smith"
        )
    )
    assert not res_booked.success
    assert res_booked.error_code == PolicyErrorCode.SLOT_UNAVAILABLE

    # 5. Target slot in the past (slot-test-past is 2026-09-20, reference is 2026-10-01)
    res_past = await booking_policy.validate_and_reschedule(
        RescheduleRequest(
            booking_id="bk-err-01", new_slot_id="slot-test-past", renter_name="Jane Smith"
        )
    )
    assert not res_past.success
    assert res_past.error_code == PolicyErrorCode.DATE_IN_PAST


@pytest.mark.asyncio
async def test_policy_cancel_success(
    booking_policy: BookingPolicyService,
    booking_repo: InMemoryBookingRepository,
    showing_repo: InMemoryShowingRepository,
    frozen_clock: FrozenClock,
) -> None:
    """Verify successful cancellation releases slot and marks booking cancelled."""
    booking = Booking(
        booking_id="bk-cancel-01",
        slot_id="slot-test-01",
        property_id="test-prop-1",
        renter_name="Agent Cooper",
        created_at=frozen_clock.now(),
        status=BookingStatus.CONFIRMED,
        idempotency_key="key-cancel-01",
    )
    await booking_repo.add(booking)
    await showing_repo.update_slot_status("slot-test-01", ShowingSlotStatus.BOOKED)

    req = CancellationRequest(
        booking_id="bk-cancel-01",
        renter_name="Agent Cooper",
        reason="Found another apartment",
    )
    res = await booking_policy.validate_and_cancel(req)
    assert res.success
    assert res.booking is not None
    assert res.booking.status == BookingStatus.CANCELLED
    assert res.booking.cancellation_reason == "Found another apartment"

    # Verify slot is released back to AVAILABLE
    slot = await showing_repo.get_slot("slot-test-01")
    assert slot is not None and slot.status == ShowingSlotStatus.AVAILABLE

    # Attempting to cancel again fails with BOOKING_ALREADY_CANCELLED
    res_again = await booking_policy.validate_and_cancel(req)
    assert not res_again.success
    assert res_again.error_code == PolicyErrorCode.BOOKING_ALREADY_CANCELLED


@pytest.mark.asyncio
async def test_concurrent_reschedules_no_deadlock(
    booking_policy: BookingPolicyService,
    booking_repo: InMemoryBookingRepository,
    showing_repo: InMemoryShowingRepository,
    frozen_clock: FrozenClock,
) -> None:
    """Verify sorted locking prevents deadlock when two requests swap slots concurrently."""
    # Booking 1 on slot 01, Booking 2 on slot 02
    b1 = Booking(
        booking_id="bk-swap-1",
        slot_id="slot-test-01",
        property_id="test-prop-1",
        renter_name="Renter One",
        created_at=frozen_clock.now(),
        status=BookingStatus.CONFIRMED,
        idempotency_key="key-s1",
    )
    b2 = Booking(
        booking_id="bk-swap-2",
        slot_id="slot-test-02",
        property_id="test-prop-1",
        renter_name="Renter Two",
        created_at=frozen_clock.now(),
        status=BookingStatus.CONFIRMED,
        idempotency_key="key-s2",
    )
    await booking_repo.add(b1)
    await booking_repo.add(b2)
    await showing_repo.update_slot_status("slot-test-01", ShowingSlotStatus.BOOKED)
    await showing_repo.update_slot_status("slot-test-02", ShowingSlotStatus.BOOKED)

    # Concurrently attempt b1 -> slot 02 and b2 -> slot 01
    # Both slots are currently BOOKED, so one or both may fail with SLOT_UNAVAILABLE,
    # but critically they must NOT DEADLOCK!
    req1 = RescheduleRequest(
        booking_id="bk-swap-1", new_slot_id="slot-test-02", renter_name="Renter One"
    )
    req2 = RescheduleRequest(
        booking_id="bk-swap-2", new_slot_id="slot-test-01", renter_name="Renter Two"
    )

    # asyncio.wait_for with short timeout proves absence of deadlock
    task1 = asyncio.create_task(booking_policy.validate_and_reschedule(req1))
    task2 = asyncio.create_task(booking_policy.validate_and_reschedule(req2))

    res1, res2 = await asyncio.wait_for(asyncio.gather(task1, task2), timeout=2.0)
    # Because both slots were initially booked, requests fail gracefully without deadlock
    assert not res1.success
    assert not res2.success


@pytest.mark.asyncio
async def test_agent_tool_event_ordering_reschedule_and_cancel(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
    event_journal: EventJournal,
) -> None:
    """Verify strict event ordering through agent tools during reschedule and cancel."""
    agent_tools.set_context(workflow_context)

    # 1. Book initial showing
    await agent_tools.book_showing(
        BookShowingInput(
            property_id="test-prop-1",
            slot_id="slot-test-01",
            renter_name="Gordon Cole",
            confirmed=False,
        )
    )
    confirm_initial = await agent_tools.confirm_pending_action()
    assert confirm_initial.data is not None
    booking_id = confirm_initial.data.booking.booking_id

    # 2. Reschedule
    await agent_tools.reschedule_showing(
        RescheduleShowingInput(
            booking_id=booking_id,
            new_slot_id="slot-test-02",
            renter_name="Gordon Cole",
            confirmed=False,
        )
    )
    await agent_tools.confirm_pending_action()

    # 3. Cancel
    await agent_tools.cancel_showing(
        CancelShowingInput(
            booking_id=booking_id,
            renter_name="Gordon Cole",
            reason="Relocating",
            confirmed=False,
        )
    )
    await agent_tools.confirm_pending_action()

    # 4. Check sequential event stream
    events = event_journal.read_all()
    types = [e.event_type for e in events]

    # Verify presence and logical sequence of key event types
    idx_bk_req = types.index(EventType.BOOKING_CONFIRMATION_REQUESTED.value)
    idx_bk_acc = types.index(EventType.BOOKING_CONFIRMATION_ACCEPTED.value)
    idx_booked = types.index(EventType.SHOWING_BOOKED.value)
    assert idx_bk_req < idx_bk_acc < idx_booked

    idx_resched_req = types.index(EventType.SHOWING_RESCHEDULE_REQUESTED.value)
    idx_rescheduled = types.index(EventType.SHOWING_RESCHEDULED.value)
    assert idx_booked < idx_resched_req < idx_rescheduled

    idx_cancel_req = types.index(EventType.SHOWING_CANCELLATION_REQUESTED.value)
    idx_cancelled = types.index(EventType.SHOWING_CANCELLED.value)
    assert idx_rescheduled < idx_cancel_req < idx_cancelled
