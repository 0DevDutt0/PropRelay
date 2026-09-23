"""Scenario loader and parser for multi-turn behavioral evaluation suites."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from proprelay.evaluation.models import ScenarioDefinition

logger = logging.getLogger(__name__)

DEFAULT_SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "scenarios"


def load_scenario(file_path: str | Path) -> ScenarioDefinition:
    """Load and validate an individual YAML scenario definition."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Scenario file not found: {p}")

    with open(p, encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    return ScenarioDefinition.model_validate(data)


def load_all_scenarios(scenarios_dir: str | Path | None = None) -> list[ScenarioDefinition]:
    """Discover, load, and sort all YAML scenarios in the scenarios directory."""
    target_dir = Path(scenarios_dir) if scenarios_dir is not None else DEFAULT_SCENARIOS_DIR
    if not target_dir.exists():
        logger.warning("Scenarios directory does not exist: %s", target_dir)
        return []

    scenarios: list[ScenarioDefinition] = []
    for yaml_file in sorted(target_dir.glob("*.yaml")):
        try:
            scenarios.append(load_scenario(yaml_file))
        except Exception as e:
            logger.error("Failed to load scenario %s: %s", yaml_file, e)

    # Sort scenarios deterministically by ID (e.g. S01, S02, ...)
    scenarios.sort(key=lambda s: s.id)
    return scenarios
