"""Metrics derived only from normalized events."""

from __future__ import annotations

from typing import Any

from turnlab.models import Event, EventKind, Scenario


def _first(events: list[Event], kind: EventKind) -> Event | None:
    return next((event for event in events if event.kind == kind), None)


def calculate_metrics(scenario: Scenario, events: list[Event]) -> dict[str, Any]:
    input_end = _first(events, EventKind.INPUT_AUDIO_ENDED)
    first_audio = _first(events, EventKind.AGENT_AUDIO_STARTED)
    ended = _first(events, EventKind.RUN_ENDED)
    started = _first(events, EventKind.RUN_STARTED)
    interruption = _first(events, EventKind.INTERRUPTION)
    tool_calls = [event.data.get("name") for event in events if event.kind == EventKind.TOOL_CALL]

    ttfa = None
    if input_end and first_audio:
        ttfa = round(first_audio.at_ms - input_end.at_ms, 3)
    recovered = None
    recovery_ms = None
    if interruption:
        recovery_origin = max(
            interruption.at_ms,
            input_end.at_ms if input_end is not None else interruption.at_ms,
        )
        resumed = next(
            (
                event
                for event in events
                if event.kind == EventKind.AGENT_AUDIO_STARTED and event.at_ms >= recovery_origin
            ),
            None,
        )
        recovered = resumed is not None
        recovery_ms = round(resumed.at_ms - recovery_origin, 3) if resumed else None

    expected_tool = scenario.expected.tool_name
    tool_outcome = None if expected_tool is None else expected_tool in tool_calls
    task_outcome = scenario.expected.task_success
    return {
        "time_to_first_audio_ms": ttfa,
        "time_to_first_audio_origin": "input_audio_ended",
        "duration_ms": round(ended.at_ms - started.at_ms, 3) if started and ended else None,
        "chunks_sent": sum(event.kind == EventKind.INPUT_CHUNK_SENT for event in events),
        "chunks_dropped": sum(event.kind == EventKind.INPUT_CHUNK_DROPPED for event in events),
        "interruption_recovered": recovered,
        "interruption_recovery_ms": recovery_ms,
        "interruption_recovery_origin": "later_of_interruption_or_input_end",
        "expected_tool_observed": tool_outcome,
        "task_success": task_outcome,
        "scoring_note": "Task success is scenario-provided; tool and interruption scores are event-derived.",
    }
