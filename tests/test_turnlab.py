from __future__ import annotations

import json

import pytest

from turnlab.cli import main
from turnlab.models import Scenario
from turnlab.scenario import load_scenario


def test_scenario_round_trip(tmp_path) -> None:
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps({"id": "clean-turn", "description": "clean"}))
    scenario = load_scenario(path)
    assert scenario == Scenario(id="clean-turn", description="clean")
    assert scenario.to_dict()["id"] == "clean-turn"


@pytest.mark.parametrize("scenario_id", ["../escape", "/tmp/absolute", "Uppercase"])
def test_scenario_id_must_be_safe_slug(scenario_id) -> None:
    with pytest.raises(ValueError, match="lowercase slug"):
        Scenario(id=scenario_id, description="invalid")


def test_cli_validates_scenario(tmp_path, capsys) -> None:
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps({"id": "cli-turn", "description": "CLI"}))
    assert main(["validate", str(path)]) == 0
    assert "Valid scenario: cli-turn" in capsys.readouterr().out
