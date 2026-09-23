"""Lightweight local metrics store, structured error taxonomy, and provenance tracking."""

from __future__ import annotations

import datetime
import json
import logging
import math
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    """Authoritative structured failure taxonomy for PropRelay."""

    STT_ERROR = "STT_ERROR"
    LLM_ERROR = "LLM_ERROR"
    TTS_ERROR = "TTS_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    POLICY_REJECTION = "POLICY_REJECTION"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    STALE_ACTION = "STALE_ACTION"


class MetricProvenance(StrEnum):
    """Categorization of where a given metric value originated."""

    LIVEKIT_NATIVE = "LiveKit native metric"
    CUSTOM_APP_TIMER = "Custom application timer"
    DOMAIN_EVENT_TS = "Domain event timestamp"
    DERIVED = "Derived metric"


class RuntimeState(StrEnum):
    """Distinction between cold model loading and warm conversational turns."""

    COLD_START = "cold_start"
    WARM_RUNTIME = "warm_runtime"


class StructuredError(BaseModel):
    """Traceable, correlated error record for failure analytics."""

    model_config = ConfigDict(frozen=True)

    error_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    error_code: ErrorCode
    message: str
    session_id: str | None = None
    workflow_id: str | None = None
    turn_id: str | None = None
    tool_name: str | None = None
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    details: dict[str, Any] = Field(default_factory=dict)


class TurnMetric(BaseModel):
    """Turn-level latency metrics with runtime state and provenance classification."""

    model_config = ConfigDict(frozen=True)

    metric_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    workflow_id: str | None = None
    turn_id: str = "0"
    runtime_state: RuntimeState = RuntimeState.WARM_RUNTIME
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    endpointing_ms: float | None = None
    stt_ms: float | None = None
    llm_ttft_ms: float | None = None
    llm_total_ms: float | None = None
    tool_ms: float | None = None
    tts_ttfb_ms: float | None = None
    turn_total_ms: float | None = None
    provenance: dict[str, str] = Field(
        default_factory=lambda: {
            "endpointing_ms": MetricProvenance.LIVEKIT_NATIVE.value,
            "stt_ms": MetricProvenance.LIVEKIT_NATIVE.value,
            "llm_ttft_ms": MetricProvenance.LIVEKIT_NATIVE.value,
            "llm_total_ms": MetricProvenance.LIVEKIT_NATIVE.value,
            "tool_ms": MetricProvenance.CUSTOM_APP_TIMER.value,
            "tts_ttfb_ms": MetricProvenance.LIVEKIT_NATIVE.value,
            "turn_total_ms": MetricProvenance.DERIVED.value,
        }
    )


class SessionReportSummary(BaseModel):
    """Aggregated report generated at the termination of a voice session."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    started_at: datetime.datetime
    completed_at: datetime.datetime
    duration_ms: float
    total_turns: int = 0
    total_tool_calls: int = 0
    workflows_completed: int = 0
    workflows_abandoned: int = 0
    errors_count: int = 0
    latency_summary: dict[str, Any] = Field(default_factory=dict)


def compute_percentiles(values: list[float], min_samples: int = 3) -> dict[str, Any]:
    """Calculate p50, p90, and p95 using standard nearest-rank percentile calculation.

    If fewer than `min_samples` observations exist, explicitly outputs
    'insufficient samples' to avoid statistical fabrication.
    """
    clean_vals = [float(v) for v in values if v is not None and not math.isnan(v)]
    n = len(clean_vals)
    if n < min_samples:
        return {
            "sample_count": n,
            "p50": f"insufficient samples (N={n})",
            "p90": f"insufficient samples (N={n})",
            "p95": f"insufficient samples (N={n})",
            "min": round(min(clean_vals), 2) if n > 0 else None,
            "max": round(max(clean_vals), 2) if n > 0 else None,
            "mean": round(sum(clean_vals) / n, 2) if n > 0 else None,
        }

    sorted_vals = sorted(clean_vals)

    def _percentile(p: float) -> float:
        # Nearest-rank method
        k = (len(sorted_vals) - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_vals[int(k)]
        d0 = sorted_vals[int(f)] * (c - k)
        d1 = sorted_vals[int(c)] * (k - f)
        return d0 + d1

    return {
        "sample_count": n,
        "p50": round(_percentile(50.0), 2),
        "p90": round(_percentile(90.0), 2),
        "p95": round(_percentile(95.0), 2),
        "min": round(sorted_vals[0], 2),
        "max": round(sorted_vals[-1], 2),
        "mean": round(sum(sorted_vals) / n, 2),
    }


class MetricsStore:
    """Local, lightweight JSONL-backed store for turn latency metrics, session summaries, and errors.

    Ensures zero cloud dependencies and durable recording of operations metrics.
    """

    def __init__(
        self,
        metrics_file: str | Path = "data/metrics.jsonl",
        reports_file: str | Path = "data/session_reports.jsonl",
    ) -> None:
        self.metrics_file = Path(metrics_file)
        self.reports_file = Path(reports_file)
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        self.reports_file.parent.mkdir(parents=True, exist_ok=True)

    def record_turn_metric(self, metric: TurnMetric) -> None:
        """Persist a single turn latency measurement."""
        line = metric.model_dump_json() + "\n"
        with open(self.metrics_file, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()

    def record_error(self, error: StructuredError) -> None:
        """Persist a structured error record to the metrics file."""
        record = {
            "record_type": "error",
            "data": error.model_dump(mode="json"),
        }
        line = json.dumps(record) + "\n"
        with open(self.metrics_file, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()

    def record_session_report(self, report: SessionReportSummary) -> None:
        """Persist a completed session summary report."""
        line = report.model_dump_json() + "\n"
        with open(self.reports_file, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()

    def get_turn_metrics(self) -> list[TurnMetric]:
        """Read all persisted turn latency metrics."""
        if not self.metrics_file.exists():
            return []
        items: list[TurnMetric] = []
        with open(self.metrics_file, encoding="utf-8") as f:
            for line in f:
                c = line.strip()
                if not c:
                    continue
                try:
                    data = json.loads(c)
                    if "record_type" in data:
                        continue  # Skip errors in turn metrics stream
                    items.append(TurnMetric.model_validate(data))
                except Exception as e:
                    logger.debug("Skipping unparseable turn metric line: %s", e)
        return items

    def get_errors(self) -> list[StructuredError]:
        """Read all persisted structured errors."""
        if not self.metrics_file.exists():
            return []
        items: list[StructuredError] = []
        with open(self.metrics_file, encoding="utf-8") as f:
            for line in f:
                c = line.strip()
                if not c:
                    continue
                try:
                    data = json.loads(c)
                    if data.get("record_type") == "error":
                        items.append(StructuredError.model_validate(data["data"]))
                except Exception as e:
                    logger.debug("Skipping unparseable error line: %s", e)
        return items

    def get_session_reports(self) -> list[SessionReportSummary]:
        """Read all persisted session summary reports."""
        if not self.reports_file.exists():
            return []
        items: list[SessionReportSummary] = []
        with open(self.reports_file, encoding="utf-8") as f:
            for line in f:
                c = line.strip()
                if not c:
                    continue
                try:
                    data = json.loads(c)
                    items.append(SessionReportSummary.model_validate(data))
                except Exception as e:
                    logger.debug("Skipping unparseable session report line: %s", e)
        return items

    def get_metrics_summary(self) -> dict[str, Any]:
        """Compute comprehensive system metrics summary with honest statistical reporting."""
        turns = self.get_turn_metrics()
        errors = self.get_errors()
        sessions = self.get_session_reports()

        cold_turns = [t for t in turns if t.runtime_state == RuntimeState.COLD_START]
        warm_turns = [t for t in turns if t.runtime_state == RuntimeState.WARM_RUNTIME]

        def _extract(metric_list: list[TurnMetric], key: str) -> list[float]:
            res: list[float] = []
            for t in metric_list:
                v = getattr(t, key, None)
                if v is not None:
                    res.append(float(v))
            return res

        error_counts: dict[str, int] = {}
        for err in errors:
            code = err.error_code.value
            error_counts[code] = error_counts.get(code, 0) + 1

        total_sessions = len(sessions)
        workflows_completed = sum(s.workflows_completed for s in sessions)
        workflows_abandoned = sum(s.workflows_abandoned for s in sessions)
        total_workflows = workflows_completed + workflows_abandoned
        wf_success_rate = (
            round((workflows_completed / total_workflows) * 100, 1) if total_workflows > 0 else None
        )

        return {
            "summary_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "sample_counts": {
                "total_sessions": total_sessions,
                "total_turns": len(turns),
                "cold_start_turns": len(cold_turns),
                "warm_runtime_turns": len(warm_turns),
                "total_errors": len(errors),
            },
            "workflows": {
                "total_workflows": total_workflows,
                "completed": workflows_completed,
                "abandoned": workflows_abandoned,
                "completion_rate_pct": wf_success_rate,
            },
            "latency": {
                "all_turns": {
                    "t_stt_ms": compute_percentiles(_extract(turns, "stt_ms")),
                    "t_llm_ttft_ms": compute_percentiles(_extract(turns, "llm_ttft_ms")),
                    "t_llm_total_ms": compute_percentiles(_extract(turns, "llm_total_ms")),
                    "t_tts_ttfb_ms": compute_percentiles(_extract(turns, "tts_ttfb_ms")),
                    "t_turn_total_ms": compute_percentiles(_extract(turns, "turn_total_ms")),
                },
                "warm_turns": {
                    "t_stt_ms": compute_percentiles(_extract(warm_turns, "stt_ms")),
                    "t_llm_ttft_ms": compute_percentiles(_extract(warm_turns, "llm_ttft_ms")),
                    "t_llm_total_ms": compute_percentiles(_extract(warm_turns, "llm_total_ms")),
                    "t_tts_ttfb_ms": compute_percentiles(_extract(warm_turns, "tts_ttfb_ms")),
                    "t_turn_total_ms": compute_percentiles(_extract(warm_turns, "turn_total_ms")),
                },
                "cold_turns": {
                    "t_turn_total_ms": compute_percentiles(_extract(cold_turns, "turn_total_ms")),
                },
            },
            "error_taxonomy": error_counts,
            "provenance_metadata": {
                "t_turn_eou_ms": MetricProvenance.LIVEKIT_NATIVE.value,
                "t_stt_ms": MetricProvenance.LIVEKIT_NATIVE.value,
                "t_llm_ttft_ms": MetricProvenance.LIVEKIT_NATIVE.value,
                "t_llm_total_ms": MetricProvenance.LIVEKIT_NATIVE.value,
                "t_tool_ms": MetricProvenance.CUSTOM_APP_TIMER.value,
                "t_tts_ttfb_ms": MetricProvenance.LIVEKIT_NATIVE.value,
                "t_turn_total_ms": MetricProvenance.DERIVED.value,
                "workflow_metrics": MetricProvenance.DOMAIN_EVENT_TS.value,
            },
        }

    def clear(self) -> None:
        """Clear metrics and report files (for test resets)."""
        if self.metrics_file.exists():
            with open(self.metrics_file, "w", encoding="utf-8") as f:
                f.truncate(0)
        if self.reports_file.exists():
            with open(self.reports_file, "w", encoding="utf-8") as f:
                f.truncate(0)
