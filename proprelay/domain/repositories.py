"""In-memory domain repositories with typed interfaces and slot-level concurrency locking."""

from __future__ import annotations

import asyncio
import datetime
import json
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager as AsyncContextManager
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol

from proprelay.domain.models import (
    Booking,
    BookingStatus,
    Lead,
    Property,
    ShowingSlot,
    ShowingSlotStatus,
)


class IPropertyRepository(Protocol):
    """Interface contract for property listing persistence."""

    async def get_by_id(self, property_id: str) -> Property | None: ...
    async def list_all(self) -> list[Property]: ...
    async def search(
        self,
        neighborhood: str | None = None,
        max_rent: int | None = None,
        bedrooms: int | None = None,
        pets_allowed: bool | None = None,
    ) -> list[Property]: ...
    async def add(self, property_obj: Property) -> None: ...


class IShowingRepository(Protocol):
    """Interface contract for showing slot persistence and status transitions."""

    async def get_slot(self, slot_id: str) -> ShowingSlot | None: ...
    async def list_by_property(
        self,
        property_id: str,
        for_date: datetime.date | None = None,
        available_only: bool = False,
    ) -> list[ShowingSlot]: ...
    async def update_slot_status(self, slot_id: str, status: ShowingSlotStatus) -> bool: ...
    async def add_slot(self, slot: ShowingSlot) -> None: ...


class IBookingRepository(Protocol):
    """Interface contract for showing booking persistence with idempotency lookup."""

    async def get_by_id(self, booking_id: str) -> Booking | None: ...
    async def get_by_idempotency_key(self, key: str) -> Booking | None: ...
    async def get_by_slot_id(self, slot_id: str) -> Booking | None: ...
    async def get_by_renter_name(self, renter_name: str) -> list[Booking]: ...
    async def list_all(self) -> list[Booking]: ...
    async def add(self, booking: Booking) -> None: ...
    async def update(self, booking: Booking) -> bool: ...
    def acquire_slot_lock(self, slot_id: str) -> AsyncContextManager[None]: ...


class ILeadRepository(Protocol):
    """Interface contract for lead persistence."""

    async def get_by_id(self, lead_id: str) -> Lead | None: ...
    async def list_all(self) -> list[Lead]: ...
    async def add(self, lead: Lead) -> None: ...


class InMemoryPropertyRepository:
    """In-memory implementation of PropertyRepository."""

    def __init__(self, properties: list[Property] | None = None) -> None:
        self._properties: dict[str, Property] = {}
        if properties:
            for p in properties:
                self._properties[p.property_id] = p

    @classmethod
    def from_json_file(cls, path: str | Path) -> InMemoryPropertyRepository:
        file_path = Path(path)
        if not file_path.exists():
            return cls([])
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        return cls([Property.model_validate(item) for item in data])

    async def get_by_id(self, property_id: str) -> Property | None:
        return self._properties.get(property_id)

    async def list_all(self) -> list[Property]:
        return list(self._properties.values())

    async def search(
        self,
        neighborhood: str | None = None,
        max_rent: int | None = None,
        bedrooms: int | None = None,
        pets_allowed: bool | None = None,
    ) -> list[Property]:
        results: list[Property] = []
        for prop in self._properties.values():
            if neighborhood and neighborhood.strip().lower() not in prop.neighborhood.lower():
                continue
            if max_rent is not None and prop.monthly_rent > max_rent:
                continue
            if bedrooms is not None and prop.bedrooms != bedrooms:
                continue
            if pets_allowed is not None and prop.pets_allowed != pets_allowed:
                continue
            results.append(prop)
        return results

    async def add(self, property_obj: Property) -> None:
        self._properties[property_obj.property_id] = property_obj


class InMemoryShowingRepository:
    """In-memory implementation of ShowingRepository."""

    def __init__(self, slots: list[ShowingSlot] | None = None) -> None:
        self._slots: dict[str, ShowingSlot] = {}
        if slots:
            for slot in slots:
                self._slots[slot.slot_id] = slot

    @classmethod
    def from_json_file(cls, path: str | Path) -> InMemoryShowingRepository:
        file_path = Path(path)
        if not file_path.exists():
            return cls([])
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        return cls([ShowingSlot.model_validate(item) for item in data])

    async def get_slot(self, slot_id: str) -> ShowingSlot | None:
        return self._slots.get(slot_id)

    async def list_by_property(
        self,
        property_id: str,
        for_date: datetime.date | None = None,
        available_only: bool = False,
    ) -> list[ShowingSlot]:
        matched: list[ShowingSlot] = []
        for slot in self._slots.values():
            if slot.property_id != property_id:
                continue
            if for_date and slot.date != for_date:
                continue
            if available_only and slot.status != ShowingSlotStatus.AVAILABLE:
                continue
            matched.append(slot)
        # Sort chronologically by date and start_time
        return sorted(matched, key=lambda s: (s.date, s.start_time))

    async def update_slot_status(self, slot_id: str, status: ShowingSlotStatus) -> bool:
        slot = self._slots.get(slot_id)
        if not slot:
            return False
        # Update status in-place
        self._slots[slot_id] = slot.model_copy(update={"status": status})
        return True

    async def add_slot(self, slot: ShowingSlot) -> None:
        self._slots[slot.slot_id] = slot


class InMemoryBookingRepository:
    """In-memory BookingRepository with per-slot asyncio locks and idempotency index."""

    def __init__(self) -> None:
        self._bookings: dict[str, Booking] = {}
        self._by_idempotency_key: dict[str, Booking] = {}
        self._by_slot_id: dict[str, Booking] = {}
        self._slot_locks: dict[str, asyncio.Lock] = {}
        self._lock_registry_lock = asyncio.Lock()

    async def _get_or_create_slot_lock(self, slot_id: str) -> asyncio.Lock:
        """Fine-grained lock registry ensuring exactly one lock per slot_id."""
        async with self._lock_registry_lock:
            if slot_id not in self._slot_locks:
                self._slot_locks[slot_id] = asyncio.Lock()
            return self._slot_locks[slot_id]

    @asynccontextmanager
    async def acquire_slot_lock(self, slot_id: str) -> AsyncIterator[None]:
        """Async context manager acquiring an exclusive lock on an individual slot."""
        lock = await self._get_or_create_slot_lock(slot_id)
        async with lock:
            yield

    async def get_by_id(self, booking_id: str) -> Booking | None:
        return self._bookings.get(booking_id)

    async def get_by_idempotency_key(self, key: str) -> Booking | None:
        return self._by_idempotency_key.get(key)

    async def get_by_slot_id(self, slot_id: str) -> Booking | None:
        return self._by_slot_id.get(slot_id)

    async def get_by_renter_name(self, renter_name: str) -> list[Booking]:
        clean = renter_name.strip().lower()
        return [b for b in self._bookings.values() if b.renter_name.strip().lower() == clean]

    async def list_all(self) -> list[Booking]:
        return list(self._bookings.values())

    async def add(self, booking: Booking) -> None:
        self._bookings[booking.booking_id] = booking
        self._by_idempotency_key[booking.idempotency_key] = booking
        self._by_slot_id[booking.slot_id] = booking

    async def update(self, booking: Booking) -> bool:
        if booking.booking_id not in self._bookings:
            return False
        old_booking = self._bookings[booking.booking_id]
        if old_booking.slot_id != booking.slot_id:
            self._by_slot_id.pop(old_booking.slot_id, None)
        if booking.status == BookingStatus.CANCELLED:
            self._by_slot_id.pop(booking.slot_id, None)
        else:
            self._by_slot_id[booking.slot_id] = booking
        self._bookings[booking.booking_id] = booking
        self._by_idempotency_key[booking.idempotency_key] = booking
        return True


class InMemoryLeadRepository:
    """In-memory LeadRepository."""

    def __init__(self, leads: list[Lead] | None = None) -> None:
        self._leads: dict[str, Lead] = {}
        if leads:
            for lead in leads:
                self._leads[lead.lead_id] = lead

    async def get_by_id(self, lead_id: str) -> Lead | None:
        return self._leads.get(lead_id)

    async def list_all(self) -> list[Lead]:
        return list(self._leads.values())

    async def add(self, lead: Lead) -> None:
        self._leads[lead.lead_id] = lead
