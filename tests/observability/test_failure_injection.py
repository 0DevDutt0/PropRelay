"""Tests for fault injection, simulated failure modes, and recovery."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from proprelay.agent.tools import AgentTools, SearchPropertiesInput
from proprelay.domain.clock import SystemClock
from proprelay.domain.policy import BookingPolicyService
from proprelay.domain.repositories import (
    InMemoryBookingRepository,
    InMemoryLeadRepository,
    InMemoryPropertyRepository,
    InMemoryShowingRepository,
)
from proprelay.events.broadcaster import LiveKitEventBroadcaster
from proprelay.events.journal import AppendOnlyEventJournal
from proprelay.events.schemas import DomainEvent, EventType
from proprelay.testing.failure_injection import (
    FailureMode,
    InjectedPublishError,
    get_active_failure,
    inject_failure,
    should_inject_failure,
)


@pytest.fixture
def mock_agent_tools(tmp_path):
    prop_repo = InMemoryPropertyRepository([])
    show_repo = InMemoryShowingRepository([])
    book_repo = InMemoryBookingRepository()
    lead_repo = InMemoryLeadRepository()
    clock = SystemClock()
    policy = BookingPolicyService(prop_repo, show_repo, book_repo, clock)
    journal = AppendOnlyEventJournal(tmp_path / "events.jsonl")

    return AgentTools(
        property_repo=prop_repo,
        showing_repo=show_repo,
        booking_repo=book_repo,
        lead_repo=lead_repo,
        booking_policy=policy,
        event_publisher=journal,
        clock=clock,
    )


def test_failure_modes_and_scopes():
    assert should_inject_failure(FailureMode.TOOL) is False

    with inject_failure(FailureMode.TOOL):
        assert should_inject_failure(FailureMode.TOOL) is True
        assert should_inject_failure(FailureMode.STT) is False
        assert get_active_failure() == "tool"

    assert should_inject_failure(FailureMode.TOOL) is False
    assert get_active_failure() is None


def test_environment_variable_failure_injection(monkeypatch):
    assert should_inject_failure(FailureMode.STT) is False

    monkeypatch.setenv("PROPRELAY_INJECT_FAILURE", "stt")
    assert should_inject_failure(FailureMode.STT) is True
    assert should_inject_failure(FailureMode.TOOL) is False

    monkeypatch.delenv("PROPRELAY_INJECT_FAILURE", raising=False)
    assert should_inject_failure(FailureMode.STT) is False


@pytest.mark.asyncio
async def test_tool_failure_injection_and_recovery(mock_agent_tools):
    # Under failure injection
    with inject_failure(FailureMode.TOOL):
        res = await mock_agent_tools.search_properties(SearchPropertiesInput(location="Downtown"))
        assert res.success is False
        assert res.error_code == "TOOL_ERROR"
        assert "Injected synthetic tool execution failure" in res.message

    # Normal recovery outside context
    res_normal = await mock_agent_tools.search_properties(
        SearchPropertiesInput(location="Downtown")
    )
    assert res_normal.success is True
    assert res_normal.error_code is None


@pytest.mark.asyncio
async def test_publish_failure_injection():
    mock_room = MagicMock()
    broadcaster = LiveKitEventBroadcaster(room=mock_room)
    test_event = DomainEvent(
        event_type=EventType.WORKFLOW_STARTED.value,
        payload={},
    )

    with (
        inject_failure(FailureMode.PUBLISH),
        pytest.raises(InjectedPublishError, match="Simulated data packet drop"),
    ):
        await broadcaster.publish(test_event)

    # Outside injection, room connection check runs without exception
    mock_room.isconnected.return_value = False
    await broadcaster.publish(test_event)
