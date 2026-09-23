"""Pytest fixtures for PropRelay test suites."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from proprelay.agent.tools import AgentTools
from proprelay.domain.clock import FrozenClock
from proprelay.domain.models import (
    Property,
    ShowingSlot,
    ShowingSlotStatus,
)
from proprelay.domain.policy import BookingPolicyService
from proprelay.domain.repositories import (
    InMemoryBookingRepository,
    InMemoryLeadRepository,
    InMemoryPropertyRepository,
    InMemoryShowingRepository,
)
from proprelay.events.journal import EventJournal


@pytest.fixture
def frozen_datetime() -> datetime.datetime:
    """Standard fixed reference datetime: 2026-10-01 08:00:00 UTC."""
    return datetime.datetime(2026, 10, 1, 8, 0, 0, tzinfo=datetime.UTC)


@pytest.fixture
def frozen_clock(frozen_datetime: datetime.datetime) -> FrozenClock:
    """Fixed-time Clock abstraction for deterministic time testing."""
    return FrozenClock(frozen_datetime)


@pytest.fixture
def sample_properties() -> list[Property]:
    """Small deterministic test fixture of properties."""
    return [
        Property(
            property_id="test-prop-1",
            title="Modern Downtown Loft",
            address="100 Main St, Apt 2A",
            city="Metropolis",
            neighborhood="Downtown",
            monthly_rent=2500,
            bedrooms=2,
            bathrooms=2.0,
            square_feet=1100,
            pets_allowed=True,
            amenities=["In-unit Washer", "Gym"],
            description="Test property 1",
            supports_showings=True,
        ),
        Property(
            property_id="test-prop-2",
            title="Cozy Suburban Cottage",
            address="200 Oak Ave",
            city="Metropolis",
            neighborhood="Suburbs",
            monthly_rent=1800,
            bedrooms=1,
            bathrooms=1.0,
            square_feet=750,
            pets_allowed=False,
            amenities=["Patio"],
            description="Test property 2",
            supports_showings=True,
        ),
        Property(
            property_id="test-prop-inactive",
            title="Inactive Renovation Property",
            address="300 Elm St",
            city="Metropolis",
            neighborhood="Uptown",
            monthly_rent=3000,
            bedrooms=3,
            bathrooms=2.0,
            square_feet=1400,
            pets_allowed=False,
            amenities=["Pool"],
            description="Showings not accepted",
            supports_showings=False,
        ),
    ]


@pytest.fixture
def sample_slots() -> list[ShowingSlot]:
    """Small deterministic test fixture of showing slots relative to 2026-10-01."""
    return [
        # Available slot on 2026-10-01
        ShowingSlot(
            slot_id="slot-test-01",
            property_id="test-prop-1",
            date=datetime.date(2026, 10, 1),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(10, 30),
            status=ShowingSlotStatus.AVAILABLE,
        ),
        # Another available slot on 2026-10-01
        ShowingSlot(
            slot_id="slot-test-02",
            property_id="test-prop-1",
            date=datetime.date(2026, 10, 1),
            start_time=datetime.time(14, 0),
            end_time=datetime.time(14, 30),
            status=ShowingSlotStatus.AVAILABLE,
        ),
        # Already booked slot on 2026-10-01
        ShowingSlot(
            slot_id="slot-test-booked",
            property_id="test-prop-1",
            date=datetime.date(2026, 10, 1),
            start_time=datetime.time(16, 0),
            end_time=datetime.time(16, 30),
            status=ShowingSlotStatus.BOOKED,
        ),
        # Future date slot on 2026-10-02
        ShowingSlot(
            slot_id="slot-test-future",
            property_id="test-prop-1",
            date=datetime.date(2026, 10, 2),
            start_time=datetime.time(11, 0),
            end_time=datetime.time(11, 30),
            status=ShowingSlotStatus.AVAILABLE,
        ),
        # Past date slot on 2026-09-20 (relative to 2026-10-01)
        ShowingSlot(
            slot_id="slot-test-past",
            property_id="test-prop-1",
            date=datetime.date(2026, 9, 20),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(10, 30),
            status=ShowingSlotStatus.AVAILABLE,
        ),
        # Slot for property 2
        ShowingSlot(
            slot_id="slot-test-prop2-01",
            property_id="test-prop-2",
            date=datetime.date(2026, 10, 1),
            start_time=datetime.time(12, 0),
            end_time=datetime.time(12, 30),
            status=ShowingSlotStatus.AVAILABLE,
        ),
        # Slot for inactive property
        ShowingSlot(
            slot_id="slot-test-inactive-01",
            property_id="test-prop-inactive",
            date=datetime.date(2026, 10, 1),
            start_time=datetime.time(15, 0),
            end_time=datetime.time(15, 30),
            status=ShowingSlotStatus.AVAILABLE,
        ),
    ]


@pytest.fixture
def property_repo(sample_properties: list[Property]) -> InMemoryPropertyRepository:
    return InMemoryPropertyRepository(sample_properties)


@pytest.fixture
def showing_repo(sample_slots: list[ShowingSlot]) -> InMemoryShowingRepository:
    return InMemoryShowingRepository(sample_slots)


@pytest.fixture
def booking_repo() -> InMemoryBookingRepository:
    return InMemoryBookingRepository()


@pytest.fixture
def lead_repo() -> InMemoryLeadRepository:
    return InMemoryLeadRepository()


@pytest.fixture
def booking_policy(
    property_repo: InMemoryPropertyRepository,
    showing_repo: InMemoryShowingRepository,
    booking_repo: InMemoryBookingRepository,
    frozen_clock: FrozenClock,
) -> BookingPolicyService:
    return BookingPolicyService(
        property_repo=property_repo,
        showing_repo=showing_repo,
        booking_repo=booking_repo,
        clock=frozen_clock,
    )


@pytest.fixture
def temp_journal_file(tmp_path: Path) -> Path:
    return tmp_path / "test_events.jsonl"


@pytest.fixture
def event_journal(temp_journal_file: Path) -> EventJournal:
    return EventJournal(temp_journal_file)


@pytest.fixture
def agent_tools(
    property_repo: InMemoryPropertyRepository,
    showing_repo: InMemoryShowingRepository,
    booking_repo: InMemoryBookingRepository,
    lead_repo: InMemoryLeadRepository,
    booking_policy: BookingPolicyService,
    event_journal: EventJournal,
    frozen_clock: FrozenClock,
) -> AgentTools:
    return AgentTools(
        property_repo=property_repo,
        showing_repo=showing_repo,
        booking_repo=booking_repo,
        lead_repo=lead_repo,
        booking_policy=booking_policy,
        event_publisher=event_journal,
        clock=frozen_clock,
    )
