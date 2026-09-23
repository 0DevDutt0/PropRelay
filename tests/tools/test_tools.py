"""Unit and integration tests for typed AgentTools, error envelopes, and event emission ordering."""

from __future__ import annotations

import datetime

import pytest

from proprelay.agent.tools import (
    AgentTools,
    BookShowingInput,
    CreateLeadInput,
    GetAvailableShowingsInput,
    GetPropertyDetailsInput,
    SearchPropertiesInput,
)
from proprelay.events.journal import EventJournal
from proprelay.events.schemas import EventType


@pytest.mark.asyncio
async def test_tool_search_properties(
    agent_tools: AgentTools,
    event_journal: EventJournal,
) -> None:
    # 1. Search with matching criteria
    res = await agent_tools.search_properties(
        SearchPropertiesInput(location="Downtown", max_rent=3000),
        correlation_id="corr-search-1",
    )
    assert res.success is True
    assert res.data is not None
    assert res.data.total_count == 1
    assert res.data.properties[0].property_id == "test-prop-1"

    # Verify event emission: tool started, property.search.completed, tool completed
    events = event_journal.read_all()
    event_types = [e.event_type for e in events]
    assert EventType.AGENT_TOOL_STARTED.value in event_types
    assert EventType.PROPERTY_SEARCH_COMPLETED.value in event_types
    assert EventType.AGENT_TOOL_COMPLETED.value in event_types


@pytest.mark.asyncio
async def test_tool_search_properties_empty(
    agent_tools: AgentTools,
) -> None:
    res = await agent_tools.search_properties(
        SearchPropertiesInput(location="NonExistentCity"),
    )
    assert res.success is True
    assert res.data is not None
    assert res.data.total_count == 0


@pytest.mark.asyncio
async def test_tool_get_property_details_success(
    agent_tools: AgentTools,
    event_journal: EventJournal,
) -> None:
    res = await agent_tools.get_property_details(
        GetPropertyDetailsInput(property_id="test-prop-1"),
    )
    assert res.success is True
    assert res.data is not None
    assert res.data.property.property_id == "test-prop-1"

    events = event_journal.read_all()
    event_types = [e.event_type for e in events]
    assert EventType.PROPERTY_DETAILS_VIEWED.value in event_types


@pytest.mark.asyncio
async def test_tool_get_property_details_not_found(
    agent_tools: AgentTools,
    event_journal: EventJournal,
) -> None:
    res = await agent_tools.get_property_details(
        GetPropertyDetailsInput(property_id="unknown-prop"),
    )
    assert res.success is False
    assert res.error_code == "PROPERTY_NOT_FOUND"

    events = event_journal.read_all()
    event_types = [e.event_type for e in events]
    assert EventType.AGENT_TOOL_FAILED.value in event_types


@pytest.mark.asyncio
async def test_tool_get_available_showings(
    agent_tools: AgentTools,
    event_journal: EventJournal,
) -> None:
    res = await agent_tools.get_available_showings(
        GetAvailableShowingsInput(
            property_id="test-prop-1",
            date=datetime.date(2026, 10, 1),
        )
    )
    assert res.success is True
    assert res.data is not None
    # On 2026-10-01, slot-test-01 and slot-test-02 are available (slot-test-booked is booked)
    assert res.data.total_available == 2

    events = event_journal.read_all()
    event_types = [e.event_type for e in events]
    assert EventType.SHOWING_AVAILABILITY_CHECKED.value in event_types


@pytest.mark.asyncio
async def test_tool_book_showing_success_and_event_ordering(
    agent_tools: AgentTools,
    event_journal: EventJournal,
) -> None:
    event_journal.clear()

    res = await agent_tools.book_showing(
        BookShowingInput(
            property_id="test-prop-1",
            slot_id="slot-test-01",
            renter_name="John Renter",
            renter_phone="555-4321",
        ),
        correlation_id="corr-book-1",
    )
    assert res.success is True
    assert res.data is not None
    assert res.data.booking.renter_name == "John Renter"
    assert res.data.is_idempotent is False

    # Event ordering verification:
    # 1. agent.tool.started
    # 2. showing.booking.requested
    # 3. showing.booked (ONLY AFTER mutation)
    # 4. agent.tool.completed
    events = event_journal.read_all()
    event_types = [e.event_type for e in events]

    assert event_types == [
        EventType.AGENT_TOOL_STARTED.value,
        EventType.SHOWING_BOOKING_REQUESTED.value,
        EventType.SHOWING_BOOKED.value,
        EventType.AGENT_TOOL_COMPLETED.value,
    ]


@pytest.mark.asyncio
async def test_tool_book_showing_rejection_and_event_ordering(
    agent_tools: AgentTools,
    event_journal: EventJournal,
) -> None:
    event_journal.clear()

    # Attempt to book already booked slot
    res = await agent_tools.book_showing(
        BookShowingInput(
            property_id="test-prop-1",
            slot_id="slot-test-booked",
            renter_name="Jane Renter",
        )
    )
    assert res.success is False
    assert res.error_code == "SLOT_UNAVAILABLE"

    # Rejection event ordering:
    # 1. agent.tool.started
    # 2. showing.booking.requested
    # 3. showing.booking.rejected
    # 4. agent.tool.failed
    events = event_journal.read_all()
    event_types = [e.event_type for e in events]

    assert event_types == [
        EventType.AGENT_TOOL_STARTED.value,
        EventType.SHOWING_BOOKING_REQUESTED.value,
        EventType.SHOWING_BOOKING_REJECTED.value,
        EventType.AGENT_TOOL_FAILED.value,
    ]
    # Invariant: showing.booked MUST NEVER be emitted on rejection
    assert EventType.SHOWING_BOOKED.value not in event_types


@pytest.mark.asyncio
async def test_tool_book_showing_idempotency(
    agent_tools: AgentTools,
) -> None:
    input_data = BookShowingInput(
        property_id="test-prop-1",
        slot_id="slot-test-02",
        renter_name="Alice Wonder",
    )
    # Call 1
    res1 = await agent_tools.book_showing(input_data)
    assert res1.success is True
    assert res1.data is not None
    assert res1.data.is_idempotent is False
    b1_id = res1.data.booking.booking_id

    # Call 2 (exact duplicate)
    res2 = await agent_tools.book_showing(input_data)
    assert res2.success is True
    assert res2.data is not None
    assert res2.data.is_idempotent is True
    assert res2.data.booking.booking_id == b1_id


@pytest.mark.asyncio
async def test_tool_create_lead(
    agent_tools: AgentTools,
    event_journal: EventJournal,
) -> None:
    res = await agent_tools.create_lead(
        CreateLeadInput(
            name="Marcus Vance",
            phone="555-8888",
            email="marcus@example.com",
            preferred_neighborhood="Downtown",
            budget=2800,
            interested_property_id="test-prop-1",
            notes="Wants ground floor",
        )
    )
    assert res.success is True
    assert res.data is not None
    assert res.data.lead_id.startswith("lead-")

    events = event_journal.read_all()
    event_types = [e.event_type for e in events]
    assert EventType.LEAD_CREATED.value in event_types


@pytest.mark.asyncio
async def test_tool_create_lead_missing_name(
    agent_tools: AgentTools,
) -> None:
    res = await agent_tools.create_lead(CreateLeadInput(name="   "))
    assert res.success is False
    assert res.error_code == "MISSING_LEAD_NAME"
