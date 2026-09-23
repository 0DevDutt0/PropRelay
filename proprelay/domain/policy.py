"""Deterministic business policy engine for showings and reservations."""

from __future__ import annotations

import datetime
import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from proprelay.domain.clock import Clock, SystemClock
from proprelay.domain.models import (
    Booking,
    BookingStatus,
    ShowingSlotStatus,
    compute_booking_idempotency_key,
)
from proprelay.domain.repositories import (
    IBookingRepository,
    IPropertyRepository,
    IShowingRepository,
)


class PolicyErrorCode(StrEnum):
    """Machine-readable, typed error codes for policy validation failures."""

    PROPERTY_NOT_FOUND = "PROPERTY_NOT_FOUND"
    SHOWINGS_NOT_SUPPORTED = "SHOWINGS_NOT_SUPPORTED"
    INVALID_DATE = "INVALID_DATE"
    DATE_IN_PAST = "DATE_IN_PAST"
    SLOT_NOT_FOUND = "SLOT_NOT_FOUND"
    SLOT_PROPERTY_MISMATCH = "SLOT_PROPERTY_MISMATCH"
    SLOT_UNAVAILABLE = "SLOT_UNAVAILABLE"
    MISSING_RENTER_NAME = "MISSING_RENTER_NAME"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    BOOKING_CONFLICT = "BOOKING_CONFLICT"
    BOOKING_NOT_FOUND = "BOOKING_NOT_FOUND"
    BOOKING_ALREADY_CANCELLED = "BOOKING_ALREADY_CANCELLED"
    RENTER_MISMATCH = "RENTER_MISMATCH"
    RESCHEDULE_SAME_SLOT = "RESCHEDULE_SAME_SLOT"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    PENDING_ACTION_EXPIRED = "PENDING_ACTION_EXPIRED"
    PENDING_ACTION_MISMATCH = "PENDING_ACTION_MISMATCH"


class BookingRequest(BaseModel):
    """Payload representing a renter's showing reservation request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    property_id: str = Field(..., description="Target property ID")
    slot_id: str = Field(..., description="Target showing slot ID")
    renter_name: str = Field(..., description="Full legal name of the prospective renter")
    renter_phone: str | None = Field(default=None, description="Contact phone number")
    renter_email: str | None = Field(default=None, description="Contact email address")
    expected_date: datetime.date | None = Field(
        default=None, description="Optional expected date to cross-verify against the slot"
    )


class RescheduleRequest(BaseModel):
    """Payload representing a request to reschedule an existing booking."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    booking_id: str = Field(..., description="Target existing booking ID")
    new_slot_id: str = Field(..., description="Target new showing slot ID")
    renter_name: str = Field(..., description="Renter name for ownership verification")
    expected_date: datetime.date | None = Field(
        default=None, description="Optional expected date to cross-verify against the new slot"
    )


class CancellationRequest(BaseModel):
    """Payload representing a request to cancel an existing booking."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    booking_id: str = Field(..., description="Target existing booking ID")
    renter_name: str = Field(..., description="Renter name for ownership verification")
    reason: str | None = Field(default=None, description="Optional cancellation reason")


class PolicyResult(BaseModel):
    """Deterministic result structure for booking operations."""

    model_config = ConfigDict(frozen=True)

    success: bool = Field(..., description="True if booking succeeded or was idempotently resolved")
    booking: Booking | None = Field(
        default=None, description="Confirmed booking entity if successful"
    )
    error_code: PolicyErrorCode | None = Field(
        default=None, description="Typed policy error code on failure"
    )
    error_message: str | None = Field(
        default=None, description="Human-readable explanation of rejection"
    )
    is_idempotent: bool = Field(
        default=False, description="True if returned existing booking via idempotency"
    )


class BookingPolicyService:
    """Enforces all deterministic business rules for property showings.

    CRITICAL ARCHITECTURAL GUARANTEE:
    The language model never makes reservation or availability decisions.
    All availability validations, past-date rejections, slot ownership checks,
    and race-condition locks are executed exclusively by this service.
    """

    def __init__(
        self,
        property_repo: IPropertyRepository,
        showing_repo: IShowingRepository,
        booking_repo: IBookingRepository,
        clock: Clock | None = None,
    ) -> None:
        self._property_repo = property_repo
        self._showing_repo = showing_repo
        self._booking_repo = booking_repo
        self._clock: Clock = clock if clock is not None else SystemClock()

    async def validate_and_reserve(self, request: BookingRequest) -> PolicyResult:
        """Validate showing booking rules and execute atomic state reservation."""
        # 1. Validate required renter name
        clean_renter_name = request.renter_name.strip() if request.renter_name else ""
        if not clean_renter_name:
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.MISSING_RENTER_NAME,
                error_message="Renter name is required to book a showing.",
            )

        # 2. Check stable idempotency key prior to lock acquisition
        idempotency_key = compute_booking_idempotency_key(
            property_id=request.property_id,
            slot_id=request.slot_id,
            renter_name=clean_renter_name,
        )
        existing_booking = await self._booking_repo.get_by_idempotency_key(idempotency_key)
        if existing_booking:
            return PolicyResult(
                success=True,
                booking=existing_booking,
                is_idempotent=True,
            )

        # 3. Acquire slot-level concurrency lock for atomic check-and-reserve
        async with self._booking_repo.acquire_slot_lock(request.slot_id):
            # Double-check idempotency inside lock
            existing_booking = await self._booking_repo.get_by_idempotency_key(idempotency_key)
            if existing_booking:
                return PolicyResult(
                    success=True,
                    booking=existing_booking,
                    is_idempotent=True,
                )

            # Check if slot already has a booking from another renter
            slot_booking = await self._booking_repo.get_by_slot_id(request.slot_id)
            if slot_booking:
                return PolicyResult(
                    success=False,
                    error_code=PolicyErrorCode.SLOT_UNAVAILABLE,
                    error_message=f"Showing slot '{request.slot_id}' is already booked by another renter.",
                )

            # Check: Property exists
            property_obj = await self._property_repo.get_by_id(request.property_id.strip())
            if not property_obj:
                return PolicyResult(
                    success=False,
                    error_code=PolicyErrorCode.PROPERTY_NOT_FOUND,
                    error_message=f"Property '{request.property_id}' was not found in catalog.",
                )

            # Check: Property supports showing requests
            if not property_obj.supports_showings:
                return PolicyResult(
                    success=False,
                    error_code=PolicyErrorCode.SHOWINGS_NOT_SUPPORTED,
                    error_message=f"Property '{request.property_id}' is not accepting showing requests.",
                )

            # Check: Slot exists
            slot = await self._showing_repo.get_slot(request.slot_id.strip())
            if not slot:
                return PolicyResult(
                    success=False,
                    error_code=PolicyErrorCode.SLOT_NOT_FOUND,
                    error_message=f"Showing slot '{request.slot_id}' was not found.",
                )

            # Check: Slot belongs to requested property
            if slot.property_id != property_obj.property_id:
                return PolicyResult(
                    success=False,
                    error_code=PolicyErrorCode.SLOT_PROPERTY_MISMATCH,
                    error_message=(
                        f"Slot '{request.slot_id}' belongs to property '{slot.property_id}', "
                        f"not '{property_obj.property_id}'."
                    ),
                )

            # Check: Expected date match if supplied
            if request.expected_date and slot.date != request.expected_date:
                return PolicyResult(
                    success=False,
                    error_code=PolicyErrorCode.INVALID_DATE,
                    error_message=(
                        f"Requested date '{request.expected_date}' does not match "
                        f"scheduled slot date '{slot.date}'."
                    ),
                )

            # Check: Date is not in the past relative to Clock
            current_date = self._clock.today()
            if slot.date < current_date:
                return PolicyResult(
                    success=False,
                    error_code=PolicyErrorCode.DATE_IN_PAST,
                    error_message=(
                        f"Showing date '{slot.date}' is in the past (current date: '{current_date}')."
                    ),
                )

            # Check: Slot is AVAILABLE
            if slot.status != ShowingSlotStatus.AVAILABLE:
                return PolicyResult(
                    success=False,
                    error_code=PolicyErrorCode.SLOT_UNAVAILABLE,
                    error_message=f"Showing slot '{request.slot_id}' is currently {slot.status.value}.",
                )

            # Execute atomic state mutation
            updated = await self._showing_repo.update_slot_status(
                request.slot_id, ShowingSlotStatus.BOOKED
            )
            if not updated:
                return PolicyResult(
                    success=False,
                    error_code=PolicyErrorCode.BOOKING_CONFLICT,
                    error_message=f"Failed to update showing slot '{request.slot_id}' status.",
                )

            booking_id = f"bk-{uuid.uuid4().hex[:10]}"
            booking = Booking(
                booking_id=booking_id,
                slot_id=slot.slot_id,
                property_id=property_obj.property_id,
                renter_name=clean_renter_name,
                renter_phone=request.renter_phone.strip() if request.renter_phone else None,
                renter_email=request.renter_email.strip() if request.renter_email else None,
                created_at=self._clock.now(),
                status=BookingStatus.CONFIRMED,
                idempotency_key=idempotency_key,
            )
            await self._booking_repo.add(booking)

            return PolicyResult(
                success=True,
                booking=booking,
                is_idempotent=False,
            )

    async def validate_and_reschedule(self, request: RescheduleRequest) -> PolicyResult:
        """Validate showing rescheduling rules and execute atomic slot migration."""
        clean_renter_name = request.renter_name.strip() if request.renter_name else ""
        if not clean_renter_name:
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.MISSING_RENTER_NAME,
                error_message="Renter name is required to reschedule a showing.",
            )

        # 1. Verify booking exists
        booking = await self._booking_repo.get_by_id(request.booking_id.strip())
        if not booking:
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.BOOKING_NOT_FOUND,
                error_message=f"Booking '{request.booking_id}' was not found.",
            )

        # 2. Verify booking is not already cancelled
        if booking.status == BookingStatus.CANCELLED:
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.BOOKING_ALREADY_CANCELLED,
                error_message=f"Booking '{request.booking_id}' has already been cancelled.",
            )

        # 3. Verify renter ownership
        if booking.renter_name.strip().lower() != clean_renter_name.lower():
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.RENTER_MISMATCH,
                error_message="Renter name does not match the reservation record.",
            )

        # 4. Check if rescheduling to same slot
        target_slot_id = request.new_slot_id.strip()
        if booking.slot_id == target_slot_id:
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.RESCHEDULE_SAME_SLOT,
                error_message="Requested new showing slot is the same as current reservation.",
            )

        # 5. Check new slot exists
        new_slot = await self._showing_repo.get_slot(target_slot_id)
        if not new_slot:
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.SLOT_NOT_FOUND,
                error_message=f"Target showing slot '{target_slot_id}' was not found.",
            )

        # 6. Check slot belongs to same property
        if new_slot.property_id != booking.property_id:
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.SLOT_PROPERTY_MISMATCH,
                error_message=(
                    f"New slot '{target_slot_id}' belongs to property '{new_slot.property_id}', "
                    f"not '{booking.property_id}'."
                ),
            )

        # 7. Check date match if provided
        if request.expected_date and new_slot.date != request.expected_date:
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.INVALID_DATE,
                error_message=(
                    f"Requested date '{request.expected_date}' does not match "
                    f"scheduled slot date '{new_slot.date}'."
                ),
            )

        # 8. Check date is not in the past
        current_date = self._clock.today()
        if new_slot.date < current_date:
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.DATE_IN_PAST,
                error_message=(
                    f"Showing date '{new_slot.date}' is in the past (current date: '{current_date}')."
                ),
            )

        # 9. Concurrency lock on both slots in sorted order to prevent deadlock
        slot_ids = sorted([booking.slot_id, target_slot_id])
        async with (
            self._booking_repo.acquire_slot_lock(slot_ids[0]),
            self._booking_repo.acquire_slot_lock(slot_ids[1]),
        ):
            # Verify new slot is still available
            rechecked_slot = await self._showing_repo.get_slot(target_slot_id)
            if not rechecked_slot or rechecked_slot.status != ShowingSlotStatus.AVAILABLE:
                return PolicyResult(
                    success=False,
                    error_code=PolicyErrorCode.SLOT_UNAVAILABLE,
                    error_message=f"Showing slot '{target_slot_id}' is no longer available.",
                )

            # Release old slot
            await self._showing_repo.update_slot_status(
                booking.slot_id, ShowingSlotStatus.AVAILABLE
            )
            # Claim new slot
            await self._showing_repo.update_slot_status(target_slot_id, ShowingSlotStatus.BOOKED)

            # Compute new idempotency key
            new_idempotency_key = compute_booking_idempotency_key(
                property_id=booking.property_id,
                slot_id=target_slot_id,
                renter_name=booking.renter_name,
            )

            updated_booking = booking.model_copy(
                update={
                    "slot_id": target_slot_id,
                    "idempotency_key": new_idempotency_key,
                    "updated_at": self._clock.now(),
                }
            )
            await self._booking_repo.update(updated_booking)

            return PolicyResult(
                success=True,
                booking=updated_booking,
                is_idempotent=False,
            )

    async def validate_and_cancel(self, request: CancellationRequest) -> PolicyResult:
        """Validate showing cancellation rules and release calendar slot."""
        clean_renter_name = request.renter_name.strip() if request.renter_name else ""
        if not clean_renter_name:
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.MISSING_RENTER_NAME,
                error_message="Renter name is required to cancel a showing.",
            )

        # 1. Verify booking exists
        booking = await self._booking_repo.get_by_id(request.booking_id.strip())
        if not booking:
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.BOOKING_NOT_FOUND,
                error_message=f"Booking '{request.booking_id}' was not found.",
            )

        # 2. Check if already cancelled
        if booking.status == BookingStatus.CANCELLED:
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.BOOKING_ALREADY_CANCELLED,
                error_message=f"Booking '{request.booking_id}' has already been cancelled.",
            )

        # 3. Check renter name match
        if booking.renter_name.strip().lower() != clean_renter_name.lower():
            return PolicyResult(
                success=False,
                error_code=PolicyErrorCode.RENTER_MISMATCH,
                error_message="Renter name does not match the reservation record.",
            )

        # 4. Acquire slot lock, release slot, update booking
        async with self._booking_repo.acquire_slot_lock(booking.slot_id):
            await self._showing_repo.update_slot_status(
                booking.slot_id, ShowingSlotStatus.AVAILABLE
            )
            updated_booking = booking.model_copy(
                update={
                    "status": BookingStatus.CANCELLED,
                    "cancellation_reason": request.reason.strip() if request.reason else None,
                    "updated_at": self._clock.now(),
                }
            )
            await self._booking_repo.update(updated_booking)

            return PolicyResult(
                success=True,
                booking=updated_booking,
                is_idempotent=False,
            )
