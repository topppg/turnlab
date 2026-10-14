"""Deterministic transport and signal impairments."""

from __future__ import annotations

import random
import struct

from turnlab.models import AudioChunk, ImpairmentSpec


def _overlaps(chunk: AudioChunk, spec: ImpairmentSpec, chunk_ms: int) -> bool:
    end = spec.at_ms + max(spec.duration_ms, 1)
    return chunk.start_ms < end and chunk.start_ms + chunk_ms > spec.at_ms


def apply_impairments(
    chunks: list[AudioChunk], specs: tuple[ImpairmentSpec, ...], chunk_ms: int
) -> list[AudioChunk]:
    output = list(chunks)
    for spec in specs:
        rng = random.Random(spec.seed)
        changed: list[AudioChunk] = []
        for chunk in output:
            if not _overlaps(chunk, spec, chunk_ms):
                changed.append(chunk)
                continue
            if spec.kind == "silence":
                chunk = AudioChunk(
                    chunk.sequence, chunk.start_ms, bytes(len(chunk.pcm_s16le)), chunk.delay_ms
                )
            elif spec.kind == "noise":
                strength = min(max(spec.amount or 0.05, 0.0), 1.0) * 32767
                values = struct.iter_unpack("<h", chunk.pcm_s16le)
                noisy = [
                    max(-32768, min(32767, value[0] + round(rng.uniform(-strength, strength))))
                    for value in values
                ]
                chunk = AudioChunk(
                    chunk.sequence,
                    chunk.start_ms,
                    b"".join(struct.pack("<h", value) for value in noisy),
                    chunk.delay_ms,
                )
            elif spec.kind == "drop":
                probability = min(max(spec.amount or 1.0, 0.0), 1.0)
                chunk = AudioChunk(
                    chunk.sequence,
                    chunk.start_ms,
                    chunk.pcm_s16le,
                    chunk.delay_ms,
                    dropped=rng.random() < probability,
                )
            elif spec.kind == "delay":
                chunk = AudioChunk(
                    chunk.sequence,
                    chunk.start_ms,
                    chunk.pcm_s16le,
                    chunk.delay_ms + max(0, round(spec.amount)),
                    chunk.dropped,
                )
            elif spec.kind == "jitter":
                maximum = max(0, round(spec.amount))
                chunk = AudioChunk(
                    chunk.sequence,
                    chunk.start_ms,
                    chunk.pcm_s16le,
                    chunk.delay_ms + rng.randint(0, maximum),
                    chunk.dropped,
                )
            # interruption is a semantic marker emitted by the runner.
            changed.append(chunk)
        output = changed
    return output
