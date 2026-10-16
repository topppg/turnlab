"""Dependency-free JSON and self-contained HTML reports."""

from __future__ import annotations

import html
import json
from pathlib import Path

from turnlab.models import RunResult, validate_scenario_id


def safe_output_path(output_dir: str | Path, scenario_id: str, extension: str) -> Path:
    """Build a report path and reject traversal even if model validation was bypassed."""
    base = Path(output_dir).resolve()
    candidate = (base / f"{scenario_id}.{extension.lstrip('.')}").resolve()
    if candidate.parent != base:
        raise ValueError("report path must stay inside the selected output directory")
    validate_scenario_id(scenario_id)
    return candidate


def write_json(result: RunResult, path: str | Path, *, include_sensitive: bool = False) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result.to_dict(include_sensitive=include_sensitive), indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def write_html(result: RunResult, path: str | Path, *, include_sensitive: bool = False) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    events = [event.to_dict(include_sensitive=include_sensitive) for event in result.events]
    duration = max((event["at_ms"] for event in events), default=1) or 1
    rows = []
    for event in events:
        left = min(100, event["at_ms"] / duration * 100)
        data = html.escape(json.dumps(event["data"], sort_keys=True))
        rows.append(
            f'<div class="event"><time>{event["at_ms"]:8.1f} ms</time>'
            f'<div class="track"><i style="left:{left:.2f}%"></i></div>'
            f"<strong>{html.escape(event['kind'])}</strong><code>{data}</code></div>"
        )
    metrics = "".join(
        f"<dt>{html.escape(str(key))}</dt><dd>{html.escape(str(value))}</dd>"
        for key, value in result.metrics.items()
    )
    transcript_status = "transcripts included" if include_sensitive else "transcripts redacted"
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>TurnLab · {html.escape(result.scenario.id)}</title>
<style>
:root{{--ink:#17202a;--muted:#68707a;--line:#dfe5eb;--accent:#6c5ce7;--bg:#f7f8fa}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif}}
main{{max-width:1100px;margin:3rem auto;padding:0 1.2rem}} h1{{font-size:2rem;margin-bottom:.2rem}} .sub{{color:var(--muted)}}
.card{{background:white;border:1px solid var(--line);border-radius:12px;padding:1.3rem;margin:1.2rem 0;box-shadow:0 4px 16px #2231}}
dl{{display:grid;grid-template-columns:minmax(190px,1fr) 2fr;gap:.45rem 1rem}} dt{{color:var(--muted)}} dd{{margin:0}}
.event{{display:grid;grid-template-columns:90px minmax(150px,1fr) 190px minmax(170px,2fr);gap:1rem;align-items:center;padding:.65rem 0;border-bottom:1px solid var(--line)}}
.event:last-child{{border:0}} time,code{{font:12px ui-monospace,monospace}} code{{overflow-wrap:anywhere}} .track{{height:4px;background:var(--line);position:relative}} .track i{{position:absolute;width:10px;height:10px;border-radius:50%;background:var(--accent);top:-3px;transform:translateX(-5px)}}
@media(max-width:720px){{.event{{grid-template-columns:85px 1fr}}.track{{order:4;grid-column:1/-1}}}}
</style></head><body><main><h1>TurnLab report</h1>
<p class="sub">{html.escape(result.scenario.id)} · {html.escape(result.adapter)} adapter · {transcript_status}</p>
<section class="card"><h2>Metrics</h2><dl>{metrics}</dl></section>
<section class="card"><h2>Timeline</h2>{"".join(rows)}</section>
</main></body></html>"""
    output.write_text(document, encoding="utf-8")
    return output
