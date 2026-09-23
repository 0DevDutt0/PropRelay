"""Report generators for evaluation results and release gate (JSON and Markdown)."""

from __future__ import annotations

from pathlib import Path

from proprelay.evaluation.models import SuiteReport


def format_markdown_report(report: SuiteReport) -> str:
    """Format an evaluation suite report into clean GitHub-flavored markdown."""
    status_badge = "READY" if report.release_gate_status == "READY" else "BLOCKED"

    lines: list[str] = [
        "# PropRelay — Evaluation & Behavioral Verification Report",
        "",
        f"**Release Gate Status**: `{status_badge}` ({report.passed_scenarios}/{report.total_scenarios} scenarios passed)  ",
        f"**Pass Rate**: `{report.pass_rate_pct}%`  ",
        f"**Critical Failures**: `{report.critical_failures_count}` | **Major Failures**: `{report.major_failures_count}` | **Minor Failures**: `{report.minor_failures_count}`  ",
        f"**Execution Timestamp**: `{report.timestamp.isoformat()}`  ",
        "",
        "## 1. Executive Summary & Quality Metrics",
        "",
        "| Metric | Result | Target Benchmark | Gate Status |",
        "| :--- | :--- | :--- | :--- |",
        f"| **Scenario Pass Rate** | {report.pass_rate_pct}% | >= 95.0% | {'PASS' if report.pass_rate_pct >= 95.0 else 'FAIL'} |",
        f"| **Tool Selection Accuracy** | {report.tool_accuracy_pct}% | 100% | {'PASS' if report.tool_accuracy_pct == 100 else 'WARN'} |",
        f"| **Tool Argument Precision** | {report.tool_argument_accuracy_pct}% | 100% | {'PASS' if report.tool_argument_accuracy_pct == 100 else 'WARN'} |",
        f"| **Consequential Action Safety** | {report.booking_safety_rate_pct}% | 100% | {'PASS' if report.booking_safety_rate_pct == 100 else 'FAIL'} |",
        f"| **Domain Grounding Rate** | {report.grounding_rate_pct}% | 100% | {'PASS' if report.grounding_rate_pct == 100 else 'FAIL'} |",
        f"| **Two-Phase Confirmation Safety** | {report.confirmation_safety_rate_pct}% | 100% | {'PASS' if report.confirmation_safety_rate_pct == 100 else 'FAIL'} |",
        f"| **Stale Action Prevention Rate** | {report.stale_action_prevention_rate_pct}% | 100% | {'PASS' if report.stale_action_prevention_rate_pct == 100 else 'FAIL'} |",
        f"| **Workflow Completion Rate** | {report.workflow_completion_rate_pct}% | N/A (behavioral) | INFO |",
        f"| **Average Tool Calls / Scenario** | {report.average_tool_calls} | < 4.0 | INFO |",
        "",
        "## 2. Release Gate Verdict",
        "",
    ]

    if report.release_gate_status == "READY":
        lines.append(
            "> [!NOTE]\n"
            "> **RELEASE STATUS: READY**\n"
            "> All critical safety, grounding, and confirmation gates passed with zero regressions."
        )
    else:
        lines.append(
            "> [!CAUTION]\n"
            "> **RELEASE STATUS: BLOCKED**\n"
            "> One or more critical assertions failed. Release gate has blocked promotion:\n"
        )
        for r in report.release_gate_reasons:
            lines.append(f"> - {r}")

    lines.extend(
        [
            "",
            "## 3. Scenario-by-Scenario Evaluation Results",
            "",
            "| Scenario ID | Name | Category | Duration | Checks Passed | Result |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )

    for res in report.results:
        checks_passed = sum(1 for c in res.checks if c.passed)
        total_checks = len(res.checks)
        res_str = "**PASS**" if res.passed else "**FAIL**"
        lines.append(
            f"| `{res.scenario_id}` | {res.name} | `{res.category}` | {res.duration_ms:.1f}ms | {checks_passed}/{total_checks} | {res_str} |"
        )

    lines.extend(
        [
            "",
            "## 4. Detailed Check Diagnostics",
            "",
        ]
    )

    for res in report.results:
        lines.append(f"### Scenario `{res.scenario_id}`: {res.name}")
        lines.append(f"*{res.description}*  ")
        lines.append(
            f"- **Final State Transitions**: `{' -> '.join(res.state_transitions) or 'IDLE'}`"
        )
        lines.append(f"- **Domain Events Recorded**: `{len(res.events)}` events")
        lines.append("")
        lines.append("| Check / Judge | Severity | Expected | Actual | Result | Notes |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for c in res.checks:
            c_res = "PASS" if c.passed else "**FAIL**"
            exp = str(c.expected).replace("|", "\\|")[:35]
            act = str(c.actual).replace("|", "\\|")[:35]
            notes = (c.reason or "OK").replace("|", "\\|")[:50]
            lines.append(f"| `{c.name}` | `{c.severity}` | `{exp}` | `{act}` | {c_res} | {notes} |")
        lines.append("")

    lines.extend(
        [
            "## 5. Evaluation Methodology & Invariants",
            "",
            "- **Authoritative Layer**: Deterministic judges (no probabilistic LLM judgment can override domain safety constraints).",
            "- **Zero Cloud Cost**: 100% local execution against deterministic in-memory domain engine and fixture catalog.",
            "- **Grounding Assertions**: All property and calendar slot IDs validated against authoritative fixture set (`data/listings.json`, `data/showings.json`).",
            "- **Two-Phase Confirmation**: State mutations cannot be committed without explicit user confirmation acceptance.",
            "",
        ]
    )

    return "\n".join(lines)


def write_evaluation_reports(
    report: SuiteReport, output_dir: str | Path = "reports/evaluation"
) -> tuple[Path, Path]:
    """Persist latest and release gate evaluation results as JSON and Markdown."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    content_json = report.model_dump_json(indent=2)
    content_md = format_markdown_report(report)

    # Write latest.json and latest.md
    json_path = out / "latest.json"
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(content_json)

    md_path = out / "latest.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content_md)

    # Write release_gate.json and release_gate.md
    gate_json = out / "release_gate.json"
    with open(gate_json, "w", encoding="utf-8") as f:
        f.write(content_json)

    gate_md = out / "release_gate.md"
    with open(gate_md, "w", encoding="utf-8") as f:
        f.write(content_md)

    return json_path, md_path
