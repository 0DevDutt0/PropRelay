# PropRelay — Domain Event Schema & Event Sourcing Specification

## 1. Overview

PropRelay utilizes an immutable, append-only event-driven architecture for state auditability, realtime UI synchronization, and telemetry. Every domain mutation, tool invocation, workflow transition, and latency measurement generates a typed `DomainEvent`.

Durable history is preserved in a local JSONL event journal (`data/events.jsonl`), while a best-effort real-time stream is projected across LiveKit WebRTC data channels (`proprelay.events`).

---

## 2. DomainEvent Schema Specification (v1.0.0)

Every event adheres to the following Pydantic schema:

```json
{
  "event_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "schema_version": "1.0.0",
  "event_type": "showing.booked",
  "timestamp": "2026-09-23T04:15:30.123456Z",
  "session_id": "sess-adef1c6262",
  "workflow_id": "wf-8f2a11b9",
  "sequence_number": 42,
  "previous_event_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "payload": {
    "booking_id": "book-5a12f9",
    "property_id": "prop-001",
    "slot_id": "slot-101",
    "renter_name": "Alice Smith",
    "renter_phone": "+1-555-***-1234",
    "renter_email": "a***e@example.com",
    "showing_time": "2026-10-02T10:00:00Z"
  }
}
```

### Schema Field Definitions

| Field | Type | Description |
| :--- | :--- | :--- |
| `event_id` | `UUIDv4` | Globally unique identifier for deduplication and tracing. |
| `schema_version` | `str` | Version identifier (currently `"1.0.0"`) for forward schema evolution. |
| `event_type` | `str` | Dot-delimited hierarchical event namespace (e.g. `showing.booked`). |
| `timestamp` | `datetime` | High-precision UTC timestamp with fractional seconds. |
| `session_id` | `str` | Voice session identifier linking call audio to domain actions. |
| `workflow_id` | `Optional[str]` | Multi-turn workflow identifier linking related operations. |
| `sequence_number` | `int` | Monotonically increasing sequential index ($0, 1, 2, \dots$). |
| `previous_event_hash` | `str` | SHA-256 digest of the preceding event record (tamper-evident chain). |
| `payload` | `dict[str, Any]` | Typed payload data containing action parameters or outcomes. |

---

## 3. Cryptographic Tamper-Evident Chaining

To guarantee that event logs cannot be retroactively modified, reordered, or deleted, `EventJournal` implements SHA-256 hash chaining:

1. **Genesis Event**: The first event in the journal has `sequence_number = 0` and `previous_event_hash = "0" * 64`.
2. **Successive Events**: Each subsequent event computes:
   $$\text{previous\_event\_hash}_{n} = \text{SHA-256}(\text{canonical\_json}(\text{event}_{n-1}))$$
3. **Integrity Verification**: `EventJournal.verify_integrity()` scans the journal from beginning to end, re-evaluating each hash and sequence number. Any modified byte, swapped line, or truncated record immediately raises an integrity violation error.

---

## 4. Automated PII Redaction

PropRelay enforces privacy compliance by sanitizing Personally Identifiable Information (PII) before records reach the event journal or WebRTC stream:

- **Phone Numbers**: Redacted to mask intermediate digits (e.g. `+1-555-***-5678`).
- **Email Addresses**: Redacted to preserve only the first and last character of the username (e.g. `j***n@domain.com`).
- **Credit Cards / SSN**: Regex patterns detect and redact sensitive identification numbers.

Redaction occurs in-memory inside `proprelay.events.journal.AppendOnlyEventJournal` prior to JSON formatting.

---

## 5. Replay Engine (`proprelay.events.replay`)

The event replay engine reconstructs historical state or inspects session trajectories:

```python
from proprelay.events.replay import EventReplayEngine

replay = EventReplayEngine(journal_path="data/events.jsonl")

# Replay all events for a given session
session_events = replay.get_session_events(session_id="sess-adef1c6262")

# Query with filtering
bookings = replay.filter_events(event_type="showing.booked", start_time="2026-10-01T00:00:00Z")
```

The replay engine is exposed via REST API at `GET /api/events` and visually in the frontend operations console under the **Event Journal & Audit Log** tab.
