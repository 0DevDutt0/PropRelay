"""Unit tests covering the 10 canonical multi-turn agentic workflow scenarios.

Guarantees:
- Scenario 1: Search -> select first property -> details.
- Scenario 2: Search -> property -> availability -> select slot.
- Scenario 3: Search -> property -> availability -> confirm booking.
- Scenario 4: Search -> invalid slot -> recovery.
- Scenario 5: Search -> booking -> user declines confirmation.
- Scenario 6: Search -> booking -> user changes date/property before confirmation (stale action check).
- Scenario 7: Booking -> user requests reschedule.
- Scenario 8: Booking -> user requests cancellation.
- Scenario 9: "Tell me about the first one" without search -> clarification, no hallucination.
- Scenario 10: "Book it" without context -> clarification, no booking.
"""

from __future__ import annotations

import datetime

import pytest

from proprelay.agent.tools import (
    AgentTools,
    BookShowingInput,
    CancelShowingInput,
    GetAvailableShowingsInput,
    GetPropertyDetailsInput,
    RescheduleShowingInput,
    SearchPropertiesInput,
)
from proprelay.domain.models import BookingStatus, ShowingSlotStatus
from proprelay.events.journal import EventJournal
from proprelay.events.schemas import EventType
from proprelay.workflows.context import ConversationContext
from proprelay.workflows.state import ActionType, WorkflowState


@pytest.fixture
def workflow_context() -> ConversationContext:
    return ConversationContext(session_id="test-session-wf")


@pytest.mark.asyncio
async def test_scenario_01_search_select_first_property_details(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
) -> None:
    """Scenario 1: Search -> select 'first one' -> inspect details."""
    agent_tools.set_context(workflow_context)

    # 1. User searches Downtown
    search_res = await agent_tools.search_properties(SearchPropertiesInput(location="Downtown"))
    assert search_res.success
    assert search_res.data is not None
    assert len(search_res.data.properties) == 1
    assert search_res.data.properties[0].property_id == "test-prop-1"
    assert workflow_context.workflow_state == WorkflowState.REVIEWING_RESULTS.value

    # 2. User says "Tell me more about the first one"
    details_res = await agent_tools.get_property_details(
        GetPropertyDetailsInput(property_id="the first one")
    )
    assert details_res.success
    assert details_res.data is not None
    assert details_res.data.property.property_id == "test-prop-1"
    assert details_res.data.property.title == "Modern Downtown Loft"
    assert workflow_context.selected_property is not None
    assert workflow_context.selected_property.property_id == "test-prop-1"
    assert workflow_context.workflow_state == WorkflowState.PROPERTY_SELECTED.value


@pytest.mark.asyncio
async def test_scenario_02_search_property_availability_select_slot(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
) -> None:
    """Scenario 2: Search -> property -> availability -> select slot."""
    agent_tools.set_context(workflow_context)

    # 1. Search & select
    await agent_tools.search_properties(SearchPropertiesInput(location="Downtown"))
    await agent_tools.get_property_details(GetPropertyDetailsInput(property_id="test-prop-1"))

    # 2. Check availability without passing property_id (inferred from context)
    avail_res = await agent_tools.get_available_showings(GetAvailableShowingsInput(property_id=""))
    assert avail_res.success
    assert avail_res.data is not None
    assert len(avail_res.data.slots) >= 2
    assert workflow_context.workflow_state == WorkflowState.CHECKING_AVAILABILITY.value

    # 3. User references "the 2 PM one"
    resolved_slot = workflow_context.resolve_slot_reference("2 PM")
    assert resolved_slot is not None
    assert resolved_slot.slot_id == "slot-test-02"
    assert resolved_slot.start_time == datetime.time(14, 0)
    workflow_context.select_showing_slot(resolved_slot)
    assert workflow_context.workflow_state == WorkflowState.SHOWING_SELECTED.value


@pytest.mark.asyncio
async def test_scenario_03_search_property_availability_confirm_booking(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
    event_journal: EventJournal,
) -> None:
    """Scenario 3: Search -> property -> availability -> stage proposal -> confirm booking."""
    agent_tools.set_context(workflow_context)

    # 1. Search & select
    await agent_tools.search_properties(SearchPropertiesInput(location="Downtown"))
    await agent_tools.get_property_details(GetPropertyDetailsInput(property_id="test-prop-1"))
    await agent_tools.get_available_showings(GetAvailableShowingsInput(property_id=""))

    # 2. User asks to book 10 AM slot for Alice Smith (confirmed=False)
    booking_proposal = await agent_tools.book_showing(
        BookShowingInput(
            property_id="test-prop-1",
            slot_id="slot-test-01",
            renter_name="Alice Smith",
            renter_phone="555-0100",
            renter_email="alice@example.com",
            confirmed=False,
        )
    )
    assert booking_proposal.success
    assert booking_proposal.data is not None
    assert booking_proposal.data.booking.status == BookingStatus.PENDING
    assert "Should I book that for you?" in (booking_proposal.message or "")
    assert workflow_context.workflow_state == WorkflowState.AWAITING_BOOKING_CONFIRMATION.value
    assert workflow_context.pending_action is not None
    assert workflow_context.pending_action.action_type == ActionType.BOOK_SHOWING

    # Verify confirmation requested event emitted
    events = event_journal.read_all()
    event_types = [e.event_type for e in events]
    assert EventType.BOOKING_CONFIRMATION_REQUESTED.value in event_types

    # 3. User confirms: "Yes, please book it"
    confirm_res = await agent_tools.confirm_pending_action()
    assert confirm_res.success
    assert confirm_res.data is not None
    assert confirm_res.data.booking.status == BookingStatus.CONFIRMED
    assert confirm_res.data.booking.booking_id.startswith("bk-")
    assert workflow_context.workflow_state == WorkflowState.BOOKED.value
    assert workflow_context.pending_action is None

    # Verify event trail
    events_after = event_journal.read_all()
    event_types_after = [e.event_type for e in events_after]
    assert EventType.BOOKING_CONFIRMATION_ACCEPTED.value in event_types_after
    assert EventType.SHOWING_BOOKED.value in event_types_after


@pytest.mark.asyncio
async def test_scenario_04_search_invalid_slot_recovery(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
) -> None:
    """Scenario 4: Search -> request invalid/unavailable slot -> graceful error recovery."""
    agent_tools.set_context(workflow_context)

    # 1. Search & select
    await agent_tools.search_properties(SearchPropertiesInput(location="Downtown"))
    await agent_tools.get_property_details(GetPropertyDetailsInput(property_id="test-prop-1"))

    # 2. User tries to book an already booked slot (slot-test-booked)
    res = await agent_tools.book_showing(
        BookShowingInput(
            property_id="test-prop-1",
            slot_id="slot-test-booked",
            renter_name="Bob Jones",
            confirmed=False,
        )
    )
    assert not res.success
    assert res.error_code == "SLOT_UNAVAILABLE"
    assert workflow_context.pending_action is None

    # 3. User recovers by asking for availability again
    avail_res = await agent_tools.get_available_showings(
        GetAvailableShowingsInput(property_id="test-prop-1")
    )
    assert avail_res.success
    assert avail_res.data is not None
    assert len(avail_res.data.slots) >= 2


@pytest.mark.asyncio
async def test_scenario_05_booking_user_declines_confirmation(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
    event_journal: EventJournal,
) -> None:
    """Scenario 5: Search -> booking proposal -> user declines confirmation."""
    agent_tools.set_context(workflow_context)

    # 1. Search and stage booking proposal
    await agent_tools.search_properties(SearchPropertiesInput(location="Downtown"))
    await agent_tools.book_showing(
        BookShowingInput(
            property_id="test-prop-1",
            slot_id="slot-test-01",
            renter_name="Charlie Brown",
            confirmed=False,
        )
    )
    assert workflow_context.pending_action is not None
    assert workflow_context.workflow_state == WorkflowState.AWAITING_BOOKING_CONFIRMATION

    # 2. User declines: "No, don't book that"
    decline_res = await agent_tools.cancel_pending_action(reason="user decided against it")
    assert decline_res.success
    assert decline_res.data == {"status": "cancelled"}
    assert workflow_context.pending_action is None
    assert workflow_context.workflow_state != WorkflowState.BOOKED

    # Slot must still be available
    slot = await agent_tools._showing_repo.get_slot("slot-test-01")
    assert slot is not None
    assert slot.status == ShowingSlotStatus.AVAILABLE

    # Verify event emitted
    events = event_journal.read_all()
    event_types = [e.event_type for e in events]
    assert EventType.BOOKING_CONFIRMATION_DECLINED.value in event_types


@pytest.mark.asyncio
async def test_scenario_06_booking_user_changes_date_stale_action_invalidation(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
) -> None:
    """Scenario 6: User stages booking, then changes date/property -> pending action invalidated."""
    agent_tools.set_context(workflow_context)

    # 1. Stage booking proposal for prop 1
    await agent_tools.search_properties(SearchPropertiesInput(location="Downtown"))
    await agent_tools.book_showing(
        BookShowingInput(
            property_id="test-prop-1",
            slot_id="slot-test-01",
            renter_name="Dana Scully",
            confirmed=False,
        )
    )
    assert workflow_context.pending_action is not None

    # 2. Turn 1 advances. User then selects a different property
    workflow_context.advance_turn()
    prop2 = await agent_tools._property_repo.get_by_id("test-prop-2")
    assert prop2 is not None
    workflow_context.select_property(prop2)
    # Selection of different property invalidates pending action!
    assert workflow_context.pending_action is None

    # 3. User says "Yes book it"
    confirm_res = await agent_tools.confirm_pending_action()
    assert not confirm_res.success
    assert confirm_res.error_code == "NO_PENDING_ACTION"


@pytest.mark.asyncio
async def test_scenario_07_booking_user_requests_reschedule(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
    event_journal: EventJournal,
) -> None:
    """Scenario 7: Existing booking -> user requests reschedule -> confirms -> updated."""
    agent_tools.set_context(workflow_context)

    # 1. Establish initial booking
    await agent_tools.book_showing(
        BookShowingInput(
            property_id="test-prop-1",
            slot_id="slot-test-01",
            renter_name="Fox Mulder",
            confirmed=False,
        )
    )
    confirm_initial = await agent_tools.confirm_pending_action()
    assert confirm_initial.data is not None
    booking_id = confirm_initial.data.booking.booking_id

    # 2. User requests reschedule to slot-test-02 (2 PM) without confirmation
    resched_proposal = await agent_tools.reschedule_showing(
        RescheduleShowingInput(
            booking_id=booking_id,
            new_slot_id="slot-test-02",
            renter_name="Fox Mulder",
            confirmed=False,
        )
    )
    assert resched_proposal.success
    assert "Should I reschedule it" in (resched_proposal.message or "")
    assert workflow_context.pending_action is not None
    assert workflow_context.pending_action.action_type == ActionType.RESCHEDULE_SHOWING

    # 3. User confirms reschedule
    confirm_resched = await agent_tools.confirm_pending_action()
    assert confirm_resched.success
    assert confirm_resched.data is not None
    assert confirm_resched.data.booking.slot_id == "slot-test-02"
    assert confirm_resched.data.booking.status == BookingStatus.CONFIRMED

    # 4. Verify slot states: old slot released, new slot booked
    old_slot = await agent_tools._showing_repo.get_slot("slot-test-01")
    new_slot = await agent_tools._showing_repo.get_slot("slot-test-02")
    assert old_slot is not None and old_slot.status == ShowingSlotStatus.AVAILABLE
    assert new_slot is not None and new_slot.status == ShowingSlotStatus.BOOKED

    # Verify event journal
    events = event_journal.read_all()
    event_types = [e.event_type for e in events]
    assert EventType.SHOWING_RESCHEDULE_REQUESTED.value in event_types
    assert EventType.SHOWING_RESCHEDULED.value in event_types


@pytest.mark.asyncio
async def test_scenario_08_booking_user_requests_cancellation(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
    event_journal: EventJournal,
) -> None:
    """Scenario 8: Existing booking -> user requests cancellation -> confirms -> cancelled."""
    agent_tools.set_context(workflow_context)

    # 1. Establish initial booking
    await agent_tools.book_showing(
        BookShowingInput(
            property_id="test-prop-1",
            slot_id="slot-test-01",
            renter_name="Walter Skinner",
            confirmed=False,
        )
    )
    confirm_initial = await agent_tools.confirm_pending_action()
    assert confirm_initial.data is not None
    booking_id = confirm_initial.data.booking.booking_id

    # 2. User requests cancellation (unconfirmed)
    cancel_proposal = await agent_tools.cancel_showing(
        CancelShowingInput(
            booking_id=booking_id,
            renter_name="Walter Skinner",
            reason="Schedule conflict",
            confirmed=False,
        )
    )
    assert cancel_proposal.success
    assert "Are you sure you want to cancel" in (cancel_proposal.message or "")
    assert workflow_context.pending_action is not None
    assert workflow_context.pending_action.action_type == ActionType.CANCEL_SHOWING

    # 3. User confirms cancellation
    confirm_cancel = await agent_tools.confirm_pending_action()
    assert confirm_cancel.success
    assert confirm_cancel.data is not None
    assert confirm_cancel.data.booking.status == BookingStatus.CANCELLED
    assert confirm_cancel.data.booking.cancellation_reason == "Schedule conflict"

    # 4. Verify slot released
    slot = await agent_tools._showing_repo.get_slot("slot-test-01")
    assert slot is not None and slot.status == ShowingSlotStatus.AVAILABLE

    # Verify event journal
    events = event_journal.read_all()
    event_types = [e.event_type for e in events]
    assert EventType.SHOWING_CANCELLATION_REQUESTED.value in event_types
    assert EventType.SHOWING_CANCELLED.value in event_types


@pytest.mark.asyncio
async def test_scenario_09_tell_me_about_first_one_without_search_no_hallucination(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
) -> None:
    """Scenario 9: 'Tell me about the first one' with empty context -> clarification, no hallucination."""
    agent_tools.set_context(workflow_context)

    # Empty context: no prior search executed
    assert len(workflow_context.shortlisted_properties) == 0

    res = await agent_tools.get_property_details(
        GetPropertyDetailsInput(property_id="the first one")
    )
    assert not res.success
    assert res.error_code == "PROPERTY_NOT_FOUND"
    assert "search for properties first" in (res.message or "").lower()
    assert workflow_context.selected_property is None


@pytest.mark.asyncio
async def test_scenario_10_book_it_without_context_no_booking(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
) -> None:
    """Scenario 10: 'Book it' without any context -> fails cleanly, no booking created."""
    agent_tools.set_context(workflow_context)

    # Empty context
    confirm_res = await agent_tools.confirm_pending_action()
    assert not confirm_res.success
    assert confirm_res.error_code == "NO_PENDING_ACTION"

    # Attempt direct book_showing with empty parameters
    direct_res = await agent_tools.book_showing(
        BookShowingInput(
            property_id="",
            slot_id="",
            renter_name="",
            confirmed=False,
        )
    )
    assert not direct_res.success
    assert direct_res.error_code in ("MISSING_RENTER_NAME", "PROPERTY_NOT_FOUND")
    assert workflow_context.pending_action is None
