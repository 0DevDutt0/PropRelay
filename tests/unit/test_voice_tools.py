"""Unit tests for LiveKit voice tool wrappers."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from proprelay.agent.tools import (
    BookShowingOutput,
    CreateLeadOutput,
    GetAvailableShowingsOutput,
    GetPropertyDetailsOutput,
    SearchPropertiesOutput,
    ToolResult,
)
from proprelay.agent.voice_tools import create_voice_tools
from proprelay.domain.models import (
    Booking,
    BookingStatus,
    Property,
)


@pytest.fixture
def mock_agent_tools() -> MagicMock:
    tools = MagicMock()
    tools.search_properties = AsyncMock(
        return_value=ToolResult(
            success=True,
            data=SearchPropertiesOutput(total_count=0, properties=[]),
            message="Found 0 properties",
        )
    )
    tools.get_property_details = AsyncMock(
        return_value=ToolResult(
            success=True,
            data=GetPropertyDetailsOutput(
                property=Property(
                    property_id="prop-101",
                    title="Modern Loft",
                    address="123 Main St",
                    city="Austin",
                    neighborhood="Downtown",
                    monthly_rent=2500,
                    bedrooms=1,
                    bathrooms=1.0,
                    square_feet=750,
                    pets_allowed=True,
                    description="Loft",
                    amenities=["Gym", "Pool"],
                    supports_showings=True,
                )
            ),
            message="Found details",
        )
    )
    tools.get_available_showings = AsyncMock(
        return_value=ToolResult(
            success=True,
            data=GetAvailableShowingsOutput(property_id="prop-101", total_available=0, slots=[]),
            message="0 slots",
        )
    )
    tools.book_showing = AsyncMock(
        return_value=ToolResult(
            success=True,
            data=BookShowingOutput(
                booking=Booking(
                    booking_id="book-101",
                    property_id="prop-101",
                    slot_id="slot-01",
                    renter_name="Jane Renter",
                    status=BookingStatus.CONFIRMED,
                    created_at=datetime.datetime(2026, 9, 23, 10, 0),
                    idempotency_key="key-1",
                )
            ),
            message="Booked",
        )
    )
    tools.reschedule_showing = AsyncMock(
        return_value=ToolResult(
            success=True,
            data=BookShowingOutput(
                booking=Booking(
                    booking_id="book-101",
                    property_id="prop-101",
                    slot_id="slot-02",
                    renter_name="Jane Renter",
                    status=BookingStatus.CONFIRMED,
                    created_at=datetime.datetime(2026, 9, 23, 10, 0),
                    idempotency_key="key-2",
                )
            ),
            message="Rescheduled",
        )
    )
    tools.cancel_showing = AsyncMock(
        return_value=ToolResult(
            success=True,
            data=BookShowingOutput(
                booking=Booking(
                    booking_id="book-101",
                    property_id="prop-101",
                    slot_id="slot-01",
                    renter_name="Jane Renter",
                    status=BookingStatus.CANCELLED,
                    created_at=datetime.datetime(2026, 9, 23, 10, 0),
                    idempotency_key="key-1",
                )
            ),
            message="Cancelled",
        )
    )
    tools.confirm_pending_action = AsyncMock(
        return_value=ToolResult(
            success=True,
            data={"status": "confirmed"},
            message="Confirmed",
        )
    )
    tools.cancel_pending_action = AsyncMock(
        return_value=ToolResult(
            success=True,
            data={"status": "cancelled"},
            message="Cancelled",
        )
    )
    tools.create_lead = AsyncMock(
        return_value=ToolResult(
            success=True,
            data=CreateLeadOutput(
                lead_id="lead-1", created_at=datetime.datetime(2026, 9, 23, 10, 0)
            ),
            message="Created lead",
        )
    )
    return tools


def test_tool_count_and_names(mock_agent_tools: MagicMock) -> None:
    tools = create_voice_tools(mock_agent_tools, session_id="sess-1")
    assert len(tools) == 9
    names = [t.info.name for t in tools]
    assert "search_properties" in names
    assert "get_property_details" in names
    assert "get_available_showings" in names
    assert "book_showing" in names
    assert "reschedule_showing" in names
    assert "cancel_showing" in names
    assert "confirm_pending_action" in names
    assert "cancel_pending_action" in names
    assert "create_lead" in names


@pytest.mark.asyncio
async def test_search_properties_delegation(mock_agent_tools: MagicMock) -> None:
    tools = {t.info.name: t for t in create_voice_tools(mock_agent_tools, session_id="sess-1")}
    tool = tools["search_properties"]

    result = await tool(location="Downtown", max_rent=3000, bedrooms=2, pets_allowed=True)
    assert isinstance(result, dict)
    assert result["success"] is True

    mock_agent_tools.search_properties.assert_called_once()
    call_args = mock_agent_tools.search_properties.call_args
    params = call_args[0][0]
    assert params.location == "Downtown"
    assert params.max_rent == 3000
    assert params.bedrooms == 2
    assert params.pets_allowed is True
    assert call_args[1]["session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_get_property_details_delegation(mock_agent_tools: MagicMock) -> None:
    tools = {t.info.name: t for t in create_voice_tools(mock_agent_tools, session_id="sess-1")}
    tool = tools["get_property_details"]

    result = await tool(property_id="prop-101")
    assert isinstance(result, dict)
    assert result["success"] is True
    mock_agent_tools.get_property_details.assert_called_once()
    params = mock_agent_tools.get_property_details.call_args[0][0]
    assert params.property_id == "prop-101"


@pytest.mark.asyncio
async def test_get_available_showings_delegation(mock_agent_tools: MagicMock) -> None:
    tools = {t.info.name: t for t in create_voice_tools(mock_agent_tools, session_id="sess-1")}
    tool = tools["get_available_showings"]

    result = await tool(property_id="prop-101", date="2026-10-05")
    assert isinstance(result, dict)
    assert result["success"] is True
    mock_agent_tools.get_available_showings.assert_called_once()
    params = mock_agent_tools.get_available_showings.call_args[0][0]
    assert params.property_id == "prop-101"
    assert params.date == datetime.date(2026, 10, 5)


@pytest.mark.asyncio
async def test_book_showing_delegation(mock_agent_tools: MagicMock) -> None:
    tools = {t.info.name: t for t in create_voice_tools(mock_agent_tools, session_id="sess-1")}
    tool = tools["book_showing"]

    result = await tool(
        property_id="prop-101",
        slot_id="slot-01",
        renter_name="Jane Renter",
        renter_phone="555-1234",
        renter_email="jane@example.com",
        expected_date="2026-10-05",
    )
    assert isinstance(result, dict)
    assert result["success"] is True
    mock_agent_tools.book_showing.assert_called_once()
    params = mock_agent_tools.book_showing.call_args[0][0]
    assert params.property_id == "prop-101"
    assert params.slot_id == "slot-01"
    assert params.renter_name == "Jane Renter"
    assert params.expected_date == datetime.date(2026, 10, 5)


@pytest.mark.asyncio
async def test_create_lead_delegation(mock_agent_tools: MagicMock) -> None:
    tools = {t.info.name: t for t in create_voice_tools(mock_agent_tools, session_id="sess-1")}
    tool = tools["create_lead"]

    result = await tool(
        name="Alex Smith",
        phone="555-5678",
        budget=2800,
        preferred_neighborhood="Downtown",
    )
    assert isinstance(result, dict)
    assert result["success"] is True
    mock_agent_tools.create_lead.assert_called_once()
    params = mock_agent_tools.create_lead.call_args[0][0]
    assert params.name == "Alex Smith"
    assert params.budget == 2800


@pytest.mark.asyncio
async def test_reschedule_showing_delegation(mock_agent_tools: MagicMock) -> None:
    tools = {t.info.name: t for t in create_voice_tools(mock_agent_tools, session_id="sess-1")}
    tool = tools["reschedule_showing"]

    result = await tool(
        booking_id="book-101",
        new_slot_id="slot-02",
        renter_name="Jane Renter",
        expected_date="2026-10-06",
        confirmed=True,
    )
    assert isinstance(result, dict)
    assert result["success"] is True
    mock_agent_tools.reschedule_showing.assert_called_once()
    params = mock_agent_tools.reschedule_showing.call_args[0][0]
    assert params.booking_id == "book-101"
    assert params.new_slot_id == "slot-02"
    assert params.confirmed is True


@pytest.mark.asyncio
async def test_cancel_showing_delegation(mock_agent_tools: MagicMock) -> None:
    tools = {t.info.name: t for t in create_voice_tools(mock_agent_tools, session_id="sess-1")}
    tool = tools["cancel_showing"]

    result = await tool(
        booking_id="book-101",
        renter_name="Jane Renter",
        reason="Found another place",
        confirmed=True,
    )
    assert isinstance(result, dict)
    assert result["success"] is True
    mock_agent_tools.cancel_showing.assert_called_once()
    params = mock_agent_tools.cancel_showing.call_args[0][0]
    assert params.booking_id == "book-101"
    assert params.reason == "Found another place"
    assert params.confirmed is True


@pytest.mark.asyncio
async def test_confirm_pending_action_delegation(mock_agent_tools: MagicMock) -> None:
    tools = {t.info.name: t for t in create_voice_tools(mock_agent_tools, session_id="sess-1")}
    tool = tools["confirm_pending_action"]

    result = await tool()
    assert isinstance(result, dict)
    assert result["success"] is True
    mock_agent_tools.confirm_pending_action.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_pending_action_delegation(mock_agent_tools: MagicMock) -> None:
    tools = {t.info.name: t for t in create_voice_tools(mock_agent_tools, session_id="sess-1")}
    tool = tools["cancel_pending_action"]

    result = await tool(reason="Changed mind")
    assert isinstance(result, dict)
    assert result["success"] is True
    mock_agent_tools.cancel_pending_action.assert_called_once()
