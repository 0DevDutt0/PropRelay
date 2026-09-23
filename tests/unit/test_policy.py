"""Unit tests verifying deterministic business policy rules for showing bookings."""

from __future__ import annotations

import datetime

import pytest

from proprelay.domain.models import BookingStatus, ShowingSlotStatus
from proprelay.domain.policy import (
    BookingPolicyService,
    BookingRequest,
    PolicyErrorCode,
)
from proprelay.domain.repositories import (
    InMemoryBookingRepository,
    InMemoryShowingRepository,
)


@pytest.mark.asyncio
async def test_policy_valid_booking(
    booking_policy: BookingPolicyService,
    showing_repo: InMemoryShowingRepository,
) -> None:
    """Rule 1: Valid booking request succeeds and transitions slot to BOOKED."""
    req = BookingRequest(
        property_id="test-prop-1",
        slot_id="slot-test-01",
        renter_name="John Doe",
        renter_phone="555-0100",
        renter_email="john@example.com",
    )
    result = await booking_policy.validate_and_reserve(req)

    assert result.success is True
    assert result.booking is not None
    assert result.booking.renter_name == "John Doe"
    assert result.booking.status == BookingStatus.CONFIRMED
    assert result.is_idempotent is False

    # Verify slot status was mutated
    slot = await showing_repo.get_slot("slot-test-01")
    assert slot is not None
    assert slot.status == ShowingSlotStatus.BOOKED


@pytest.mark.asyncio
async def test_policy_property_not_found(
    booking_policy: BookingPolicyService,
) -> None:
    """Rule 2: Non-existent property returns PROPERTY_NOT_FOUND."""
    req = BookingRequest(
        property_id="non-existent-prop",
        slot_id="slot-test-01",
        renter_name="John Doe",
    )
    result = await booking_policy.validate_and_reserve(req)

    assert result.success is False
    assert result.error_code == PolicyErrorCode.PROPERTY_NOT_FOUND
    assert "not found" in (result.error_message or "").lower()


@pytest.mark.asyncio
async def test_policy_showings_not_supported(
    booking_policy: BookingPolicyService,
) -> None:
    """Rule: Property not accepting showings returns SHOWINGS_NOT_SUPPORTED."""
    req = BookingRequest(
        property_id="test-prop-inactive",
        slot_id="slot-test-inactive-01",
        renter_name="John Doe",
    )
    result = await booking_policy.validate_and_reserve(req)

    assert result.success is False
    assert result.error_code == PolicyErrorCode.SHOWINGS_NOT_SUPPORTED


@pytest.mark.asyncio
async def test_policy_slot_not_found(
    booking_policy: BookingPolicyService,
) -> None:
    """Rule 3: Non-existent slot returns SLOT_NOT_FOUND."""
    req = BookingRequest(
        property_id="test-prop-1",
        slot_id="slot-does-not-exist",
        renter_name="John Doe",
    )
    result = await booking_policy.validate_and_reserve(req)

    assert result.success is False
    assert result.error_code == PolicyErrorCode.SLOT_NOT_FOUND


@pytest.mark.asyncio
async def test_policy_slot_property_mismatch(
    booking_policy: BookingPolicyService,
) -> None:
    """Rule 4: Slot belonging to another property returns SLOT_PROPERTY_MISMATCH."""
    # slot-test-prop2-01 belongs to test-prop-2, but we pass test-prop-1
    req = BookingRequest(
        property_id="test-prop-1",
        slot_id="slot-test-prop2-01",
        renter_name="John Doe",
    )
    result = await booking_policy.validate_and_reserve(req)

    assert result.success is False
    assert result.error_code == PolicyErrorCode.SLOT_PROPERTY_MISMATCH


@pytest.mark.asyncio
async def test_policy_date_in_past(
    booking_policy: BookingPolicyService,
) -> None:
    """Rule 5: Showing slot with date in past relative to Clock returns DATE_IN_PAST."""
    # slot-test-past date is 2026-09-20, while frozen clock is 2026-10-01
    req = BookingRequest(
        property_id="test-prop-1",
        slot_id="slot-test-past",
        renter_name="John Doe",
    )
    result = await booking_policy.validate_and_reserve(req)

    assert result.success is False
    assert result.error_code == PolicyErrorCode.DATE_IN_PAST


@pytest.mark.asyncio
async def test_policy_invalid_expected_date(
    booking_policy: BookingPolicyService,
) -> None:
    """Rule 6: Mismatched expected date returns INVALID_DATE."""
    # slot-test-01 is 2026-10-01, but caller expects 2026-10-05
    req = BookingRequest(
        property_id="test-prop-1",
        slot_id="slot-test-01",
        renter_name="John Doe",
        expected_date=datetime.date(2026, 10, 5),
    )
    result = await booking_policy.validate_and_reserve(req)

    assert result.success is False
    assert result.error_code == PolicyErrorCode.INVALID_DATE


@pytest.mark.asyncio
async def test_policy_unavailable_slot(
    booking_policy: BookingPolicyService,
) -> None:
    """Rule 7: Slot that is already BOOKED returns SLOT_UNAVAILABLE."""
    # slot-test-booked is pre-booked
    req = BookingRequest(
        property_id="test-prop-1",
        slot_id="slot-test-booked",
        renter_name="Jane Smith",
    )
    result = await booking_policy.validate_and_reserve(req)

    assert result.success is False
    assert result.error_code == PolicyErrorCode.SLOT_UNAVAILABLE


@pytest.mark.asyncio
async def test_policy_missing_renter_name(
    booking_policy: BookingPolicyService,
) -> None:
    """Rule 8: Missing or whitespace renter name returns MISSING_RENTER_NAME."""
    req = BookingRequest(
        property_id="test-prop-1",
        slot_id="slot-test-01",
        renter_name="   ",
    )
    result = await booking_policy.validate_and_reserve(req)

    assert result.success is False
    assert result.error_code == PolicyErrorCode.MISSING_RENTER_NAME


@pytest.mark.asyncio
async def test_policy_idempotent_duplicate_booking(
    booking_policy: BookingPolicyService,
) -> None:
    """Rule 9 & 10: Repeated identical booking returns original booking with is_idempotent=True."""
    req = BookingRequest(
        property_id="test-prop-1",
        slot_id="slot-test-02",
        renter_name="Alice Wonder",
    )
    # First invocation -> creates booking
    res1 = await booking_policy.validate_and_reserve(req)
    assert res1.success is True
    assert res1.is_idempotent is False
    orig_booking_id = res1.booking.booking_id  # type: ignore[union-attr]

    # Second identical invocation -> returns same booking idempotently
    res2 = await booking_policy.validate_and_reserve(req)
    assert res2.success is True
    assert res2.is_idempotent is True
    assert res2.booking is not None
    assert res2.booking.booking_id == orig_booking_id


@pytest.mark.asyncio
async def test_policy_different_renter_same_slot_rejected(
    booking_policy: BookingPolicyService,
) -> None:
    """Rule: Once booked by Renter A, Renter B attempting the same slot is rejected."""
    req_a = BookingRequest(
        property_id="test-prop-1",
        slot_id="slot-test-future",
        renter_name="Renter A",
    )
    res_a = await booking_policy.validate_and_reserve(req_a)
    assert res_a.success is True

    req_b = BookingRequest(
        property_id="test-prop-1",
        slot_id="slot-test-future",
        renter_name="Renter B",
    )
    res_b = await booking_policy.validate_and_reserve(req_b)
    assert res_b.success is False
    assert res_b.error_code == PolicyErrorCode.SLOT_UNAVAILABLE


@pytest.mark.asyncio
async def test_policy_double_check_idempotency_inside_lock(
    booking_policy: BookingPolicyService,
    booking_repo: InMemoryBookingRepository,
) -> None:
    """Verify that if another coroutine created the booking while lock was contested,
    the inner idempotency check returns the booking successfully.
    """
    req = BookingRequest(
        property_id="test-prop-1",
        slot_id="slot-test-01",
        renter_name="Lock Contest Renter",
    )
    # Simulate: acquire lock first so validate_and_reserve waits
    async with booking_repo.acquire_slot_lock("slot-test-01"):
        # Directly insert booking into repo as if another task completed it
        from proprelay.domain.models import Booking, compute_booking_idempotency_key

        key = compute_booking_idempotency_key("test-prop-1", "slot-test-01", "Lock Contest Renter")
        booking = Booking(
            booking_id="bk-contest-1",
            slot_id="slot-test-01",
            property_id="test-prop-1",
            renter_name="Lock Contest Renter",
            created_at=datetime.datetime.now(datetime.UTC),
            status=BookingStatus.CONFIRMED,
            idempotency_key=key,
        )
        await booking_repo.add(booking)

    # Now call validate_and_reserve: the outer check or inner check finds it
    res = await booking_policy.validate_and_reserve(req)
    assert res.success is True
    assert res.is_idempotent is True
    assert res.booking is not None
    assert res.booking.booking_id == "bk-contest-1"
