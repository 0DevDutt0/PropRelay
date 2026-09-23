"""Unit tests verifying Pydantic domain models, validation, and immutability."""

from __future__ import annotations

import datetime

import pytest
from pydantic import ValidationError

from proprelay.domain.models import (
    Booking,
    BookingStatus,
    Lead,
    Property,
    ShowingSlot,
    ShowingSlotStatus,
    compute_booking_idempotency_key,
)
from proprelay.events.schemas import DomainEvent, EventType


def test_property_valid() -> None:
    prop = Property(
        property_id="prop-1",
        title="Valid Title",
        address="123 Test St",
        city="Metropolis",
        neighborhood="Downtown",
        monthly_rent=2000,
        bedrooms=2,
        bathrooms=1.5,
        square_feet=900,
        pets_allowed=True,
        amenities=["AC"],
        description="Great unit",
    )
    assert prop.property_id == "prop-1"
    assert prop.monthly_rent == 2000
    assert prop.supports_showings is True


def test_property_invalid_rent() -> None:
    with pytest.raises(ValidationError):
        Property(
            property_id="prop-1",
            title="Valid Title",
            address="123 Test St",
            city="Metropolis",
            neighborhood="Downtown",
            monthly_rent=-500,  # Invalid: must be > 0
            bedrooms=2,
            bathrooms=1.0,
            square_feet=900,
            description="Great unit",
        )


def test_property_empty_strings() -> None:
    with pytest.raises(ValidationError):
        Property(
            property_id="   ",  # Invalid: blank
            title="Valid Title",
            address="123 Test St",
            city="Metropolis",
            neighborhood="Downtown",
            monthly_rent=2000,
            bedrooms=2,
            bathrooms=1.0,
            square_feet=900,
            description="Great unit",
        )


def test_property_immutability() -> None:
    prop = Property(
        property_id="prop-1",
        title="Valid Title",
        address="123 Test St",
        city="Metropolis",
        neighborhood="Downtown",
        monthly_rent=2000,
        bedrooms=2,
        bathrooms=1.0,
        square_feet=900,
        description="Great unit",
    )
    with pytest.raises(ValidationError):
        prop.monthly_rent = 2500  # type: ignore[misc]


def test_showing_slot_valid() -> None:
    slot = ShowingSlot(
        slot_id="slot-1",
        property_id="prop-1",
        date=datetime.date(2026, 10, 1),
        start_time=datetime.time(10, 0),
        end_time=datetime.time(10, 30),
        status=ShowingSlotStatus.AVAILABLE,
    )
    assert slot.slot_id == "slot-1"
    assert slot.status == ShowingSlotStatus.AVAILABLE


def test_showing_slot_invalid_times() -> None:
    # end_time <= start_time
    with pytest.raises(ValidationError, match="end_time .* must be after start_time"):
        ShowingSlot(
            slot_id="slot-1",
            property_id="prop-1",
            date=datetime.date(2026, 10, 1),
            start_time=datetime.time(11, 0),
            end_time=datetime.time(10, 0),
        )


def test_showing_slot_invalid_status() -> None:
    with pytest.raises(ValidationError):
        ShowingSlot(
            slot_id="slot-1",
            property_id="prop-1",
            date=datetime.date(2026, 10, 1),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(10, 30),
            status="UNKNOWN_STATUS",
        )


def test_booking_model_valid() -> None:
    now = datetime.datetime.now(datetime.UTC)
    booking = Booking(
        booking_id="bk-123",
        slot_id="slot-1",
        property_id="prop-1",
        renter_name="John Doe",
        renter_phone="555-1234",
        renter_email="john@example.com",
        created_at=now,
        status=BookingStatus.CONFIRMED,
        idempotency_key="key-abc",
    )
    assert booking.booking_id == "bk-123"
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.renter_phone == "555-1234"


def test_booking_empty_renter_name() -> None:
    with pytest.raises(ValidationError):
        Booking(
            booking_id="bk-123",
            slot_id="slot-1",
            property_id="prop-1",
            renter_name="  ",
            created_at=datetime.datetime.now(datetime.UTC),
            idempotency_key="key-abc",
        )


def test_lead_model_valid() -> None:
    now = datetime.datetime.now(datetime.UTC)
    lead = Lead(
        lead_id="lead-001",
        name="Jane Renter",
        phone="555-9876",
        email="jane@example.com",
        preferred_neighborhood="Downtown",
        budget=2500,
        interested_property_id="prop-1",
        notes="Looking for pet friendly",
        created_at=now,
    )
    assert lead.lead_id == "lead-001"
    assert lead.budget == 2500


def test_idempotency_key_deterministic() -> None:
    k1 = compute_booking_idempotency_key("prop-1", "slot-1", "Jane Doe")
    k2 = compute_booking_idempotency_key("prop-1", "slot-1", "Jane Doe")
    k3 = compute_booking_idempotency_key("prop-1", "slot-1", "jane doe ")  # casing/trim
    k4 = compute_booking_idempotency_key("prop-1", "slot-2", "Jane Doe")

    assert k1 == k2
    assert k1 == k3
    assert k1 != k4


def test_showing_slot_empty_id() -> None:
    with pytest.raises(ValidationError):
        ShowingSlot(
            slot_id="  ",
            property_id="prop-1",
            date=datetime.date(2026, 10, 1),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(10, 30),
        )


def test_lead_empty_name() -> None:
    with pytest.raises(ValidationError):
        Lead(
            lead_id="lead-1",
            name="   ",
            created_at=datetime.datetime.now(datetime.UTC),
        )


def test_domain_event_model() -> None:
    event = DomainEvent(
        event_type=EventType.PROPERTY_SEARCH_COMPLETED.value,
        payload={"query": "Downtown", "matched": 2},
        tool_name="search_properties",
        duration_ms=45.2,
    )
    assert event.event_type == "property.search.completed"
    assert event.duration_ms == 45.2
    assert event.event_id is not None
    json_line = event.to_jsonl_line()
    assert json_line.endswith("\n")
    assert "property.search.completed" in json_line
