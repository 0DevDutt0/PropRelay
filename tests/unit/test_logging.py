"""Unit tests verifying structured logging and PII masking."""

from __future__ import annotations

import json

import pytest

from proprelay.logging import StructuredLogRecord, mask_pii


def test_pii_masking_phone_and_email() -> None:
    raw_email = "User email is renter.alice@example.com in message."
    masked_email = mask_pii(raw_email)
    assert "renter.alice@example.com" not in masked_email
    assert "@example.com" in masked_email

    raw_phone = "Contact number is 555-867-5309 immediately."
    masked_phone = mask_pii(raw_phone)
    assert "555-867-5309" not in masked_phone
    assert "5309" in masked_phone


def test_structured_log_record_dict_and_json() -> None:
    record = StructuredLogRecord(
        component="agent",
        event="tool.completed",
        level="INFO",
        correlation_id="corr-1",
        session_id="sess-1",
        tool_name="book_showing",
        duration_ms=12.3456,
        status="SUCCESS",
        details={"renter_email": "jane@example.com"},
    )
    d = record.to_dict()
    assert d["component"] == "agent"
    assert d["event"] == "tool.completed"
    assert d["tool_name"] == "book_showing"
    assert d["duration_ms"] == 12.35
    assert d["status"] == "SUCCESS"
    assert "jane@example.com" not in d["details"]["renter_email"]

    js = record.to_json()
    loaded = json.loads(js)
    assert loaded["component"] == "agent"


def test_structured_logger_methods(capsys: pytest.CaptureFixture[str]) -> None:
    from proprelay.logging import get_logger

    logger = get_logger("test_comp")

    logger.info("info_event", details={"msg": "hello"})
    captured = capsys.readouterr()
    assert "info_event" in captured.out

    logger.warning("warn_event")
    captured = capsys.readouterr()
    assert "warn_event" in captured.out

    logger.error("error_event")
    captured = capsys.readouterr()
    assert "error_event" in captured.err

    logger.debug("debug_event")
    # By default, min_level is INFO so debug is suppressed
    captured = capsys.readouterr()
    assert "debug_event" not in captured.out
