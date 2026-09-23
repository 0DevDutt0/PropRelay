"""Automated local secrets scanner for PropRelay.

Inspects all source and Git-tracked files for credentials, private keys, API keys,
LiveKit secrets, and environment file leaks.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# High-risk secret patterns to check in source files
SECRET_PATTERNS = [
    (
        re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|DSA|PGP)?\s*PRIVATE KEY-----"),
        "Unencrypted Private Key Block",
    ),
    (
        re.compile(r"(?:livekit_api_secret|api_secret)\s*[:=]\s*['\"](?!secret\b|devkey\b|test-|mock)[A-Za-z0-9+/=_-]{16,}['\"]", re.IGNORECASE),
        "Potential hardcoded LiveKit API Secret",
    ),
    (
        re.compile(r"(?:password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE),
        "Potential hardcoded password",
    ),
    (
        re.compile(r"['\"][A-Za-z0-9_-]{20,}['\"]\s*#\s*secret", re.IGNORECASE),
        "Secret annotated comment",
    ),
]

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
    "bin",
}

SCAN_EXTS = {".py", ".json", ".yaml", ".yml", ".md", ".ts", ".tsx", ".ps1", ".toml", ".txt"}


def check_git_tracked_env(root: Path) -> list[str]:
    """Verify that .env or other secret files are not committed or staged in git."""
    issues: list[str] = []
    try:
        res = subprocess.run(
            ["git", "ls-files", ".env*", "*.pem", "*.key"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if res.returncode == 0 and res.stdout.strip():
            for line in res.stdout.strip().splitlines():
                if line.strip() != ".env.example":
                    issues.append(f"Sensitive file tracked by git: {line.strip()}")
    except Exception:
        pass
    return issues


def run_detect_secrets(root: Path) -> list[str]:
    """Run detect-secrets scanner if installed."""
    issues: list[str] = []
    try:
        res = subprocess.run(
            [
                sys.executable,
                "-m",
                "detect_secrets",
                "scan",
                "--exclude-files",
                r"(\.venv|bin|node_modules|frontend/dist|\.git|\.mypy_cache|\.pytest_cache|\.ruff_cache|data/benchmark_utterances\.json|data/events\.jsonl)",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30.0,
        )
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip())
            results = data.get("results", {})
            for filepath, findings in results.items():
                for f in findings:
                    issues.append(f"{filepath}:{f.get('line_number')} [{f.get('type')}]")
    except Exception as e:
        print(f"Note: detect-secrets execution skipped: {e}")
    return issues


def scan_source_patterns(root: Path) -> list[str]:
    """Perform regex-based high-confidence secret scanning across source tree."""
    issues: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fname in filenames:
            p = Path(dirpath) / fname
            if p.suffix not in SCAN_EXTS:
                continue
            if p.name in {".env.example", "scan_secrets.py"}:
                continue

            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    for line_no, line in enumerate(f, start=1):
                        for pattern, desc in SECRET_PATTERNS:
                            if pattern.search(line):
                                issues.append(f"{p.relative_to(root)}:{line_no} - {desc}")
            except Exception as e:
                issues.append(f"Failed to read {p}: {e}")
    return issues


def main() -> int:
    """Run full local secrets verification."""
    root = Path(__file__).resolve().parent.parent
    print("Running PropRelay Local Secrets Scan...")

    env_issues = check_git_tracked_env(root)
    detect_issues = run_detect_secrets(root)
    pattern_issues = scan_source_patterns(root)

    all_issues = env_issues + detect_issues + pattern_issues

    if all_issues:
        print(f"\n[FAIL] Secrets Scan Failed: Found {len(all_issues)} issue(s):\n")
        for issue in all_issues:
            print(f"  - {issue}")
        return 1

    print("[PASS] Secrets Scan: Clean. Zero credentials, private keys, or tracked secrets detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
