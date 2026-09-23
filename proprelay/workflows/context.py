"""Structured conversational session context and reference resolution."""

from __future__ import annotations

import datetime
import logging
import re
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from proprelay.agent.date_normalization import match_slot_reference
from proprelay.domain.models import Booking, Property
from proprelay.workflows.state import PendingAction, WorkflowState, WorkflowType

if TYPE_CHECKING:
    from proprelay.agent.tools import PropertySummary, ShowingSlotSummary

logger = logging.getLogger(__name__)


class ConversationContext:
    """Maintains structured session context across multi-turn conversational workflows.

    CRITICAL ARCHITECTURAL GUARANTEE (TDR-026):
    Structured domain state is kept in this object rather than asking the LLM
    to reconstruct entity relationships from free-form conversation history.
    """

    def __init__(
        self,
        session_id: str,
        workflow_id: str | None = None,
        on_state_change: Callable[[WorkflowState, WorkflowState], Any] | None = None,
    ) -> None:
        self.session_id: str = session_id
        self.workflow_id: str = workflow_id or f"wf_{session_id}_{uuid.uuid4().hex[:6]}"
        self.current_turn: int = 0
        self.workflow_state: WorkflowState = WorkflowState.IDLE
        self.workflow_type: WorkflowType = WorkflowType.DISCOVERY
        self._on_state_change = on_state_change

        # Structured discovery & listing context
        self.search_preferences: dict[str, Any] = {}
        self.shortlisted_properties: list[PropertySummary] = []
        self.selected_property: PropertySummary | Property | None = None

        # Structured showing context
        self.selected_showing_date: datetime.date | None = None
        self.available_slots: list[ShowingSlotSummary] = []
        self.selected_showing_slot: ShowingSlotSummary | None = None

        # Renter context
        self.renter_information: dict[str, str] = {}

        # Consequential action safety context
        self.pending_action: PendingAction | None = None
        self.active_booking: Booking | None = None

    def advance_turn(self) -> None:
        """Increment turn counter and evaluate pending action expiration."""
        self.current_turn += 1
        if self.pending_action and self.pending_action.is_expired(self.current_turn):
            logger.info(
                "Pending action '%s' expired at turn %d (created at %d)",
                self.pending_action.action_type.value,
                self.current_turn,
                self.pending_action.created_turn,
            )
            self.pending_action = None
            if self.workflow_state == WorkflowState.AWAITING_BOOKING_CONFIRMATION:
                self.set_workflow_state(
                    WorkflowState.SHOWING_SELECTED
                    if self.selected_showing_slot
                    else WorkflowState.PROPERTY_SELECTED
                )

    def set_workflow_state(self, new_state: WorkflowState) -> None:
        """Update workflow state and notify listener if state transitioned."""
        old_state = self.workflow_state
        if old_state != new_state:
            self.workflow_state = new_state
            logger.info("Workflow state: %s -> %s", old_state.value, new_state.value)
            if self._on_state_change:
                self._on_state_change(old_state, new_state)

    def record_search(
        self,
        criteria: dict[str, Any],
        results: list[PropertySummary],
    ) -> None:
        """Record property search preferences and authoritative shortlist."""
        # If user changed search criteria while action was pending, invalidate action
        if self.pending_action:
            self.invalidate_pending_action(reason="new_search_executed")

        self.search_preferences = criteria
        self.shortlisted_properties = results
        self.workflow_type = WorkflowType.DISCOVERY
        self.set_workflow_state(WorkflowState.REVIEWING_RESULTS)

    def select_property(self, property_obj: PropertySummary | Property) -> None:
        """Authoritatively set current active property."""
        prop_id = property_obj.property_id
        if self.pending_action and self.pending_action.property_id != prop_id:
            self.invalidate_pending_action(reason="property_changed")

        self.selected_property = property_obj
        # Clear slots from prior property
        self.available_slots = []
        self.selected_showing_slot = None
        self.set_workflow_state(WorkflowState.PROPERTY_SELECTED)

    def record_available_showings(
        self,
        date: datetime.date | None,
        slots: list[ShowingSlotSummary],
    ) -> None:
        """Record showing calendar lookup result."""
        self.selected_showing_date = date
        self.available_slots = slots
        self.workflow_type = WorkflowType.SHOWING_BOOKING
        self.set_workflow_state(WorkflowState.CHECKING_AVAILABILITY)

    def select_showing_slot(self, slot: ShowingSlotSummary) -> None:
        """Authoritatively set current selected showing slot."""
        if self.pending_action and self.pending_action.slot_id != slot.slot_id:
            self.invalidate_pending_action(reason="slot_changed")

        self.selected_showing_slot = slot
        self.set_workflow_state(WorkflowState.SHOWING_SELECTED)

    def set_renter_info(
        self,
        name: str | None = None,
        phone: str | None = None,
        email: str | None = None,
    ) -> None:
        """Store or update prospective renter contact details."""
        if name and name.strip():
            self.renter_information["name"] = name.strip()
        if phone and phone.strip():
            self.renter_information["phone"] = phone.strip()
        if email and email.strip():
            self.renter_information["email"] = email.strip()

    def stage_pending_action(self, action: PendingAction) -> None:
        """Explicitly stage a consequential action awaiting user confirmation."""
        self.pending_action = action
        self.set_workflow_state(WorkflowState.AWAITING_BOOKING_CONFIRMATION)

    def confirm_pending_action(self) -> PendingAction | None:
        """Verify and return active pending action for execution, clearing pending state."""
        if not self.pending_action:
            return None
        if self.pending_action.is_expired(self.current_turn):
            self.pending_action = None
            return None

        action = self.pending_action
        self.pending_action = None
        return action

    def cancel_pending_action(self) -> PendingAction | None:
        """User explicitly rejected or cancelled the pending proposal."""
        if not self.pending_action:
            return None
        cancelled = self.pending_action
        self.pending_action = None
        self.set_workflow_state(
            WorkflowState.SHOWING_SELECTED
            if self.selected_showing_slot
            else WorkflowState.PROPERTY_SELECTED
        )
        return cancelled

    def invalidate_pending_action(self, reason: str = "correction") -> bool:
        """Stale action prevention: invalidate pending action upon correction."""
        if self.pending_action:
            logger.info(
                "Invalidating pending action '%s' due to: %s",
                self.pending_action.action_type.value,
                reason,
            )
            self.pending_action = None
            return True
        return False

    def resolve_property_reference(self, ref: str | None) -> PropertySummary | None:
        """Deterministically resolve a property reference against current shortlist.

        Handles:
        - Exact property_id ('prop-101')
        - Positional references ('the first one', 'first', '1', 'the second', 'second', '2', 'last')
        - Attribute superlatives ('cheaper', 'cheapest', 'pet friendly')
        - Title / neighborhood substrings ('solaris', 'pinecrest', 'downtown')
        """
        if not self.shortlisted_properties:
            if (
                self.selected_property
                and ref
                and ref.strip().lower()
                in (
                    self.selected_property.property_id.lower(),
                    "this",
                    "it",
                    "that property",
                    "that apartment",
                )
            ):
                from proprelay.agent.tools import PropertySummary

                if isinstance(self.selected_property, PropertySummary):
                    return self.selected_property
                return PropertySummary(
                    property_id=self.selected_property.property_id,
                    title=self.selected_property.title,
                    address=self.selected_property.address,
                    city=self.selected_property.city,
                    neighborhood=self.selected_property.neighborhood,
                    monthly_rent=self.selected_property.monthly_rent,
                    bedrooms=self.selected_property.bedrooms,
                    bathrooms=self.selected_property.bathrooms,
                    square_feet=self.selected_property.square_feet,
                    pets_allowed=self.selected_property.pets_allowed,
                )
            return None

        if not ref or not ref.strip():
            # If only 1 property in shortlist, default to it
            return self.shortlisted_properties[0] if len(self.shortlisted_properties) == 1 else None

        cleaned = ref.strip().lower()

        # 1. Exact ID
        for p in self.shortlisted_properties:
            if p.property_id.lower() == cleaned:
                return p

        # 2. Positional references
        if re.search(r"\b(first|1st|first one|1)\b", cleaned):
            return self.shortlisted_properties[0]
        if (
            re.search(r"\b(second|2nd|second one|2)\b", cleaned)
            and len(self.shortlisted_properties) >= 2
        ):
            return self.shortlisted_properties[1]
        if (
            re.search(r"\b(third|3rd|third one|3)\b", cleaned)
            and len(self.shortlisted_properties) >= 3
        ):
            return self.shortlisted_properties[2]
        if re.search(r"\b(last|last one)\b", cleaned):
            return self.shortlisted_properties[-1]

        # 3. Superlative: cheaper / cheapest
        if "cheap" in cleaned or "lower rent" in cleaned or "less expensive" in cleaned:
            return min(self.shortlisted_properties, key=lambda p: p.monthly_rent)

        # 4. Filter: pet friendly
        if "pet" in cleaned:
            pet_props = [p for p in self.shortlisted_properties if p.pets_allowed]
            if len(pet_props) == 1:
                return pet_props[0]

        # 5. Matching title or neighborhood name
        for p in self.shortlisted_properties:
            if p.title.lower() in cleaned or cleaned in p.title.lower():
                return p
            if p.neighborhood.lower() in cleaned or cleaned in p.neighborhood.lower():
                return p

        # 6. Single item fallback
        if len(self.shortlisted_properties) == 1:
            return self.shortlisted_properties[0]

        return None

    def resolve_slot_reference(self, ref: str | None) -> ShowingSlotSummary | None:
        """Resolve a showing slot reference against current available slots."""
        return match_slot_reference(self.available_slots, ref)

    def reset_context(self, keep_renter: bool = True) -> None:
        """Reset conversation context at workflow completion or explicit topic change."""
        self.workflow_id = f"wf_{self.session_id}_{uuid.uuid4().hex[:6]}"
        self.workflow_state = WorkflowState.IDLE
        self.workflow_type = WorkflowType.DISCOVERY
        self.search_preferences = {}
        self.shortlisted_properties = []
        self.selected_property = None
        self.selected_showing_date = None
        self.available_slots = []
        self.selected_showing_slot = None
        self.pending_action = None
        if not keep_renter:
            self.renter_information = {}

    def start_new_workflow(self, workflow_type: WorkflowType = WorkflowType.DISCOVERY) -> str:
        """Start a new workflow execution with a fresh workflow_id."""
        self.reset_context(keep_renter=True)
        self.workflow_type = workflow_type
        return self.workflow_id
