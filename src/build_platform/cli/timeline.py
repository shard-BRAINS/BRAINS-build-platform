"""`/build-timeline` entry point — chronological view of the audit trail."""
import json
import sys
from datetime import datetime
from pathlib import Path

import click

from build_platform.audit import load_audit_index
from build_platform.paths import find_brains_build_root


@click.command("timeline")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option(
    "--count",
    "-n",
    default=20,
    type=int,
    help="Number of most-recent entries to include in the window (default 20).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output JSON list of entries instead of a formatted timeline.",
)
def timeline_cmd(root, count, as_json):
    """Display a chronological timeline of work-package dispatches.

    Reads the append-only audit index (.brains-build/audit/index.jsonl), takes
    the N most-recent entries, then prints them oldest-first so the page reads
    like a transcript. Timestamps render as HH:MM when the dispatch was today
    (local time) and YYYY-MM-DD HH:MM otherwise.
    """
    if count <= 0:
        click.echo("Error: --count must be a positive integer.", err=True)
        sys.exit(1)

    root_path = Path(root).resolve() if root else find_brains_build_root()
    entries = load_audit_index(root_path)

    if not entries:
        if as_json:
            click.echo("[]")
        else:
            click.echo("No audit entries found. Has a work package been dispatched yet?")
        return

    by_recency = sorted(entries, key=lambda e: e.get("timestamp", ""), reverse=True)[:count]
    chronological = sorted(by_recency, key=lambda e: e.get("timestamp", ""))

    if as_json:
        click.echo(json.dumps(chronological, separators=(",", ":")))
        return

    today = datetime.now().astimezone().date()
    click.echo("--- Build Timeline ---\n")
    for e in chronological:
        ts = _format_timestamp(e.get("timestamp", ""), today)
        persona = (e.get("persona") or "?")[:24]
        wp = e.get("wp_id") or "?"
        result = (e.get("result") or "?")[:18]
        tier = e.get("tier", "?")
        runtime = float(e.get("runtime_seconds") or 0)
        cost = float(e.get("cost_usd") or 0)
        click.echo(
            f"{ts:<16}  {persona:<24}  {wp:<10}  tier-{tier}  {result:<18}  {runtime:>6.0f}s  ${cost:>5.2f}"
        )


def _format_timestamp(ts_raw: str, today) -> str:
    """HH:MM if same local date, YYYY-MM-DD HH:MM otherwise. Returns '????-??-?? ??:??' on parse error."""
    try:
        dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        if local_dt.date() == today:
            return local_dt.strftime("%H:%M")
        return local_dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError, TypeError):
        return "????-??-?? ??:??"


if __name__ == "__main__":
    timeline_cmd()
