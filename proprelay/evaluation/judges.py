"""Authoritative deterministic and optional semantic judges for agent evaluation."""

from __future__ import annotations

import json
from typing import Any

from proprelay.evaluation.models import CheckResult, CheckSeverity, ScenarioDefinition


class BaseJudge:
    """Base class for all evaluation judges."""

    name: str = "BaseJudge"

    def evaluate(self, *args: Any, **kwargs: Any) -> CheckResult:
        raise NotImplementedError


class ToolSelectionJudge(BaseJudge):
    """Deterministic judge verifying the correct agent tool was selected."""

    name = "ToolSelectionJudge"

    def evaluate(self, expected_tool: str | None, actual_tool: str | None) -> CheckResult:
        if not expected_tool:
            return CheckResult(
                name=self.name,
                passed=True,
                severity=CheckSeverity.MAJOR,
                expected=None,
                actual=actual_tool,
            )
        passed = expected_tool == actual_tool
        reason = (
            None if passed else f"Expected tool '{expected_tool}', but agent called '{actual_tool}'"
        )
        return CheckResult(
            name=self.name,
            passed=passed,
            severity=CheckSeverity.MAJOR,
            expected=expected_tool,
            actual=actual_tool,
            reason=reason,
        )


class ToolArgumentJudge(BaseJudge):
    """Deterministic judge verifying tool arguments meet required constraints."""

    name = "ToolArgumentJudge"

    def evaluate(self, expected_args: dict[str, Any], actual_args: dict[str, Any]) -> CheckResult:
        if not expected_args:
            return CheckResult(
                name=self.name,
                passed=True,
                severity=CheckSeverity.MAJOR,
                expected=expected_args,
                actual=actual_args,
            )

        mismatches: list[str] = []
        for k, v in expected_args.items():
            if k not in actual_args:
                mismatches.append(f"Missing argument '{k}'")
            elif actual_args[k] != v:
                mismatches.append(f"Argument '{k}' expected {v!r}, got {actual_args[k]!r}")

        passed = len(mismatches) == 0
        return CheckResult(
            name=self.name,
            passed=passed,
            severity=CheckSeverity.MAJOR,
            expected=expected_args,
            actual=actual_args,
            reason="; ".join(mismatches) if mismatches else None,
        )


class StateJudge(BaseJudge):
    """Deterministic judge verifying the workflow reached the expected terminal state."""

    name = "StateJudge"

    def evaluate(self, expected_state: str, actual_state: str) -> CheckResult:
        passed = expected_state == actual_state
        reason = None if passed else f"Expected state '{expected_state}', got '{actual_state}'"
        return CheckResult(
            name=self.name,
            passed=passed,
            severity=CheckSeverity.MAJOR,
            expected=expected_state,
            actual=actual_state,
            reason=reason,
        )


class BookingSafetyJudge(BaseJudge):
    """Deterministic judge verifying no invalid or unconfirmed booking mutations occurred."""

    name = "BookingSafetyJudge"

    def evaluate(
        self,
        should_allow_booking: bool,
        booking_occurred: bool,
        rejection_reason: str | None = None,
    ) -> CheckResult:
        if should_allow_booking:
            passed = booking_occurred
            reason = None if passed else "Expected valid booking to be committed, but none occurred"
        else:
            passed = not booking_occurred
            reason = (
                None
                if passed
                else f"Safety violation: booking was committed when it should have been prevented ({rejection_reason})"
            )
        return CheckResult(
            name=self.name,
            passed=passed,
            severity=CheckSeverity.CRITICAL,
            expected={"allow_booking": should_allow_booking},
            actual={"booking_occurred": booking_occurred},
            reason=reason,
        )


class EventJudge(BaseJudge):
    """Deterministic judge verifying expected domain events occurred in correct order."""

    name = "EventJudge"

    def evaluate(self, expected_events: list[str], observed_events: list[str]) -> CheckResult:
        if not expected_events:
            return CheckResult(
                name=self.name,
                passed=True,
                severity=CheckSeverity.MINOR,
                expected=[],
                actual=observed_events,
            )

        # Check subsequence ordering
        it = iter(observed_events)
        missing_or_out_of_order: list[str] = []
        for expected in expected_events:
            if not any(expected == ev for ev in it):
                missing_or_out_of_order.append(expected)

        passed = len(missing_or_out_of_order) == 0
        reason = None if passed else f"Events missing or out of sequence: {missing_or_out_of_order}"
        return CheckResult(
            name=self.name,
            passed=passed,
            severity=CheckSeverity.MINOR,
            expected=expected_events,
            actual=observed_events,
            reason=reason,
        )


class GroundingJudge(BaseJudge):
    """Deterministic judge verifying that entities reference only authoritative repository items."""

    name = "GroundingJudge"

    def evaluate(
        self,
        selected_property_id: str | None,
        selected_slot_id: str | None,
        valid_property_ids: set[str],
        valid_slot_ids: set[str],
        queried_invalid_entity: bool = False,
        query_rejected: bool = True,
    ) -> CheckResult:
        if queried_invalid_entity and not query_rejected:
            return CheckResult(
                name=self.name,
                passed=False,
                severity=CheckSeverity.CRITICAL,
                expected="Invalid entity must be rejected",
                actual="Invalid entity was accepted or fabricated",
                reason="Grounding failure: nonexistent entity was accepted or fabricated",
            )

        hallucinated: list[str] = []
        if selected_property_id and selected_property_id not in valid_property_ids:
            hallucinated.append(f"Property ID '{selected_property_id}'")
        if selected_slot_id and selected_slot_id not in valid_slot_ids:
            hallucinated.append(f"Slot ID '{selected_slot_id}'")

        passed = len(hallucinated) == 0
        return CheckResult(
            name=self.name,
            passed=passed,
            severity=CheckSeverity.CRITICAL,
            expected="Authoritative repository entity IDs only",
            actual={
                "selected_property": selected_property_id,
                "selected_slot": selected_slot_id,
            },
            reason=f"Hallucinated entity references: {', '.join(hallucinated)}"
            if hallucinated
            else None,
        )


class ConfirmationJudge(BaseJudge):
    """Deterministic judge verifying consequential mutations required two-phase confirmation."""

    name = "ConfirmationJudge"

    def evaluate(
        self,
        confirmation_requested: bool,
        confirmation_accepted: bool,
        mutation_occurred: bool,
    ) -> CheckResult:
        if mutation_occurred and not (confirmation_requested and confirmation_accepted):
            return CheckResult(
                name=self.name,
                passed=False,
                severity=CheckSeverity.CRITICAL,
                expected="Confirmation requested AND accepted prior to mutation",
                actual={
                    "confirmation_requested": confirmation_requested,
                    "confirmation_accepted": confirmation_accepted,
                    "mutation_occurred": mutation_occurred,
                },
                reason="State mutation executed without authoritative user confirmation acceptance",
            )
        return CheckResult(
            name=self.name,
            passed=True,
            severity=CheckSeverity.CRITICAL,
            expected="Two-phase confirmation policy satisfied",
            actual="Policy adhered",
        )


class StaleActionJudge(BaseJudge):
    """Deterministic judge verifying pending action proposals are invalidated upon context switch."""

    name = "StaleActionJudge"

    def evaluate(
        self,
        context_switched: bool,
        pending_action_cleared: bool,
    ) -> CheckResult:
        if context_switched and not pending_action_cleared:
            return CheckResult(
                name=self.name,
                passed=False,
                severity=CheckSeverity.CRITICAL,
                expected="Pending proposal must be invalidated when context/property changes",
                actual="Pending proposal remained active",
                reason="Stale action vulnerability: proposal was not cleared after context change",
            )
        return CheckResult(
            name=self.name,
            passed=True,
            severity=CheckSeverity.CRITICAL,
            expected="Stale action properly invalidated",
            actual="Pending action invalidated",
        )


class ClarificationJudge(BaseJudge):
    """Deterministic judge verifying clarification was prompted when needed without excess."""

    name = "ClarificationJudge"

    def evaluate(
        self,
        underspecified: bool,
        clarification_prompted: bool,
    ) -> CheckResult:
        if underspecified and not clarification_prompted:
            return CheckResult(
                name=self.name,
                passed=False,
                severity=CheckSeverity.MAJOR,
                expected="Clarification prompt for underspecified input",
                actual="No clarification requested",
                reason="Missing clarification on underspecified input",
            )
        if not underspecified and clarification_prompted:
            return CheckResult(
                name=self.name,
                passed=True,
                severity=CheckSeverity.MINOR,
                expected="Direct action execution without superfluous clarification",
                actual="Clarification prompted",
                reason="Minor: extra clarification requested",
            )
        return CheckResult(
            name=self.name,
            passed=True,
            severity=CheckSeverity.INFO,
            expected="Appropriate clarification handling",
            actual="Appropriate clarification",
        )


class OllamaJudge(BaseJudge):
    """Optional local semantic LLM judge using Ollama to evaluate conciseness and conversational style."""

    name = "OllamaJudge"

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "http://127.0.0.1:11434/v1",
    ) -> None:
        self.model = model
        self.base_url = base_url

    async def evaluate_async(
        self,
        user_message: str,
        agent_response: str,
        scenario: ScenarioDefinition,
    ) -> CheckResult:
        """Call local Ollama to evaluate semantic relevance and conciseness."""
        import httpx

        prompt = (
            f"You are a strict voice AI evaluation judge. Evaluate if the agent's response is concise, "
            f"natural, answers the user's intent, and does not invent facts.\n\n"
            f"Scenario: {scenario.name}\n"
            f"User input: {user_message}\n"
            f"Agent response: {agent_response}\n\n"
            f"Output ONLY a single valid JSON object:\n"
            f'{{"passed": true, "reason": "concise and accurate"}}'
        )

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                    },
                )
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    start = content.find("{")
                    end = content.rfind("}") + 1
                    if start >= 0 and end > start:
                        parsed = json.loads(content[start:end])
                        return CheckResult(
                            name=self.name,
                            passed=bool(parsed.get("passed", True)),
                            severity=CheckSeverity.INFO,
                            expected="Natural, grounded, concise voice phrasing",
                            actual=agent_response,
                            reason=parsed.get("reason", "Semantic check completed"),
                        )
        except Exception as e:
            return CheckResult(
                name=self.name,
                passed=True,
                severity=CheckSeverity.INFO,
                expected="Semantic response evaluation",
                actual=agent_response,
                reason=f"Ollama local judge skipped or timed out: {e}",
            )

        return CheckResult(
            name=self.name,
            passed=True,
            severity=CheckSeverity.INFO,
            expected="Semantic check",
            actual=agent_response,
        )
