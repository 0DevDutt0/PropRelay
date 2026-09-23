"""LiveKit @function_tool wrappers exposing Phase 2/4 typed AgentTools to the voice runtime."""

from __future__ import annotations

import datetime
import logging
from typing import Any

from livekit.agents import llm

from proprelay.agent.date_normalization import normalize_date_expression
from proprelay.agent.tools import (
    AgentTools,
    BookShowingInput,
    CancelShowingInput,
    CreateLeadInput,
    GetAvailableShowingsInput,
    GetPropertyDetailsInput,
    RescheduleShowingInput,
    SearchPropertiesInput,
)

logger = logging.getLogger(__name__)


def create_voice_tools(
    agent_tools: AgentTools,
    session_id: str | None = None,
) -> list[llm.FunctionTool[Any, Any]]:
    """Create LiveKit FunctionTool bindings delegating directly to AgentTools.

    Preserves typed Pydantic models, ToolResult envelopes, action safety, and deterministic policy enforcement.
    """

    @llm.function_tool(
        description=(
            "Search property listings by location/neighborhood, maximum monthly rent in USD, "
            "exact number of bedrooms (0 for studio), and pet allowance. "
            "Call when the user wants to find or filter rental properties. "
            "Do NOT call if the user is asking about an already selected property or scheduling a showing."
        )
    )
    async def search_properties(
        location: str | None = None,
        max_rent: int | None = None,
        bedrooms: int | None = None,
        pets_allowed: bool | None = None,
    ) -> dict[str, Any]:
        """Search available property listings."""
        params = SearchPropertiesInput(
            location=location.strip() if location else None,
            max_rent=max_rent,
            bedrooms=bedrooms,
            pets_allowed=pets_allowed,
        )
        res = await agent_tools.search_properties(params, session_id=session_id)
        return res.model_dump(mode="json")

    @llm.function_tool(
        description=(
            "Retrieve full authoritative listing details for a property. "
            "Accepts a property ID (e.g. 'prop-101') or a reference like 'the first one', "
            "'the second one', 'the cheaper one', or property name from recent search results. "
            "Call when the user asks for details about a listing. Never invent details."
        )
    )
    async def get_property_details(
        property_id: str,
    ) -> dict[str, Any]:
        """Get complete property details."""
        params = GetPropertyDetailsInput(property_id=property_id.strip())
        res = await agent_tools.get_property_details(params, session_id=session_id)
        return res.model_dump(mode="json")

    @llm.function_tool(
        description=(
            "Query available showing calendar slots for a property. "
            "Accepts property ID (or uses current selected property) and optional date "
            "such as 'tomorrow', 'Saturday', 'this weekend', or 'YYYY-MM-DD'. "
            "Call when the user asks when they can see or tour an apartment."
        )
    )
    async def get_available_showings(
        property_id: str | None = None,
        date: str | None = None,
    ) -> dict[str, Any]:
        """Check showing calendar availability."""
        parsed_date: datetime.date | None = None
        if date and date.strip():
            clock_date = agent_tools._clock.today()
            parsed_date = normalize_date_expression(date.strip(), reference_date=clock_date)

        params = GetAvailableShowingsInput(
            property_id=property_id.strip() if property_id else "",
            date=parsed_date,
        )
        res = await agent_tools.get_available_showings(params, session_id=session_id)
        return res.model_dump(mode="json")

    @llm.function_tool(
        description=(
            "Propose or book a property showing slot. "
            "Requires property ID (or current property), slot ID (or time like 'the 3 PM one'), "
            "and the renter's full legal name. "
            "If not yet confirmed, creates a proposal that you must speak to the user to confirm. "
            "Set confirmed=True only after the user has explicitly confirmed the proposal."
        )
    )
    async def book_showing(
        property_id: str | None = None,
        slot_id: str | None = None,
        renter_name: str | None = None,
        renter_phone: str | None = None,
        renter_email: str | None = None,
        expected_date: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Book a property showing slot."""
        parsed_date: datetime.date | None = None
        if expected_date and expected_date.strip():
            clock_date = agent_tools._clock.today()
            parsed_date = normalize_date_expression(
                expected_date.strip(), reference_date=clock_date
            )

        params = BookShowingInput(
            property_id=property_id.strip() if property_id else "",
            slot_id=slot_id.strip() if slot_id else "",
            renter_name=renter_name.strip() if renter_name else "",
            renter_phone=renter_phone.strip() if renter_phone else None,
            renter_email=renter_email.strip() if renter_email else None,
            expected_date=parsed_date,
            confirmed=confirmed,
        )
        res = await agent_tools.book_showing(params, session_id=session_id)
        return res.model_dump(mode="json")

    @llm.function_tool(
        description=(
            "Propose or execute rescheduling of an existing reservation. "
            "Requires booking ID, new slot ID (or time), and renter name. "
            "If confirmed is False, stages proposal for explicit confirmation. "
            "If confirmed is True, commits rescheduling through deterministic policy."
        )
    )
    async def reschedule_showing(
        booking_id: str,
        new_slot_id: str,
        renter_name: str,
        expected_date: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Reschedule an existing showing."""
        parsed_date: datetime.date | None = None
        if expected_date and expected_date.strip():
            clock_date = agent_tools._clock.today()
            parsed_date = normalize_date_expression(
                expected_date.strip(), reference_date=clock_date
            )

        params = RescheduleShowingInput(
            booking_id=booking_id.strip(),
            new_slot_id=new_slot_id.strip(),
            renter_name=renter_name.strip(),
            expected_date=parsed_date,
            confirmed=confirmed,
        )
        res = await agent_tools.reschedule_showing(params, session_id=session_id)
        return res.model_dump(mode="json")

    @llm.function_tool(
        description=(
            "Propose or execute cancellation of an existing reservation. "
            "Requires booking ID and renter name. "
            "If confirmed is False, stages proposal for user confirmation. "
            "If confirmed is True, commits deterministic cancellation and releases slot."
        )
    )
    async def cancel_showing(
        booking_id: str,
        renter_name: str,
        reason: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Cancel an existing showing."""
        params = CancelShowingInput(
            booking_id=booking_id.strip(),
            renter_name=renter_name.strip(),
            reason=reason.strip() if reason else None,
            confirmed=confirmed,
        )
        res = await agent_tools.cancel_showing(params, session_id=session_id)
        return res.model_dump(mode="json")

    @llm.function_tool(
        description=(
            "Commit the currently pending consequential action (booking, reschedule, or cancellation) "
            "after the user explicitly says 'Yes', 'Book it', 'Confirm', 'Go ahead', or 'Please do'. "
            "Do NOT call if there was no preceding proposal or if the user changed topic."
        )
    )
    async def confirm_pending_action() -> dict[str, Any]:
        """Confirm and finalize active pending action."""
        res = await agent_tools.confirm_pending_action(session_id=session_id)
        return res.model_dump(mode="json")

    @llm.function_tool(
        description=(
            "Decline or cancel the currently pending proposal when the user says "
            "'No', 'Cancel that', 'Don't book it', or changes their mind."
        )
    )
    async def cancel_pending_action(
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Cancel active pending proposal."""
        res = await agent_tools.cancel_pending_action(reason=reason, session_id=session_id)
        return res.model_dump(mode="json")

    @llm.function_tool(
        description=(
            "Register prospective renter contact information, district preference, budget, "
            "and conversational notes for agent follow-up."
        )
    )
    async def create_lead(
        name: str,
        phone: str | None = None,
        email: str | None = None,
        preferred_neighborhood: str | None = None,
        budget: int | None = None,
        interested_property_id: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Create prospective renter lead."""
        params = CreateLeadInput(
            name=name.strip(),
            phone=phone.strip() if phone else None,
            email=email.strip() if email else None,
            preferred_neighborhood=preferred_neighborhood.strip()
            if preferred_neighborhood
            else None,
            budget=budget,
            interested_property_id=interested_property_id.strip()
            if interested_property_id
            else None,
            notes=notes.strip() if notes else None,
        )
        res = await agent_tools.create_lead(params, session_id=session_id)
        return res.model_dump(mode="json")

    return [
        search_properties,
        get_property_details,
        get_available_showings,
        book_showing,
        reschedule_showing,
        cancel_showing,
        confirm_pending_action,
        cancel_pending_action,
        create_lead,
    ]
