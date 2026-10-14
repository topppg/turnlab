from __future__ import annotations

import json

import pytest

from turnlab.adapters.mock import MockAdapter
from turnlab.cli import build_parser, main
from turnlab.fixtures import generate_tone
from turnlab.impairments import apply_impairments
from turnlab.models import AudioSpec, ImpairmentSpec, Scenario
from turnlab.reports import safe_output_path, write_html, write_json
from turnlab.runner import run_scenario
from turnlab.scenario import load_scenario


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
    assert first[0].pcm_s16le != chunks[0].pcm_s16le


def test_mock_run_calculates_metrics_and_redacts_transcript(tmp_path) -> None:
    scenario = Scenario.from_dict(
        {
            "id": "test",
            "description": "test",
            "audio": {"duration_ms": 300, "chunk_ms": 100},
            "impairments": [{"kind": "interruption", "at_ms": 100}],
            "expected": {"tool_name": "lookup", "interruption_recovered": True},
        }
    )
    result = run_scenario(scenario, MockAdapter())
    assert result.metrics["time_to_first_audio_ms"] == 240
    assert result.metrics["expected_tool_observed"] is True
    assert result.metrics["interruption_recovered"] is True
    assert result.metrics["interruption_recovery_ms"] == 240
    audio_starts = [event for event in result.events if event.kind.value == "agent_audio_started"]
    assert len(audio_starts) == 1
    assert audio_starts[0].at_ms == 540
    path = write_json(result, tmp_path / "report.json")
    report = json.loads(path.read_text())
    transcript = next(event for event in report["events"] if event["kind"] == "agent_transcript")
    assert transcript["data"] == {"redacted": True}
    assert report["privacy"]["raw_audio_persisted"] is False
    assert report["privacy"]["sensitive_event_data_in_report"] is False
    sensitive = result.to_dict(include_sensitive=True)
    assert sensitive["privacy"]["sensitive_event_data_in_report"] is True


def test_html_report_is_self_contained(tmp_path) -> None:
    result = run_scenario(Scenario(id="html", description="report"), MockAdapter())
    content = write_html(result, tmp_path / "report.html").read_text()
    assert "<!doctype html>" in content
    assert "TurnLab report" in content
    assert "http" not in content


def test_html_sensitive_header_matches_content(tmp_path) -> None:
    result = run_scenario(Scenario(id="sensitive", description="report"), MockAdapter())
    content = write_html(result, tmp_path / "report.html", include_sensitive=True).read_text()
    assert "transcripts included" in content
    assert "mock response" in content
    assert "transcripts redacted" not in content


@pytest.mark.parametrize("scenario_id", ["../escape", "/tmp/absolute"])
def test_report_path_cannot_escape_output_directory(tmp_path, scenario_id) -> None:
    with pytest.raises(ValueError, match="stay inside"):
        safe_output_path(tmp_path, scenario_id, "json")


@pytest.mark.parametrize("scenario_id", ["Uppercase", "two--hyphens", "with_underscore"])
def test_scenario_id_must_be_safe_slug(scenario_id) -> None:
    with pytest.raises(ValueError, match="lowercase slug"):
        Scenario(id=scenario_id, description="invalid")


def test_example_scenario_loads() -> None:
    scenario = load_scenario("examples/scenarios/hostile-network.json")
    assert scenario.id == "hostile-network"
    assert {item.kind for item in scenario.impairments} == {
        "noise",
        "silence",
        "jitter",
        "delay",
        "drop",
        "interruption",
    }


def test_hostile_scenario_recovery_uses_real_response_after_input_end() -> None:
    scenario = load_scenario("examples/scenarios/hostile-network.json")
    result = run_scenario(scenario, MockAdapter())
    input_end = next(event for event in result.events if event.kind.value == "input_audio_ended")
    audio_starts = [event for event in result.events if event.kind.value == "agent_audio_started"]
    assert len(audio_starts) == 1
    assert audio_starts[0].at_ms == input_end.at_ms + 240
    assert result.metrics["interruption_recovered"] is True
    assert result.metrics["interruption_recovery_ms"] == 240


def test_private_agent_url_comes_from_environment_without_leaking(
    tmp_path, monkeypatch, capsys
) -> None:
    secret = "wss://example.test/private?token=do-not-print"
    captured: dict[str, str | None] = {}

    class FakeElevenLabsAdapter(MockAdapter):
        name = "elevenlabs"

        def __init__(self, *, agent_id=None, signed_url=None) -> None:
            super().__init__()
            captured["agent_id"] = agent_id
            captured["signed_url"] = signed_url

    scenario = tmp_path / "private.json"
    scenario.write_text(json.dumps({"id": "private", "description": "private"}))
    output = tmp_path / "reports"
    monkeypatch.setenv("TURNLAB_ELEVENLABS_SIGNED_URL", secret)
    monkeypatch.setattr("turnlab.adapters.elevenlabs.ElevenLabsAdapter", FakeElevenLabsAdapter)

    assert main(["run", str(scenario), "--adapter", "elevenlabs", "--output", str(output)]) == 0
    assert captured == {"agent_id": None, "signed_url": secret}
    assert "--signed-url" not in build_parser().format_help()
    visible = (
        capsys.readouterr().out
        + (output / "private.json").read_text()
        + (output / "private.html").read_text()
    )
    assert secret not in visible
    assert "do-not-print" not in visible
