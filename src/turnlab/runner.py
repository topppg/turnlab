"""Scenario orchestration independent of any provider."""

from __future__ import annotations

from turnlab.adapters.base import VoiceAdapter
from turnlab.fixtures import generate_tone
from turnlab.impairments import apply_impairments
from turnlab.metrics import calculate_metrics
from turnlab.models import Event, EventKind, RunResult, Scenario


def run_scenario(scenario: Scenario, adapter: VoiceAdapter) -> RunResult:
    chunks = apply_impairments(
        generate_tone(scenario.audio), scenario.impairments, scenario.audio.chunk_ms
    )
    input_end = max(
        (chunk.start_ms + scenario.audio.chunk_ms + chunk.delay_ms for chunk in chunks), default=0
    )
    events = [Event(EventKind.RUN_STARTED, 0), Event(EventKind.INPUT_AUDIO_STARTED, 0)]
    events.extend(adapter.run(scenario, chunks))
    events.append(Event(EventKind.INPUT_AUDIO_ENDED, input_end))
    final_time = max((event.at_ms for event in events), default=0)
    events.append(Event(EventKind.RUN_ENDED, final_time))
    events.sort(key=lambda event: event.at_ms)
    metrics = calculate_metrics(scenario, events)
    return RunResult(
        scenario=scenario,
        adapter=adapter.name,
        events=events,
        metrics=metrics,
        privacy={"raw_audio_persisted": False, "sensitive_event_data_in_report": False},
    )
