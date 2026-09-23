"""Tests for DomainEvent schemas, cryptographic hash-chaining, sequencing, and PII masking."""

from __future__ import annotations

from proprelay.events.schemas import DomainEvent, EventType, mask_pii_payload


def test_domain_event_defaults_and_version():
    event = DomainEvent(
        event_type=EventType.WORKFLOW_STARTED.value,
        payload={"query": "2 bedroom apartment"},
    )
    assert event.schema_version == 1
    assert event.event_id is not None
    assert event.timestamp is not None
    assert event.sequence_number is None
    assert event.event_hash is None


def test_hash_chaining_and_verification():
    # Genesis event
    ev1 = DomainEvent(
        event_type=EventType.SESSION_STARTED.value,
        payload={"user": "tenant"},
        session_id="sess-100",
    ).with_integrity(sequence_number=1, previous_hash="")

    assert ev1.sequence_number == 1
    assert ev1.previous_event_hash == ""
    assert ev1.event_hash is not None
    assert ev1.verify_hash() is True

    # Chained second event
    ev2 = DomainEvent(
        event_type=EventType.PROPERTY_DETAILS_VIEWED.value,
        payload={"property_id": "prop-101"},
        session_id="sess-100",
    ).with_integrity(sequence_number=2, previous_hash=ev1.event_hash)

    assert ev2.sequence_number == 2
    assert ev2.previous_event_hash == ev1.event_hash
    assert ev2.event_hash is not None
    assert ev2.verify_hash() is True
    assert ev2.event_hash != ev1.event_hash


def test_tamper_detection_in_event():
    ev = DomainEvent(
        event_type=EventType.SHOWING_BOOKED.value,
        payload={"slot_id": "slot-1", "rent": 2400},
        session_id="sess-100",
    ).with_integrity(sequence_number=1, previous_hash="")

    assert ev.verify_hash() is True

    # Tampering with payload
    tampered_dict = ev.model_dump()
    tampered_dict["payload"]["rent"] = 1200
    tampered_ev = DomainEvent.model_validate(tampered_dict)
    assert tampered_ev.verify_hash() is False

    # Tampering with sequence number
    tampered_seq = ev.model_dump()
    tampered_seq["sequence_number"] = 99
    tampered_seq_ev = DomainEvent.model_validate(tampered_seq)
    assert tampered_seq_ev.verify_hash() is False


def test_pii_masking_comprehensive():
    raw_payload = {
        "renter_name": "Alexander Hamilton",
        "renter_email": "alex@example.com",
        "renter_phone": "+1 (555) 123-4567",
        "ssn": "123-45-6789",
        "property_id": "prop-101",
        "monthly_rent": 3200,
        "nested": {
            "applicant_name": "Eliza Schuyler",
            "contact_email": "eliza@example.org",
        },
    }

    masked = mask_pii_payload(raw_payload)

    # Specific key redactions
    assert masked["renter_name"] == "[REDACTED_NAME]"
    assert masked["renter_email"] == "a***@example.com"
    assert masked["renter_phone"] == "***-***-4567"
    assert masked["ssn"] == "[REDACTED_SSN]"

    # Non-sensitive domain data untouched
    assert masked["property_id"] == "prop-101"
    assert masked["monthly_rent"] == 3200

    # Recursive nested masking
    assert masked["nested"]["applicant_name"] == "[REDACTED_NAME]"
    assert masked["nested"]["contact_email"] == "e***@example.org"
