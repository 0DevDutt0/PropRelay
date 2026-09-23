"""Typed tool contracts and adapters bridging agent intents to deterministic domain services."""

from __future__ import annotations

import datetime
import time
import uuid
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from proprelay.domain.clock import Clock, SystemClock
from proprelay.domain.models import (
    Booking,
    BookingStatus,
    Lead,
    Property,
    ShowingSlotStatus,
)
from proprelay.domain.policy import (
    BookingPolicyService,
    BookingRequest,
    CancellationRequest,
    RescheduleRequest,
)
from proprelay.domain.repositories import (
    IBookingRepository,
    ILeadRepository,
    IPropertyRepository,
    IShowingRepository,
)
from proprelay.events.journal import IEventPublisher
from proprelay.events.schemas import DomainEvent, EventType
from proprelay.observability.metrics import WorkflowMetricsTracker
from proprelay.testing.failure_injection import (
    FailureMode,
    should_inject_failure,
)
from proprelay.workflows.context import ConversationContext
from proprelay.workflows.state import ActionType, PendingAction, WorkflowState

T = TypeVar("T")


class ToolResult[T](BaseModel):
    """Structured, type-safe result envelope returned by all agent tools."""

    model_config = ConfigDict(frozen=True)

    success: bool = Field(..., description="Whether the tool operation succeeded")
    data: T | None = Field(default=None, description="Typed return payload on success")
    error_code: str | None = Field(default=None, description="Structured error code on failure")
    message: str | None = Field(default=None, description="Human-readable explanation or summary")


class SearchPropertiesInput(BaseModel):
    """Input parameters for searching property listings."""

    model_config = ConfigDict(extra="forbid")

    location: str | None = Field(
        default=None, description="Neighborhood or city name to match (case-insensitive substring)"
    )
    max_rent: int | None = Field(
        default=None, gt=0, description="Maximum monthly rent threshold in USD"
    )
    bedrooms: int | None = Field(
        default=None, ge=0, description="Exact number of bedrooms (0 for studio)"
    )
    pets_allowed: bool | None = Field(
        default=None, description="True to filter for pet-friendly properties only"
    )


class PropertySummary(BaseModel):
    """Concise representation of a listing returned to the language model."""

    model_config = ConfigDict(frozen=True)

    property_id: str
    title: str
    address: str
    city: str
    neighborhood: str
    monthly_rent: int
    bedrooms: int
    bathrooms: float
    square_feet: int
    pets_allowed: bool


class SearchPropertiesOutput(BaseModel):
    """Output payload for property searches."""

    model_config = ConfigDict(frozen=True)

    total_count: int
    properties: list[PropertySummary]


class GetPropertyDetailsInput(BaseModel):
    """Input parameters for retrieving full listing details."""

    model_config = ConfigDict(extra="forbid")

    property_id: str = Field(..., description="Alphanumeric property identifier (e.g. 'prop-101')")


class GetPropertyDetailsOutput(BaseModel):
    """Output payload containing authoritative property details."""

    model_config = ConfigDict(frozen=True)

    property: Property


class GetAvailableShowingsInput(BaseModel):
    """Input parameters for querying showing calendar availability."""

    model_config = ConfigDict(extra="forbid")

    property_id: str = Field(..., description="Target property ID")
    date: datetime.date | None = Field(
        default=None, description="Optional target date in YYYY-MM-DD format"
    )


class ShowingSlotSummary(BaseModel):
    """Concise showing slot availability summary."""

    model_config = ConfigDict(frozen=True)

    slot_id: str
    property_id: str
    date: datetime.date
    start_time: datetime.time
    end_time: datetime.time
    status: ShowingSlotStatus


class GetAvailableShowingsOutput(BaseModel):
    """Output payload containing list of available showing slots."""

    model_config = ConfigDict(frozen=True)

    property_id: str
    total_available: int
    slots: list[ShowingSlotSummary]


class BookShowingInput(BaseModel):
    """Input parameters for scheduling a property showing."""

    model_config = ConfigDict(extra="forbid")

    property_id: str = Field(..., description="Target property ID")
    slot_id: str = Field(..., description="Target showing slot ID")
    renter_name: str = Field(..., description="Full legal name of the renter")
    renter_phone: str | None = Field(default=None, description="Optional contact telephone")
    renter_email: str | None = Field(default=None, description="Optional contact email")
    expected_date: datetime.date | None = Field(
        default=None, description="Optional expected showing date for cross-checking"
    )
    confirmed: bool = Field(
        default=False, description="True if renter explicitly confirmed the booking proposal"
    )


class BookShowingOutput(BaseModel):
    """Output payload confirming a showing reservation."""

    model_config = ConfigDict(frozen=True)

    booking: Booking
    is_idempotent: bool = Field(
        default=False,
        description="True if request was satisfied via existing duplicate reservation",
    )


class RescheduleShowingInput(BaseModel):
    """Input parameters for rescheduling an existing showing."""

    model_config = ConfigDict(extra="forbid")

    booking_id: str = Field(..., description="Target existing booking ID")
    new_slot_id: str = Field(..., description="Target new showing slot ID")
    renter_name: str = Field(..., description="Renter name on reservation")
    expected_date: datetime.date | None = Field(
        default=None, description="Optional expected showing date"
    )
    confirmed: bool = Field(
        default=False, description="True if renter explicitly confirmed rescheduling"
    )


class RescheduleShowingOutput(BaseModel):
    """Output payload confirming rescheduled showing."""

    model_config = ConfigDict(frozen=True)

    booking: Booking


class CancelShowingInput(BaseModel):
    """Input parameters for cancelling an existing showing."""

    model_config = ConfigDict(extra="forbid")

    booking_id: str = Field(..., description="Target existing booking ID")
    renter_name: str = Field(..., description="Renter name on reservation")
    reason: str | None = Field(default=None, description="Optional reason for cancellation")
    confirmed: bool = Field(
        default=False, description="True if renter explicitly confirmed cancellation"
    )


class CancelShowingOutput(BaseModel):
    """Output payload confirming cancelled showing."""

    model_config = ConfigDict(frozen=True)

    booking: Booking


class ConfirmPendingActionInput(BaseModel):
    """Input for confirming an in-flight pending proposal."""

    model_config = ConfigDict(extra="forbid")

    action_type: str | None = Field(default=None, description="Optional action type to verify")


class CancelPendingActionInput(BaseModel):
    """Input for declining/cancelling an in-flight pending proposal."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, description="Optional cancellation explanation")


class CreateLeadInput(BaseModel):
    """Input parameters for registering a prospective renter lead."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Lead contact full name")
    phone: str | None = Field(default=None, description="Contact phone")
    email: str | None = Field(default=None, description="Contact email")
    preferred_neighborhood: str | None = Field(
        default=None, description="Preferred district or area"
    )
    budget: int | None = Field(default=None, ge=0, description="Monthly budget ceiling in USD")
    interested_property_id: str | None = Field(default=None, description="Property ID of interest")
    notes: str | None = Field(
        default=None, description="Renter preferences or conversational context"
    )


class CreateLeadOutput(BaseModel):
    """Output payload confirming lead registration."""

    model_config = ConfigDict(frozen=True)

    lead_id: str
    created_at: datetime.datetime


class AgentTools:
    """Application service providing typed tool implementations for the voice agent.

    Enforces validation, deterministic business policy invocation, structured telemetry,
    and event publishing across all agent actions.
    """

    def __init__(
        self,
        property_repo: IPropertyRepository,
        showing_repo: IShowingRepository,
        booking_repo: IBookingRepository,
        lead_repo: ILeadRepository,
        booking_policy: BookingPolicyService,
        event_publisher: IEventPublisher | None = None,
        clock: Clock | None = None,
        context: ConversationContext | None = None,
        metrics_tracker: WorkflowMetricsTracker | None = None,
    ) -> None:
        self._property_repo = property_repo
        self._showing_repo = showing_repo
        self._booking_repo = booking_repo
        self._lead_repo = lead_repo
        self._booking_policy = booking_policy
        self._publisher = event_publisher
        self._clock = clock if clock is not None else SystemClock()
        self._context = context
        self._metrics = metrics_tracker or WorkflowMetricsTracker()

    @property
    def metrics(self) -> WorkflowMetricsTracker:
        return self._metrics

    @property
    def context(self) -> ConversationContext | None:
        return self._context

    def set_context(self, context: ConversationContext | None) -> None:
        self._context = context

    async def _handle_injected_failure(
        self,
        tool_name: str,
        start_time: float,
        correlation_id: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> ToolResult[Any] | None:
        """Check if synthetic tool failure injection is active, emit failure event, and return error envelope."""
        if should_inject_failure(FailureMode.TOOL):
            duration_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_event(
                EventType.AGENT_TOOL_FAILED.value,
                payload={"error": f"Injected synthetic tool execution failure for {tool_name}"},
                tool_name=tool_name,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
            return ToolResult(
                success=False,
                error_code="TOOL_ERROR",
                message=f"Injected synthetic tool execution failure for {tool_name}",
            )
        return None

    async def _emit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        tool_name: str | None = None,
        duration_ms: float | None = None,
        correlation_id: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> None:
        if event_type == EventType.AGENT_TOOL_COMPLETED.value:
            if tool_name:
                self._metrics.record_tool_call(
                    tool_name=tool_name,
                    duration_ms=duration_ms or 0.0,
                    success=True,
                    arguments=payload,
                )
        elif event_type == EventType.AGENT_TOOL_FAILED.value:
            if tool_name:
                self._metrics.record_tool_call(
                    tool_name=tool_name,
                    duration_ms=duration_ms or 0.0,
                    success=False,
                    arguments=payload,
                )
        elif event_type == EventType.BOOKING_CONFIRMATION_REQUESTED.value:
            self._metrics.record_confirmation_requested()
        elif event_type == EventType.BOOKING_CONFIRMATION_ACCEPTED.value:
            self._metrics.record_confirmation_accepted()
        elif event_type == EventType.BOOKING_CONFIRMATION_DECLINED.value:
            self._metrics.record_confirmation_declined()
        elif event_type in (
            EventType.SHOWING_BOOKED.value,
            EventType.SHOWING_RESCHEDULED.value,
            EventType.SHOWING_CANCELLED.value,
        ):
            self._metrics.record_action_success()
            if event_type == EventType.SHOWING_BOOKED.value:
                self._metrics.complete_workflow()
        elif event_type == EventType.SHOWING_BOOKING_REJECTED.value:
            self._metrics.record_action_rejected()

        if not self._publisher:
            return

        effective_session = session_id or (self._context.session_id if self._context else None)
        effective_workflow = self._context.workflow_id if self._context else None
        effective_turn = turn_id or (str(self._context.current_turn) if self._context else None)

        event = DomainEvent(
            event_type=event_type,
            timestamp=self._clock.now(),
            correlation_id=correlation_id,
            session_id=effective_session,
            workflow_id=effective_workflow,
            turn_id=effective_turn,
            tool_name=tool_name,
            duration_ms=duration_ms,
            payload=payload,
        )
        await self._publisher.publish(event)

    async def search_properties(
        self,
        params: SearchPropertiesInput,
        correlation_id: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> ToolResult[SearchPropertiesOutput]:
        """Search available property listings matching criteria."""
        start_time = time.perf_counter()
        tool_name = "search_properties"

        await self._emit_event(
            EventType.AGENT_TOOL_STARTED.value,
            payload={"params": params.model_dump(mode="json")},
            tool_name=tool_name,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        if injected := await self._handle_injected_failure(
            tool_name, start_time, correlation_id, session_id, turn_id
        ):
            return injected

        try:
            properties = await self._property_repo.search(
                neighborhood=params.location,
                max_rent=params.max_rent,
                bedrooms=params.bedrooms,
                pets_allowed=params.pets_allowed,
            )

            summaries = [
                PropertySummary(
                    property_id=p.property_id,
                    title=p.title,
                    address=p.address,
                    city=p.city,
                    neighborhood=p.neighborhood,
                    monthly_rent=p.monthly_rent,
                    bedrooms=p.bedrooms,
                    bathrooms=p.bathrooms,
                    square_feet=p.square_feet,
                    pets_allowed=p.pets_allowed,
                )
                for p in properties
            ]

            if self._context is not None:
                self._context.record_search(
                    criteria=params.model_dump(mode="json"),
                    results=summaries,
                )

            duration_ms = (time.perf_counter() - start_time) * 1000

            await self._emit_event(
                EventType.PROPERTY_SEARCH_COMPLETED.value,
                payload={
                    "query": params.model_dump(mode="json"),
                    "matched_count": len(summaries),
                    "matched_ids": [s.property_id for s in summaries],
                },
                tool_name=tool_name,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )

            await self._emit_event(
                EventType.AGENT_TOOL_COMPLETED.value,
                payload={"matched_count": len(summaries)},
                tool_name=tool_name,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )

            return ToolResult(
                success=True,
                data=SearchPropertiesOutput(total_count=len(summaries), properties=summaries),
                message=f"Found {len(summaries)} matching properties.",
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_event(
                EventType.AGENT_TOOL_FAILED.value,
                payload={"error": str(e)},
                tool_name=tool_name,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
            return ToolResult(
                success=False,
                error_code="SEARCH_ERROR",
                message=f"Failed to execute property search: {e}",
            )

    async def get_property_details(
        self,
        params: GetPropertyDetailsInput,
        correlation_id: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> ToolResult[GetPropertyDetailsOutput]:
        """Fetch authoritative full details for a specific property."""
        start_time = time.perf_counter()
        tool_name = "get_property_details"

        await self._emit_event(
            EventType.AGENT_TOOL_STARTED.value,
            payload={"property_id": params.property_id},
            tool_name=tool_name,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        if injected := await self._handle_injected_failure(
            tool_name, start_time, correlation_id, session_id, turn_id
        ):
            return injected

        target_id = params.property_id
        if self._context is not None:
            resolved = self._context.resolve_property_reference(target_id)
            if resolved:
                target_id = resolved.property_id
            elif (not target_id or not target_id.strip()) and self._context.selected_property:
                target_id = self._context.selected_property.property_id

        property_obj = await self._property_repo.get_by_id(target_id)
        duration_ms = (time.perf_counter() - start_time) * 1000

        if not property_obj:
            await self._emit_event(
                EventType.AGENT_TOOL_FAILED.value,
                payload={"property_id": params.property_id, "error": "PROPERTY_NOT_FOUND"},
                tool_name=tool_name,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
            msg = (
                "Please search for properties first or specify a valid property name."
                if (self._context and not self._context.shortlisted_properties)
                else f"Property with ID '{params.property_id}' was not found in catalog."
            )
            return ToolResult(
                success=False,
                error_code="PROPERTY_NOT_FOUND",
                message=msg,
            )

        if self._context is not None:
            self._context.select_property(property_obj)

        await self._emit_event(
            EventType.PROPERTY_DETAILS_VIEWED.value,
            payload={"property_id": property_obj.property_id, "title": property_obj.title},
            tool_name=tool_name,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        await self._emit_event(
            EventType.AGENT_TOOL_COMPLETED.value,
            payload={"property_id": property_obj.property_id},
            tool_name=tool_name,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        return ToolResult(
            success=True,
            data=GetPropertyDetailsOutput(property=property_obj),
            message=f"Retrieved details for '{property_obj.title}'.",
        )

    async def get_available_showings(
        self,
        params: GetAvailableShowingsInput,
        correlation_id: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> ToolResult[GetAvailableShowingsOutput]:
        """Fetch available showing calendar windows for a property."""
        start_time = time.perf_counter()
        tool_name = "get_available_showings"

        target_property_id = params.property_id
        if self._context is not None:
            if not target_property_id or not target_property_id.strip():
                if self._context.selected_property:
                    target_property_id = self._context.selected_property.property_id
            else:
                resolved = self._context.resolve_property_reference(target_property_id)
                if resolved:
                    target_property_id = resolved.property_id

        await self._emit_event(
            EventType.AGENT_TOOL_STARTED.value,
            payload={
                "property_id": target_property_id,
                "date": params.date.isoformat() if params.date else None,
            },
            tool_name=tool_name,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        if injected := await self._handle_injected_failure(
            tool_name, start_time, correlation_id, session_id, turn_id
        ):
            return injected

        # Check property exists
        property_obj = await self._property_repo.get_by_id(target_property_id)
        if not property_obj:
            duration_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_event(
                EventType.AGENT_TOOL_FAILED.value,
                payload={"property_id": target_property_id, "error": "PROPERTY_NOT_FOUND"},
                tool_name=tool_name,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
            return ToolResult(
                success=False,
                error_code="PROPERTY_NOT_FOUND",
                message=f"Property '{target_property_id}' was not found in catalog.",
            )

        slots = await self._showing_repo.list_by_property(
            property_id=target_property_id,
            for_date=params.date,
            available_only=True,
        )

        # Filter out slots in the past relative to clock
        current_date = self._clock.today()
        future_available_slots = [s for s in slots if s.date >= current_date]

        slot_summaries = [
            ShowingSlotSummary(
                slot_id=s.slot_id,
                property_id=s.property_id,
                date=s.date,
                start_time=s.start_time,
                end_time=s.end_time,
                status=s.status,
            )
            for s in future_available_slots
        ]

        if self._context is not None:
            self._context.record_available_showings(params.date, slot_summaries)

        duration_ms = (time.perf_counter() - start_time) * 1000

        await self._emit_event(
            EventType.SHOWING_AVAILABILITY_CHECKED.value,
            payload={
                "property_id": target_property_id,
                "requested_date": params.date.isoformat() if params.date else None,
                "available_slots_count": len(slot_summaries),
                "slot_ids": [s.slot_id for s in slot_summaries],
            },
            tool_name=tool_name,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        await self._emit_event(
            EventType.AGENT_TOOL_COMPLETED.value,
            payload={"available_slots_count": len(slot_summaries)},
            tool_name=tool_name,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        return ToolResult(
            success=True,
            data=GetAvailableShowingsOutput(
                property_id=target_property_id,
                total_available=len(slot_summaries),
                slots=slot_summaries,
            ),
            message=f"Found {len(slot_summaries)} available showing slots.",
        )

    async def book_showing(
        self,
        params: BookShowingInput,
        correlation_id: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> ToolResult[BookShowingOutput]:
        """Book a showing slot subject to deterministic policy validation."""
        start_time = time.perf_counter()
        tool_name = "book_showing"

        if injected := await self._handle_injected_failure(
            tool_name, start_time, correlation_id, session_id, turn_id
        ):
            return injected

        property_id = params.property_id
        slot_id = params.slot_id
        renter_name = params.renter_name

        if self._context is not None:
            if (not property_id or not property_id.strip()) and self._context.selected_property:
                property_id = self._context.selected_property.property_id
            resolved_p = self._context.resolve_property_reference(property_id)
            if resolved_p:
                property_id = resolved_p.property_id

            resolved_s = self._context.resolve_slot_reference(slot_id)
            if resolved_s:
                slot_id = resolved_s.slot_id

            if (
                not renter_name or not renter_name.strip()
            ) and "name" in self._context.renter_information:
                renter_name = self._context.renter_information["name"]

        # 1. Action Confirmation Policy Gate:
        # If context is active and confirmed is False, stage proposal and require confirmation!
        if self._context is not None and not params.confirmed:
            clean_name = renter_name.strip() if renter_name else ""
            if not clean_name:
                return ToolResult(
                    success=False,
                    error_code="MISSING_RENTER_NAME",
                    message="A renter name is required to book a showing. Could you please provide your full name?",
                )

            prop = await self._property_repo.get_by_id(property_id)
            if not prop:
                return ToolResult(
                    success=False,
                    error_code="PROPERTY_NOT_FOUND",
                    message=f"Property '{property_id}' was not found in catalog.",
                )

            slot = await self._showing_repo.get_slot(slot_id)
            if not slot:
                return ToolResult(
                    success=False,
                    error_code="SLOT_NOT_FOUND",
                    message=f"Showing slot '{slot_id}' was not found.",
                )

            if slot.status != ShowingSlotStatus.AVAILABLE:
                existing_booking = await self._booking_repo.get_by_slot_id(slot.slot_id)
                if (
                    existing_booking
                    and existing_booking.renter_name.strip().lower() == clean_name.lower()
                    and existing_booking.status != BookingStatus.CANCELLED
                ):
                    time_str = slot.start_time.strftime("%I:%M %p").lstrip("0")
                    date_str = slot.date.strftime("%A, %B %d")
                    return ToolResult(
                        success=True,
                        data=BookShowingOutput(
                            booking=existing_booking,
                            is_idempotent=True,
                        ),
                        message=(
                            f"You already have a confirmed reservation for {prop.title} "
                            f"on {date_str} at {time_str}."
                        ),
                    )

                duration_ms = (time.perf_counter() - start_time) * 1000
                await self._emit_event(
                    EventType.SHOWING_BOOKING_REJECTED.value,
                    payload={
                        "property_id": property_id,
                        "slot_id": slot_id,
                        "renter_name": clean_name,
                        "error_code": "SLOT_UNAVAILABLE",
                        "reason": f"Showing slot '{slot_id}' is no longer available.",
                    },
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    turn_id=turn_id,
                )
                await self._emit_event(
                    EventType.AGENT_TOOL_FAILED.value,
                    payload={
                        "error_code": "SLOT_UNAVAILABLE",
                        "reason": f"Showing slot '{slot_id}' is no longer available.",
                    },
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    turn_id=turn_id,
                )
                if self._context is not None:
                    self._context.set_workflow_state(WorkflowState.BOOKING_FAILED)
                return ToolResult(
                    success=False,
                    error_code="SLOT_UNAVAILABLE",
                    message=f"Showing slot '{slot_id}' is no longer available.",
                )

            if (
                slot.date < self._clock.today()
                or (params.expected_date and params.expected_date < self._clock.today())
            ):
                return ToolResult(
                    success=False,
                    error_code="DATE_IN_PAST",
                    message="Showing date is in the past.",
                )

            date_str = slot.date.strftime("%A, %B %d")
            time_str = slot.start_time.strftime("%I:%M %p").lstrip("0")
            proposal_summary = f"I have {prop.title} on {date_str} at {time_str} for {clean_name}. Should I book that for you?"

            pending_action = PendingAction(
                action_type=ActionType.BOOK_SHOWING,
                property_id=prop.property_id,
                property_title=prop.title,
                slot_id=slot.slot_id,
                slot_time_str=f"{date_str} at {time_str}",
                renter_name=clean_name,
                renter_phone=params.renter_phone,
                renter_email=params.renter_email,
                expected_date=slot.date,
                summary=proposal_summary,
                created_turn=self._context.current_turn,
                expires_after_turns=2,
            )
            self._context.stage_pending_action(pending_action)
            self._context.set_renter_info(
                name=clean_name,
                phone=params.renter_phone,
                email=params.renter_email,
            )

            await self._emit_event(
                EventType.BOOKING_CONFIRMATION_REQUESTED.value,
                payload={
                    "property_id": prop.property_id,
                    "property_title": prop.title,
                    "slot_id": slot.slot_id,
                    "date": slot.date.isoformat(),
                    "time": time_str,
                    "renter_name": clean_name,
                    "summary": proposal_summary,
                },
                tool_name=tool_name,
                duration_ms=(time.perf_counter() - start_time) * 1000,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )

            return ToolResult(
                success=True,
                data=BookShowingOutput(
                    booking=Booking(
                        booking_id="pending-confirmation",
                        slot_id=slot.slot_id,
                        property_id=prop.property_id,
                        renter_name=clean_name,
                        renter_phone=params.renter_phone,
                        renter_email=params.renter_email,
                        created_at=self._clock.now(),
                        status=BookingStatus.PENDING,
                        idempotency_key="pending",
                    ),
                    is_idempotent=False,
                ),
                message=proposal_summary,
            )

        # 2. If confirmed is True: verify pending action
        if self._context is not None and params.confirmed:
            pending = self._context.confirm_pending_action()
            if not pending or pending.action_type != ActionType.BOOK_SHOWING:
                return ToolResult(
                    success=False,
                    error_code="NO_PENDING_ACTION",
                    message="There is no active pending booking proposal to confirm.",
                )
            property_id = pending.property_id or property_id
            slot_id = pending.slot_id or slot_id
            renter_name = pending.renter_name or renter_name
            phone = pending.renter_phone or params.renter_phone
            email = pending.renter_email or params.renter_email
            expected_date = pending.expected_date or params.expected_date

            await self._emit_event(
                EventType.BOOKING_CONFIRMATION_ACCEPTED.value,
                payload={
                    "property_id": property_id,
                    "slot_id": slot_id,
                    "renter_name": renter_name,
                },
                tool_name=tool_name,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
        else:
            phone = params.renter_phone
            email = params.renter_email
            expected_date = params.expected_date

        # 3. Emit tool started & booking requested
        await self._emit_event(
            EventType.AGENT_TOOL_STARTED.value,
            payload={
                "property_id": property_id,
                "slot_id": slot_id,
                "renter_name": renter_name,
            },
            tool_name=tool_name,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        await self._emit_event(
            EventType.SHOWING_BOOKING_REQUESTED.value,
            payload={
                "property_id": property_id,
                "slot_id": slot_id,
                "renter_name": renter_name,
                "expected_date": expected_date.isoformat() if expected_date else None,
            },
            tool_name=tool_name,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        # 4. Invoke deterministic booking policy service
        booking_request = BookingRequest(
            property_id=property_id,
            slot_id=slot_id,
            renter_name=renter_name,
            renter_phone=phone,
            renter_email=email,
            expected_date=expected_date,
        )
        policy_res = await self._booking_policy.validate_and_reserve(booking_request)

        duration_ms = (time.perf_counter() - start_time) * 1000

        # 5. Handle Rejection
        if not policy_res.success or not policy_res.booking:
            error_code = policy_res.error_code.value if policy_res.error_code else "POLICY_REJECTED"
            await self._emit_event(
                EventType.SHOWING_BOOKING_REJECTED.value,
                payload={
                    "property_id": property_id,
                    "slot_id": slot_id,
                    "renter_name": renter_name,
                    "error_code": error_code,
                    "reason": policy_res.error_message,
                },
                tool_name=tool_name,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
            await self._emit_event(
                EventType.AGENT_TOOL_FAILED.value,
                payload={"error_code": error_code, "reason": policy_res.error_message},
                tool_name=tool_name,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
            return ToolResult(
                success=False,
                error_code=error_code,
                message=policy_res.error_message
                or "Booking request was rejected by business policy.",
            )

        # 6. Handle Acceptance (Emitted ONLY AFTER state mutation succeeded inside policy)
        await self._emit_event(
            EventType.SHOWING_BOOKED.value,
            payload={
                "booking_id": policy_res.booking.booking_id,
                "property_id": policy_res.booking.property_id,
                "slot_id": policy_res.booking.slot_id,
                "renter_name": policy_res.booking.renter_name,
                "is_idempotent": policy_res.is_idempotent,
            },
            tool_name=tool_name,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        await self._emit_event(
            EventType.AGENT_TOOL_COMPLETED.value,
            payload={
                "booking_id": policy_res.booking.booking_id,
                "is_idempotent": policy_res.is_idempotent,
            },
            tool_name=tool_name,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        if self._context is not None:
            self._context.active_booking = policy_res.booking
            self._context.set_workflow_state(WorkflowState.BOOKED)

        msg = (
            "Showing reservation previously confirmed (idempotent result)."
            if policy_res.is_idempotent
            else "Showing reservation successfully confirmed."
        )
        return ToolResult(
            success=True,
            data=BookShowingOutput(
                booking=policy_res.booking,
                is_idempotent=policy_res.is_idempotent,
            ),
            message=msg,
        )

    async def reschedule_showing(
        self,
        params: RescheduleShowingInput,
        correlation_id: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> ToolResult[RescheduleShowingOutput]:
        """Reschedule an existing showing reservation to a new calendar slot."""
        start_time = time.perf_counter()
        tool_name = "reschedule_showing"

        await self._emit_event(
            EventType.AGENT_TOOL_STARTED.value,
            payload=params.model_dump(mode="json"),
            tool_name=tool_name,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        if injected := await self._handle_injected_failure(
            tool_name, start_time, correlation_id, session_id, turn_id
        ):
            return injected

        target_new_slot_id = params.new_slot_id
        if self._context is not None:
            resolved_s = self._context.resolve_slot_reference(target_new_slot_id)
            if resolved_s:
                target_new_slot_id = resolved_s.slot_id

        # Confirmation Policy Gate for Rescheduling
        if self._context is not None and not params.confirmed:
            booking = await self._booking_repo.get_by_id(params.booking_id)
            if not booking:
                return ToolResult(
                    success=False,
                    error_code="BOOKING_NOT_FOUND",
                    message=f"Booking '{params.booking_id}' was not found.",
                )
            if booking.status == BookingStatus.CANCELLED:
                return ToolResult(
                    success=False,
                    error_code="BOOKING_ALREADY_CANCELLED",
                    message=f"Booking '{params.booking_id}' has already been cancelled.",
                )
            if booking.renter_name.strip().lower() != params.renter_name.strip().lower():
                return ToolResult(
                    success=False,
                    error_code="RENTER_MISMATCH",
                    message="Renter name does not match the reservation record.",
                )

            new_slot = await self._showing_repo.get_slot(target_new_slot_id)
            if not new_slot:
                return ToolResult(
                    success=False,
                    error_code="SLOT_NOT_FOUND",
                    message=f"Target showing slot '{target_new_slot_id}' was not found.",
                )
            if new_slot.status != ShowingSlotStatus.AVAILABLE:
                return ToolResult(
                    success=False,
                    error_code="SLOT_UNAVAILABLE",
                    message=f"Target showing slot '{target_new_slot_id}' is not available.",
                )

            time_str = new_slot.start_time.strftime("%I:%M %p").lstrip("0")
            date_str = new_slot.date.strftime("%A, %B %d")
            summary = (
                f"I have your reservation {booking.booking_id}. "
                f"Should I reschedule it to {date_str} at {time_str}?"
            )

            pending = PendingAction(
                action_type=ActionType.RESCHEDULE_SHOWING,
                booking_id=booking.booking_id,
                property_id=booking.property_id,
                slot_id=new_slot.slot_id,
                slot_time_str=f"{date_str} at {time_str}",
                renter_name=params.renter_name,
                expected_date=new_slot.date,
                summary=summary,
                created_turn=self._context.current_turn,
                expires_after_turns=2,
            )
            self._context.stage_pending_action(pending)

            await self._emit_event(
                EventType.SHOWING_RESCHEDULE_REQUESTED.value,
                payload={
                    "booking_id": booking.booking_id,
                    "new_slot_id": new_slot.slot_id,
                    "date": new_slot.date.isoformat(),
                    "time": time_str,
                    "renter_name": params.renter_name,
                    "summary": summary,
                },
                tool_name=tool_name,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )

            return ToolResult(
                success=True,
                data=RescheduleShowingOutput(booking=booking),
                message=summary,
            )

        if self._context is not None and params.confirmed:
            pending_resched = self._context.confirm_pending_action()
            if not pending_resched or pending_resched.action_type != ActionType.RESCHEDULE_SHOWING:
                return ToolResult(
                    success=False,
                    error_code="NO_PENDING_ACTION",
                    message="There is no active pending reschedule proposal to confirm.",
                )
            target_booking_id = pending_resched.booking_id or params.booking_id
            target_new_slot_id = pending_resched.slot_id or target_new_slot_id
            renter_name = pending_resched.renter_name or params.renter_name
            expected_date = pending_resched.expected_date or params.expected_date

            await self._emit_event(
                EventType.BOOKING_CONFIRMATION_ACCEPTED.value,
                payload={"booking_id": target_booking_id, "new_slot_id": target_new_slot_id},
                tool_name=tool_name,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
        else:
            target_booking_id = params.booking_id
            renter_name = params.renter_name
            expected_date = params.expected_date

        resched_req = RescheduleRequest(
            booking_id=target_booking_id,
            new_slot_id=target_new_slot_id,
            renter_name=renter_name,
            expected_date=expected_date,
        )
        policy_res = await self._booking_policy.validate_and_reschedule(resched_req)
        duration_ms = (time.perf_counter() - start_time) * 1000

        if not policy_res.success or not policy_res.booking:
            err_code = policy_res.error_code.value if policy_res.error_code else "POLICY_REJECTED"
            await self._emit_event(
                EventType.AGENT_TOOL_FAILED.value,
                payload={"error_code": err_code, "reason": policy_res.error_message},
                tool_name=tool_name,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
            return ToolResult(
                success=False,
                error_code=err_code,
                message=policy_res.error_message
                or "Reschedule request was rejected by business policy.",
            )

        await self._emit_event(
            EventType.SHOWING_RESCHEDULED.value,
            payload={
                "booking_id": policy_res.booking.booking_id,
                "new_slot_id": policy_res.booking.slot_id,
                "renter_name": policy_res.booking.renter_name,
            },
            tool_name=tool_name,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        await self._emit_event(
            EventType.AGENT_TOOL_COMPLETED.value,
            payload={"booking_id": policy_res.booking.booking_id},
            tool_name=tool_name,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        if self._context is not None:
            self._context.active_booking = policy_res.booking
            self._context.set_workflow_state(WorkflowState.BOOKED)

        return ToolResult(
            success=True,
            data=RescheduleShowingOutput(booking=policy_res.booking),
            message="Showing successfully rescheduled.",
        )

    async def cancel_showing(
        self,
        params: CancelShowingInput,
        correlation_id: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> ToolResult[CancelShowingOutput]:
        """Cancel an existing showing reservation and release the calendar slot."""
        start_time = time.perf_counter()
        tool_name = "cancel_showing"

        await self._emit_event(
            EventType.AGENT_TOOL_STARTED.value,
            payload=params.model_dump(mode="json"),
            tool_name=tool_name,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        if injected := await self._handle_injected_failure(
            tool_name, start_time, correlation_id, session_id, turn_id
        ):
            return injected

        # Confirmation Policy Gate for Cancellation
        if self._context is not None and not params.confirmed:
            booking = await self._booking_repo.get_by_id(params.booking_id)
            if not booking:
                return ToolResult(
                    success=False,
                    error_code="BOOKING_NOT_FOUND",
                    message=f"Booking '{params.booking_id}' was not found.",
                )
            if booking.status == BookingStatus.CANCELLED:
                return ToolResult(
                    success=False,
                    error_code="BOOKING_ALREADY_CANCELLED",
                    message=f"Booking '{params.booking_id}' has already been cancelled.",
                )
            if booking.renter_name.strip().lower() != params.renter_name.strip().lower():
                return ToolResult(
                    success=False,
                    error_code="RENTER_MISMATCH",
                    message="Renter name does not match the reservation record.",
                )

            summary = f"Are you sure you want to cancel your showing for reservation {booking.booking_id}?"
            pending = PendingAction(
                action_type=ActionType.CANCEL_SHOWING,
                booking_id=booking.booking_id,
                property_id=booking.property_id,
                slot_id=booking.slot_id,
                renter_name=params.renter_name,
                summary=summary,
                created_turn=self._context.current_turn,
                expires_after_turns=2,
                metadata={"reason": params.reason},
            )
            self._context.stage_pending_action(pending)

            await self._emit_event(
                EventType.SHOWING_CANCELLATION_REQUESTED.value,
                payload={
                    "booking_id": booking.booking_id,
                    "renter_name": params.renter_name,
                    "reason": params.reason,
                    "summary": summary,
                },
                tool_name=tool_name,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )

            return ToolResult(
                success=True,
                data=CancelShowingOutput(booking=booking),
                message=summary,
            )

        if self._context is not None and params.confirmed:
            pending_cancel = self._context.confirm_pending_action()
            if not pending_cancel or pending_cancel.action_type != ActionType.CANCEL_SHOWING:
                return ToolResult(
                    success=False,
                    error_code="NO_PENDING_ACTION",
                    message="There is no active pending cancellation to confirm.",
                )
            target_booking_id = pending_cancel.booking_id or params.booking_id
            renter_name = pending_cancel.renter_name or params.renter_name
            reason = pending_cancel.metadata.get("reason") or params.reason

            await self._emit_event(
                EventType.BOOKING_CONFIRMATION_ACCEPTED.value,
                payload={"booking_id": target_booking_id},
                tool_name=tool_name,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
        else:
            target_booking_id = params.booking_id
            renter_name = params.renter_name
            reason = params.reason

        cancel_req = CancellationRequest(
            booking_id=target_booking_id,
            renter_name=renter_name,
            reason=reason,
        )
        policy_res = await self._booking_policy.validate_and_cancel(cancel_req)
        duration_ms = (time.perf_counter() - start_time) * 1000

        if not policy_res.success or not policy_res.booking:
            err_code = policy_res.error_code.value if policy_res.error_code else "POLICY_REJECTED"
            await self._emit_event(
                EventType.AGENT_TOOL_FAILED.value,
                payload={"error_code": err_code, "reason": policy_res.error_message},
                tool_name=tool_name,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
            return ToolResult(
                success=False,
                error_code=err_code,
                message=policy_res.error_message
                or "Cancellation request was rejected by business policy.",
            )

        await self._emit_event(
            EventType.SHOWING_CANCELLED.value,
            payload={
                "booking_id": policy_res.booking.booking_id,
                "slot_id": policy_res.booking.slot_id,
                "renter_name": policy_res.booking.renter_name,
                "reason": reason,
            },
            tool_name=tool_name,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        await self._emit_event(
            EventType.AGENT_TOOL_COMPLETED.value,
            payload={"booking_id": policy_res.booking.booking_id},
            tool_name=tool_name,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        if self._context is not None:
            self._context.active_booking = policy_res.booking
            self._context.set_workflow_state(WorkflowState.IDLE)

        return ToolResult(
            success=True,
            data=CancelShowingOutput(booking=policy_res.booking),
            message="Showing successfully cancelled.",
        )

    async def confirm_pending_action(
        self,
        correlation_id: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> ToolResult[Any]:
        """User confirms the active pending proposal (booking, reschedule, or cancel)."""
        if not self._context or not self._context.pending_action:
            return ToolResult(
                success=False,
                error_code="NO_PENDING_ACTION",
                message="There is no pending action to confirm.",
            )
        pending = self._context.pending_action
        if pending.action_type == ActionType.BOOK_SHOWING:
            return await self.book_showing(
                BookShowingInput(
                    property_id=pending.property_id or "",
                    slot_id=pending.slot_id or "",
                    renter_name=pending.renter_name or "",
                    renter_phone=pending.renter_phone,
                    renter_email=pending.renter_email,
                    expected_date=pending.expected_date,
                    confirmed=True,
                ),
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
        elif pending.action_type == ActionType.RESCHEDULE_SHOWING:
            return await self.reschedule_showing(
                RescheduleShowingInput(
                    booking_id=pending.booking_id or "",
                    new_slot_id=pending.slot_id or "",
                    renter_name=pending.renter_name or "",
                    expected_date=pending.expected_date,
                    confirmed=True,
                ),
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
        elif pending.action_type == ActionType.CANCEL_SHOWING:
            return await self.cancel_showing(
                CancelShowingInput(
                    booking_id=pending.booking_id or "",
                    renter_name=pending.renter_name or "",
                    reason=pending.metadata.get("reason"),
                    confirmed=True,
                ),
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
        return ToolResult(
            success=False,
            error_code="UNKNOWN_ACTION",
            message="Unknown pending action type.",
        )

    async def cancel_pending_action(
        self,
        reason: str | None = None,
        correlation_id: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> ToolResult[dict[str, str]]:
        """User rejects, declines, or cancels the active pending proposal."""
        if not self._context or not self._context.pending_action:
            return ToolResult(
                success=True,
                data={"status": "no_pending_action"},
                message="No pending action was active.",
            )
        cancelled = self._context.cancel_pending_action()
        await self._emit_event(
            EventType.BOOKING_CONFIRMATION_DECLINED.value,
            payload={
                "action_type": cancelled.action_type.value if cancelled else "unknown",
                "reason": reason,
            },
            tool_name="cancel_pending_action",
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )
        return ToolResult(
            success=True,
            data={"status": "cancelled"},
            message="The pending request has been cancelled. What would you like to do instead?",
        )

    async def create_lead(
        self,
        params: CreateLeadInput,
        correlation_id: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> ToolResult[CreateLeadOutput]:
        """Capture prospective renter inquiry or follow-up lead."""
        start_time = time.perf_counter()
        tool_name = "create_lead"

        await self._emit_event(
            EventType.AGENT_TOOL_STARTED.value,
            payload={"name": params.name},
            tool_name=tool_name,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        clean_name = params.name.strip()
        if not clean_name:
            duration_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_event(
                EventType.AGENT_TOOL_FAILED.value,
                payload={"error": "MISSING_LEAD_NAME"},
                tool_name=tool_name,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                session_id=session_id,
                turn_id=turn_id,
            )
            return ToolResult(
                success=False,
                error_code="MISSING_LEAD_NAME",
                message="Lead name cannot be empty.",
            )

        lead_id = f"lead-{uuid.uuid4().hex[:10]}"
        now = self._clock.now()

        lead = Lead(
            lead_id=lead_id,
            name=clean_name,
            phone=params.phone.strip() if params.phone else None,
            email=params.email.strip() if params.email else None,
            preferred_neighborhood=(
                params.preferred_neighborhood.strip() if params.preferred_neighborhood else None
            ),
            budget=params.budget,
            interested_property_id=(
                params.interested_property_id.strip() if params.interested_property_id else None
            ),
            notes=params.notes.strip() if params.notes else None,
            created_at=now,
        )

        await self._lead_repo.add(lead)

        duration_ms = (time.perf_counter() - start_time) * 1000

        await self._emit_event(
            EventType.LEAD_CREATED.value,
            payload={
                "lead_id": lead.lead_id,
                "name": lead.name,
                "has_phone": lead.phone is not None,
                "has_email": lead.email is not None,
                "interested_property_id": lead.interested_property_id,
            },
            tool_name=tool_name,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        await self._emit_event(
            EventType.AGENT_TOOL_COMPLETED.value,
            payload={"lead_id": lead.lead_id},
            tool_name=tool_name,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            session_id=session_id,
            turn_id=turn_id,
        )

        return ToolResult(
            success=True,
            data=CreateLeadOutput(lead_id=lead.lead_id, created_at=lead.created_at),
            message=f"Lead recorded successfully with ID '{lead.lead_id}'.",
        )
