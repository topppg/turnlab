# TurnLab

**A privacy-first, reproducible evaluation harness for the media layer of real-time voice
agents.**

[![CI](https://github.com/topppg/turnlab/actions/workflows/ci.yml/badge.svg)](https://github.com/topppg/turnlab/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB)](https://www.python.org/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Voice-agent tests often check *what* an agent says while skipping *how* the conversation
travels through audio and the network. TurnLab makes that layer observable. It streams
deterministic audio, applies controlled adverse conditions, normalizes provider events,
calculates turn-level metrics, and produces a replayable timeline.

The built-in mock adapter runs fully offline on a virtual clock. This makes media-path tests
fast, deterministic, and suitable for pull-request checks. An experimental ElevenLabs adapter
uses the same scenario, event, metric, and reporting pipeline for live sessions.

> [!IMPORTANT]
> TurnLab is an early research and engineering prototype. It is not a certification, security,
> safety, or compliance tool. The results below are synthetic mock results, not an ElevenLabs
> latency benchmark.

## Why TurnLab

Real-time conversational systems fail in ways that text-only evaluations cannot see:

- user audio arrives late, out of order, or not at all;
- silence and background noise change turn-taking behavior;
- an interruption is detected but the agent never recovers;
- provider-specific events make results difficult to compare;
- debugging artifacts accidentally retain transcripts, credentials, or raw audio.

TurnLab provides a small provider-neutral layer for describing these cases as versioned JSON,
replaying them, and inspecting their results. The goal is repeatable engineering evidence, not
a single opaque quality score.

## Current achievements

- **Deterministic offline evaluation.** Seeded noise, jitter, delay, silence, dropped chunks,
  and interruption markers produce repeatable event streams.
- **One normalized timeline.** Audio, transcript, interruption, tool, latency, and lifecycle
  events share a compact provider-neutral model.
- **Explicit metric origins.** Latency and recovery metrics record the event used as their time
  origin, making their meaning auditable.
- **Privacy-safe reporting by default.** Raw audio is never persisted, transcript payloads are
  redacted, HTML reports have no external assets, and credentials are excluded from reports.
- **Concurrent live protocol handling.** The ElevenLabs adapter receives audio, transcript,
  tool, interruption, and ping events while input audio is still being streamed.
- **Path and secret hardening.** Scenario identifiers cannot escape the report directory, and
  signed URLs are accepted only through an environment variable and removed from errors.
- **Automated quality checks.** The current implementation passes 17 offline tests, Ruff lint
  and format checks, and source/wheel builds. CI repeats the offline checks on Python 3.11 and
  3.12 without provider credentials.

## How it works

```text
JSON scenario
    │
    ├── generated PCM fixture (memory only)
    ├── deterministic signal and transport impairments
    ▼
provider adapter ──► normalized event timeline ──► metrics
      │                                             ├── JSON report
      ├── mock (offline virtual clock)              └── HTML timeline
      └── ElevenLabs (experimental live adapter)
```

The workflow is intentionally simple:

1. Load and validate a provider-neutral scenario.
2. Generate 16-bit little-endian PCM audio in memory.
3. Apply each configured impairment to the relevant audio chunks.
4. Stream the chunks through the selected adapter.
5. Normalize adapter activity into timestamped events.
6. Derive metrics from those events and write JSON and self-contained HTML reports.

Adapters implement one small contract: accept a `Scenario` and a sequence of `AudioChunk`
values, then return normalized `Event` values. Provider details stay out of scoring and
reporting.

## Installation

TurnLab requires Python 3.11 or newer.

```bash
git clone https://github.com/topppg/turnlab.git
cd turnlab
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Install the optional WebSocket dependency only when using ElevenLabs:

```bash
python -m pip install -e '.[elevenlabs]'
```

For local development:

```bash
python -m pip install -e '.[dev]'
```

## Quick start

Run the included hostile-network scenario with the offline mock adapter:

```bash
turnlab run examples/scenarios/hostile-network.json
```

TurnLab writes two artifacts:

```text
reports/hostile-network.json   # machine-readable scenario, metrics, and events
reports/hostile-network.html   # self-contained visual timeline
```

Open the HTML report locally:

```bash
open reports/hostile-network.html      # macOS
# xdg-open reports/hostile-network.html  # Linux
```

The mock adapter requires no network, microphone, API key, or proprietary audio. Re-running the
same scenario produces the same synthetic event timeline and metrics.

## Scenario format

Scenarios are JSON documents and intentionally provider-neutral:

```json
{
  "id": "interrupted-turn",
  "description": "Noise and an interruption during one synthetic turn.",
  "audio": {
    "duration_ms": 2000,
    "sample_rate_hz": 16000,
    "frequency_hz": 330.0,
    "amplitude": 0.12,
    "chunk_ms": 100
  },
  "impairments": [
    {"kind": "noise", "at_ms": 0, "duration_ms": 2000, "amount": 0.04, "seed": 7},
    {"kind": "jitter", "at_ms": 0, "duration_ms": 2000, "amount": 90, "seed": 9},
    {"kind": "interruption", "at_ms": 1700}
  ],
  "expected": {
    "task_success": true,
    "interruption_recovered": true
  }
}
```

### Audio fields

| Field | Meaning |
| --- | --- |
| `duration_ms` | Total generated fixture duration. |
| `sample_rate_hz` | PCM sample rate; defaults to 16 kHz. |
| `frequency_hz` | Frequency of the generated sine tone. |
| `amplitude` | Tone amplitude from 0 to 1. |
| `chunk_ms` | Audio chunk size used by the transport simulation. |

### Supported impairments

| Kind | Behavior | `amount` |
| --- | --- | --- |
| `silence` | Replaces samples in the selected window with zeroes. | Not used. |
| `noise` | Adds seeded uniform noise and clips it to signed 16-bit PCM. | Noise strength from 0 to 1. |
| `jitter` | Adds a seeded per-chunk delivery delay. | Maximum delay in milliseconds. |
| `delay` | Adds a fixed delay to chunks in the selected window. | Delay in milliseconds. |
| `drop` | Marks selected chunks as dropped. | Drop probability from 0 to 1. |
| `interruption` | Adds a semantic interruption marker to the timeline. | Not used. |

`at_ms` and `duration_ms` select the impairment window. `seed` makes random operations
reproducible. Multiple impairments are applied in their listed order.

Scenario IDs must be lowercase slugs such as `interrupted-turn`. Absolute paths, `..` traversal,
underscores, uppercase letters, and repeated hyphens are rejected. Report paths are resolved and
checked again before writing.

## Metrics

Metrics are derived from normalized events unless noted otherwise:

| Metric | Definition |
| --- | --- |
| `time_to_first_audio_ms` | First `agent_audio_started` minus `input_audio_ended`. |
| `duration_ms` | `run_ended` minus `run_started`. |
| `chunks_sent` | Count of `input_chunk_sent` events. |
| `chunks_dropped` | Count of `input_chunk_dropped` events. |
| `interruption_recovered` | Whether agent audio starts after the later of interruption or input end. |
| `interruption_recovery_ms` | Delay from that recovery origin to resumed agent audio. |
| `expected_tool_observed` | Whether the scenario's expected tool appears in normalized tool-call events. |
| `task_success` | Scenario-provided label; TurnLab does not infer semantic success yet. |

The JSON report also records `time_to_first_audio_origin` and
`interruption_recovery_origin`. This avoids silently changing what a duration means when adapters
or scenarios evolve.

## Reproducible mock result

The included [`hostile-network.json`](examples/scenarios/hostile-network.json) fixture combines:

- a 2,000 ms, 16 kHz synthetic tone split into 20 chunks;
- full-turn seeded noise and up to 90 ms of seeded jitter;
- a 300 ms silence window;
- an additional 180 ms delay window;
- two deliberately dropped chunks; and
- an interruption marker at 1,700 ms.

Running it with the default mock adapter produces the following deterministic result:

| Result | Value |
| --- | ---: |
| Input chunks sent | 18 |
| Input chunks dropped | 2 |
| Input audio ended | 2,021 ms |
| Time to first agent audio | 240 ms after input end |
| Interruption recovered | `true` |
| Interruption recovery time | 240 ms from the later of interruption or input end |
| Total synthetic run duration | 2,761 ms |
| Raw audio persisted | `false` |
| Sensitive event data included | `false` |

These values are a regression fixture for TurnLab's own orchestration and reporting behavior.
They use a virtual clock and a mock response configured for 240 ms latency and 500 ms duration.
They do **not** measure ElevenLabs, a speech model, the public internet, or real-time wall-clock
performance. The scenario's `task_success: true` value is supplied by the fixture; it is not an
automated semantic judgment.

## Reports and privacy

Each run generates:

- a versioned JSON document containing the scenario, adapter name, privacy flags, metrics, and
  normalized events; and
- a self-contained HTML timeline with no remote scripts, fonts, styles, or other assets.

Privacy defaults are conservative:

- generated and received raw audio is not written to disk;
- user and agent transcript events are marked sensitive and redacted in both report formats;
- the core accepts no credentials and report writers serialize no credentials;
- live private-agent URLs are read only from an environment variable;
- `--include-sensitive` is explicit and affects transcript fields only.

To include transcript text in a report you control:

```bash
turnlab run examples/scenarios/basic-latency.json --include-sensitive
```

Treat that report as sensitive data. These engineering defaults are not a promise of regulatory
compliance. A live provider still receives the audio you send under its own terms and data
practices.

## ElevenLabs adapter

The experimental live adapter targets the ElevenLabs Agents WebSocket API while keeping the
runner, event model, impairments, metrics, and reports provider-neutral.

For a public agent:

```bash
turnlab run examples/scenarios/basic-latency.json \
  --adapter elevenlabs \
  --agent-id YOUR_PUBLIC_AGENT_ID
```

For a private agent, obtain a short-lived signed URL in a trusted backend and pass it through the
environment:

```bash
export TURNLAB_ELEVENLABS_SIGNED_URL="$(your-secret-helper)"
turnlab run examples/scenarios/basic-latency.json --adapter elevenlabs
unset TURNLAB_ELEVENLABS_SIGNED_URL
```

TurnLab deliberately has no API-key or signed-URL command-line option. This keeps secrets out of
shell history and process argument lists. The adapter also avoids printing the URL, excludes it
from reports, and replaces provider exception details with a redacted error type. Never commit a
signed URL or a report containing private conversation data.

The adapter currently handles:

- `conversation_initiation_client_data` and streamed `user_audio_chunk` messages;
- concurrent inbound agent audio and input-audio transmission;
- user and agent transcripts, marked sensitive;
- interruption and client tool-call events; and
- provider ping/pong messages while audio is being sent.

Protocol behavior is covered by offline fake-WebSocket tests, including interleaved send/receive,
ping responses, transcript sensitivity, tool calls, and signed-URL redaction. No live-provider
result is claimed in this repository. Provider protocols can change, so pin TurnLab versions in
automated evaluations and confirm behavior against the
[ElevenLabs Agents WebSocket reference](https://elevenlabs.io/docs/eleven-agents/api-reference/eleven-agents/websocket).

## Project structure

```text
turnlab/
├── examples/scenarios/       # clean and hostile deterministic fixtures
├── src/turnlab/
│   ├── adapters/             # mock and ElevenLabs implementations
│   ├── fixtures.py           # in-memory PCM generation
│   ├── impairments.py        # signal and transport transformations
│   ├── metrics.py            # event-derived measurements
│   ├── models.py             # typed scenarios, chunks, events, and results
│   ├── reports.py            # JSON and self-contained HTML output
│   └── runner.py             # provider-neutral orchestration
├── tests/                    # offline behavior and protocol tests
└── .github/workflows/ci.yml  # Python 3.11/3.12 quality gate
```

## Development and verification

```bash
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
pytest -q
python -m pip install build
python -m build
```

The repository currently contains 17 offline tests. They cover deterministic fixtures and
impairments, metric calculation, report redaction, self-contained HTML, path traversal defenses,
safe scenario IDs, mock interruption recovery, ElevenLabs protocol concurrency, ping/pong,
optional-dependency errors, and signed-URL secrecy. Live provider calls are intentionally absent
from CI so pull requests never require secrets or incur usage.

## Limitations

- The built-in generator produces tones, not realistic speech, accents, or acoustic rooms.
- The mock adapter validates TurnLab behavior; its timings are configured synthetic values.
- The live adapter currently models one input turn and has minimal session lifecycle handling.
- Client-side delay and jitter are controlled impairments, not a full network emulator.
- TurnLab does not yet measure packet-level network behavior or audio quality.
- Task success is supplied by the scenario; semantic correctness is not judged automatically.
- Tool scoring observes names but does not execute arbitrary tools.
- Audio playback, SIP, telephony, echo cancellation, and multi-speaker simulation are out of
  scope for this release.

## Roadmap

- WAV fixture ingestion with explicit consent and retention controls
- Speech fixtures from openly licensed corpora
- Multi-turn scenarios and richer assertions
- Pluggable semantic and audio-quality scorers
- SIP and telephony transport adapters
- Trace comparison and CI regression thresholds
- Additional provider adapters behind the same normalized event contract

## Contributing

Issues and focused pull requests are welcome. Please keep tests deterministic, avoid adding live
credentials or private conversation data, and include an offline test for any provider-protocol
change. Before opening a pull request, run the commands in
[Development and verification](#development-and-verification).

## License

Apache License 2.0. See [LICENSE](LICENSE).
