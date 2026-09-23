"""Workflow state definitions and pending action models."""

from __future__ import annotations

import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkflowState(StrEnum):
    """Authoritative states of the agentic workflow state machine.

    Hard constraints:
    - AWAITING_BOOKING_CONFIRMATION: System has proposed an action and requires explicit confirmation.
      No state mutation can occur unless a valid PendingAction is verified.
    - BOOKING / RESCHEDULING / CANCELLING: In-flight state mutation within domain policy.
    - BOOKED: Consequential state mutation committed successfully.

    Informational context:
    - IDLE, SEARCHING, REVIEWING_RESULTS, PROPERTY_SELECTED, CHECKING_AVAILABILITY, SHOWING_SELECTED, LEAD_CAPTURE:
      Track conversation progression to resolve references and guide natural spoken dialogue.
    """

    IDLE = "IDLE"
    SEARCHING = "SEARCHING"
    REVIEWING_RESULTS = "REVIEWING_RESULTS"
    PROPERTY_SELECTED = "PROPERTY_SELECTED"
    CHECKING_AVAILABILITY = "CHECKING_AVAILABILITY"
    SHOWING_SELECTED = "SHOWING_SELECTED"
    AWAITING_BOOKING_CONFIRMATION = "AWAITING_BOOKING_CONFIRMATION"
    BOOKING = "BOOKING"
    BOOKED = "BOOKED"
    BOOKING_FAILED = "BOOKING_FAILED"
    LEAD_CAPTURE = "LEAD_CAPTURE"
    RESCHEDULING = "RESCHEDULING"
    CANCELLING = "CANCELLING"


class WorkflowType(StrEnum):
    """Categorization of the current active workflow."""

    DISCOVERY = "DISCOVERY"
    SHOWING_BOOKING = "SHOWING_BOOKING"
    RESCHEDULE = "RESCHEDULE"
    CANCELLATION = "CANCELLATION"
    LEAD_CAPTURE = "LEAD_CAPTURE"


class ActionType(StrEnum):
    """Type of consequential state-changing action requiring confirmation."""

    BOOK_SHOWING = "BOOK_SHOWING"
    RESCHEDULE_SHOWING = "RESCHEDULE_SHOWING"
    CANCEL_SHOWING = "CANCEL_SHOWING"


class PendingAction(BaseModel):
    """Explicit application-level representation of a consequential action awaiting confirmation.

    CRITICAL ARCHITECTURAL GUARANTEE (TDR-025):
    The LLM is NEVER trusted as confirmation state.
    Consequential actions must be explicitly staged here with exact parameters.
    The action expires after a bounded turn lifetime and is immediately invalidated
    if the user alters any related parameter (property, slot, date).
    """

    model_config = ConfigDict(frozen=True)

    action_type: ActionType = Field(..., description="Action to execute upon confirmation")
    property_id: str | None = Field(default=None, description="Target property ID")
    property_title: str | None = Field(default=None, description="Human readable property title")
    slot_id: str | None = Field(default=None, description="Target showing slot ID")
    slot_time_str: str | None = Field(default=None, description="Human readable slot time")
    renter_name: str | None = Field(default=None, description="Confirmed renter name")
    renter_phone: str | None = Field(default=None, description="Confirmed renter phone")
    renter_email: str | None = Field(default=None, description="Confirmed renter email")
    expected_date: datetime.date | None = Field(default=None, description="Showing date")
    booking_id: str | None = Field(
        default=None, description="Existing booking ID for reschedule/cancel"
    )
    summary: str = Field(..., description="Spoken proposal sentence presented to renter")
    created_turn: int = Field(..., description="Turn index when this proposal was created")
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="Timestamp when proposal was created",
    )
    expires_after_turns: int = Field(
        default=2, description="Number of conversational turns after which this action expires"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional context payload")

    def is_expired(self, current_turn: int) -> bool:
        """Evaluate if the pending proposal has expired due to turn progression."""
        return (current_turn - self.created_turn) >= self.expires_after_turns
