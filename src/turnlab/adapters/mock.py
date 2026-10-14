"""Offline adapter with a deterministic virtual clock."""

from __future__ import annotations

from turnlab.models import AudioChunk, Event, EventKind, Scenario


class MockAdapter:
    name = "mock"

    def __init__(self, response_latency_ms: int = 240, response_duration_ms: int = 500) -> None:
        self.response_latency_ms = response_latency_ms
        self.response_duration_ms = response_duration_ms

    def run(self, scenario: Scenario, chunks: list[AudioChunk]) -> list[Event]:
        events: list[Event] = []
        for chunk in chunks:
            at_ms = chunk.start_ms + chunk.delay_ms
            kind = EventKind.INPUT_CHUNK_DROPPED if chunk.dropped else EventKind.INPUT_CHUNK_SENT
            events.append(
                Event(kind, at_ms, {"sequence": chunk.sequence, "bytes": len(chunk.pcm_s16le)})
            )
        input_end = max(
            (chunk.start_ms + scenario.audio.chunk_ms + chunk.delay_ms for chunk in chunks),
            default=0,
        )
        response_at = input_end + self.response_latency_ms
        events.extend(
            [
                Event(
                    EventKind.AGENT_TRANSCRIPT,
                    response_at,
                    {"text": "mock response"},
                    sensitive=True,
                ),
                Event(EventKind.AGENT_AUDIO_STARTED, response_at, {"source": "mock"}),
                Event(
                    EventKind.LATENCY,
                    response_at,
                    {"name": "response", "value_ms": self.response_latency_ms},
                ),
            ]
        )
        if scenario.expected.tool_name:
            events.extend(
                [
                    Event(
                        EventKind.TOOL_CALL, response_at + 50, {"name": scenario.expected.tool_name}
                    ),
                    Event(
                        EventKind.TOOL_RESULT,
                        response_at + 70,
                        {"name": scenario.expected.tool_name, "ok": True},
                    ),
                ]
            )
        for spec in scenario.impairments:
            if spec.kind == "interruption":
                events.append(Event(EventKind.INTERRUPTION, spec.at_ms, {"source": "scenario"}))
        events.append(Event(EventKind.AGENT_AUDIO_ENDED, response_at + self.response_duration_ms))
        return sorted(events, key=lambda event: event.at_ms)
