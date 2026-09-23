"""Evaluation models, structured test results, and release gate representations."""

from __future__ import annotations

import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CheckSeverity(StrEnum):
    """Evaluation check severity classification for prioritized failure gating."""

    INFO = "INFO"
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"


class CheckResult(BaseModel):
    """An individual assertion result evaluated by a deterministic or semantic judge."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Unique check identifier or judge name")
    passed: bool = Field(..., description="Whether the specific assertion passed")
    severity: CheckSeverity = Field(
        default=CheckSeverity.CRITICAL, description="Failure severity level"
    )
    expected: Any = Field(default=None, description="Expected value or condition")
    actual: Any = Field(default=None, description="Actual observed value")
    reason: str | None = Field(default=None, description="Explanation or diagnostic context")


class ScenarioTurn(BaseModel):
    """A single turn specification within an evaluation scenario."""

    turn: int
    user_input: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    expected_tool: str | None = None
    expected_state: str | None = None
    expected_args: dict[str, Any] | None = None
    confirm: bool | None = None
    is_clarification: bool = False


class ScenarioDefinition(BaseModel):
    """Canonical specification of a multi-turn behavioral evaluation scenario."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Scenario identifier (e.g. S01)")
    name: str = Field(..., description="Human-readable scenario name")
    description: str = Field(..., description="Detailed description of tested behavior")
    category: str = Field(default="core", description="Scenario category: core, safety, adversarial")
    initial_state: str = Field(default="IDLE", description="Initial workflow state")
    turns: list[ScenarioTurn] = Field(default_factory=list)
    expected_tool_calls: list[str] = Field(default_factory=list)
    expected_state: str = Field(default="IDLE")
    expected_events: list[str] = Field(default_factory=list)
    safety_assertions: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    """Comprehensive outcome record for an executed evaluation scenario."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    name: str
    description: str
    category: str = "core"
    started_at: datetime.datetime
    completed_at: datetime.datetime
    duration_ms: float
    passed: bool
    checks: list[CheckResult] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    state_transitions: list[str] = Field(default_factory=list)
    latency: dict[str, float] | None = None
    errors: list[str] = Field(default_factory=list)


class SuiteReport(BaseModel):
    """Aggregated suite-level evaluation summary across all executed scenarios."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    pass_rate_pct: float
    tool_accuracy_pct: float
    tool_argument_accuracy_pct: float
    booking_safety_rate_pct: float
    grounding_rate_pct: float
    confirmation_safety_rate_pct: float
    stale_action_prevention_rate_pct: float
    workflow_completion_rate_pct: float
    workflow_abandonment_rate_pct: float
    average_tool_calls: float
    clarification_count: int
    unnecessary_clarification_count: int = 0
    missing_clarification_count: int = 0
    critical_failures_count: int = 0
    major_failures_count: int = 0
    minor_failures_count: int = 0
    release_gate_status: str = "READY"  # "READY" or "BLOCKED"
    release_gate_reasons: list[str] = Field(default_factory=list)
    results: list[EvaluationResult] = Field(default_factory=list)
