"""Optional concurrent ElevenLabs Agents WebSocket adapter.

The adapter imports ``websockets`` only when used. It intentionally exposes no
API-key option: private agents should use a short-lived signed URL obtained by
the caller's trusted backend.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlencode

from turnlab.models import AudioChunk, Event, EventKind, Scenario

ConnectFactory = Callable[..., Any]
Sleeper = Callable[[float], Awaitable[None]]


class ElevenLabsAdapter:
    name = "elevenlabs"

    def __init__(
        self,
        *,
        agent_id: str | None = None,
        signed_url: str | None = None,
        timeout_seconds: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Sleeper = asyncio.sleep,
        connect_factory: ConnectFactory | None = None,
    ) -> None:
        if bool(agent_id) == bool(signed_url):
            raise ValueError("provide exactly one of agent_id or signed_url")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.url = signed_url or (
            "wss://api.elevenlabs.io/v1/convai/conversation?" + urlencode({"agent_id": agent_id})
        )
        self.timeout_seconds = timeout_seconds
        self.clock = clock
        self.sleep = sleep
        self.connect_factory = connect_factory

    def run(self, scenario: Scenario, chunks: list[AudioChunk]) -> list[Event]:
        """Run one live turn from synchronous code.

        Sending and receiving run as separate asyncio tasks so server pings,
        audio, and tool events are handled while input audio is still streaming.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._run(scenario, chunks))
        raise RuntimeError("ElevenLabsAdapter.run() must be called outside an active event loop")

    def _get_connector(self) -> ConnectFactory:
        if self.connect_factory is not None:
            return self.connect_factory
        try:
            from websockets.asyncio.client import connect
        except ImportError as exc:
            raise RuntimeError("install TurnLab with: pip install 'turnlab[elevenlabs]'") from exc
        return connect

    async def _run(self, scenario: Scenario, chunks: list[AudioChunk]) -> list[Event]:
        connector = self._get_connector()
        started = self.clock()
        input_end_ms = max(
            (chunk.start_ms + scenario.audio.chunk_ms + chunk.delay_ms for chunk in chunks),
            default=0,
        )
        deadline = started + input_end_ms / 1000 + self.timeout_seconds
        events: list[Event] = []
        try:
            async with connector(
                self.url, open_timeout=self.timeout_seconds, close_timeout=2
            ) as socket:
                await socket.send(json.dumps({"type": "conversation_initiation_client_data"}))
                receiver = asyncio.create_task(
                    self._receive_events(socket, started=started, deadline=deadline, events=events)
                )
                try:
                    await self._send_chunks(socket, chunks, started=started, events=events)
                    await receiver
                finally:
                    if not receiver.done():
                        receiver.cancel()
                        await asyncio.gather(receiver, return_exceptions=True)
        except Exception as exc:  # noqa: BLE001 - provider errors may contain the signed URL.
            raise RuntimeError(
                f"ElevenLabs WebSocket session failed ({type(exc).__name__})"
            ) from None
        return sorted(events, key=lambda event: event.at_ms)

    async def _send_chunks(
        self, socket: Any, chunks: list[AudioChunk], *, started: float, events: list[Event]
    ) -> None:
        for chunk in chunks:
            target = started + (chunk.start_ms + chunk.delay_ms) / 1000
            remaining = target - self.clock()
            if remaining > 0:
                await self.sleep(remaining)
            at_ms = (self.clock() - started) * 1000
            if chunk.dropped:
                events.append(
                    Event(EventKind.INPUT_CHUNK_DROPPED, at_ms, {"sequence": chunk.sequence})
                )
                continue
            await socket.send(
                json.dumps({"user_audio_chunk": base64.b64encode(chunk.pcm_s16le).decode("ascii")})
            )
            events.append(Event(EventKind.INPUT_CHUNK_SENT, at_ms, {"sequence": chunk.sequence}))

    async def _receive_events(
        self, socket: Any, *, started: float, deadline: float, events: list[Event]
    ) -> None:
        audio_active = False
        interrupted = False
        last_audio_ms: float | None = None
        while (remaining := deadline - self.clock()) > 0:
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=remaining)
            except TimeoutError:
                break
            message = json.loads(raw)
            now_ms = (self.clock() - started) * 1000
            kind = message.get("type")
            if kind == "ping":
                ping = message.get("ping_event", {})
                await socket.send(json.dumps({"type": "pong", "event_id": ping.get("event_id")}))
            elif kind == "audio":
                if not audio_active:
                    events.append(
                        Event(
                            EventKind.AGENT_AUDIO_STARTED,
                            now_ms,
                            {"source": "elevenlabs", "recovery": interrupted},
                        )
                    )
                    audio_active = True
                    interrupted = False
                last_audio_ms = now_ms
            elif kind == "user_transcript":
                text = message.get("user_transcription_event", {}).get("user_transcript", "")
                events.append(
                    Event(EventKind.USER_TRANSCRIPT, now_ms, {"text": text}, sensitive=True)
                )
            elif kind in {"agent_response", "agent_response_correction"}:
                payload = message.get(f"{kind}_event", {})
                text = payload.get("agent_response") or payload.get("corrected_agent_response", "")
                events.append(
                    Event(EventKind.AGENT_TRANSCRIPT, now_ms, {"text": text}, sensitive=True)
                )
            elif kind == "interruption":
                if audio_active:
                    events.append(
                        Event(EventKind.AGENT_AUDIO_ENDED, now_ms, {"source": "elevenlabs"})
                    )
                    audio_active = False
                interrupted = True
                events.append(Event(EventKind.INTERRUPTION, now_ms, {"source": "elevenlabs"}))
            elif kind == "client_tool_call":
                call = message.get("client_tool_call", {})
                events.append(Event(EventKind.TOOL_CALL, now_ms, {"name": call.get("tool_name")}))
            elif kind == "error":
                events.append(Event(EventKind.ERROR, now_ms, {"source": "elevenlabs"}))
                break
        if audio_active and last_audio_ms is not None:
            events.append(
                Event(EventKind.AGENT_AUDIO_ENDED, last_audio_ms, {"source": "elevenlabs"})
            )
