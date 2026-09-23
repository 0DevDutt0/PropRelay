"""Domain models for PropRelay property management and showing reservations."""

from __future__ import annotations

import datetime
import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ShowingSlotStatus(StrEnum):
    """Lifecycle status of a showing calendar slot."""

    AVAILABLE = "AVAILABLE"
    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"


class BookingStatus(StrEnum):
    """Lifecycle status of a renter booking request."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class Property(BaseModel):
    """Authoritative representation of a residential rental property listing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    property_id: str = Field(
        ..., description="Unique alphanumeric property identifier (e.g., 'prop-101')"
    )
    title: str = Field(..., description="Marketing title of the listing")
    address: str = Field(..., description="Street address of the property")
    city: str = Field(..., description="City where property is located")
    neighborhood: str = Field(..., description="Neighborhood or district name")
    monthly_rent: int = Field(..., gt=0, description="Monthly rent amount in USD")
    bedrooms: int = Field(..., ge=0, description="Number of bedrooms (0 for studio)")
    bathrooms: float = Field(..., ge=0.0, description="Number of bathrooms (e.g. 1.0, 1.5, 2.0)")
    square_feet: int = Field(..., gt=0, description="Total interior area in square feet")
    pets_allowed: bool = Field(default=False, description="Whether pets are permitted")
    amenities: list[str] = Field(default_factory=list, description="List of notable amenities")
    description: str = Field(..., description="Full descriptive summary of the listing")
    supports_showings: bool = Field(
        default=True, description="Whether showings can currently be scheduled"
    )

    @field_validator("property_id", "title", "address", "city", "neighborhood")
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Field cannot be empty or purely whitespace")
        return s


class ShowingSlot(BaseModel):
    """An individual showing window on a property's calendar."""

    model_config = ConfigDict(extra="forbid")

    slot_id: str = Field(..., description="Unique slot identifier (e.g., 'slot-101-01')")
    property_id: str = Field(..., description="Associated property identifier")
    date: datetime.date = Field(..., description="Date of the showing (YYYY-MM-DD)")
    start_time: datetime.time = Field(
        ..., description="Start time of the showing window (HH:MM:SS)"
    )
    end_time: datetime.time = Field(..., description="End time of the showing window (HH:MM:SS)")
    status: ShowingSlotStatus = Field(
        default=ShowingSlotStatus.AVAILABLE, description="Current reservation status of the slot"
    )

    @field_validator("slot_id", "property_id")
    @classmethod
    def validate_ids(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("ID cannot be empty")
        return s

    @model_validator(mode="after")
    def validate_slot_times(self) -> ShowingSlot:
        if self.end_time <= self.start_time:
            raise ValueError(
                f"end_time ({self.end_time}) must be after start_time ({self.start_time})"
            )
        return self


def compute_booking_idempotency_key(property_id: str, slot_id: str, renter_name: str) -> str:
    """Derive a stable, deterministic idempotency key from booking identity parameters."""
    normalized = (
        f"{property_id.strip().lower()}:{slot_id.strip().lower()}:{renter_name.strip().lower()}"
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


class Booking(BaseModel):
    """A confirmed or recorded showing reservation made by a renter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    booking_id: str = Field(..., description="Unique booking record ID (e.g., 'bk-...')")
    slot_id: str = Field(..., description="Referenced showing slot ID")
    property_id: str = Field(..., description="Referenced property ID")
    renter_name: str = Field(..., description="Full name of the requesting renter")
    renter_phone: str | None = Field(default=None, description="Optional contact telephone")
    renter_email: str | None = Field(default=None, description="Optional contact email")
    created_at: datetime.datetime = Field(..., description="Timestamp when booking was created")
    status: BookingStatus = Field(default=BookingStatus.CONFIRMED, description="Booking status")
    idempotency_key: str = Field(..., description="Deterministic key preventing duplicate bookings")
    updated_at: datetime.datetime | None = Field(
        default=None, description="Timestamp when booking was last updated or cancelled"
    )
    cancellation_reason: str | None = Field(
        default=None, description="Optional cancellation explanation"
    )

    @field_validator("booking_id", "slot_id", "property_id", "renter_name")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("String field cannot be empty")
        return s


class Lead(BaseModel):
    """Captured prospective renter lead information for CRM / follow-up."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lead_id: str = Field(..., description="Unique lead identifier (e.g., 'lead-...')")
    name: str = Field(..., description="Lead contact name")
    phone: str | None = Field(default=None, description="Contact phone")
    email: str | None = Field(default=None, description="Contact email")
    preferred_neighborhood: str | None = Field(default=None, description="Desired location")
    budget: int | None = Field(default=None, ge=0, description="Monthly budget limit in USD")
    interested_property_id: str | None = Field(default=None, description="Associated property ID")
    notes: str | None = Field(default=None, description="Agent notes or renter preferences")
    created_at: datetime.datetime = Field(..., description="Timestamp when lead was recorded")
    lifecycle_state: str = Field(
        default="NEW",
        description="Lead lifecycle state (e.g., 'NEW', 'CONTACTED', 'QUALIFIED', 'CLOSED')",
    )

    @field_validator("lead_id", "name")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Field cannot be empty")
        return s
