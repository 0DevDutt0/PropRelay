"""Deterministic scenario replay CLI for reproducible evaluation debugging."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from proprelay.evaluation.models import ScenarioDefinition
from proprelay.evaluation.runner import ScenarioRunner

console = Console()


def find_scenario_file(scenario_id: str, scenarios_dir: Path) -> Path | None:
    """Find scenario YAML file matching ID (case-insensitive)."""
    norm_id = scenario_id.lower().strip()
    for p in scenarios_dir.glob("*.yaml"):
        if p.stem.lower().startswith(norm_id) or f"_{norm_id}_" in p.stem.lower():
            return p
    for p in scenarios_dir.glob("*.json"):
        if p.stem.lower().startswith(norm_id):
            return p
    return None


async def replay_scenario(scenario_path: Path, verbose: bool = False) -> bool:
    """Replay a scenario file and print detailed execution trace."""
    console.print(f"[bold cyan]Replaying scenario from:[/bold cyan] {scenario_path}")

    content = scenario_path.read_text(encoding="utf-8")
    if scenario_path.suffix.lower() in {".yaml", ".yml"}:
        import yaml

        data = yaml.safe_load(content)
    else:
        data = json.loads(content)

    # Handle failure dump format vs scenario definition format
    if "scenario_id" in data and "turns" in data and "id" not in data:
        data["id"] = data["scenario_id"]

    scenario = ScenarioDefinition(**data)
    runner = ScenarioRunner()
    result = await runner.run_scenario(scenario)

    console.print()
    status_color = "green" if result.passed else "red"
    console.print(
        Panel(
            f"[bold {status_color}]Scenario {result.scenario_id}: {result.name}[/bold {status_color}]\n"
            f"[dim]{result.description}[/dim]\n"
            f"Result: [bold {status_color}]{'PASSED' if result.passed else 'FAILED'}[/bold {status_color}] "
            f"in {result.duration_ms:.2f}ms",
            title="Replay Execution Summary",
            expand=False,
        )
    )

    # Tool calls table
    tool_table = Table(title="Turn-by-Turn Tool Execution", show_header=True, header_style="bold magenta")
    tool_table.add_column("Turn", justify="right", width=6)
    tool_table.add_column("Action / Tool", width=22)
    tool_table.add_column("Success", justify="center", width=8)
    tool_table.add_column("Duration", justify="right", width=10)
    tool_table.add_column("Message / Error", width=40)

    for tc in result.tool_calls:
        success_str = "[green]YES[/green]" if tc.get("success") else "[red]NO[/red]"
        tool_table.add_row(
            str(tc.get("turn", 0)),
            tc.get("action", ""),
            success_str,
            f"{tc.get('duration_ms', 0):.2f}ms",
            str(tc.get("message") or ""),
        )
    console.print(tool_table)

    # Judge assertions table
    judge_table = Table(title="Judge Assertions & Invariants", show_header=True, header_style="bold blue")
    judge_table.add_column("Judge", width=22)
    judge_table.add_column("Severity", width=10)
    judge_table.add_column("Status", justify="center", width=8)
    judge_table.add_column("Details", width=44)

    for chk in result.checks:
        chk_status = "[green]PASS[/green]" if chk.passed else "[red]FAIL[/red]"
        sev_color = {
            "CRITICAL": "red",
            "MAJOR": "bright_yellow",
            "MINOR": "cyan",
            "INFO": "dim",
        }.get(chk.severity.value, "white")
        judge_table.add_row(
            chk.name,
            f"[{sev_color}]{chk.severity.value}[/{sev_color}]",
            chk_status,
            chk.reason or f"Expected {chk.expected} == Actual {chk.actual}",
        )
    console.print(judge_table)

    # Observed events
    if verbose:
        console.print(f"\n[bold]Captured Domain Events ({len(result.events)}):[/bold]")
        for i, ev in enumerate(result.events, 1):
            console.print(f"  {i}. [dim]{ev}[/dim]")

    return result.passed


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="proprelay.evaluation.replay",
        description="Deterministically replay and verify an evaluation scenario or failure fixture.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-s",
        "--scenario",
        help="Scenario ID (e.g. S04, S12, S18)",
    )
    group.add_argument(
        "-f",
        "--file",
        type=Path,
        help="Path to scenario YAML or failure fixture JSON",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose diagnostics including all captured domain events",
    )
    args = parser.parse_args()

    target_file: Path | None = None
    if args.file:
        target_file = args.file
        if not target_file.exists():
            console.print(f"[bold red]Error:[/bold red] File not found: {target_file}")
            sys.exit(1)
    else:
        scenarios_dir = Path("tests/scenarios")
        target_file = find_scenario_file(args.scenario, scenarios_dir)
        if not target_file:
            console.print(
                f"[bold red]Error:[/bold red] Scenario '{args.scenario}' not found in {scenarios_dir}"
            )
            sys.exit(1)

    passed = asyncio.run(replay_scenario(target_file, verbose=args.verbose))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
