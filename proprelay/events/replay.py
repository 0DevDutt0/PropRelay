"""Local Event Replay & Integrity Inspection Tool for PropRelay Event Journals."""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
from typing import Any

from proprelay.events.journal import EventJournal
from proprelay.events.schemas import DomainEvent, EventType


class EventReplayEngine:
    """Read-only replay and diagnostic inspection engine for local event journals."""

    def __init__(self, journal_path: str | Path = "data/events.jsonl") -> None:
        self.journal_path = Path(journal_path)
        self.journal = EventJournal(self.journal_path)

    def load_events(
        self,
        session_id: str | None = None,
        workflow_id: str | None = None,
        event_type: str | None = None,
        since: datetime.datetime | None = None,
        until: datetime.datetime | None = None,
    ) -> list[DomainEvent]:
        """Load and filter events in strict sequential order."""
        raw_events = self.journal.read_all(skip_malformed=True)
        filtered: list[DomainEvent] = []

        for ev in raw_events:
            if session_id and ev.session_id != session_id:
                continue
            if workflow_id and ev.workflow_id != workflow_id:
                continue
            if event_type and ev.event_type != event_type:
                continue
            if since and ev.timestamp < since:
                continue
            if until and ev.timestamp > until:
                continue
            filtered.append(ev)

        return filtered

    def inspect_diagnostics(self) -> dict[str, Any]:
        """Perform comprehensive integrity and anomaly diagnostics over the journal."""
        is_valid, integrity_issues = self.journal.verify_integrity()
        events = self.journal.read_all(skip_malformed=True)

        unknown_types: list[str] = []
        known_types = {e.value for e in EventType}
        missing_correlation: list[str] = []
        duplicate_events: list[str] = []
        seen_ids: set[str] = set()

        for ev in events:
            if ev.event_id in seen_ids:
                duplicate_events.append(ev.event_id)
            seen_ids.add(ev.event_id)

            if ev.event_type not in known_types:
                unknown_types.append(f"{ev.event_id} ({ev.event_type})")

            # Consequential actions should carry correlation identifiers
            if ("showing.book" in ev.event_type or "showing.reschedule" in ev.event_type) and (
                not ev.session_id or not ev.turn_id
            ):
                missing_correlation.append(
                    f"Event {ev.event_id} ({ev.event_type}) missing session_id or turn_id"
                )

        return {
            "total_events": len(events),
            "integrity_valid": is_valid,
            "integrity_issues": integrity_issues,
            "duplicate_ids": duplicate_events,
            "unknown_event_types": unknown_types,
            "missing_correlation": missing_correlation,
        }

    def group_by_session_and_workflow(
        self, events: list[DomainEvent]
    ) -> dict[str, dict[str, list[DomainEvent]]]:
        """Group events hierarchically: session_id -> workflow_id -> list of events."""
        tree: dict[str, dict[str, list[DomainEvent]]] = {}
        for ev in events:
            sess = ev.session_id or "unspecified_session"
            wf = ev.workflow_id or "unspecified_workflow"
            if sess not in tree:
                tree[sess] = {}
            if wf not in tree[sess]:
                tree[sess][wf] = []
            tree[sess][wf].append(ev)
        return tree

    def format_summary(self, events: list[DomainEvent]) -> str:
        """Format an ASCII timeline summary grouped by session and workflow."""
        if not events:
            return "No matching domain events found in journal."

        grouped = self.group_by_session_and_workflow(events)
        lines: list[str] = [
            f"=== PropRelay Event Replay ({len(events)} events) ===",
            "",
        ]

        for sess, workflows in grouped.items():
            lines.append(f"Session: {sess}")
            for wf, ev_list in workflows.items():
                lines.append(f"  Workflow: {wf}")
                for idx, ev in enumerate(ev_list, start=1):
                    seq_str = (
                        f"#{ev.sequence_number}" if ev.sequence_number is not None else f"{idx}"
                    )
                    tool_info = f" [tool: {ev.tool_name}]" if ev.tool_name else ""
                    dur_info = f" ({ev.duration_ms:.1f}ms)" if ev.duration_ms is not None else ""
                    ts = ev.timestamp.strftime("%H:%M:%S.%f")[:-3]
                    lines.append(f"    {seq_str:<5} {ts}  {ev.event_type:<32}{tool_info}{dur_info}")
                lines.append("")

        return "\n".join(lines)


def main() -> None:
    """CLI entrypoint for event replay and journal diagnostics."""
    parser = argparse.ArgumentParser(
        description="PropRelay Local Event Replay & Integrity Inspector"
    )
    parser.add_argument(
        "journal_path",
        nargs="?",
        default="data/events.jsonl",
        help="Path to JSONL event journal file (default: data/events.jsonl)",
    )
    parser.add_argument("--session", help="Filter by session_id")
    parser.add_argument("--workflow", help="Filter by workflow_id")
    parser.add_argument("--event-type", help="Filter by event_type name")
    parser.add_argument(
        "--since", help="Filter events since UTC ISO timestamp (e.g. 2026-09-23T00:00:00)"
    )
    parser.add_argument("--until", help="Filter events until UTC ISO timestamp")
    parser.add_argument(
        "--check-integrity", action="store_true", help="Run full cryptographic hash chain check"
    )
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON format")

    args = parser.parse_args()

    engine = EventReplayEngine(args.journal_path)

    since_dt = datetime.datetime.fromisoformat(args.since) if args.since else None
    until_dt = datetime.datetime.fromisoformat(args.until) if args.until else None

    events = engine.load_events(
        session_id=args.session,
        workflow_id=args.workflow,
        event_type=args.event_type,
        since=since_dt,
        until=until_dt,
    )

    diagnostics = engine.inspect_diagnostics()

    if args.json:
        output: dict[str, Any] = {
            "journal_path": str(args.journal_path),
            "filter": {
                "session": args.session,
                "workflow": args.workflow,
                "event_type": args.event_type,
            },
            "diagnostics": diagnostics,
            "events": [ev.model_dump(mode="json") for ev in events],
        }
        print(json.dumps(output, indent=2))
        return

    # Print human-readable summary
    print(engine.format_summary(events))

    if args.check_integrity or diagnostics["integrity_issues"]:
        print("--- Journal Integrity Report ---")
        if diagnostics["integrity_valid"]:
            print("Status: PASS (Hash chain verified, sequential ordering intact)")
        else:
            print("Status: FAIL (Integrity issues detected):")
            for issue in diagnostics["integrity_issues"]:
                print(f"  - {issue}")

    if diagnostics["unknown_event_types"]:
        print("\nWarnings:")
        for warn in diagnostics["unknown_event_types"]:
            print(f"  [Unknown Event Type] {warn}")

    if diagnostics["missing_correlation"]:
        print("\nCorrelation Warnings:")
        for warn in diagnostics["missing_correlation"]:
            print(f"  [Missing Correlation] {warn}")


if __name__ == "__main__":
    main()
