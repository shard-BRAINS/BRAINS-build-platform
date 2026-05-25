"""`/build-status` entry point — read-only status query."""
import json
import sys
from collections import Counter
from pathlib import Path

import click

from build_platform.paths import find_brains_build_root
from build_platform.schemas import WPState
from build_platform.state import load_project, load_work_packages


@click.command("status")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--wp", default=None, help="Show status for a specific WP id.")
@click.option("--json", "as_json", is_flag=True)
def status_cmd(root, wp, as_json):
    root_path = Path(root).resolve() if root else find_brains_build_root()
    project = load_project(root_path)
    wps = load_work_packages(root_path)
    if wp:
        match = next((w for w in wps if w.id == wp), None)
        if not match:
            click.echo(json.dumps({"error": f"WP {wp} not found"}) if as_json else f"WP {wp} not found", err=True)
            sys.exit(1)
        payload = match.model_dump(mode="json")
        click.echo(json.dumps(payload) if as_json else _human(match))
        return
    counts = Counter(w.state for w in wps)
    payload = {
        "project": project.name,
        "total_wps": len(wps),
        "by_state": {k.value: v for k, v in counts.items()},
    }
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(f"Project: {project.name}")
        click.echo(f"Total WPs: {len(wps)}")
        for state, n in counts.items():
            click.echo(f"  {state.value}: {n}")


def _human(wp) -> str:
    return (
        f"{wp.id} · {wp.title}\n"
        f"  workstream: {wp.workstream} · deliverable: {wp.deliverable_id}\n"
        f"  tier: {wp.tier.value} · state: {wp.state.value} · persona: {wp.executor_persona}\n"
        f"  spec: {wp.spec}\n"
        f"  acceptance: {'; '.join(wp.acceptance)}\n"
        f"  history: {len(wp.history)} events"
    )


if __name__ == "__main__":
    status_cmd()
