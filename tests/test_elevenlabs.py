from __future__ import annotations

import asyncio
import builtins
import json
from typing import Any

import pytest

from turnlab.adapters.elevenlabs import ElevenLabsAdapter
from turnlab.models import AudioChunk, EventKind, Scenario


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.value += seconds
        await asyncio.sleep(0)


class FakeSocket:
    def __init__(self, clock: FakeClock, incoming: list[tuple[int, dict[str, Any]]]) -> None:
        self.clock = clock
        self.incoming = incoming
        self.incoming_index = 0
        self.sent: list[dict[str, Any]] = []
        self.actions: list[str] = []
        self.timed_out = False

    async def send(self, raw: str) -> None:
        message = json.loads(raw)
        self.sent.append(message)
        kind = "audio" if "user_audio_chunk" in message else message["type"]
        self.actions.append(f"send:{kind}")
        await asyncio.sleep(0)

    async def recv(self) -> str:
        if self.incoming_index >= len(self.incoming):
            self.timed_out = True
            raise TimeoutError
        required_audio_chunks, message = self.incoming[self.incoming_index]
        while self.audio_chunks_sent < required_audio_chunks:
            await asyncio.sleep(0)
        self.incoming_index += 1
        self.actions.append(f"receive:{message['type']}")
        return json.dumps(message)

    @property
    def audio_chunks_sent(self) -> int:
        return sum("user_audio_chunk" in message for message in self.sent)


class FakeConnection:
    def __init__(self, socket: FakeSocket) -> None:
        self.socket = socket

    async def __aenter__(self) -> FakeSocket:
        return self.socket

    async def __aexit__(self, *args: object) -> None:
        return None


def connector_for(socket: FakeSocket):
    def connect(*args: object, **kwargs: object) -> FakeConnection:
        return FakeConnection(socket)

    return connect


def test_requires_exactly_one_connection_target() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        ElevenLabsAdapter()
    with pytest.raises(ValueError, match="exactly one"):
        ElevenLabsAdapter(agent_id="a", signed_url="wss://example.test")


def test_optional_dependency_error_is_actionable(monkeypatch) -> None:
    adapter = ElevenLabsAdapter(agent_id="public-agent")
    original_import = builtins.__import__

    def reject_websockets(name, *args, **kwargs):
        if name.startswith("websockets"):
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_websockets)
    with pytest.raises(RuntimeError, match=r"turnlab\[elevenlabs\]"):
        adapter.run(Scenario(id="x", description="x"), [])


def test_protocol_events_are_received_while_audio_is_sent() -> None:
    clock = FakeClock()
    socket = FakeSocket(
        clock,
        [
            (1, {"type": "ping", "ping_event": {"event_id": 41}}),
            (1, {"type": "audio", "audio_event": {"audio_base_64": "YQ=="}}),
            (
                2,
                {
                    "type": "user_transcript",
                    "user_transcription_event": {"user_transcript": "private user words"},
                },
            ),
            (
                2,
                {
                    "type": "agent_response",
                    "agent_response_event": {"agent_response": "agent words"},
                },
            ),
            (
                3,
                {
                    "type": "client_tool_call",
                    "client_tool_call": {"tool_name": "lookup_order"},
                },
            ),
        ],
    )
    chunks = [
        AudioChunk(sequence=0, start_ms=0, pcm_s16le=b"aa"),
        AudioChunk(sequence=1, start_ms=100, pcm_s16le=b"bb"),
        AudioChunk(sequence=2, start_ms=200, pcm_s16le=b"cc"),
    ]
    adapter = ElevenLabsAdapter(
        agent_id="public-agent",
        timeout_seconds=1,
        clock=clock,
        sleep=clock.sleep,
        connect_factory=connector_for(socket),
    )

    events = adapter.run(Scenario(id="protocol", description="protocol"), chunks)

    kinds = [event.kind for event in events]
    assert EventKind.AGENT_AUDIO_STARTED in kinds
    assert EventKind.AGENT_AUDIO_ENDED in kinds
    assert EventKind.USER_TRANSCRIPT in kinds
    assert EventKind.AGENT_TRANSCRIPT in kinds
    assert EventKind.TOOL_CALL in kinds
    assert next(event for event in events if event.kind == EventKind.TOOL_CALL).data == {
        "name": "lookup_order"
    }
    assert {event.sensitive for event in events if "transcript" in event.kind.value} == {True}
    assert {"type": "pong", "event_id": 41} in socket.sent
    audio_actions = [index for index, action in enumerate(socket.actions) if action == "send:audio"]
    assert audio_actions[0] < socket.actions.index("send:pong") < audio_actions[-1]
    assert socket.timed_out is True


def test_connection_errors_do_not_expose_signed_url() -> None:
    secret = "wss://example.test/private?token=very-secret"

    def failing_connector(*args: object, **kwargs: object) -> FakeConnection:
        raise OSError(f"could not connect to {secret}")

    adapter = ElevenLabsAdapter(signed_url=secret, connect_factory=failing_connector)
    with pytest.raises(RuntimeError) as caught:
        adapter.run(Scenario(id="private", description="private"), [])
    assert secret not in str(caught.value)
    assert "very-secret" not in str(caught.value)
