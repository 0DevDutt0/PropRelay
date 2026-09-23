"""System environment and hardware telemetry probe for performance benchmarking."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Any


def get_system_telemetry() -> dict[str, Any]:
    """Capture full hardware, OS, and software environment metadata."""
    info: dict[str, Any] = {
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
        },
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
        },
        "cpu": {
            "cpu_count_logical": os.cpu_count() or 1,
        },
        "gpu": {
            "name": "Unknown",
            "driver_version": "Unknown",
            "cuda_version": "Unknown",
            "total_vram_mb": 0.0,
            "free_vram_mb": 0.0,
            "used_vram_mb": 0.0,
            "available": False,
        },
        "ram": {
            "total_mb": 0.0,
            "available_mb": 0.0,
        },
        "models": {
            "stt_default": os.getenv("PROPRELAY_STT_MODEL", "base.en"),
            "llm_default": os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            "tts_default": "kokoro-v1.0.onnx (af_alloy)",
            "vad_default": "silero-v5",
            "turn_detector_default": "turn-detector-v1-mini",
        },
        "git": {
            "commit": "workspace-uncommitted",
            "branch": "main",
        },
    }

    # Probe CPU via wmic or PowerShell on Windows
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"],
            capture_output=True,
            text=True,
            timeout=3.0,
        )
        if res.returncode == 0 and res.stdout.strip():
            info["cpu"]["model_name"] = res.stdout.strip().splitlines()[0]
    except Exception:
        info["cpu"]["model_name"] = platform.processor()

    # Probe RAM via PowerShell on Windows
    try:
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                '$os = Get-CimInstance Win32_OperatingSystem; Write-Output "$([math]::Round($os.TotalVisibleMemorySize/1024)),$([math]::Round($os.FreePhysicalMemory/1024))"',
            ],
            capture_output=True,
            text=True,
            timeout=3.0,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = res.stdout.strip().split(",")
            if len(parts) >= 2:
                info["ram"]["total_mb"] = float(parts[0])
                info["ram"]["available_mb"] = float(parts[1])
    except Exception:
        pass

    # Probe GPU via nvidia-smi
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total,memory.free,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3.0,
        )
        if res.returncode == 0 and res.stdout.strip():
            line = res.stdout.strip().splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                info["gpu"]["name"] = parts[0]
                info["gpu"]["driver_version"] = parts[1]
                info["gpu"]["total_vram_mb"] = float(parts[2])
                info["gpu"]["free_vram_mb"] = float(parts[3])
                info["gpu"]["used_vram_mb"] = float(parts[4])
                info["gpu"]["available"] = True
    except Exception:
        pass

    # Probe Git commit if available
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if res.returncode == 0 and res.stdout.strip():
            info["git"]["commit"] = res.stdout.strip()
    except Exception:
        pass

    return info


def get_current_process_resources() -> dict[str, float]:
    """Capture current process and GPU resource utilization."""
    resources: dict[str, float] = {
        "gpu_utilization_percent": 0.0,
        "vram_used_mb": 0.0,
        "vram_free_mb": 0.0,
    }
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if res.returncode == 0 and res.stdout.strip():
            line = res.stdout.strip().splitlines()[0]
            parts = [float(p.strip()) for p in line.split(",")]
            if len(parts) >= 3:
                resources["gpu_utilization_percent"] = parts[0]
                resources["vram_used_mb"] = parts[1]
                resources["vram_free_mb"] = parts[2]
    except Exception:
        pass
    return resources
