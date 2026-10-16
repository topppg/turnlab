from __future__ import annotations

import json

import pytest

from turnlab.adapters.mock import MockAdapter
from turnlab.cli import main
from turnlab.fixtures import generate_tone
from turnlab.impairments import apply_impairments
from turnlab.models import AudioSpec, ImpairmentSpec, Scenario
from turnlab.reports import safe_output_path, write_html, write_json
from turnlab.runner import run_scenario
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


def test_run_calculates_metrics_and_redacts_transcript(tmp_path) -> None:
    scenario = Scenario.from_dict(
        {
            "id": "private-turn",
            "description": "private",
            "audio": {"duration_ms": 300, "chunk_ms": 100},
            "expected": {"tool_name": "lookup"},
        }
    )
    result = run_scenario(scenario, MockAdapter())
    assert result.metrics["time_to_first_audio_ms"] == 240
    path = write_json(result, tmp_path / "report.json")
    report = json.loads(path.read_text())
    transcript = next(event for event in report["events"] if event["kind"] == "agent_transcript")
    assert transcript["data"] == {"redacted": True}
    assert report["privacy"]["raw_audio_persisted"] is False


def test_html_report_is_self_contained(tmp_path) -> None:
    result = run_scenario(Scenario(id="html", description="report"), MockAdapter())
    content = write_html(result, tmp_path / "report.html").read_text()
    assert "<!doctype html>" in content
    assert "TurnLab report" in content
    assert "http" not in content


@pytest.mark.parametrize("scenario_id", ["../escape", "/tmp/absolute"])
def test_report_path_cannot_escape_output_directory(tmp_path, scenario_id) -> None:
    with pytest.raises(ValueError, match="stay inside"):
        safe_output_path(tmp_path, scenario_id, "json")


def test_cli_runs_mock_scenario(tmp_path, capsys) -> None:
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps({"id": "cli-turn", "description": "CLI"}))
    output = tmp_path / "reports"
    assert main(["run", str(path), "--output", str(output)]) == 0
    assert "JSON:" in capsys.readouterr().out
    assert (output / "cli-turn.json").exists()
    assert (output / "cli-turn.html").exists()
