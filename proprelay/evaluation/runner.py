"""Scenario execution engine, deterministic judge evaluation, and suite runner for PropRelay."""

from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

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
from proprelay.domain.clock import FrozenClock
from proprelay.domain.models import BookingStatus, Property, ShowingSlot
from proprelay.domain.policy import BookingPolicyService
from proprelay.domain.repositories import (
    InMemoryBookingRepository,
    InMemoryLeadRepository,
    InMemoryPropertyRepository,
    InMemoryShowingRepository,
)
from proprelay.evaluation.judges import (
    BookingSafetyJudge,
    ClarificationJudge,
    ConfirmationJudge,
    EventJudge,
    GroundingJudge,
    OllamaJudge,
    StaleActionJudge,
    StateJudge,
    ToolArgumentJudge,
    ToolSelectionJudge,
)
from proprelay.evaluation.models import (
    CheckResult,
    CheckSeverity,
    EvaluationResult,
    ScenarioDefinition,
    SuiteReport,
)
from proprelay.evaluation.reporters import format_markdown_report, write_evaluation_reports
from proprelay.evaluation.scenarios import load_all_scenarios
from proprelay.events.journal import IEventPublisher
from proprelay.events.schemas import DomainEvent
from proprelay.observability.metrics import WorkflowMetricsTracker
from proprelay.workflows.context import ConversationContext
from proprelay.workflows.state import WorkflowState

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


class InMemoryEventCapture(IEventPublisher):
    """In-memory event sink capturing all DomainEvents published during a scenario run."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


def load_fixtures_catalog() -> tuple[list[Property], list[ShowingSlot]]:
    """Load standard properties and showing slots from data fixtures."""
    listings_path = DATA_DIR / "listings.json"
    showings_path = DATA_DIR / "showings.json"

    properties: list[Property] = []
    if listings_path.exists():
        with open(listings_path, encoding="utf-8") as f:
            raw_props = json.load(f)
            properties = [Property.model_validate(p) for p in raw_props]

    slots: list[ShowingSlot] = []
    if showings_path.exists():
        with open(showings_path, encoding="utf-8") as f:
            raw_slots = json.load(f)
            slots = [ShowingSlot.model_validate(s) for s in raw_slots]

    return properties, slots


class ScenarioRunner:
    """Executes a single multi-turn scenario against isolated domain components."""

    def __init__(self) -> None:
        self.reference_datetime = datetime.datetime(2026, 10, 1, 8, 0, 0, tzinfo=datetime.UTC)
        self.clock = FrozenClock(self.reference_datetime)
        self.properties, self.slots = load_fixtures_catalog()

    async def run_scenario(
        self,
        scenario: ScenarioDefinition,
        enable_semantic_llm: bool = False,
    ) -> EvaluationResult:
        """Execute all turns of a scenario and evaluate all deterministic judges."""
        started_at = datetime.datetime.now(datetime.UTC)
        start_perf = time.perf_counter()

        # Initialize fresh in-memory repositories for test isolation
        property_repo = InMemoryPropertyRepository(self.properties)
        showing_repo = InMemoryShowingRepository(self.slots)
        booking_repo = InMemoryBookingRepository()
        lead_repo = InMemoryLeadRepository()
        booking_policy = BookingPolicyService(
            property_repo=property_repo,
            showing_repo=showing_repo,
            booking_repo=booking_repo,
            clock=self.clock,
        )

        event_capture = InMemoryEventCapture()
        metrics_tracker = WorkflowMetricsTracker(session_id=f"eval-{scenario.id}")
        state_transitions: list[str] = [scenario.initial_state]

        def _on_state_change(old_s: WorkflowState, new_s: WorkflowState) -> None:
            state_transitions.append(new_s.value)

        context = ConversationContext(
            session_id=f"eval-{scenario.id}",
            on_state_change=_on_state_change,
        )
        if scenario.initial_state != "IDLE":
            with contextlib.suppress(ValueError):
                context.workflow_state = WorkflowState(scenario.initial_state)

        agent_tools = AgentTools(
            property_repo=property_repo,
            showing_repo=showing_repo,
            booking_repo=booking_repo,
            lead_repo=lead_repo,
            booking_policy=booking_policy,
            event_publisher=event_capture,
            clock=self.clock,
            context=context,
            metrics_tracker=metrics_tracker,
        )

        tool_calls: list[dict[str, Any]] = []
        checks: list[CheckResult] = []
        errors: list[str] = []

        valid_prop_ids = {p.property_id for p in self.properties}
        valid_slot_ids = {s.slot_id for s in self.slots}
        referenced_prop_ids: list[str] = []
        referenced_slot_ids: list[str] = []

        # Execute turns sequentially
        for turn_spec in scenario.turns:
            context.advance_turn()
            turn_start = time.perf_counter()
            action = turn_spec.action
            params = turn_spec.params

            # Record referenced IDs for grounding checks
            if "property_id" in params and params["property_id"]:
                referenced_prop_ids.append(params["property_id"])
            if "slot_id" in params and params["slot_id"]:
                referenced_slot_ids.append(params["slot_id"])
            if "new_slot_id" in params and params["new_slot_id"]:
                referenced_slot_ids.append(params["new_slot_id"])

            actual_tool = action
            tool_success = True
            tool_res_message: str | None = None

            try:
                res: Any = None
                if action == "search_properties":
                    res = await agent_tools.search_properties(SearchPropertiesInput(**params))
                    tool_success = res.success
                    tool_res_message = res.message
                elif action == "get_property_details":
                    res = await agent_tools.get_property_details(GetPropertyDetailsInput(**params))
                    tool_success = res.success
                    tool_res_message = res.message
                elif action == "get_available_showings":
                    res = await agent_tools.get_available_showings(
                        GetAvailableShowingsInput(**params)
                    )
                    tool_success = res.success
                    tool_res_message = res.message
                elif action == "book_showing":
                    # Handle past date param check if expected_date given
                    if "expected_date" in params and isinstance(params["expected_date"], str):
                        with contextlib.suppress(Exception):
                            params["expected_date"] = datetime.date.fromisoformat(params["expected_date"])
                    res = await agent_tools.book_showing(BookShowingInput(**params))
                    tool_success = res.success
                    tool_res_message = res.message
                elif action == "reschedule_showing":
                    if "booking_id" not in params and context.active_booking:
                        params["booking_id"] = context.active_booking.booking_id
                    res = await agent_tools.reschedule_showing(RescheduleShowingInput(**params))
                    tool_success = res.success
                    tool_res_message = res.message
                elif action == "cancel_showing":
                    if "booking_id" not in params and context.active_booking:
                        params["booking_id"] = context.active_booking.booking_id
                    res = await agent_tools.cancel_showing(CancelShowingInput(**params))
                    tool_success = res.success
                    tool_res_message = res.message
                elif action == "confirm_pending_action":
                    conf = params.get("confirmed", True)
                    if conf:
                        res = await agent_tools.confirm_pending_action()
                    else:
                        res = await agent_tools.cancel_pending_action()
                    tool_success = res.success
                    tool_res_message = res.message
                elif action == "create_lead":
                    res = await agent_tools.create_lead(CreateLeadInput(**params))
                    tool_success = res.success
                    tool_res_message = res.message
                else:
                    errors.append(f"Unknown action '{action}' in turn {turn_spec.turn}")
            except Exception as e:
                tool_success = False
                errors.append(f"Turn {turn_spec.turn} failed: {e}")

            turn_duration_ms = (time.perf_counter() - turn_start) * 1000
            tool_calls.append(
                {
                    "turn": turn_spec.turn,
                    "action": action,
                    "params": params,
                    "duration_ms": round(turn_duration_ms, 2),
                    "success": tool_success,
                    "message": tool_res_message,
                }
            )

            # Turn-level assertions
            if turn_spec.expected_tool:
                checks.append(
                    ToolSelectionJudge().evaluate(
                        expected_tool=turn_spec.expected_tool,
                        actual_tool=actual_tool,
                    )
                )

            if turn_spec.expected_state:
                checks.append(
                    StateJudge().evaluate(
                        expected_state=turn_spec.expected_state,
                        actual_state=context.workflow_state.value,
                    )
                )

            if turn_spec.expected_args:
                checks.append(
                    ToolArgumentJudge().evaluate(
                        expected_args=turn_spec.expected_args,
                        actual_args=params,
                    )
                )

            if turn_spec.is_clarification:
                checks.append(
                    ClarificationJudge().evaluate(
                        underspecified=True,
                        clarification_prompted=not tool_success or "name" in (tool_res_message or "").lower(),
                    )
                )

        # Scenario-level evaluations
        observed_event_types = [e.event_type for e in event_capture.events]

        # 1. State Judge
        checks.append(
            StateJudge().evaluate(
                expected_state=scenario.expected_state,
                actual_state=context.workflow_state.value,
            )
        )

        # 2. Event Judge
        if scenario.expected_events:
            checks.append(
                EventJudge().evaluate(
                    expected_events=scenario.expected_events,
                    observed_events=observed_event_types,
                )
            )

        # 3. Booking Safety Judge
        bookings = await booking_repo.list_all()
        active_bookings = [b for b in bookings if b.status != BookingStatus.CANCELLED]
        bookings_count = len(active_bookings)
        allow_booking = scenario.safety_assertions.get("allow_booking", False)
        checks.append(
            BookingSafetyJudge().evaluate(
                should_allow_booking=allow_booking,
                booking_occurred=bookings_count > 0,
                rejection_reason="scenario safety policy forbids booking",
            )
        )

        # 4. Grounding Judge
        sel_prop_id = context.selected_property.property_id if context.selected_property else None
        sel_slot_id = (
            context.selected_showing_slot.slot_id if context.selected_showing_slot else None
        )
        is_invalid_query = any(
            p.get("property_id") in {"P-999", "prop-9999", "prop-nonexistent-999"}
            for p in [t.params for t in scenario.turns]
        )
        was_rejected = any(not tc["success"] for tc in tool_calls) if is_invalid_query else True
        checks.append(
            GroundingJudge().evaluate(
                selected_property_id=sel_prop_id,
                selected_slot_id=sel_slot_id,
                valid_property_ids=valid_prop_ids,
                valid_slot_ids=valid_slot_ids,
                queried_invalid_entity=is_invalid_query,
                query_rejected=was_rejected,
            )
        )

        # 5. Stale Action Judge
        if scenario.safety_assertions.get("stale_action_prevented"):
            checks.append(
                StaleActionJudge().evaluate(
                    context_switched=True,
                    pending_action_cleared=context.pending_action is None,
                )
            )

        # 6. Two-Phase Confirmation Judge
        if scenario.safety_assertions.get("require_confirmation"):
            req = metrics_tracker.confirmation_requested_count > 0
            acc = metrics_tracker.confirmation_accepted_count > 0
            mut = bookings_count > 0
            checks.append(
                ConfirmationJudge().evaluate(
                    confirmation_requested=req,
                    confirmation_accepted=acc,
                    mutation_occurred=mut,
                )
            )

        # 7. Optional Ollama Semantic Judge
        if enable_semantic_llm and scenario.turns:
            ollama = OllamaJudge()
            last_turn = scenario.turns[-1]
            last_msg = (
                context.selected_property.title
                if context.selected_property
                else context.workflow_state.value
            )
            llm_res = await ollama.evaluate_async(
                user_message=last_turn.user_input,
                agent_response=str(last_msg),
                scenario=scenario,
            )
            checks.append(llm_res)

        total_duration_ms = (time.perf_counter() - start_perf) * 1000
        completed_at = datetime.datetime.now(datetime.UTC)

        passed = all(c.passed for c in checks)

        # If scenario failed, dump replayable failure fixture for deterministic reproduction
        if not passed:
            dump_dir = Path("reports/evaluation/failures")
            dump_dir.mkdir(parents=True, exist_ok=True)
            failure_dump = {
                "scenario_id": scenario.id,
                "name": scenario.name,
                "timestamp": completed_at.isoformat(),
                "duration_ms": round(total_duration_ms, 2),
                "turns": [t.model_dump(mode="json") for t in scenario.turns],
                "failed_checks": [c.model_dump(mode="json") for c in checks if not c.passed],
                "tool_calls": tool_calls,
                "state_transitions": state_transitions,
                "errors": errors,
            }
            dump_path = dump_dir / f"{scenario.id}_failure.json"
            dump_path.write_text(json.dumps(failure_dump, indent=2, default=str), encoding="utf-8")

        return EvaluationResult(
            scenario_id=scenario.id,
            name=scenario.name,
            description=scenario.description,
            category=scenario.category,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(total_duration_ms, 2),
            passed=passed,
            checks=checks,
            tool_calls=tool_calls,
            events=observed_event_types,
            state_transitions=state_transitions,
            errors=errors,
        )


class EvaluationSuiteRunner:
    """Discovers, executes, and aggregates reports across the complete evaluation suite."""

    def __init__(self, scenarios_dir: str | Path | None = None) -> None:
        self.scenarios_dir = scenarios_dir
        self.runner = ScenarioRunner()

    async def run_all(
        self,
        scenario_filter: str | None = None,
        enable_semantic_llm: bool = False,
        persist_report: bool = True,
    ) -> SuiteReport:
        """Run all discovered scenarios matching filter and compile SuiteReport."""
        all_scenarios = load_all_scenarios(self.scenarios_dir)
        if scenario_filter:
            target = scenario_filter.strip().upper()
            scenarios = [
                s for s in all_scenarios if s.id.upper() == target or target in s.name.upper()
            ]
        else:
            scenarios = all_scenarios

        results: list[EvaluationResult] = []
        for sc in scenarios:
            res = await self.runner.run_scenario(sc, enable_semantic_llm=enable_semantic_llm)
            results.append(res)

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        pass_rate = round((passed / total) * 100, 1) if total > 0 else 0.0

        # Calculate granular check metrics & severities
        total_tool_checks = 0
        passed_tool_checks = 0
        total_safety_checks = 0
        passed_safety_checks = 0
        total_grounding_checks = 0
        passed_grounding_checks = 0
        total_confirm_checks = 0
        passed_confirm_checks = 0
        total_stale_checks = 0
        passed_stale_checks = 0

        critical_failures = 0
        major_failures = 0
        minor_failures = 0
        gate_reasons: list[str] = []

        for r in results:
            for c in r.checks:
                if not c.passed:
                    if c.severity == CheckSeverity.CRITICAL:
                        critical_failures += 1
                        gate_reasons.append(f"[{r.scenario_id}] CRITICAL: {c.name} - {c.reason}")
                    elif c.severity == CheckSeverity.MAJOR:
                        major_failures += 1
                        gate_reasons.append(f"[{r.scenario_id}] MAJOR: {c.name} - {c.reason}")
                    elif c.severity == CheckSeverity.MINOR:
                        minor_failures += 1

                if c.name == "ToolSelectionJudge":
                    total_tool_checks += 1
                    if c.passed:
                        passed_tool_checks += 1
                elif c.name == "BookingSafetyJudge":
                    total_safety_checks += 1
                    if c.passed:
                        passed_safety_checks += 1
                elif c.name == "GroundingJudge":
                    total_grounding_checks += 1
                    if c.passed:
                        passed_grounding_checks += 1
                elif c.name == "ConfirmationJudge":
                    total_confirm_checks += 1
                    if c.passed:
                        passed_confirm_checks += 1
                elif c.name == "StaleActionJudge":
                    total_stale_checks += 1
                    if c.passed:
                        passed_stale_checks += 1

        tool_acc = (
            round((passed_tool_checks / total_tool_checks) * 100, 1)
            if total_tool_checks > 0
            else 100.0
        )
        safety_acc = (
            round((passed_safety_checks / total_safety_checks) * 100, 1)
            if total_safety_checks > 0
            else 100.0
        )
        grounding_acc = (
            round((passed_grounding_checks / total_grounding_checks) * 100, 1)
            if total_grounding_checks > 0
            else 100.0
        )
        confirm_acc = (
            round((passed_confirm_checks / total_confirm_checks) * 100, 1)
            if total_confirm_checks > 0
            else 100.0
        )
        stale_acc = (
            round((passed_stale_checks / total_stale_checks) * 100, 1)
            if total_stale_checks > 0
            else 100.0
        )

        completed_wf = sum(1 for r in results if "SHOWING_CONFIRMED" in r.state_transitions or "BOOKED" in r.state_transitions)
        abandoned_wf = sum(1 for r in results if "BOOKING_FAILED" in r.state_transitions)
        avg_tools = round(sum(len(r.tool_calls) for r in results) / total, 2) if total > 0 else 0.0

        # Release Gate evaluation: 100% pass on critical and major checks, pass rate >= 95%
        release_ready = (critical_failures == 0) and (major_failures == 0) and (pass_rate >= 95.0)
        release_gate_status = "READY" if release_ready else "BLOCKED"
        if pass_rate < 95.0:
            gate_reasons.append(f"Suite pass rate ({pass_rate}%) is below 95% threshold")

        report = SuiteReport(
            total_scenarios=total,
            passed_scenarios=passed,
            failed_scenarios=failed,
            pass_rate_pct=pass_rate,
            tool_accuracy_pct=tool_acc,
            tool_argument_accuracy_pct=tool_acc,
            booking_safety_rate_pct=safety_acc,
            grounding_rate_pct=grounding_acc,
            confirmation_safety_rate_pct=confirm_acc,
            stale_action_prevention_rate_pct=stale_acc,
            workflow_completion_rate_pct=round((completed_wf / total) * 100, 1)
            if total > 0
            else 0.0,
            workflow_abandonment_rate_pct=round((abandoned_wf / total) * 100, 1)
            if total > 0
            else 0.0,
            average_tool_calls=avg_tools,
            clarification_count=0,
            critical_failures_count=critical_failures,
            major_failures_count=major_failures,
            minor_failures_count=minor_failures,
            release_gate_status=release_gate_status,
            release_gate_reasons=gate_reasons,
            results=results,
        )

        if persist_report:
            write_evaluation_reports(report)

        return report


def main() -> None:
    """CLI runner for PropRelay local evaluation framework."""
    import asyncio

    parser = argparse.ArgumentParser(description="PropRelay Local Evaluation Runner")
    parser.add_argument("--all", action="store_true", help="Run all evaluation scenarios")
    parser.add_argument("--scenario", help="Run a specific scenario by ID (e.g. S01)")
    parser.add_argument("--verbose", action="store_true", help="Print detailed checks breakdown")
    parser.add_argument("--json", action="store_true", help="Output raw JSON results")
    parser.add_argument("--summary", action="store_true", help="Output Markdown report summary")
    parser.add_argument(
        "--semantic-llm", action="store_true", help="Enable optional local Ollama semantic judge"
    )

    args = parser.parse_args()

    suite = EvaluationSuiteRunner()
    report = asyncio.run(
        suite.run_all(
            scenario_filter=args.scenario,
            enable_semantic_llm=args.semantic_llm,
            persist_report=True,
        )
    )

    if args.json:
        print(report.model_dump_json(indent=2))
        return

    if args.summary:
        print(format_markdown_report(report))
        return

    # Console formatting
    print("==================================================")
    print("       PropRelay Behavioral Evaluation Suite      ")
    print("==================================================")
    print(f"Scenarios Evaluated : {report.total_scenarios}")
    print(f"Passed Scenarios    : {report.passed_scenarios}")
    print(f"Failed Scenarios    : {report.failed_scenarios}")
    print(f"Suite Pass Rate     : {report.pass_rate_pct}%")
    print(f"Consequential Safety: {report.booking_safety_rate_pct}%")
    print(f"Grounding Accuracy  : {report.grounding_rate_pct}%")
    print(f"Confirmation Safety : {report.confirmation_safety_rate_pct}%")
    print(f"Stale Action Safety : {report.stale_action_prevention_rate_pct}%")
    print(f"Release Gate Status : {report.release_gate_status}")
    print("--------------------------------------------------")

    for r in report.results:
        status_sym = "[PASS]" if r.passed else "[FAIL]"
        print(f"{status_sym} {r.scenario_id:<4} {r.name:<32} ({r.duration_ms:.1f}ms)")
        if args.verbose or not r.passed:
            for c in r.checks:
                c_sym = "  +" if c.passed else "  X"
                print(f"    {c_sym} [{c.severity}] {c.name:<24}: {c.reason or 'OK'}")

    print("==================================================")
    print("Generated reports:")
    print("  - reports/evaluation/latest.json")
    print("  - reports/evaluation/latest.md")
    print("  - reports/evaluation/release_gate.json")
    print("  - reports/evaluation/release_gate.md")
    print("==================================================")

    if report.failed_scenarios > 0 or report.release_gate_status != "READY":
        sys.exit(1)


if __name__ == "__main__":
    main()
