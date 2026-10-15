"""Command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from turnlab.scenario import load_scenario


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="turnlab", description="Evaluate real-time voice-agent media paths"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate one JSON scenario")
    validate.add_argument("scenario", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenario = load_scenario(args.scenario)
    print(f"Valid scenario: {scenario.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
