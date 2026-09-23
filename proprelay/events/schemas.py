"""Domain event schemas, sequencing, correlation, and integrity definitions for PropRelay."""

from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    """Standardized event type names emitted across the PropRelay lifecycle."""

    # Session lifecycle events
    SESSION_STARTED = "session.started"
    SESSION_COMPLETED = "session.completed"

    # Property discovery events
    PROPERTY_SEARCH_COMPLETED = "property.search.completed"
    PROPERTY_DETAILS_VIEWED = "property.details.viewed"

    # Showing availability & booking events
    SHOWING_AVAILABILITY_CHECKED = "showing.availability.checked"
    SHOWING_BOOKING_REQUESTED = "showing.booking.requested"
    SHOWING_BOOKED = "showing.booked"
    SHOWING_BOOKING_REJECTED = "showing.booking.rejected"
    SHOWING_RESCHEDULE_REQUESTED = "showing.reschedule.requested"
    SHOWING_RESCHEDULED = "showing.rescheduled"
    SHOWING_CANCELLATION_REQUESTED = "showing.cancellation.requested"
    SHOWING_CANCELLED = "showing.cancelled"

    # Action safety & confirmation events
    BOOKING_CONFIRMATION_REQUESTED = "booking.confirmation.requested"
    BOOKING_CONFIRMATION_ACCEPTED = "booking.confirmation.accepted"
    BOOKING_CONFIRMATION_DECLINED = "booking.confirmation.declined"

    # Workflow lifecycle events
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_STATE_CHANGED = "workflow.state.changed"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_ABANDONED = "workflow.abandoned"

    # Lead capture events
    LEAD_CREATED = "lead.created"

    # Agent tool lifecycle events
    AGENT_TOOL_STARTED = "agent.tool.started"
    AGENT_TOOL_COMPLETED = "agent.tool.completed"
    AGENT_TOOL_FAILED = "agent.tool.failed"

    # Voice runtime & observability events
    VOICE_STATE_CHANGED = "voice.state.changed"
    VOICE_TRANSCRIPT_USER = "voice.transcript.user"
    VOICE_TRANSCRIPT_AGENT = "voice.transcript.agent"
    VOICE_LATENCY_METRICS = "voice.latency.metrics"

    # Structured error events
    SYSTEM_ERROR = "system.error"


def _mask_value(key: str, val: Any) -> Any:
    """Mask potentially sensitive PII or credential fields."""
    if not isinstance(val, str):
        return val
    lower_k = key.lower()
    if any(s in lower_k for s in ("phone", "telephone")):
        return f"***-***-{val[-4:]}" if len(val) >= 4 else "***"
    if any(s in lower_k for s in ("email", "mail")):
        parts = val.split("@")
        if len(parts) == 2 and len(parts[0]) > 1:
            return f"{parts[0][0]}***@{parts[1]}"
        return "***@***"
    if any(s in lower_k for s in ("secret", "token", "password", "key")):
        return "***REDACTED***"
    if any(s in lower_k for s in ("ssn", "social")):
        return "[REDACTED_SSN]"
    if (
        any(s in lower_k for s in ("name", "renter_name", "applicant_name"))
        and "property" not in lower_k
        and "room" not in lower_k
        and "file" not in lower_k
        and "tool" not in lower_k
        and "user" not in lower_k
    ):
        return "[REDACTED_NAME]"
    return val


def mask_pii_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask sensitive renter PII and credentials in a dictionary."""
    masked: dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, dict):
            masked[k] = mask_pii_payload(v)
        elif isinstance(v, list):
            masked[k] = [
                mask_pii_payload(item) if isinstance(item, dict) else _mask_value(k, item)
                for item in v
            ]
        else:
            masked[k] = _mask_value(k, v)
    return masked


class DomainEvent(BaseModel):
    """Immutable event envelope representing an authoritative state change or telemetry record.

    Includes explicit correlation (session_id -> workflow_id -> turn_id -> tool_name -> event_id),
    sequence ordering, schema versioning, and lightweight append-only hash chaining.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(
        default=1, description="Event envelope schema version for forward compatibility"
    )
    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique event UUID"
    )
    event_type: str = Field(..., description="Canonical dot-delimited event name")
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="UTC event occurrence timestamp",
    )
    sequence_number: int | None = Field(
        default=None, description="Monotonically increasing sequence number within session/journal"
    )
    correlation_id: str | None = Field(
        default=None, description="Traces an external or cross-service user request chain"
    )
    session_id: str | None = Field(default=None, description="Voice/WebRTC session identifier")
    workflow_id: str | None = Field(
        default=None, description="Multi-turn workflow execution identifier"
    )
    turn_id: str | None = Field(default=None, description="Conversational turn identifier")
    tool_name: str | None = Field(default=None, description="Associated agent tool name")
    duration_ms: float | None = Field(
        default=None, description="Execution duration in milliseconds"
    )
    previous_event_hash: str | None = Field(
        default=None, description="SHA-256 hash of previous event in journal"
    )
    event_hash: str | None = Field(
        default=None, description="Cryptographic SHA-256 integrity hash of this event"
    )
    payload: dict[str, Any] = Field(default_factory=dict, description="Event-specific payload data")

    def compute_hash(self, previous_hash: str | None = None) -> str:
        """Compute deterministic SHA-256 hash across envelope fields and canonicalized payload."""
        prev = previous_hash if previous_hash is not None else (self.previous_event_hash or "")
        canonical_dict = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "sequence_number": self.sequence_number,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "turn_id": self.turn_id,
            "tool_name": self.tool_name,
            "correlation_id": self.correlation_id,
            "previous_event_hash": prev,
            "payload": self.payload,
        }
        encoded = json.dumps(canonical_dict, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def with_integrity(
        self,
        sequence_number: int | None = None,
        previous_hash: str | None = None,
    ) -> DomainEvent:
        """Return a new copy of the event with sequence number and computed hash attached."""
        seq = sequence_number if sequence_number is not None else self.sequence_number
        prev = previous_hash if previous_hash is not None else self.previous_event_hash
        # First assign sequence and previous hash to compute hash correctly
        temp = self.model_copy(
            update={
                "sequence_number": seq,
                "previous_event_hash": prev,
                "event_hash": None,
            }
        )
        chash = temp.compute_hash(previous_hash=prev)
        return temp.model_copy(update={"event_hash": chash})

    def verify_hash(self) -> bool:
        """Verify that the stored event_hash matches the computed hash."""
        if not self.event_hash:
            return False
        return self.compute_hash(self.previous_event_hash) == self.event_hash

    def mask_pii_payload(self) -> dict[str, Any]:
        """Return payload with sensitive renter PII and credentials safely masked."""
        return mask_pii_payload(self.payload)

    def to_jsonl_line(self) -> str:
        """Serialize event to a single newline-terminated JSON string."""
        return self.model_dump_json() + "\n"
