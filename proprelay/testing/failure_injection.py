"""Controlled test-only failure injection hooks for fault tolerance and recovery evaluation."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from enum import StrEnum


class FailureMode(StrEnum):
    """Categorization of failure injection points."""

    NONE = "none"
    STT = "stt"
    LLM = "llm"
    TTS = "tts"
    TOOL = "tool"
    PUBLISH = "publish"


class InjectedFaultError(Exception):
    """Base exception for deliberately injected test failures."""


class InjectedSTTError(InjectedFaultError):
    """Injected STT audio transcription failure."""


class InjectedLLMError(InjectedFaultError):
    """Injected LLM inference generation failure."""


class InjectedTTSError(InjectedFaultError):
    """Injected TTS synthesis failure."""


class InjectedToolError(InjectedFaultError):
    """Injected agent tool execution failure."""


class InjectedPublishError(InjectedFaultError):
    """Injected WebRTC data channel packet broadcast failure."""


# Thread-safe thread-local or contextual override
_active_failure_override: str | None = None


def set_active_failure(mode: FailureMode | str | None) -> None:
    """Set process-wide synthetic failure injection mode."""
    global _active_failure_override
    if mode is None:
        _active_failure_override = None
    elif isinstance(mode, FailureMode):
        _active_failure_override = mode.value
    else:
        _active_failure_override = str(mode).lower()


def get_active_failure() -> str | None:
    """Get active failure injection mode, checking context override then environment."""
    if _active_failure_override is not None:
        return _active_failure_override
    env_val = os.getenv("PROPRELAY_INJECT_FAILURE")
    return env_val.strip().lower() if env_val else None


def should_inject_failure(mode: FailureMode | str) -> bool:
    """Check if the given failure mode is currently requested for injection."""
    active = get_active_failure()
    target = mode.value if isinstance(mode, FailureMode) else str(mode).lower()
    return active == target


@contextlib.contextmanager
def inject_failure(mode: FailureMode | str) -> Iterator[None]:
    """Scoped context manager for injecting a specific fault during test execution.

    Example:
        with inject_failure(FailureMode.TOOL):
            res = await agent_tools.search_properties(...)
            assert not res.success
    """
    previous = get_active_failure()
    set_active_failure(mode)
    try:
        yield
    finally:
        set_active_failure(previous)
