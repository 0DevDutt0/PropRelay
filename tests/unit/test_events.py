"""Unit tests verifying Event schemas, EventJournal append-only persistence, and readback."""

from __future__ import annotations

from pathlib import Path

import pytest

from proprelay.events.journal import EventJournal
from proprelay.events.schemas import DomainEvent, EventType


@pytest.mark.asyncio
async def test_event_journal_append_and_read(temp_journal_file: Path) -> None:
    journal = EventJournal(temp_journal_file)
    assert journal.read_all() == []
    assert journal.count() == 0

    event1 = DomainEvent(
        event_type=EventType.PROPERTY_SEARCH_COMPLETED.value,
        payload={"query": "Downtown", "count": 2},
    )
    event2 = DomainEvent(
        event_type=EventType.SHOWING_BOOKED.value,
        payload={"booking_id": "bk-123", "slot_id": "slot-1"},
    )

    await journal.publish(event1)
    await journal.publish(event2)

    events = journal.read_all()
    assert len(events) == 2
    assert events[0].event_type == EventType.PROPERTY_SEARCH_COMPLETED.value
    assert events[1].event_type == EventType.SHOWING_BOOKED.value
    assert journal.count() == 2


def test_event_journal_malformed_line_handling(temp_journal_file: Path) -> None:
    journal = EventJournal(temp_journal_file)

    # Write one valid line and one corrupt line directly
    valid_event = DomainEvent(event_type="test.event", payload={"k": "v"})
    with open(temp_journal_file, "w", encoding="utf-8") as f:
        f.write(valid_event.to_jsonl_line())
        f.write("CORRUPT_NON_JSON_LINE\n")

    # With skip_malformed=False, raises ValueError
    with pytest.raises(ValueError, match="Malformed event at line 2"):
        journal.read_all(skip_malformed=False)

    # With skip_malformed=True, skips corrupt line
    events = journal.read_all(skip_malformed=True)
    assert len(events) == 1
    assert events[0].event_type == "test.event"


@pytest.mark.asyncio
async def test_event_journal_clear(temp_journal_file: Path) -> None:
    journal = EventJournal(temp_journal_file)
    event = DomainEvent(event_type="test.event", payload={})
    await journal.publish(event)
    assert journal.count() == 1

    journal.clear()
    assert journal.count() == 0
    assert journal.read_all() == []
