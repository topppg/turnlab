"""Generate license-free PCM fixtures in memory."""

from __future__ import annotations

import math
import struct

from turnlab.models import AudioChunk, AudioSpec


def generate_tone(spec: AudioSpec) -> list[AudioChunk]:
    """Create deterministic signed 16-bit mono PCM chunks without persisting audio."""
    total_samples = round(spec.sample_rate_hz * spec.duration_ms / 1000)
    samples_per_chunk = max(1, round(spec.sample_rate_hz * spec.chunk_ms / 1000))
    peak = min(max(spec.amplitude, 0.0), 1.0) * 32767
    output: list[AudioChunk] = []
    for sequence, offset in enumerate(range(0, total_samples, samples_per_chunk)):
        count = min(samples_per_chunk, total_samples - offset)
        values = (
            round(
                peak
                * math.sin(2 * math.pi * spec.frequency_hz * (offset + i) / spec.sample_rate_hz)
            )
            for i in range(count)
        )
        pcm = b"".join(struct.pack("<h", value) for value in values)
        output.append(
            AudioChunk(
                sequence=sequence,
                start_ms=round(offset * 1000 / spec.sample_rate_hz),
                pcm_s16le=pcm,
            )
        )
    return output
