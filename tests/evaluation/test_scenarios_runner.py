"""Tests for ScenarioRunner, deterministic judges, and evaluation reporting."""

from __future__ import annotations

from pathlib import Path

import pytest

from proprelay.evaluation.judges import (
    BookingSafetyJudge,
    ConfirmationJudge,
    EventJudge,
    GroundingJudge,
    StaleActionJudge,
    StateJudge,
    ToolArgumentJudge,
    ToolSelectionJudge,
)
from proprelay.evaluation.reporters import write_evaluation_reports
from proprelay.evaluation.runner import EvaluationSuiteRunner, ScenarioRunner
from proprelay.evaluation.scenarios import load_all_scenarios


def test_tool_selection_judge():
    judge = ToolSelectionJudge()
    res_ok = judge.evaluate(expected_tool="search_properties", actual_tool="search_properties")
    assert res_ok.passed is True

    res_fail = judge.evaluate(expected_tool="book_showing", actual_tool="search_properties")
    assert res_fail.passed is False
    assert "Expected tool 'book_showing'" in (res_fail.reason or "")


def test_tool_argument_judge():
    judge = ToolArgumentJudge()
    res_ok = judge.evaluate(
        expected_args={"location": "Downtown", "min_beds": 2},
        actual_args={"location": "Downtown", "min_beds": 2, "max_price": 3000},
    )
    assert res_ok.passed is True

    res_fail = judge.evaluate(
        expected_args={"location": "Downtown", "min_beds": 3},
        actual_args={"location": "Downtown", "min_beds": 2},
    )
    assert res_fail.passed is False


def test_state_judge():
    judge = StateJudge()
    res_ok = judge.evaluate(expected_state="BOOKED", actual_state="BOOKED")
    assert res_ok.passed is True

    res_fail = judge.evaluate(expected_state="BOOKED", actual_state="IDLE")
    assert res_fail.passed is False


def test_booking_safety_judge():
    judge = BookingSafetyJudge()
    # When booking should occur and did occur
    assert judge.evaluate(should_allow_booking=True, booking_occurred=True).passed is True

    # When booking should occur but did NOT
    res_missed = judge.evaluate(should_allow_booking=True, booking_occurred=False)
    assert res_missed.passed is False
    assert "Expected valid booking to be committed" in (res_missed.reason or "")

    # When booking should NOT occur and did not
    assert judge.evaluate(should_allow_booking=False, booking_occurred=False).passed is True

    # Safety violation: booking occurred when forbidden
    res_violation = judge.evaluate(should_allow_booking=False, booking_occurred=True)
    assert res_violation.passed is False
    assert "Safety violation" in (res_violation.reason or "")


def test_event_judge_ordering():
    judge = EventJudge()
    expected = ["agent.tool.started", "showing.booked", "agent.tool.completed"]
    observed = [
        "session.started",
        "agent.tool.started",
        "showing.booked",
        "showing.availability.checked",
        "agent.tool.completed",
    ]
    res_ok = judge.evaluate(expected_events=expected, observed_events=observed)
    assert res_ok.passed is True

    # Missing event or wrong order
    observed_wrong_order = [
        "agent.tool.completed",
        "agent.tool.started",
        "showing.booked",
    ]
    res_fail = judge.evaluate(expected_events=expected, observed_events=observed_wrong_order)
    assert res_fail.passed is False


def test_grounding_judge():
    judge = GroundingJudge()
    valid_props = {"prop-101", "prop-102"}
    valid_slots = {"slot-101-01", "slot-101-02"}

    # Valid grounded entities
    res_ok = judge.evaluate(
        selected_property_id="prop-101",
        selected_slot_id="slot-101-01",
        valid_property_ids=valid_props,
        valid_slot_ids=valid_slots,
    )
    assert res_ok.passed is True

    # Hallucinated / ungrounded property
    res_bad = judge.evaluate(
        selected_property_id="prop-nonexistent-999",
        selected_slot_id=None,
        valid_property_ids=valid_props,
        valid_slot_ids=valid_slots,
    )
    assert res_bad.passed is False

    # Queried invalid entity was properly rejected
    res_rejected = judge.evaluate(
        selected_property_id=None,
        selected_slot_id=None,
        valid_property_ids=valid_props,
        valid_slot_ids=valid_slots,
        queried_invalid_entity=True,
        query_rejected=True,
    )
    assert res_rejected.passed is True


def test_confirmation_and_stale_action_judges():
    c_judge = ConfirmationJudge()
    # Two-phase confirmation requirement satisfied
    assert (
        c_judge.evaluate(
            confirmation_requested=True,
            confirmation_accepted=True,
            mutation_occurred=True,
        ).passed
        is True
    )

    # Mutation occurred without confirmation requested
    assert (
        c_judge.evaluate(
            confirmation_requested=False,
            confirmation_accepted=False,
            mutation_occurred=True,
        ).passed
        is False
    )

    sa_judge = StaleActionJudge()
    # Cleared on context switch
    assert (
        sa_judge.evaluate(
            context_switched=True,
            pending_action_cleared=True,
        ).passed
        is True
    )

    # Pending action lingered despite switch
    assert (
        sa_judge.evaluate(
            context_switched=True,
            pending_action_cleared=False,
        ).passed
        is False
    )


@pytest.mark.asyncio
async def test_scenario_runner_execution_and_reports(tmp_path: Path) -> None:
    runner = ScenarioRunner()
    scenarios = load_all_scenarios()
    assert len(scenarios) == 25

    # Run S01 and S04
    s01 = next(s for s in scenarios if s.id == "S01")
    s04 = next(s for s in scenarios if s.id == "S04")

    res_01 = await runner.run_scenario(s01)
    assert res_01.passed is True

    res_04 = await runner.run_scenario(s04)
    assert res_04.passed is True

    # Test suite runner & report generation
    suite = EvaluationSuiteRunner()
    report = await suite.run_all(scenario_filter="S01", persist_report=False)
    assert report.total_scenarios == 1
    assert report.passed_scenarios == 1

    reports_dir = tmp_path / "reports"
    write_evaluation_reports(report, output_dir=reports_dir)

    json_report = reports_dir / "latest.json"
    md_report = reports_dir / "latest.md"

    assert json_report.exists()
    assert md_report.exists()
    assert "S01" in md_report.read_text(encoding="utf-8")
