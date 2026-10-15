"""Load TurnLab's intentionally small JSON scenario format."""

from __future__ import annotations

import json
from pathlib import Path

from turnlab.models import Scenario


def load_scenario(path: str | Path) -> Scenario:
    scenario_path = Path(path)
    try:
        raw = json.loads(scenario_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid scenario JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise TypeError("scenario must be a JSON object")
    return Scenario.from_dict(raw)
