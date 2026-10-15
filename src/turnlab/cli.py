"""Command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from turnlab.adapters.mock import MockAdapter
from turnlab.fixtures import generate_tone
from turnlab.impairments import apply_impairments
from turnlab.scenario import load_scenario


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="turnlab", description="Evaluate real-time voice-agent media paths"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run one JSON scenario with the offline mock")
    run.add_argument("scenario", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenario = load_scenario(args.scenario)
    chunks = apply_impairments(
        generate_tone(scenario.audio), scenario.impairments, scenario.audio.chunk_ms
    )
    events = MockAdapter().run(scenario, chunks)
    print(f"Scenario: {scenario.id}")
    print(f"Events: {len(events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
