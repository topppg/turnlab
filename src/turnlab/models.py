"""Small, serializable models shared by adapters, metrics, and reports."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

SCENARIO_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_scenario_id(value: str) -> str:
    if not SCENARIO_ID_PATTERN.fullmatch(value):
        raise ValueError(
            "scenario id must be a lowercase slug containing letters, digits, and single hyphens"
        )
    return value


class EventKind(StrEnum):
    RUN_STARTED = "run_started"
    INPUT_AUDIO_STARTED = "input_audio_started"
    INPUT_AUDIO_ENDED = "input_audio_ended"
    INPUT_CHUNK_SENT = "input_chunk_sent"
    INPUT_CHUNK_DROPPED = "input_chunk_dropped"
    AGENT_AUDIO_STARTED = "agent_audio_started"
    AGENT_AUDIO_ENDED = "agent_audio_ended"
    USER_TRANSCRIPT = "user_transcript"
    AGENT_TRANSCRIPT = "agent_transcript"
    INTERRUPTION = "interruption"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    LATENCY = "latency"
    RUN_ENDED = "run_ended"
    ERROR = "error"


@dataclass(frozen=True)
class Event:
    kind: EventKind
    at_ms: float
    data: dict[str, Any] = field(default_factory=dict)
    sensitive: bool = False

    def to_dict(self, *, include_sensitive: bool = False) -> dict[str, Any]:
        data = dict(self.data)
        if self.sensitive and not include_sensitive:
            data = {"redacted": True}
        return {"kind": self.kind.value, "at_ms": round(self.at_ms, 3), "data": data}


@dataclass(frozen=True)
class AudioSpec:
    duration_ms: int = 1200
    sample_rate_hz: int = 16_000
    frequency_hz: float = 440.0
    amplitude: float = 0.15
    chunk_ms: int = 100


@dataclass(frozen=True)
class ImpairmentSpec:
    kind: str
    at_ms: int = 0
    duration_ms: int = 0
    amount: float = 0.0
    seed: int = 0


@dataclass(frozen=True)
class ExpectedOutcome:
    task_success: bool | None = None
    tool_name: str | None = None
    interruption_recovered: bool | None = None


@dataclass(frozen=True)
class Scenario:
    id: str
    description: str
    audio: AudioSpec = field(default_factory=AudioSpec)
    impairments: tuple[ImpairmentSpec, ...] = ()
    expected: ExpectedOutcome = field(default_factory=ExpectedOutcome)

    def __post_init__(self) -> None:
        validate_scenario_id(self.id)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Scenario:
        allowed = {"silence", "noise", "jitter", "delay", "drop", "interruption"}
        specs = tuple(ImpairmentSpec(**item) for item in raw.get("impairments", []))
        unknown = sorted({item.kind for item in specs} - allowed)
        if unknown:
            raise ValueError(f"unknown impairment(s): {', '.join(unknown)}")
        audio = AudioSpec(**raw.get("audio", {}))
        if audio.duration_ms <= 0 or audio.chunk_ms <= 0 or audio.sample_rate_hz <= 0:
            raise ValueError("audio duration, chunk size, and sample rate must be positive")
        return cls(
            id=str(raw["id"]),
            description=str(raw.get("description", "")),
            audio=audio,
            impairments=specs,
            expected=ExpectedOutcome(**raw.get("expected", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AudioChunk:
    sequence: int
    start_ms: int
    pcm_s16le: bytes
    delay_ms: int = 0
    dropped: bool = False


@dataclass
class RunResult:
    scenario: Scenario
    adapter: str
    events: list[Event]
    metrics: dict[str, Any]
    privacy: dict[str, bool]

    def to_dict(self, *, include_sensitive: bool = False) -> dict[str, Any]:
        privacy = dict(self.privacy)
        privacy["sensitive_event_data_in_report"] = include_sensitive
        return {
            "schema_version": "1",
            "scenario": self.scenario.to_dict(),
            "adapter": self.adapter,
            "privacy": privacy,
            "metrics": self.metrics,
            "events": [event.to_dict(include_sensitive=include_sensitive) for event in self.events],
        }
