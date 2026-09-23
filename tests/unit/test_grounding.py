"""Unit tests verifying strict grounding against authoritative domain data.

Guarantees:
- Agent tools and context never invent property IDs, prices, amenities, or specs.
- Availability queries strictly ground to calendar repository slots.
- Date normalization resolves relative temporal expressions strictly against injected Clock.
- Reference resolution never fabricates entity references on out-of-bounds indices or unmatched times.
"""

from __future__ import annotations

import datetime

import pytest

from proprelay.agent.date_normalization import normalize_date_expression
from proprelay.agent.tools import (
    AgentTools,
    GetAvailableShowingsInput,
    GetPropertyDetailsInput,
    SearchPropertiesInput,
)
from proprelay.domain.clock import FrozenClock
from proprelay.workflows.context import ConversationContext


@pytest.fixture
def workflow_context() -> ConversationContext:
    return ConversationContext(session_id="test-session-grounding")


@pytest.mark.asyncio
async def test_property_search_and_details_strictly_grounded_to_repo(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
) -> None:
    """Verify that property details strictly match repository records without hallucination."""
    agent_tools.set_context(workflow_context)

    # 1. Search properties
    res = await agent_tools.search_properties(SearchPropertiesInput(location="Downtown"))
    assert res.success
    assert res.data is not None
    assert len(res.data.properties) == 1

    summary = res.data.properties[0]
    repo_prop = await agent_tools._property_repo.get_by_id(summary.property_id)
    assert repo_prop is not None

    # Verify exact grounding
    assert summary.property_id == repo_prop.property_id
    assert summary.title == repo_prop.title
    assert summary.monthly_rent == repo_prop.monthly_rent
    assert summary.bedrooms == repo_prop.bedrooms
    assert summary.bathrooms == repo_prop.bathrooms
    assert summary.square_feet == repo_prop.square_feet
    assert summary.pets_allowed == repo_prop.pets_allowed

    # 2. Query full details
    details_res = await agent_tools.get_property_details(
        GetPropertyDetailsInput(property_id=summary.property_id)
    )
    assert details_res.success
    assert details_res.data is not None
    assert details_res.data.property.amenities == repo_prop.amenities
    assert details_res.data.property.address == repo_prop.address


@pytest.mark.asyncio
async def test_nonexistent_property_id_never_fabricated(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
) -> None:
    """Verify that querying a non-existent property ID returns structured failure rather than fabricated data."""
    agent_tools.set_context(workflow_context)

    res = await agent_tools.get_property_details(
        GetPropertyDetailsInput(property_id="fake-prop-999")
    )
    assert not res.success
    assert res.error_code == "PROPERTY_NOT_FOUND"
    assert res.data is None


@pytest.mark.asyncio
async def test_showing_availability_never_invents_slots(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
) -> None:
    """Verify that showing availability only returns slots physically present in showing repo."""
    agent_tools.set_context(workflow_context)

    res = await agent_tools.get_available_showings(
        GetAvailableShowingsInput(property_id="test-prop-1")
    )
    assert res.success
    assert res.data is not None

    # Every slot must exist in repo and match exactly
    for slot_summary in res.data.slots:
        repo_slot = await agent_tools._showing_repo.get_slot(slot_summary.slot_id)
        assert repo_slot is not None
        assert repo_slot.property_id == "test-prop-1"
        assert repo_slot.date == slot_summary.date
        assert repo_slot.start_time == slot_summary.start_time
        assert repo_slot.end_time == slot_summary.end_time


def test_date_normalization_strictly_anchored_to_frozen_clock(
    frozen_clock: FrozenClock,
) -> None:
    """Verify relative expressions resolve strictly against clock date (2026-10-01), never system clock."""
    # Reference date is Thursday, 2026-10-01
    today_dt = normalize_date_expression("today", frozen_clock.today())
    assert today_dt == datetime.date(2026, 10, 1)

    tomorrow_dt = normalize_date_expression("tomorrow", frozen_clock.today())
    assert tomorrow_dt == datetime.date(2026, 10, 2)

    # Next Friday: Oct 1 is Thursday, so this Friday is Oct 2, next Friday is Oct 9
    friday_dt = normalize_date_expression("Friday", frozen_clock.today())
    assert friday_dt == datetime.date(2026, 10, 2)

    next_friday_dt = normalize_date_expression("next Friday", frozen_clock.today())
    assert next_friday_dt == datetime.date(2026, 10, 9)


@pytest.mark.asyncio
async def test_reference_resolution_out_of_bounds_never_fabricates(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
) -> None:
    """Verify ordinal resolution rejects indices out of bounds (e.g. 5th when only 3 exist)."""
    agent_tools.set_context(workflow_context)

    # Perform search that returns 3 properties
    await agent_tools.search_properties(SearchPropertiesInput())
    assert len(workflow_context.shortlisted_properties) == 3

    # Query "the 5th one"
    res = workflow_context.resolve_property_reference("the 5th one")
    assert res is None

    # Query "the tenth property"
    res_tenth = workflow_context.resolve_property_reference("the tenth property")
    assert res_tenth is None


@pytest.mark.asyncio
async def test_slot_reference_resolution_unmatched_time_never_fabricates(
    agent_tools: AgentTools,
    workflow_context: ConversationContext,
) -> None:
    """Verify slot reference rejects times that do not exist in available slots."""
    agent_tools.set_context(workflow_context)

    await agent_tools.get_available_showings(GetAvailableShowingsInput(property_id="test-prop-1"))
    # Available slots are 10:00 AM and 2:00 PM (14:00) on 2026-10-01 and 11:00 AM on 2026-10-02
    # Match for "7:30 PM" or "8:00 AM" must return None
    matched_8am = workflow_context.resolve_slot_reference("8:00 AM")
    assert matched_8am is None

    matched_night = workflow_context.resolve_slot_reference("night slot")
    assert matched_night is None
