"""Lightweight structured logging with PII masking and security safeguards."""

from __future__ import annotations

import datetime
import json
import logging
import re
import sys
from typing import Any

# PII masking patterns
_PHONE_PATTERN = re.compile(r"(\+?\d{1,3}[-.\s]?)?(\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}")
_EMAIL_PATTERN = re.compile(r"([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")


def mask_pii(text: str) -> str:
    """Mask phone numbers and email addresses in log text."""
    if not text:
        return text

    def mask_email(match: re.Match[str]) -> str:
        name, domain = match.groups()
        masked_name = name[0] + "***" if len(name) > 1 else "*"
        return f"{masked_name}@{domain}"

    def mask_phone(match: re.Match[str]) -> str:
        s = match.group(0)
        digits = re.sub(r"\D", "", s)
        if len(digits) >= 4:
            return f"***-***-{digits[-4:]}"
        return "***-****"

    text = _EMAIL_PATTERN.sub(mask_email, text)
    text = _PHONE_PATTERN.sub(mask_phone, text)
    return text


class StructuredLogRecord:
    """Standardized log payload format for PropRelay runtime events."""

    def __init__(
        self,
        component: str,
        event: str,
        level: str = "INFO",
        correlation_id: str | None = None,
        session_id: str | None = None,
        tool_name: str | None = None,
        duration_ms: float | None = None,
        status: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.timestamp = datetime.datetime.now(datetime.UTC).isoformat()
        self.level = level
        self.component = component
        self.event = event
        self.correlation_id = correlation_id
        self.session_id = session_id
        self.tool_name = tool_name
        self.duration_ms = duration_ms
        self.status = status
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "timestamp": self.timestamp,
            "level": self.level,
            "component": self.component,
            "event": self.event,
        }
        if self.correlation_id is not None:
            data["correlation_id"] = self.correlation_id
        if self.session_id is not None:
            data["session_id"] = self.session_id
        if self.tool_name is not None:
            data["tool_name"] = self.tool_name
        if self.duration_ms is not None:
            data["duration_ms"] = round(self.duration_ms, 2)
        if self.status is not None:
            data["status"] = self.status
        if self.details:
            # Mask any PII in details
            cleaned_details: dict[str, Any] = {}
            for k, v in self.details.items():
                if isinstance(v, str):
                    cleaned_details[k] = mask_pii(v)
                else:
                    cleaned_details[k] = v
            data["details"] = cleaned_details
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class StructuredLogger:
    """Logger outputting machine-readable structured JSON lines."""

    def __init__(self, component: str, min_level: int = logging.INFO) -> None:
        self.component = component
        self.min_level = min_level
        self._raw_logger = logging.getLogger(f"proprelay.{component}")
        self._raw_logger.setLevel(min_level)

    def log(
        self,
        event: str,
        level: str = "INFO",
        correlation_id: str | None = None,
        session_id: str | None = None,
        tool_name: str | None = None,
        duration_ms: float | None = None,
        status: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        numeric_level = getattr(logging, level.upper(), logging.INFO)
        if numeric_level < self.min_level:
            return

        rec = StructuredLogRecord(
            component=self.component,
            event=event,
            level=level.upper(),
            correlation_id=correlation_id,
            session_id=session_id,
            tool_name=tool_name,
            duration_ms=duration_ms,
            status=status,
            details=details,
        )
        msg = rec.to_json()
        if numeric_level >= logging.ERROR:
            sys.stderr.write(msg + "\n")
            sys.stderr.flush()
        else:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()

    def info(self, event: str, **kwargs: Any) -> None:
        self.log(event=event, level="INFO", **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self.log(event=event, level="WARNING", **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self.log(event=event, level="ERROR", **kwargs)

    def debug(self, event: str, **kwargs: Any) -> None:
        self.log(event=event, level="DEBUG", **kwargs)


def get_logger(component: str) -> StructuredLogger:
    """Obtain a structured logger for a component."""
    return StructuredLogger(component=component)
