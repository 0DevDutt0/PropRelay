"""Tests for MetricsStore, statistical percentile calculation, and provenance tracking."""

from __future__ import annotations

import datetime
from pathlib import Path

from proprelay.observability.store import (
    ErrorCode,
    MetricsStore,
    RuntimeState,
    SessionReportSummary,
    StructuredError,
    TurnMetric,
    compute_percentiles,
)


def test_compute_percentiles_insufficient_samples():
    # Empty
    res_0 = compute_percentiles([])
    assert res_0["sample_count"] == 0
    assert res_0["p50"] == "insufficient samples (N=0)"

    # 1 sample
    res_1 = compute_percentiles([150.0])
    assert res_1["sample_count"] == 1
    assert res_1["p50"] == "insufficient samples (N=1)"

    # 2 samples
    res_2 = compute_percentiles([100.0, 200.0])
    assert res_2["sample_count"] == 2
    assert res_2["p50"] == "insufficient samples (N=2)"


def test_compute_percentiles_adequate_samples():
    samples = [100.0, 150.0, 200.0, 250.0, 300.0]
    res = compute_percentiles(samples)

    assert isinstance(res, dict)
    assert res["sample_count"] == 5
    assert res["min"] == 100.0
    assert res["max"] == 300.0
    assert res["mean"] == 200.0
    assert res["p50"] == 200.0
    assert res["p90"] == 280.0
    assert "p95" in res


def test_metrics_store_turn_metrics_and_classification(tmp_path: Path) -> None:
    store = MetricsStore(
        metrics_file=tmp_path / "metrics.jsonl",
        reports_file=tmp_path / "reports.jsonl",
    )

    cold_turn = TurnMetric(
        session_id="sess-1",
        workflow_id="wf-1",
        turn_id="0",
        runtime_state=RuntimeState.COLD_START,
        stt_ms=450.0,
        turn_total_ms=1200.0,
    )
    warm_turn_1 = TurnMetric(
        session_id="sess-1",
        workflow_id="wf-1",
        turn_id="1",
        runtime_state=RuntimeState.WARM_RUNTIME,
        stt_ms=110.0,
        turn_total_ms=350.0,
    )
    warm_turn_2 = TurnMetric(
        session_id="sess-1",
        workflow_id="wf-1",
        turn_id="2",
        runtime_state=RuntimeState.WARM_RUNTIME,
        stt_ms=120.0,
        turn_total_ms=360.0,
    )
    warm_turn_3 = TurnMetric(
        session_id="sess-1",
        workflow_id="wf-1",
        turn_id="3",
        runtime_state=RuntimeState.WARM_RUNTIME,
        stt_ms=105.0,
        turn_total_ms=340.0,
    )

    store.record_turn_metric(cold_turn)
    store.record_turn_metric(warm_turn_1)
    store.record_turn_metric(warm_turn_2)
    store.record_turn_metric(warm_turn_3)

    loaded = store.get_turn_metrics()
    assert len(loaded) == 4

    summary = store.get_metrics_summary()
    assert summary["sample_counts"]["cold_start_turns"] == 1
    assert summary["sample_counts"]["warm_runtime_turns"] == 3

    # Warm turns have 3 samples, so percentiles must be calculated
    warm_lat = summary["latency"]["warm_turns"]["t_stt_ms"]
    assert isinstance(warm_lat, dict)
    assert warm_lat["sample_count"] == 3
    assert isinstance(warm_lat["p50"], float)

    # Cold turns only have 1 sample, so percentiles must be guarded
    cold_lat = summary["latency"]["cold_turns"]["t_turn_total_ms"]
    assert cold_lat["sample_count"] == 1
    assert cold_lat["p50"] == "insufficient samples (N=1)"


def test_metrics_store_errors_and_session_reports(tmp_path: Path) -> None:
    store = MetricsStore(
        metrics_file=tmp_path / "metrics.jsonl",
        reports_file=tmp_path / "reports.jsonl",
    )

    err1 = StructuredError(
        error_code=ErrorCode.POLICY_REJECTION,
        message="Slot unavailable",
        session_id="sess-2",
        workflow_id="wf-2",
    )
    err2 = StructuredError(
        error_code=ErrorCode.STT_ERROR,
        message="Buffer overflow",
        session_id="sess-2",
    )
    store.record_error(err1)
    store.record_error(err2)

    errors = store.get_errors()
    assert len(errors) == 2

    now = datetime.datetime.now(datetime.UTC)
    report = SessionReportSummary(
        session_id="sess-2",
        started_at=now - datetime.timedelta(seconds=45),
        completed_at=now,
        duration_ms=45200.0,
        total_turns=5,
        workflows_completed=1,
        workflows_abandoned=0,
    )
    store.record_session_report(report)

    reports = store.get_session_reports()
    assert len(reports) == 1
    assert reports[0].session_id == "sess-2"

    summary = store.get_metrics_summary()
    assert summary["error_taxonomy"][ErrorCode.POLICY_REJECTION.value] == 1
    assert summary["error_taxonomy"][ErrorCode.STT_ERROR.value] == 1
    assert summary["workflows"]["completed"] == 1
    assert summary["workflows"]["completion_rate_pct"] == 100.0
