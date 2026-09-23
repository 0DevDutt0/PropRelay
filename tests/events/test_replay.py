"""Tests for Event Journal replay, filtering, and integrity verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from proprelay.events.journal import AppendOnlyEventJournal
from proprelay.events.replay import EventReplayEngine
from proprelay.events.schemas import DomainEvent, EventType


@pytest.fixture
def populated_journal(tmp_path: Path) -> tuple[AppendOnlyEventJournal, Path]:
    journal_path = tmp_path / "test_events.jsonl"
    journal = AppendOnlyEventJournal(file_path=journal_path)
    return journal, journal_path


@pytest.mark.asyncio
async def test_journal_append_and_sequential_ordering(populated_journal):
    journal, path = populated_journal

    ev1 = DomainEvent(
        event_type=EventType.SESSION_STARTED.value,
        session_id="s1",
        workflow_id="w1",
        payload={"room": "room-1"},
    )
    ev2 = DomainEvent(
        event_type=EventType.PROPERTY_SEARCH_COMPLETED.value,
        session_id="s1",
        workflow_id="w1",
        payload={"results": 2},
    )
    ev3 = DomainEvent(
        event_type=EventType.SHOWING_BOOKED.value,
        session_id="s2",
        workflow_id="w2",
        payload={"slot_id": "slot-1"},
    )

    await journal.append(ev1)
    await journal.append(ev2)
    await journal.append(ev3)

    events = journal.read_all()
    assert len(events) == 3
    assert events[0].sequence_number == 1
    assert events[1].sequence_number == 2
    assert events[2].sequence_number == 3

    # Check hash chaining
    assert events[0].previous_event_hash == ""
    assert events[1].previous_event_hash == events[0].event_hash
    assert events[2].previous_event_hash == events[1].event_hash

    is_valid, issues = journal.verify_integrity()
    assert is_valid is True
    assert issues == []


@pytest.mark.asyncio
async def test_journal_filtering_criteria(populated_journal):
    journal, path = populated_journal

    await journal.append(
        DomainEvent(
            event_type=EventType.SESSION_STARTED.value,
            session_id="s1",
            workflow_id="w1",
        )
    )
    await journal.append(
        DomainEvent(
            event_type=EventType.SHOWING_BOOKED.value,
            session_id="s1",
            workflow_id="w1",
        )
    )
    await journal.append(
        DomainEvent(
            event_type=EventType.SHOWING_BOOKED.value,
            session_id="s2",
            workflow_id="w2",
        )
    )

    # Filter by session
    s1_events = journal.read_filtered(session_id="s1")
    assert len(s1_events) == 2

    # Filter by workflow
    w2_events = journal.read_filtered(workflow_id="w2")
    assert len(w2_events) == 1
    assert w2_events[0].session_id == "s2"

    # Filter by event type
    booked_events = journal.read_filtered(event_type=EventType.SHOWING_BOOKED.value)
    assert len(booked_events) == 2


@pytest.mark.asyncio
async def test_replayer_filtering_and_diagnostics(populated_journal):
    journal, path = populated_journal

    await journal.append(
        DomainEvent(
            event_type=EventType.SESSION_STARTED.value,
            session_id="s10",
            workflow_id="w10",
        )
    )
    await journal.append(
        DomainEvent(
            event_type=EventType.SHOWING_BOOKED.value,
            session_id="s10",
            workflow_id="w10",
            turn_id="1",
        )
    )

    engine = EventReplayEngine(path)
    filtered = engine.load_events(session_id="s10")
    assert len(filtered) == 2

    diag = engine.inspect_diagnostics()
    assert diag["total_events"] == 2
    assert diag["integrity_valid"] is True
    assert diag["integrity_issues"] == []


@pytest.mark.asyncio
async def test_journal_detects_corrupted_hash_chain(populated_journal):
    journal, path = populated_journal

    await journal.append(
        DomainEvent(
            event_type=EventType.SESSION_STARTED.value,
            session_id="s1",
            payload={"msg": "hello"},
        )
    )
    await journal.append(
        DomainEvent(
            event_type=EventType.SESSION_COMPLETED.value,
            session_id="s1",
            payload={"msg": "bye"},
        )
    )

    # Corrupt line 1 in the raw file
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    corrupt_line1 = json.loads(lines[0])
    corrupt_line1["payload"]["msg"] = "tampered"
    lines[0] = json.dumps(corrupt_line1) + "\n"

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    is_valid, issues = journal.verify_integrity()
    assert is_valid is False
    assert any("Hash mismatch" in issue for issue in issues)
