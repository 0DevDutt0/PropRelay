"""Agentic workflow metrics and telemetry tracking."""

from __future__ import annotations

import time
from typing import Any


class WorkflowMetricsTracker:
    """Tracks multi-turn agentic metrics, tool performance, and consequential action lifecycles.

    CRITICAL ARCHITECTURAL GUARANTEE:
    Measures workflow duration, tool counts, clarifications, and action confirmations/rejections
    separately from low-level voice pipeline latencies.
    """

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id: str | None = session_id
        self._workflow_started_at: float | None = None
        self._workflow_completed_at: float | None = None
        self.tool_calls_count: int = 0
        self.tool_calls_history: list[dict[str, Any]] = []
        self.clarification_count: int = 0
        self.confirmation_requested_count: int = 0
        self.confirmation_accepted_count: int = 0
        self.confirmation_declined_count: int = 0
        self.rejected_action_count: int = 0
        self.successful_action_count: int = 0
        self.workflow_completed: bool = False
        self.workflow_abandoned: bool = False

    def start_workflow(self) -> None:
        """Mark the start of a multi-turn agentic workflow (e.g. search started)."""
        if self._workflow_started_at is None:
            self._workflow_started_at = time.perf_counter()

    def record_tool_call(
        self,
        tool_name: str,
        duration_ms: float,
        success: bool,
        arguments: dict[str, Any] | None = None,
    ) -> None:
        """Record an individual agent tool invocation and its performance."""
        self.start_workflow()
        self.tool_calls_count += 1
        record = {
            "tool_name": tool_name,
            "duration_ms": round(duration_ms, 2),
            "success": success,
            "arguments": arguments or {},
            "timestamp": time.time(),
        }
        self.tool_calls_history.append(record)

    def record_clarification(self) -> None:
        """Record when the agent requested clarification due to missing or ambiguous input."""
        self.clarification_count += 1

    def record_confirmation_requested(self) -> None:
        """Record when an application-level proposal was generated and staged."""
        self.confirmation_requested_count += 1

    def record_confirmation_accepted(self) -> None:
        """Record when the user authorized the proposed consequential action."""
        self.confirmation_accepted_count += 1

    def record_confirmation_declined(self) -> None:
        """Record when the user rejected the proposed consequential action."""
        self.confirmation_declined_count += 1

    def record_action_success(self) -> None:
        """Record when a state mutation succeeded."""
        self.successful_action_count += 1

    def record_action_rejected(self) -> None:
        """Record when domain policy rejected a state mutation."""
        self.rejected_action_count += 1

    def complete_workflow(self) -> dict[str, Any]:
        """Mark workflow as successfully completed (e.g. showing booked)."""
        self._workflow_completed_at = time.perf_counter()
        self.workflow_completed = True
        return self.get_summary()

    def abandon_workflow(self) -> dict[str, Any]:
        """Mark workflow as abandoned without terminal goal completion."""
        self._workflow_completed_at = time.perf_counter()
        self.workflow_abandoned = True
        return self.get_summary()

    def get_summary(self) -> dict[str, Any]:
        """Compute structured summary of multi-turn workflow metrics."""
        duration_ms: float | None = None
        if self._workflow_started_at is not None:
            end_time = self._workflow_completed_at or time.perf_counter()
            duration_ms = round((end_time - self._workflow_started_at) * 1000, 2)

        return {
            "session_id": self.session_id,
            "workflow_duration_ms": duration_ms,
            "tool_calls_per_workflow": self.tool_calls_count,
            "clarification_count": self.clarification_count,
            "confirmation_count": self.confirmation_accepted_count,
            "confirmation_proposals_count": self.confirmation_requested_count,
            "rejected_action_count": self.rejected_action_count,
            "successful_action_count": self.successful_action_count,
            "workflow_completed": self.workflow_completed,
            "workflow_abandoned": self.workflow_abandoned,
            "tool_calls_history": self.tool_calls_history,
        }
