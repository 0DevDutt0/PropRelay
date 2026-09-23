"""Local Observability & Metrics Report CLI for PropRelay."""

from __future__ import annotations

import argparse
import json
from typing import Any

from proprelay.observability.store import MetricsStore


def format_report_console(summary: dict[str, Any]) -> str:
    """Format structured metrics dictionary into a readable CLI report."""
    counts = summary.get("sample_counts", {})
    workflows = summary.get("workflows", {})
    latency = summary.get("latency", {}).get("warm_turns", {})
    errors = summary.get("error_taxonomy", {})

    lines: list[str] = [
        "==================================================",
        "          PropRelay Operations & Metrics Report   ",
        "==================================================",
        f"Generated At: {summary.get('summary_timestamp')}",
        "",
        "--- Sample Counts ---",
        f"Total Sessions Recorded: {counts.get('total_sessions', 0)}",
        f"Total Conversational Turns: {counts.get('total_turns', 0)}",
        f"  - Cold Start Turns: {counts.get('cold_start_turns', 0)}",
        f"  - Warm Runtime Turns: {counts.get('warm_runtime_turns', 0)}",
        f"Total Errors Captured: {counts.get('total_errors', 0)}",
        "",
        "--- Workflow Execution Summary ---",
        f"Total Multi-Turn Workflows: {workflows.get('total_workflows', 0)}",
        f"Successfully Completed: {workflows.get('completed', 0)}",
        f"Abandoned / Cancelled: {workflows.get('abandoned', 0)}",
        f"Completion Rate: {workflows.get('completion_rate_pct')}%"
        if workflows.get("completion_rate_pct") is not None
        else "Completion Rate: N/A (no completed workflows)",
        "",
        "--- Latency Statistics (Warm Runtime Turns) ---",
    ]

    for metric_name, label in [
        ("t_stt_ms", "STT Transcription (ms)"),
        ("t_llm_ttft_ms", "LLM Time-To-First-Token (ms)"),
        ("t_llm_total_ms", "LLM Total Inference (ms)"),
        ("t_tts_ttfb_ms", "TTS Time-To-First-Byte (ms)"),
        ("t_turn_total_ms", "Total Reconstructed Turn (ms)"),
    ]:
        data = latency.get(metric_name, {})
        n = data.get("sample_count", 0)
        p50 = data.get("p50")
        p95 = data.get("p95")
        mean = data.get("mean")
        lines.append(f"• {label:<32} [N={n}]")
        lines.append(f"    p50: {p50:<20} p95: {p95:<20} mean: {mean}")

    lines.extend(
        [
            "",
            "--- Error Taxonomy Breakdown ---",
        ]
    )
    if not errors:
        lines.append("No system or policy errors recorded.")
    else:
        for code, count in errors.items():
            lines.append(f"  {code:<24}: {count}")

    lines.extend(
        [
            "",
            "--- Metric Provenance Declarations ---",
            "  LiveKit Native Metric  : STT, LLM TTFT, LLM duration, TTS TTFB, EOU",
            "  Custom App Timer       : Tool execution latency",
            "  Domain Event Timestamp : Workflow start/completion duration",
            "  Derived Metric         : Total reconstructed turn latency, Percentiles",
            "==================================================",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    """CLI runner for observability reporting."""
    parser = argparse.ArgumentParser(description="PropRelay Operations Metrics Report")
    parser.add_argument(
        "--metrics-file",
        default="data/metrics.jsonl",
        help="Path to metrics JSONL file (default: data/metrics.jsonl)",
    )
    parser.add_argument(
        "--reports-file",
        default="data/session_reports.jsonl",
        help="Path to session reports JSONL file (default: data/session_reports.jsonl)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON summary",
    )

    args = parser.parse_args()

    store = MetricsStore(metrics_file=args.metrics_file, reports_file=args.reports_file)
    summary = store.get_metrics_summary()

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(format_report_console(summary))


if __name__ == "__main__":
    main()
