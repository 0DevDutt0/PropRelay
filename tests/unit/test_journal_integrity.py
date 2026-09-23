"""Event journal recovery, corruption detection, and tamper-evident auditability tests."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from proprelay.events.broadcaster import CompositeEventPublisher
from proprelay.events.journal import EventJournal, IEventPublisher
from proprelay.events.schemas import DomainEvent, EventType


class FailingBroadcaster(IEventPublisher):
    """Simulates a broken WebRTC data channel or network disconnect."""

    async def publish(self, event: DomainEvent) -> None:
        raise ConnectionResetError("WebRTC Data Channel disconnected unexpectedly")


@pytest.fixture
def temp_journal(tmp_path: Path) -> EventJournal:
    journal_path = tmp_path / "events.jsonl"
    return EventJournal(file_path=journal_path)


@pytest.mark.asyncio
async def test_durable_journal_survives_realtime_broadcast_failure(temp_journal: EventJournal) -> None:
    """Invariant: Realtime packet delivery failure MUST NOT lose durable event journal state."""
    failing_broadcaster = FailingBroadcaster()

    # Composite publisher attempts journal append first, then broadcaster
    composite = CompositeEventPublisher([temp_journal, failing_broadcaster])

    event = DomainEvent(
        event_type=EventType.SHOWING_BOOKED.value,
        timestamp=datetime.datetime.now(datetime.UTC),
        session_id="sess-survive-01",
        workflow_id="wf-survive-01",
        payload={"booking_id": "book-survive-01", "renter_name": "Resilient Renter"},
    )

    # Publishing succeeds without raising because CompositeEventPublisher isolates transport failures
    await composite.publish(event)

    # Mutation and event journal remain committed and durable!
    recorded = temp_journal.read_all()
    assert len(recorded) == 1
    assert recorded[0].event_type == EventType.SHOWING_BOOKED.value
    assert recorded[0].payload["booking_id"] == "book-survive-01"


@pytest.mark.asyncio
async def test_event_journal_detects_tampered_payload_hash_mismatch(temp_journal: EventJournal) -> None:
    """Tampering with an event payload must be detected as a hash mismatch."""
    event1 = DomainEvent(
        event_type=EventType.SESSION_STARTED.value,
        timestamp=datetime.datetime.now(datetime.UTC),
        session_id="sess-tamper-01",
        payload={"status": "init"},
    )
    event2 = DomainEvent(
        event_type=EventType.SHOWING_BOOKED.value,
        timestamp=datetime.datetime.now(datetime.UTC),
        session_id="sess-tamper-01",
        payload={"booking_id": "book-tamper-01", "rent": 2500},
    )

    await temp_journal.append(event1)
    await temp_journal.append(event2)

    valid, issues = temp_journal.verify_integrity()
    assert valid is True
    assert len(issues) == 0

    # Tamper with the second event payload on disk
    with open(temp_journal.file_path, encoding="utf-8") as f:
        lines = f.readlines()

    tampered_data = json.loads(lines[1])
    tampered_data["payload"]["rent"] = 1000  # Malicious price modification
    lines[1] = json.dumps(tampered_data) + "\n"

    with open(temp_journal.file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    is_valid, corruption_issues = temp_journal.verify_integrity()
    assert is_valid is False
    assert any("Hash mismatch" in issue for issue in corruption_issues)


@pytest.mark.asyncio
async def test_event_journal_detects_sequence_gap(temp_journal: EventJournal) -> None:
    """A deleted or dropped event introduces a sequence gap that must be flagged."""
    for i in range(3):
        await temp_journal.append(
            DomainEvent(
                event_type=EventType.PROPERTY_DETAILS_VIEWED.value,
                timestamp=datetime.datetime.now(datetime.UTC),
                session_id="sess-seq-01",
                payload={"index": i},
            )
        )

    # Read lines and delete line 2 (seq=2)
    with open(temp_journal.file_path, encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 3
    # Remove second line (sequence 2)
    remaining_lines = [lines[0], lines[2]]

    with open(temp_journal.file_path, "w", encoding="utf-8") as f:
        f.writelines(remaining_lines)

    is_valid, corruption_issues = temp_journal.verify_integrity()
    assert is_valid is False
    assert any("Sequence gap" in issue or "Hash chain broken" in issue for issue in corruption_issues)


@pytest.mark.asyncio
async def test_event_journal_detects_duplicate_event_id(temp_journal: EventJournal) -> None:
    """Duplicate event IDs must be caught during audit verification."""
    ev = DomainEvent(
        event_type=EventType.PROPERTY_SEARCH_COMPLETED.value,
        timestamp=datetime.datetime.now(datetime.UTC),
        session_id="sess-dup-01",
        payload={"query": "2 bedroom"},
    )
    stamped1 = await temp_journal.append(ev)

    # Append same event_id manually
    ev_duplicate = DomainEvent(
        event_id=stamped1.event_id,
        event_type=EventType.PROPERTY_SEARCH_COMPLETED.value,
        timestamp=datetime.datetime.now(datetime.UTC),
        session_id="sess-dup-01",
        payload={"query": "duplicate attempt"},
        sequence_number=stamped1.sequence_number + 1 if stamped1.sequence_number else 2,
        previous_event_hash=stamped1.event_hash,
    )
    with open(temp_journal.file_path, "a", encoding="utf-8") as f:
        f.write(ev_duplicate.to_jsonl_line())

    is_valid, issues = temp_journal.verify_integrity()
    assert is_valid is False
    assert any("Duplicate event_id" in issue for issue in issues)


@pytest.mark.asyncio
async def test_event_journal_detects_malformed_json_line(temp_journal: EventJournal) -> None:
    """Malformed unparseable lines raise ValueError when skip_malformed is False."""
    await temp_journal.append(
        DomainEvent(
            event_type=EventType.SESSION_STARTED.value,
            timestamp=datetime.datetime.now(datetime.UTC),
            session_id="sess-malform-01",
            payload={"status": "ok"},
        )
    )

    with open(temp_journal.file_path, "a", encoding="utf-8") as f:
        f.write("{malformed json line truncated...\n")

    with pytest.raises(ValueError, match="Malformed event at line 2"):
        temp_journal.read_all(skip_malformed=False)

    # When skipping malformed lines, valid records are still readable
    rescued = temp_journal.read_all(skip_malformed=True)
    assert len(rescued) == 1
