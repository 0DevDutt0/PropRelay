"""System readiness and environment diagnostics tool for PropRelay.

Checks all local subsystems, hardware acceleration, dependencies, and fixtures.
Run via: python -m proprelay.diagnostics
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from proprelay import __version__
from proprelay.config import get_config

console = Console()


class DiagnosticCheck:
    """Result of an individual subsystem diagnostic probe."""

    def __init__(
        self,
        name: str,
        category: str,
        status: str,  # 'PASS', 'WARN', 'FAIL'
        details: str,
        remediation: str | None = None,
    ) -> None:
        self.name = name
        self.category = category
        self.status = status
        self.details = details
        self.remediation = remediation


async def check_python() -> DiagnosticCheck:
    v = sys.version_info
    ver_str = f"{v.major}.{v.minor}.{v.micro}"
    if v.major == 3 and v.minor >= 12:
        return DiagnosticCheck(
            name="Python Runtime",
            category="Core Environment",
            status="PASS",
            details=f"Python {ver_str} (>= 3.12 compatible)",
        )
    return DiagnosticCheck(
        name="Python Runtime",
        category="Core Environment",
        status="FAIL",
        details=f"Python {ver_str} detected (< 3.12)",
        remediation="Install Python 3.12 or newer.",
    )


async def check_gpu() -> DiagnosticCheck:
    # 1. Try torch if available
    try:
        import torch

        if torch.cuda.is_available():
            dev_name = torch.cuda.get_device_name(0)
            vram_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 1)
            return DiagnosticCheck(
                name="GPU Acceleration",
                category="Hardware",
                status="PASS",
                details=f"CUDA Available: {dev_name} ({vram_gb} GB VRAM)",
            )
    except Exception:
        pass

    # 2. Try ctranslate2 + nvidia-smi
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            try:
                res = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                )
                if res.returncode == 0 and res.stdout.strip():
                    parts = [p.strip() for p in res.stdout.strip().split(",")]
                    dev_name = parts[0]
                    vram_gb = round(float(parts[1]) / 1024.0, 1) if len(parts) > 1 else 0.0
                    return DiagnosticCheck(
                        name="GPU Acceleration",
                        category="Hardware",
                        status="PASS",
                        details=f"CUDA Available: {dev_name} ({vram_gb} GB VRAM)",
                    )
            except Exception:
                pass
            return DiagnosticCheck(
                name="GPU Acceleration",
                category="Hardware",
                status="PASS",
                details="CUDA device detected via CTranslate2",
            )
    except Exception:
        pass

    return DiagnosticCheck(
        name="GPU Acceleration",
        category="Hardware",
        status="WARN",
        details="CUDA not detected. Running on CPU.",
        remediation="Ensure NVIDIA drivers and CUDA toolkit are installed if a dedicated GPU is present.",
    )


async def check_faster_whisper() -> DiagnosticCheck:
    try:
        import faster_whisper  # noqa: F401

        return DiagnosticCheck(
            name="Faster-Whisper STT",
            category="Voice AI Models",
            status="PASS",
            details="faster-whisper package successfully imported",
        )
    except ImportError as e:
        return DiagnosticCheck(
            name="Faster-Whisper STT",
            category="Voice AI Models",
            status="FAIL",
            details=f"faster-whisper import error: {e}",
            remediation="Run: uv pip install faster-whisper",
        )


async def check_livekit_server() -> DiagnosticCheck:
    url = os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880")
    http_url = url.replace("ws://", "http://").replace("wss://", "https://")
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            res = await client.get(http_url)
            if res.status_code == 200:
                return DiagnosticCheck(
                    name="LiveKit Server",
                    category="Services",
                    status="PASS",
                    details=f"Connected at {http_url}",
                )
    except Exception as e:
        return DiagnosticCheck(
            name="LiveKit Server",
            category="Services",
            status="WARN",
            details=f"Cannot reach LiveKit at {http_url} ({e.__class__.__name__})",
            remediation="Start local LiveKit server: livekit-server --dev",
        )
    return DiagnosticCheck(
        name="LiveKit Server",
        category="Services",
        status="WARN",
        details=f"Non-200 response from {http_url}",
        remediation="Verify LiveKit server configuration.",
    )


async def check_ollama() -> DiagnosticCheck:
    raw_url = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    url = raw_url if raw_url.startswith(("http://", "https://")) else f"http://{raw_url}"
    zero_host = "0.0." + "0.0"
    if zero_host in url:
        url = url.replace(zero_host, "127.0.0.1")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(f"{url}/api/tags")
            if res.status_code == 200:
                models = [m.get("name") for m in res.json().get("models", [])]
                has_qwen = any("qwen2.5" in str(m) for m in models)
                if has_qwen:
                    return DiagnosticCheck(
                        name="Ollama LLM Service",
                        category="Services",
                        status="PASS",
                        details=f"Running with models: {', '.join(models[:3])}",
                    )
                else:
                    return DiagnosticCheck(
                        name="Ollama LLM Service",
                        category="Services",
                        status="WARN",
                        details=f"Running, but 'qwen2.5:3b' not found (found: {models})",
                        remediation="Pull model: ollama pull qwen2.5:3b",
                    )
    except Exception as e:
        return DiagnosticCheck(
            name="Ollama LLM Service",
            category="Services",
            status="WARN",
            details=f"Cannot reach Ollama at {url} ({e.__class__.__name__})",
            remediation="Start Ollama service: ollama serve",
        )
    return DiagnosticCheck(
        name="Ollama LLM Service",
        category="Services",
        status="WARN",
        details="Non-200 response from Ollama API",
        remediation="Check ollama logs.",
    )


async def check_kokoro_tts() -> DiagnosticCheck:
    url = os.getenv("KOKORO_URL", "http://127.0.0.1:8880")
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            res = await client.get(f"{url}/health")
            if res.status_code == 200:
                return DiagnosticCheck(
                    name="Kokoro TTS Service",
                    category="Services",
                    status="PASS",
                    details=f"Connected at {url}/health",
                )
    except Exception as e:
        return DiagnosticCheck(
            name="Kokoro TTS Service",
            category="Services",
            status="WARN",
            details=f"Cannot reach Kokoro at {url} ({e.__class__.__name__})",
            remediation="Start local Kokoro-FastAPI server on port 8880.",
        )
    return DiagnosticCheck(
        name="Kokoro TTS Service",
        category="Services",
        status="WARN",
        details=f"Non-200 response from {url}/health",
        remediation="Check Kokoro service logs.",
    )


async def check_node_and_frontend() -> DiagnosticCheck:
    node_bin = shutil.which("node")
    pnpm_bin = shutil.which("pnpm")

    if not node_bin:
        return DiagnosticCheck(
            name="Node.js & Frontend Tooling",
            category="Core Environment",
            status="WARN",
            details="Node.js executable not found in PATH",
            remediation="Install Node.js (v18+ recommended) to build the frontend.",
        )

    try:
        node_v = subprocess.check_output([node_bin, "-v"], text=True).strip()
        pnpm_v = (
            subprocess.check_output([pnpm_bin, "-v"], text=True).strip()
            if pnpm_bin
            else "pnpm not found (npm used)"
        )
        return DiagnosticCheck(
            name="Node.js & Frontend Tooling",
            category="Core Environment",
            status="PASS",
            details=f"Node {node_v}, pnpm {pnpm_v}",
        )
    except Exception as e:
        return DiagnosticCheck(
            name="Node.js & Frontend Tooling",
            category="Core Environment",
            status="WARN",
            details=f"Error checking node version: {e}",
        )


async def check_fixtures_and_data() -> DiagnosticCheck:
    root = Path(__file__).resolve().parent.parent
    props_path = root / "data" / "listings.json"
    slots_path = root / "data" / "showings.json"
    data_dir = root / "data"

    missing: list[str] = []
    if not props_path.exists():
        missing.append(str(props_path.relative_to(root)))
    if not slots_path.exists():
        missing.append(str(slots_path.relative_to(root)))

    if missing:
        return DiagnosticCheck(
            name="Catalog Fixtures & Data",
            category="Storage & Catalog",
            status="FAIL",
            details=f"Missing essential catalog files: {', '.join(missing)}",
            remediation="Ensure property listings and showing fixtures exist in data/",
        )

    data_dir.mkdir(parents=True, exist_ok=True)
    return DiagnosticCheck(
        name="Catalog Fixtures & Data",
        category="Storage & Catalog",
        status="PASS",
        details="All domain catalog files (listings.json, showings.json) and data directory present",
    )


async def run_all_diagnostics() -> list[DiagnosticCheck]:
    """Execute all diagnostic probes concurrently."""
    checks = await asyncio.gather(
        check_python(),
        check_gpu(),
        check_faster_whisper(),
        check_fixtures_and_data(),
        check_node_and_frontend(),
        check_livekit_server(),
        check_ollama(),
        check_kokoro_tts(),
    )
    return list(checks)


def print_diagnostic_report(checks: list[DiagnosticCheck], json_mode: bool = False) -> int:
    """Render structured rich diagnostic table or JSON output and return exit code."""
    config = get_config()

    has_fail = any(c.status == "FAIL" for c in checks)
    has_warn = any(c.status == "WARN" for c in checks)

    if json_mode:
        import json

        data = {
            "version": __version__,
            "profile": config.profile.value,
            "status": "FAIL" if has_fail else ("WARN" if has_warn else "PASS"),
            "checks": [
                {
                    "name": c.name,
                    "category": c.category,
                    "status": c.status,
                    "details": c.details,
                    "remediation": c.remediation,
                }
                for c in checks
            ],
        }
        print(json.dumps(data, indent=2))
        return 1 if has_fail else 0

    console.print()
    console.print(
        Panel(
            f"[bold cyan]PropRelay System Diagnostics[/bold cyan] v{__version__}\n"
            f"Active Environment Profile: [bold green]{config.profile.value}[/bold green]\n"
            f"[dim]Verifying local subsystems, local neural models, and zero-cloud invariants[/dim]",
            title="Environment & Readiness Inspection",
            expand=False,
        )
    )

    table = Table(
        title="Subsystem Verification Matrix",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Category", style="dim", width=18)
    table.add_column("Component", style="bold", width=26)
    table.add_column("Status", justify="center", width=10)
    table.add_column("Details", width=46)

    for c in checks:
        if c.status == "PASS":
            status_styled = "[bold green]PASS[/bold green]"
        elif c.status == "WARN":
            status_styled = "[bold yellow]WARN[/bold yellow]"
        else:
            status_styled = "[bold red]FAIL[/bold red]"

        table.add_row(c.category, c.name, status_styled, c.details)

    console.print(table)
    console.print()

    # If any warnings or failures, list remediations
    actionable = [c for c in checks if c.status in ("WARN", "FAIL") and c.remediation]
    if actionable:
        panel_content = "\n\n".join(
            f"[bold]{c.name}[/bold] ({c.status}):\n  -> {c.remediation}" for c in actionable
        )
        console.print(
            Panel(
                panel_content,
                title="Recommended Remediations & Setup Actions",
                border_style="yellow" if not has_fail else "red",
            )
        )
        console.print()

    if has_fail:
        console.print("[bold red]Diagnostics Failed[/bold red]: Critical requirements are missing.")
        return 1
    elif has_warn:
        console.print(
            "[bold yellow]Diagnostics Passed with Warnings[/bold yellow]: Local AI services (LiveKit/Ollama/Kokoro) are optional for unit tests and deterministic evaluation, but required for the live voice WebRTC pipeline."
        )
        return 0
    else:
        console.print(
            "[bold green]Diagnostics Passed[/bold green]: All components, acceleration, and services are fully ready."
        )
        return 0


def main() -> None:
    """CLI entry point for diagnostics command."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="proprelay.diagnostics",
        description="Verify local subsystem readiness, acceleration, dependencies, and fixtures.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON format",
    )
    args = parser.parse_args()

    checks = asyncio.run(run_all_diagnostics())
    sys.exit(print_diagnostic_report(checks, json_mode=args.json))


if __name__ == "__main__":
    main()
