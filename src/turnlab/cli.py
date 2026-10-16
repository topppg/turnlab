"""Command-line interface."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from turnlab.adapters.mock import MockAdapter
from turnlab.reports import safe_output_path, write_html, write_json
from turnlab.runner import run_scenario
from turnlab.scenario import load_scenario


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="turnlab", description="Evaluate real-time voice-agent media paths"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run one JSON scenario")
    run.add_argument("scenario", type=Path)
    run.add_argument("--adapter", choices=("mock", "elevenlabs"), default="mock")
    run.add_argument("--agent-id", help="ElevenLabs public agent ID")
    run.add_argument("--output", type=Path, default=Path("reports"))
    run.add_argument(
        "--include-sensitive",
        action="store_true",
        help="include transcript text in reports (off by default)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenario = load_scenario(args.scenario)
    if args.adapter == "mock":
        adapter = MockAdapter()
    else:
        from turnlab.adapters.elevenlabs import ElevenLabsAdapter

        adapter = ElevenLabsAdapter(
            agent_id=args.agent_id,
            signed_url=os.environ.get("TURNLAB_ELEVENLABS_SIGNED_URL"),
        )
    result = run_scenario(scenario, adapter)
    json_output = safe_output_path(args.output, scenario.id, "json")
    html_output = safe_output_path(args.output, scenario.id, "html")
    json_path = write_json(result, json_output, include_sensitive=args.include_sensitive)
    html_path = write_html(result, html_output, include_sensitive=args.include_sensitive)
    print(f"JSON: {json_path}")
    print(f"HTML: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
