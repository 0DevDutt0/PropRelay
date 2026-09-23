"""Tests for PropRelay local operations observability API endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from proprelay.api.server import create_api_app
from proprelay.events.journal import AppendOnlyEventJournal
from proprelay.events.schemas import DomainEvent, EventType
from proprelay.observability.store import ErrorCode, MetricsStore, StructuredError, TurnMetric


@pytest.fixture
def temp_api_environment(
    tmp_path: Path,
) -> tuple[Any, AppendOnlyEventJournal, MetricsStore, Path]:
    events_file = tmp_path / "events.jsonl"
    metrics_file = tmp_path / "metrics.jsonl"
    reports_file = tmp_path / "session_reports.jsonl"
    eval_file = tmp_path / "latest.json"

    journal = AppendOnlyEventJournal(file_path=events_file)
    store = MetricsStore(metrics_file=metrics_file, reports_file=reports_file)

    # Seed an evaluation report
    eval_data = {
        "summary": {
            "scenarios_evaluated": 15,
            "passed_scenarios": 15,
            "failed_scenarios": 0,
            "pass_rate_pct": 100.0,
        },
        "results": [],
    }
    with open(eval_file, "w", encoding="utf-8") as f:
        json.dump(eval_data, f)

    app = create_api_app(
        events_path=events_file,
        metrics_store=store,
        evaluations_path=eval_file,
    )
    return app, journal, store, eval_file


@pytest.mark.asyncio
async def test_api_events_empty_and_populated(temp_api_environment):
    app, journal, _, _ = temp_api_environment
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Initially empty
        res = await client.get("/api/events")
        assert res.status_code == 200
        assert res.json() == []

        # Populate events
        ev1 = DomainEvent(
            event_type=EventType.WORKFLOW_STARTED.value,
            payload={"action": "search"},
            session_id="sess-001",
            workflow_id="wf-001",
        )
        ev2 = DomainEvent(
            event_type=EventType.SHOWING_BOOKED.value,
            payload={"slot_id": "slot-1"},
            session_id="sess-001",
            workflow_id="wf-001",
        )
        await journal.append(ev1)
        await journal.append(ev2)

        # Query all
        res = await client.get("/api/events")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2

        # Query by event_type filter
        res_filtered = await client.get(f"/api/events?event_type={EventType.SHOWING_BOOKED.value}")
        assert res_filtered.status_code == 200
        assert len(res_filtered.json()) == 1
        assert res_filtered.json()[0]["event_type"] == EventType.SHOWING_BOOKED.value

        # Query single event by ID
        res_single = await client.get(f"/api/events/{ev1.event_id}")
        assert res_single.status_code == 200
        assert res_single.json()["event_id"] == ev1.event_id

        # Query non-existent event ID
        res_not_found = await client.get("/api/events/nonexistent-id")
        assert res_not_found.status_code == 404


@pytest.mark.asyncio
async def test_api_workflows_and_sessions(temp_api_environment):
    app, journal, store, _ = temp_api_environment
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Append events for a workflow
        ev1 = DomainEvent(
            event_type=EventType.WORKFLOW_STARTED.value,
            payload={},
            session_id="sess-42",
            workflow_id="wf-42",
        )
        ev2 = DomainEvent(
            event_type=EventType.WORKFLOW_COMPLETED.value,
            payload={},
            session_id="sess-42",
            workflow_id="wf-42",
        )
        await journal.append(ev1)
        await journal.append(ev2)

        # Record metrics and an error for the session
        store.record_turn_metric(
            TurnMetric(
                session_id="sess-42",
                workflow_id="wf-42",
                turn_id="1",
                stt_ms=120.0,
                turn_total_ms=450.0,
            )
        )
        store.record_error(
            StructuredError(
                error_code=ErrorCode.STT_ERROR,
                message="Audio clipping detected",
                session_id="sess-42",
                workflow_id="wf-42",
            )
        )

        # Test GET /api/workflows/{workflow_id}
        res_wf = await client.get("/api/workflows/wf-42")
        assert res_wf.status_code == 200
        wf_data = res_wf.json()
        assert wf_data["workflow_id"] == "wf-42"
        assert wf_data["status"] == "COMPLETED"
        assert wf_data["events_count"] == 2

        # Non-existent workflow
        res_wf_404 = await client.get("/api/workflows/wf-missing")
        assert res_wf_404.status_code == 404

        # Test GET /api/sessions/{session_id}
        res_sess = await client.get("/api/sessions/sess-42")
        assert res_sess.status_code == 200
        sess_data = res_sess.json()
        assert sess_data["session_id"] == "sess-42"
        assert "wf-42" in sess_data["workflow_ids"]
        assert sess_data["events_count"] == 2
        assert sess_data["turns_count"] == 1
        assert sess_data["errors_count"] == 1

        # Non-existent session
        res_sess_404 = await client.get("/api/sessions/sess-missing")
        assert res_sess_404.status_code == 404


@pytest.mark.asyncio
async def test_api_metrics_summary_and_evaluations(temp_api_environment):
    app, _, store, eval_file = temp_api_environment
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /api/metrics/summary
        res_metrics = await client.get("/api/metrics/summary")
        assert res_metrics.status_code == 200
        summary = res_metrics.json()
        assert "sample_counts" in summary
        assert "latency" in summary
        assert "warm_turns" in summary["latency"]

        # GET /api/evaluations/latest
        res_eval = await client.get("/api/evaluations/latest")
        assert res_eval.status_code == 200
        eval_resp = res_eval.json()
        assert eval_resp["summary"]["pass_rate_pct"] == 100.0

        # When evaluation file does not exist
        eval_file.unlink()
        res_eval_404 = await client.get("/api/evaluations/latest")
        assert res_eval_404.status_code == 404
