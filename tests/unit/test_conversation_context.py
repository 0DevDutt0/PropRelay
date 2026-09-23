"""Unit tests for ConversationContext, reference resolution, and action expiration."""

from __future__ import annotations

import datetime

import pytest

from proprelay.agent.tools import PropertySummary, ShowingSlotSummary
from proprelay.domain.models import ShowingSlotStatus
from proprelay.workflows.context import ConversationContext
from proprelay.workflows.state import ActionType, PendingAction, WorkflowState


@pytest.fixture
def sample_properties() -> list[PropertySummary]:
    return [
        PropertySummary(
            property_id="prop-101",
            title="The Solaris Loft",
            address="100 Grand Ave",
            city="Metropolis",
            neighborhood="Downtown",
            monthly_rent=2850,
            bedrooms=2,
            bathrooms=2.0,
            square_feet=1150,
            pets_allowed=False,
        ),
        PropertySummary(
            property_id="prop-102",
            title="Pinecrest Garden Duplex",
            address="450 Valley Rd",
            city="Metropolis",
            neighborhood="North Hills",
            monthly_rent=2200,
            bedrooms=2,
            bathrooms=1.5,
            square_feet=980,
            pets_allowed=True,
        ),
    ]


@pytest.fixture
def sample_slots() -> list[ShowingSlotSummary]:
    return [
        ShowingSlotSummary(
            slot_id="slot-101-01",
            property_id="prop-101",
            date=datetime.date(2026, 10, 5),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(10, 45),
            status=ShowingSlotStatus.AVAILABLE,
        ),
        ShowingSlotSummary(
            slot_id="slot-101-02",
            property_id="prop-101",
            date=datetime.date(2026, 10, 5),
            start_time=datetime.time(15, 0),
            end_time=datetime.time(15, 45),
            status=ShowingSlotStatus.AVAILABLE,
        ),
    ]


def test_initial_context() -> None:
    ctx = ConversationContext(session_id="test-sess")
    assert ctx.workflow_state == WorkflowState.IDLE
    assert ctx.current_turn == 0
    assert ctx.shortlisted_properties == []
    assert ctx.selected_property is None
    assert ctx.pending_action is None


def test_record_search_and_reference_resolution(
    sample_properties: list[PropertySummary],
) -> None:
    ctx = ConversationContext(session_id="test-sess")
    ctx.record_search({"bedrooms": 2, "max_rent": 3000}, sample_properties)

    assert ctx.workflow_state == WorkflowState.REVIEWING_RESULTS
    assert len(ctx.shortlisted_properties) == 2

    # "the first one"
    first = ctx.resolve_property_reference("the first one")
    assert first is not None
    assert first.property_id == "prop-101"

    # "the second one" / "2"
    second = ctx.resolve_property_reference("second")
    assert second is not None
    assert second.property_id == "prop-102"

    # "the cheaper one"
    cheaper = ctx.resolve_property_reference("the cheaper one")
    assert cheaper is not None
    assert cheaper.property_id == "prop-102"
    assert cheaper.monthly_rent == 2200

    # "pet friendly"
    pets = ctx.resolve_property_reference("the one that allows pets")
    assert pets is not None
    assert pets.property_id == "prop-102"

    # Substring title
    solaris = ctx.resolve_property_reference("Solaris")
    assert solaris is not None
    assert solaris.property_id == "prop-101"


def test_empty_shortlist_reference_resolution_no_hallucination() -> None:
    ctx = ConversationContext(session_id="test-sess")
    # No search performed
    assert ctx.resolve_property_reference("the first one") is None
    assert ctx.resolve_property_reference("the cheaper one") is None


def test_showing_slot_resolution(sample_slots: list[ShowingSlotSummary]) -> None:
    ctx = ConversationContext(session_id="test-sess")
    ctx.record_available_showings(datetime.date(2026, 10, 5), sample_slots)
    assert ctx.workflow_state == WorkflowState.CHECKING_AVAILABILITY

    # "The 3 PM one"
    slot_3pm = ctx.resolve_slot_reference("The 3 PM one")
    assert slot_3pm is not None
    assert slot_3pm.slot_id == "slot-101-02"

    # "afternoon"
    slot_afternoon = ctx.resolve_slot_reference("afternoon slot")
    assert slot_afternoon is not None
    assert slot_afternoon.slot_id == "slot-101-02"

    # "morning"
    slot_morning = ctx.resolve_slot_reference("morning")
    assert slot_morning is not None
    assert slot_morning.slot_id == "slot-101-01"


def test_pending_action_expiration() -> None:
    ctx = ConversationContext(session_id="test-sess")
    action = PendingAction(
        action_type=ActionType.BOOK_SHOWING,
        property_id="prop-101",
        slot_id="slot-101-02",
        renter_name="Alex Smith",
        summary="Book Solaris Loft at 3 PM",
        created_turn=0,
        expires_after_turns=2,
    )
    ctx.stage_pending_action(action)
    assert ctx.workflow_state == WorkflowState.AWAITING_BOOKING_CONFIRMATION
    assert ctx.pending_action is not None

    # Advance 1 turn
    ctx.advance_turn()
    assert ctx.current_turn == 1
    assert ctx.pending_action is not None  # Not expired yet

    # Advance 2nd turn
    ctx.advance_turn()
    assert ctx.current_turn == 2
    assert ctx.pending_action is None  # Expired!


def test_stale_action_invalidation_on_property_change(
    sample_properties: list[PropertySummary],
) -> None:
    ctx = ConversationContext(session_id="test-sess")
    ctx.record_search({}, sample_properties)
    ctx.select_property(sample_properties[0])

    action = PendingAction(
        action_type=ActionType.BOOK_SHOWING,
        property_id="prop-101",
        slot_id="slot-101-02",
        renter_name="Alex Smith",
        summary="Book Solaris Loft",
        created_turn=0,
    )
    ctx.stage_pending_action(action)
    assert ctx.pending_action is not None

    # User corrects: "Actually, let's do the second property"
    ctx.select_property(sample_properties[1])
    assert ctx.selected_property is not None
    assert ctx.selected_property.property_id == "prop-102"
    assert ctx.pending_action is None  # Immediately invalidated!


def test_stale_action_invalidation_on_slot_change(
    sample_slots: list[ShowingSlotSummary],
) -> None:
    ctx = ConversationContext(session_id="test-sess")
    ctx.record_available_showings(datetime.date(2026, 10, 5), sample_slots)
    ctx.select_showing_slot(sample_slots[0])

    action = PendingAction(
        action_type=ActionType.BOOK_SHOWING,
        property_id="prop-101",
        slot_id="slot-101-01",
        renter_name="Alex Smith",
        summary="Book Solaris Loft at 10 AM",
        created_turn=0,
    )
    ctx.stage_pending_action(action)
    assert ctx.pending_action is not None

    # User corrects: "Actually, 3 PM is better"
    ctx.select_showing_slot(sample_slots[1])
    assert ctx.pending_action is None  # Invalidated!


def test_cancel_pending_action() -> None:
    ctx = ConversationContext(session_id="test-sess")
    action = PendingAction(
        action_type=ActionType.BOOK_SHOWING,
        property_id="prop-101",
        slot_id="slot-101-01",
        renter_name="Alex Smith",
        summary="Book Solaris Loft",
        created_turn=0,
    )
    ctx.stage_pending_action(action)
    assert ctx.workflow_state == WorkflowState.AWAITING_BOOKING_CONFIRMATION

    cancelled = ctx.cancel_pending_action()
    assert cancelled is not None
    assert cancelled.property_id == "prop-101"
    assert ctx.pending_action is None
    assert ctx.workflow_state != WorkflowState.AWAITING_BOOKING_CONFIRMATION
