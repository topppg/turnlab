from __future__ import annotations

import json

import pytest

from turnlab.adapters.mock import MockAdapter
from turnlab.cli import main
from turnlab.fixtures import generate_tone
from turnlab.impairments import apply_impairments
from turnlab.models import AudioSpec, ImpairmentSpec, Scenario
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


def test_fixture_is_deterministic() -> None:
    spec = AudioSpec(duration_ms=200, chunk_ms=100)
    assert generate_tone(spec) == generate_tone(spec)
    assert len(generate_tone(spec)) == 2


def test_impairments_are_deterministic_and_drop_targeted_chunks() -> None:
    chunks = generate_tone(AudioSpec(duration_ms=300, chunk_ms=100))
    specs = (
        ImpairmentSpec(kind="noise", at_ms=0, duration_ms=300, amount=0.1, seed=4),
        ImpairmentSpec(kind="drop", at_ms=100, duration_ms=100, amount=1.0, seed=4),
    )
    first = apply_impairments(chunks, specs, 100)
    second = apply_impairments(chunks, specs, 100)
    assert first == second
    assert [chunk.dropped for chunk in first] == [False, True, False]


def test_mock_adapter_emits_a_deterministic_response() -> None:
    scenario = Scenario(id="mock-turn", description="mock")
    events = MockAdapter().run(scenario, generate_tone(scenario.audio))
    assert [event.kind.value for event in events].count("agent_audio_started") == 1


def test_cli_runs_mock_scenario(tmp_path, capsys) -> None:
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps({"id": "cli-turn", "description": "CLI"}))
    assert main(["run", str(path)]) == 0
    assert "Scenario: cli-turn" in capsys.readouterr().out
