"""`/build-triage` (v2.7) — suggest a tier for a WP without committing.

Two modes:
  1. By WP id (against the active project): loads spec/files/acceptance from
     work-packages.jsonl and runs the heuristic against on-disk file sizes.
  2. Ad-hoc: pass --spec / --file / --accept directly. Useful BEFORE running
     /build-package so the Dev Orchestrator can decide tier first.

Read-only — never mutates state.
"""
import json
import sys
from pathlib import Path

import click

from build_platform.paths import find_brains_build_root
from build_platform.state import load_wp_state
from build_platform.triage import suggest_tier


def _err(msg: str, as_json: bool, code: int) -> None:
    click.echo(json.dumps({"error": msg}) if as_json else f"Error: {msg}", err=True)
    sys.exit(code)


@click.command("triage")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--wp", "wp_id", default=None,
              help="WP id to triage. If omitted, must pass --spec/--file/--accept.")
@click.option("--spec", default=None, help="Ad-hoc: WP spec text.")
@click.option("--file", "spec_files", multiple=True,
              help="Ad-hoc: file in scope (repeatable).")
@click.option("--accept", "acceptance", multiple=True,
              help="Ad-hoc: acceptance criterion (repeatable).")
@click.option("--json", "as_json", is_flag=True)
def triage_cmd(root, wp_id, spec, spec_files, acceptance, as_json):
    """Suggest tier-1 vs tier-2 for a WP. Read-only."""
    root_path = Path(root).resolve() if root else find_brains_build_root()

    if wp_id:
        wps = load_wp_state(root_path)
        if wp_id not in wps:
            _err(f"WP {wp_id} not found", as_json, 1)
        wp = wps[wp_id]
        result = suggest_tier(
            spec=wp.spec,
            spec_files=list(wp.spec_files),
            acceptance=list(wp.acceptance),
            project_root=root_path,
        )
        result["wp_id"] = wp.id
        result["current_tier"] = int(wp.tier.value)
        result["matches_current_tier"] = (result["suggested_tier"] == int(wp.tier.value))
    else:
        if not spec:
            _err("Either --wp or --spec is required", as_json, 1)
        result = suggest_tier(
            spec=spec,
            spec_files=list(spec_files),
            acceptance=list(acceptance),
            project_root=root_path,
        )
        result["wp_id"] = None

    if as_json:
        click.echo(json.dumps(result))
    else:
        click.echo(f"Suggested tier: {result['suggested_tier']}")
        if result.get("wp_id") and not result.get("matches_current_tier", True):
            click.echo(f"  (current tier on WP {result['wp_id']}: {result['current_tier']})")
        click.echo(f"Rationale: {result['rationale']}")
        click.echo("Criteria:")
        for c in result["criteria"]:
            mark = "✓" if c["pass"] else "✗"
            click.echo(f"  {mark} {c['name']}: {c['detail']}")
    sys.exit(0)


if __name__ == "__main__":
    triage_cmd()
