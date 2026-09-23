"""Unit tests verifying In-Memory Repositories, queries, mutations, and isolation."""

from __future__ import annotations

import datetime

import pytest

from proprelay.domain.models import (
    Booking,
    BookingStatus,
    Lead,
    Property,
    ShowingSlot,
    ShowingSlotStatus,
)
from proprelay.domain.repositories import (
    InMemoryBookingRepository,
    InMemoryLeadRepository,
    InMemoryPropertyRepository,
    InMemoryShowingRepository,
)


@pytest.mark.asyncio
async def test_property_repository_crud() -> None:
    repo = InMemoryPropertyRepository()
    assert await repo.list_all() == []

    prop = Property(
        property_id="p-1",
        title="Test Apt",
        address="123 St",
        city="City",
        neighborhood="Downtown",
        monthly_rent=2000,
        bedrooms=1,
        bathrooms=1.0,
        square_feet=600,
        pets_allowed=True,
        amenities=["Laundry"],
        description="Nice unit",
    )
    await repo.add(prop)

    fetched = await repo.get_by_id("p-1")
    assert fetched == prop
    assert await repo.get_by_id("non-existent") is None
    assert len(await repo.list_all()) == 1


@pytest.mark.asyncio
async def test_property_repository_search_filters() -> None:
    p1 = Property(
        property_id="p1",
        title="Apt 1",
        address="1",
        city="C",
        neighborhood="Downtown",
        monthly_rent=2000,
        bedrooms=2,
        bathrooms=1.0,
        square_feet=800,
        pets_allowed=True,
        description="Desc",
    )
    p2 = Property(
        property_id="p2",
        title="Apt 2",
        address="2",
        city="C",
        neighborhood="Uptown",
        monthly_rent=3000,
        bedrooms=2,
        bathrooms=2.0,
        square_feet=1200,
        pets_allowed=False,
        description="Desc",
    )
    repo = InMemoryPropertyRepository([p1, p2])

    # Search by neighborhood substring
    res = await repo.search(neighborhood="down")
    assert len(res) == 1
    assert res[0].property_id == "p1"

    # Search by max_rent
    res_rent = await repo.search(max_rent=2500)
    assert len(res_rent) == 1
    assert res_rent[0].property_id == "p1"

    # Search by bedrooms
    res_bed = await repo.search(bedrooms=2)
    assert len(res_bed) == 2

    # Search by pets_allowed
    res_pets = await repo.search(pets_allowed=False)
    assert len(res_pets) == 1
    assert res_pets[0].property_id == "p2"

    # Search with no match
    res_none = await repo.search(neighborhood="NonExistent")
    assert len(res_none) == 0


@pytest.mark.asyncio
async def test_showing_repository_crud_and_status_update() -> None:
    slot = ShowingSlot(
        slot_id="s1",
        property_id="p1",
        date=datetime.date(2026, 10, 1),
        start_time=datetime.time(10, 0),
        end_time=datetime.time(10, 30),
        status=ShowingSlotStatus.AVAILABLE,
    )
    repo = InMemoryShowingRepository([slot])

    # Get slot
    assert await repo.get_slot("s1") == slot
    assert await repo.get_slot("unknown") is None

    # List by property and date
    slots = await repo.list_by_property("p1", for_date=datetime.date(2026, 10, 1))
    assert len(slots) == 1

    # Update slot status
    updated = await repo.update_slot_status("s1", ShowingSlotStatus.BOOKED)
    assert updated is True
    slot_after = await repo.get_slot("s1")
    assert slot_after is not None
    assert slot_after.status == ShowingSlotStatus.BOOKED

    # Update non-existent slot
    assert await repo.update_slot_status("unknown", ShowingSlotStatus.BOOKED) is False


@pytest.mark.asyncio
async def test_booking_repository_idempotency_and_locks() -> None:
    repo = InMemoryBookingRepository()
    booking = Booking(
        booking_id="bk-1",
        slot_id="slot-1",
        property_id="prop-1",
        renter_name="Alice",
        created_at=datetime.datetime.now(datetime.UTC),
        status=BookingStatus.CONFIRMED,
        idempotency_key="idem-key-1",
    )
    await repo.add(booking)

    # Retrieval methods
    assert await repo.get_by_id("bk-1") == booking
    assert await repo.get_by_idempotency_key("idem-key-1") == booking
    assert await repo.get_by_slot_id("slot-1") == booking
    assert await repo.get_by_idempotency_key("unknown") is None

    # Slot lock acquisition
    async with repo.acquire_slot_lock("slot-1"):
        # Lock held
        pass


@pytest.mark.asyncio
async def test_repositories_from_json_files() -> None:
    # Test valid files
    prop_repo = InMemoryPropertyRepository.from_json_file("data/listings.json")
    all_props = await prop_repo.list_all()
    assert len(all_props) >= 6

    showing_repo = InMemoryShowingRepository.from_json_file("data/showings.json")
    p101_slots = await showing_repo.list_by_property("prop-101")
    assert len(p101_slots) >= 3

    # Test non-existent file path returns empty repo
    empty_prop_repo = InMemoryPropertyRepository.from_json_file("data/non_existent.json")
    assert await empty_prop_repo.list_all() == []

    empty_showing_repo = InMemoryShowingRepository.from_json_file("data/non_existent.json")
    assert await empty_showing_repo.list_by_property("prop-101") == []


@pytest.mark.asyncio
async def test_lead_repository_crud() -> None:
    repo = InMemoryLeadRepository()
    lead = Lead(
        lead_id="lead-1",
        name="Bob Smith",
        phone="555-0000",
        created_at=datetime.datetime.now(datetime.UTC),
    )
    await repo.add(lead)
    assert await repo.get_by_id("lead-1") == lead
    assert await repo.get_by_id("missing") is None
    all_leads = await repo.list_all()
    assert len(all_leads) == 1
