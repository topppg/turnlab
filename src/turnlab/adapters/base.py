"""Adapter contract: translate PCM chunks into normalized TurnLab events."""

from __future__ import annotations

from typing import Protocol

from turnlab.models import AudioChunk, Event, Scenario


class VoiceAdapter(Protocol):
    name: str

    def run(self, scenario: Scenario, chunks: list[AudioChunk]) -> list[Event]: ...
