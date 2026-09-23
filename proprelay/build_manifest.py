"""Build manifest and runtime provenance generator for PropRelay."""

from __future__ import annotations

import argparse
import datetime
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from proprelay import __version__
from proprelay.config import get_config


def get_git_commit() -> str:
    """Safely obtain current git commit hash, or 'untracked' if git is unavailable."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
        )
        return res.stdout.strip()
    except Exception:
        return "uncommitted/unknown"


def get_installed_packages(package_names: list[str]) -> dict[str, str]:
    """Retrieve installed version for specified packages."""
    versions: dict[str, str] = {}
    for name in package_names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not_installed"
        except Exception as e:
            versions[name] = f"error: {e}"
    return versions


def generate_manifest() -> dict[str, Any]:
    """Generate comprehensive build provenance manifest."""
    config = get_config()

    core_packages = [
        "livekit",
        "livekit-agents",
        "fastapi",
        "uvicorn",
        "pydantic",
        "faster-whisper",
        "ollama",
        "kokoro-onnx",
        "sounddevice",
        "numpy",
        "rich",
        "pytest",
        "ruff",
        "mypy",
        "bandit",
    ]

    return {
        "project": "PropRelay",
        "version": __version__,
        "app_profile": config.profile.value,
        "built_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "git_commit": get_git_commit(),
        "runtime": {
            "python_version": sys.version.split()[0],
            "python_implementation": platform.python_implementation(),
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
        },
        "neural_models": {
            "stt": {
                "name": "faster-whisper-base.en",
                "framework": "CTranslate2 (int8 CPU / float16 CUDA)",
                "source": "Systran/faster-whisper-base.en",
                "license": "MIT",
                "local_only": True,
            },
            "llm": {
                "name": config.ollama_model,
                "framework": "Ollama (llama.cpp GGUF 4-bit quant)",
                "source": "Qwen/Qwen2.5-3B-Instruct",
                "license": "Apache-2.0",
                "local_only": True,
            },
            "tts": {
                "name": "Kokoro-82M",
                "framework": "ONNX Runtime (82M params fp32/fp16)",
                "source": "hexgrad/Kokoro-82M",
                "license": "Apache-2.0",
                "local_only": True,
            },
        },
        "installed_dependencies": get_installed_packages(core_packages),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="proprelay.build_manifest",
        description="Emit build provenance manifest for PropRelay release verification.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional path to write build manifest JSON (e.g. build_manifest.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON to stdout",
    )
    args = parser.parse_args()

    manifest = generate_manifest()
    json_str = json.dumps(manifest, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json_str, encoding="utf-8")
        print(f"Wrote build manifest to {args.output}")

    if args.json or not args.output:
        print(json_str)


if __name__ == "__main__":
    main()
