"""Manual demonstration script for Checkpoint 10.

Demonstrates:
1. Valid booking -> success
2. Same booking -> idempotent result
3. Invalid / unavailable slot -> rejection
4. Concurrent booking -> exactly one success
"""

import asyncio
import datetime
from pathlib import Path

from proprelay.agent.tools import AgentTools, BookShowingInput
from proprelay.domain.clock import FrozenClock
from proprelay.domain.policy import BookingPolicyService
from proprelay.domain.repositories import (
    InMemoryBookingRepository,
    InMemoryLeadRepository,
    InMemoryPropertyRepository,
    InMemoryShowingRepository,
)
from proprelay.events.journal import EventJournal


async def run_scenario() -> None:
    clock = FrozenClock(datetime.datetime(2026, 10, 1, 9, 0, tzinfo=datetime.UTC))
    prop_repo = InMemoryPropertyRepository.from_json_file("data/listings.json")
    showing_repo = InMemoryShowingRepository.from_json_file("data/showings.json")
    booking_repo = InMemoryBookingRepository()
    lead_repo = InMemoryLeadRepository()

    demo_journal_path = Path("data/events_manual_demo.jsonl")
    journal = EventJournal(demo_journal_path)
    journal.clear()

    policy = BookingPolicyService(prop_repo, showing_repo, booking_repo, clock)
    tools = AgentTools(prop_repo, showing_repo, booking_repo, lead_repo, policy, journal, clock)

    print("=== SCENARIO 1: Valid Booking ===")
    res1 = await tools.book_showing(
        BookShowingInput(
            property_id="prop-101",
            slot_id="slot-101-01",
            renter_name="Sarah Jenkins",
            renter_phone="555-0199",
        )
    )
    b1_id = res1.data.booking.booking_id if res1.data else None
    print(
        f"Result: success={res1.success}, booking_id={b1_id}, is_idempotent={res1.data.is_idempotent if res1.data else None}"
    )

    print("\n=== SCENARIO 2: Idempotent Duplicate Request ===")
    res2 = await tools.book_showing(
        BookShowingInput(
            property_id="prop-101",
            slot_id="slot-101-01",
            renter_name="Sarah Jenkins",
            renter_phone="555-0199",
        )
    )
    b2_id = res2.data.booking.booking_id if res2.data else None
    print(
        f"Result: success={res2.success}, booking_id={b2_id}, is_idempotent={res2.data.is_idempotent if res2.data else None}"
    )

    print("\n=== SCENARIO 3: Invalid / Unavailable Slot (pre-booked slot) ===")
    res3 = await tools.book_showing(
        BookShowingInput(
            property_id="prop-101",
            slot_id="slot-101-03",
            renter_name="David Miller",
        )
    )
    print(f"Result: success={res3.success}, error_code={res3.error_code}, message={res3.message}")

    print("\n=== SCENARIO 4: 10 Concurrent Renter Requests for Same Slot ===")
    tasks = [
        tools.book_showing(
            BookShowingInput(
                property_id="prop-101",
                slot_id="slot-101-02",
                renter_name=f"Competitor Renter {i}",
            )
        )
        for i in range(10)
    ]
    results = await asyncio.gather(*tasks)
    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]
    print(f"Concurrent outcomes: {len(successes)} succeeded, {len(failures)} rejected.")
    if successes and successes[0].data:
        print(f"Winning booking ID: {successes[0].data.booking.booking_id}")
    if failures:
        print(f"First rejection error code: {failures[0].error_code}")

    print("\n=== Journal Events Recorded ===")
    events = journal.read_all()
    print(f"Total events recorded in JSONL journal: {len(events)}")
    for evt in events[:8]:
        summary = (
            evt.payload.get("booking_id")
            or evt.payload.get("error_code")
            or evt.payload.get("slot_id")
            or ""
        )
        print(f"  [{evt.event_type}] {summary}")
    if len(events) > 8:
        print(f"  ... and {len(events) - 8} more events.")

    # Cleanup demo journal
    if demo_journal_path.exists():
        demo_journal_path.unlink()


if __name__ == "__main__":
    asyncio.run(run_scenario())
