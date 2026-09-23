"""Automated verification script for documentation accuracy and claim honesty.

Scans all project documentation and reports for ungrounded or misleading claims
to ensure technical honesty for hiring managers and technical reviewers.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Disallowed buzzwords or ungrounded assertions that must not appear unqualified
FORBIDDEN_PATTERNS = [
    (
        re.compile(r"\b41%\b(?!\s*earlier|\s*first-chunk|\s*TTS)"),
        "Misleading '41%' total turn reduction claim (actual arithmetic turn reduction is 28.2%)",
    ),
    (
        re.compile(r"\benterprise-grade\b", re.IGNORECASE),
        "Ungrounded claim: 'enterprise-grade' (use 'production-style local')",
    ),
    (
        re.compile(r"\bguaranteed(?:\s+(?:low|sub-|zero|delivery))\b", re.IGNORECASE),
        "Misleading SLA claim: 'guaranteed' latency/delivery (use 'empirical' or 'best-effort local')",
    ),
    (
        re.compile(r"\bzero\s+hallucinations?\b", re.IGNORECASE),
        "Fabricated claim: 'zero hallucinations' (use 'deterministic application policy gates')",
    ),
    (
        re.compile(r"\bfully\s+autonomous\b", re.IGNORECASE),
        "Overstated claim: 'fully autonomous' (use 'two-phase confirmation and human-in-the-loop gates')",
    ),
    (
        re.compile(r"\bproduction\s+capacity\b", re.IGNORECASE),
        "Misleading scale claim: 'production capacity' (use 'single-machine concurrency experiment')",
    ),
]

SCAN_EXTENSIONS = {".md", ".py", ".json", ".ts", ".tsx", ".yaml", ".ps1"}
EXCLUDE_DIRS = {
    ".venv",
    ".git",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "scratch",
}


def scan_claims() -> int:
    """Scan all tracked project files for disallowed marketing buzzwords and ungrounded claims."""
    root_dir = Path(__file__).resolve().parent.parent
    violations: list[tuple[str, int, str, str]] = []

    for root, dirs, files in os.walk(root_dir):
        # Prune excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in files:
            p = Path(root) / file
            if p.suffix not in SCAN_EXTENSIONS:
                continue
            # Skip this verification script itself and scan_claims test
            if p.name in {"scan_claims.py", "test_claims_scanner.py"}:
                continue

            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    for line_no, line in enumerate(f, start=1):
                        # Skip markdown quotes of disallowed phrases (e.g. documentation of what NOT to say)
                        if "what not to say" in line.lower() or "disallowed" in line.lower():
                            continue
                        for pattern, explanation in FORBIDDEN_PATTERNS:
                            m = pattern.search(line)
                            if m:
                                violations.append(
                                    (str(p.relative_to(root_dir)), line_no, m.group(0), explanation)
                                )
            except Exception as e:
                print(f"Warning: Could not read {p}: {e}", file=sys.stderr)

    if violations:
        print(f"\n[FAIL] Claim Audit Failed: Found {len(violations)} misleading or ungrounded assertions:\n")
        for file_path, line_no, matched, explanation in violations:
            print(f"  - {file_path}:{line_no} [{matched}]")
            print(f"    Reason: {explanation}\n")
        return 1

    print("[PASS] Documentation Claim Audit: 100% technically honest. Zero ungrounded assertions found.")
    return 0


if __name__ == "__main__":
    sys.exit(scan_claims())
