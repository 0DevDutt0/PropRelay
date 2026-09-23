"""Append-only local JSONL Event Journal and Event Publisher Protocol."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Protocol

from proprelay.events.schemas import DomainEvent

logger = logging.getLogger(__name__)


class IEventPublisher(Protocol):
    """Protocol for publishing domain events."""

    async def publish(self, event: DomainEvent) -> None:
        """Publish a domain event to the underlying transport or storage."""
        ...


class EventJournal(IEventPublisher):
    """Local, append-only JSONL event journal with sequencing and hash-chaining integrity.

    Persists DomainEvent records to a local file, one JSON object per line.
    Guarantees thread and async safety via an internal asyncio lock and synchronous OS write/flush.
    Maintains sequence counters and SHA-256 hash chains for tamper-evident auditability.
    """

    def __init__(self, file_path: str | Path = "data/events.jsonl") -> None:
        self.file_path = Path(file_path)
        self._lock = asyncio.Lock()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_sequence: int = 0
        self._last_hash: str | None = None
        self._init_state_from_disk()

    def _init_state_from_disk(self) -> None:
        """Initialize sequence and hash state from existing journal file on disk."""
        if not self.file_path.exists():
            return
        try:
            events = self.read_all(skip_malformed=True)
            if events:
                last = events[-1]
                if last.sequence_number is not None:
                    self._last_sequence = last.sequence_number
                else:
                    self._last_sequence = len(events)
                self._last_hash = last.event_hash
        except Exception as e:
            logger.warning("Could not initialize sequence state from %s: %s", self.file_path, e)

    async def append(self, event: DomainEvent) -> DomainEvent:
        """Append a single DomainEvent to the JSONL journal with sequencing and integrity."""
        async with self._lock:
            # Attach sequence and hash if not already populated
            if event.sequence_number is None or event.event_hash is None:
                seq = self._last_sequence + 1
                prev_hash = self._last_hash or ""
                stamped_event = event.with_integrity(sequence_number=seq, previous_hash=prev_hash)
            else:
                stamped_event = event

            self._last_sequence = stamped_event.sequence_number or (self._last_sequence + 1)
            self._last_hash = stamped_event.event_hash

            line = stamped_event.to_jsonl_line()
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()

            return stamped_event

    async def publish(self, event: DomainEvent) -> None:
        """IEventPublisher protocol implementation."""
        await self.append(event)

    def read_all(self, skip_malformed: bool = False) -> list[DomainEvent]:
        """Read all persisted domain events from the journal file.

        Args:
            skip_malformed: If True, log a warning on unparseable lines rather than raising.
        """
        if not self.file_path.exists():
            return []

        events: list[DomainEvent] = []
        with open(self.file_path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                clean_line = line.strip()
                if not clean_line:
                    continue
                try:
                    data = json.loads(clean_line)
                    events.append(DomainEvent.model_validate(data))
                except Exception as e:
                    if skip_malformed:
                        logger.warning(
                            "Skipping malformed event journal line %d in %s: %s",
                            line_no,
                            self.file_path,
                            e,
                        )
                    else:
                        raise ValueError(
                            f"Malformed event at line {line_no} in {self.file_path}: {e}"
                        ) from e
        return events

    def read_filtered(
        self,
        session_id: str | None = None,
        workflow_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[DomainEvent]:
        """Read events filtered by criteria, sorted in journal order up to limit."""
        events = self.read_all(skip_malformed=True)
        filtered: list[DomainEvent] = []
        for ev in events:
            if session_id and ev.session_id != session_id:
                continue
            if workflow_id and ev.workflow_id != workflow_id:
                continue
            if event_type and ev.event_type != event_type:
                continue
            filtered.append(ev)
            if len(filtered) >= limit:
                break
        return filtered

    def verify_integrity(self) -> tuple[bool, list[str]]:
        """Verify sequential ordering, hash chain integrity, and schema compliance.

        Returns:
            Tuple of (is_valid: bool, issues: list[str])
        """
        if not self.file_path.exists():
            return True, []

        events = self.read_all(skip_malformed=True)
        issues: list[str] = []
        seen_ids: set[str] = set()
        expected_prev_hash = ""
        expected_seq = 1

        for idx, ev in enumerate(events, start=1):
            # Check duplicate IDs
            if ev.event_id in seen_ids:
                issues.append(f"Duplicate event_id '{ev.event_id}' at position {idx}")
            seen_ids.add(ev.event_id)

            # Check schema version
            if ev.schema_version != 1:
                issues.append(
                    f"Unsupported schema_version {ev.schema_version} for event {ev.event_id}"
                )

            # Check sequence ordering if sequence_number exists
            if ev.sequence_number is not None:
                if ev.sequence_number != expected_seq and expected_seq > 1:
                    issues.append(
                        f"Sequence gap: expected {expected_seq}, found {ev.sequence_number} at position {idx}"
                    )
                expected_seq = ev.sequence_number + 1

            # Check hash chain if hashes exist
            if ev.event_hash is not None:
                if ev.previous_event_hash != expected_prev_hash and idx > 1:
                    issues.append(
                        f"Hash chain broken at event {ev.event_id} (seq {ev.sequence_number}): "
                        f"expected prev_hash {expected_prev_hash[:8]}..., found {ev.previous_event_hash[:8] if ev.previous_event_hash else 'None'}..."
                    )
                if not ev.verify_hash():
                    issues.append(
                        f"Hash mismatch at event {ev.event_id} (seq {ev.sequence_number}): computed hash differs from stored"
                    )
                expected_prev_hash = ev.event_hash

        return len(issues) == 0, issues

    def clear(self) -> None:
        """Truncate the journal file and reset counters (primarily for test resets)."""
        self._last_sequence = 0
        self._last_hash = None
        if self.file_path.exists():
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.truncate(0)

    def count(self) -> int:
        """Return total count of recorded events."""
        return len(self.read_all(skip_malformed=True))


# Type alias for descriptive architectural naming
AppendOnlyEventJournal = EventJournal


def read_filtered(
    file_path: str | Path,
    session_id: str | None = None,
    workflow_id: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
) -> list[DomainEvent]:
    """Helper function to read filtered events from an event journal file."""
    journal = EventJournal(file_path=file_path)
    return journal.read_filtered(
        session_id=session_id,
        workflow_id=workflow_id,
        event_type=event_type,
        limit=limit,
    )
