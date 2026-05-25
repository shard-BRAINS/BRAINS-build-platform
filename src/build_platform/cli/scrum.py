"""`/build-scrum` entry point — assemble the scrum brief and recap stub."""
import json
from datetime import datetime, timezone
from pathlib import Path

import click

from build_platform.git_utils import commits_since
from build_platform.paths import find_brains_build_root
from build_platform.render_dashboard import render_dashboard
from build_platform.schemas import WPState
from build_platform.state import load_work_packages


@click.command("scrum")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--json", "as_json", is_flag=True)
def scrum_cmd(root, as_json):
    root_path = Path(root).resolve() if root else find_brains_build_root()
    sprints_dir = root_path / ".brains-build" / "sprints"
    existing = sorted(sprints_dir.glob("sprint-*.md"))
    sprint_n = len(existing) + 1
    last_ts = (
        datetime.fromtimestamp(existing[-1].stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
        if existing else "2020-01-01T00:00:00Z"
    )

    wps = load_work_packages(root_path)
    since_history = [(wp, ev) for wp in wps for ev in wp.history if ev.at >= last_ts]
    created = [wp for wp in wps if wp.created_at >= last_ts]
    blocked = [wp for wp in wps if wp.state == WPState.BLOCKED]
    done = [wp for wp in wps if wp.state == WPState.DONE
            and wp.history and wp.history[-1].at >= last_ts]
    commits = commits_since(root_path, last_ts)

    brief = {
        "sprint_number": sprint_n,
        "since": last_ts,
        "now": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "created": [{"id": wp.id, "title": wp.title} for wp in created],
        "done": [{"id": wp.id, "title": wp.title} for wp in done],
        "blocked": [{"id": wp.id, "title": wp.title, "reason": wp.history[-1].event if wp.history else "unknown"} for wp in blocked],
        "dispatched_events": len(since_history),
        "commits": commits[:50],
    }

    recap_path = sprints_dir / f"sprint-{sprint_n:02d}.md"
    sprints_dir.mkdir(parents=True, exist_ok=True)
    recap_path.write_text(
        f"# Sprint {sprint_n} recap\n\n"
        f"_Generated stub: {brief['now']}_\n_Since: {brief['since']}_\n\n"
        f"## Diff (raw)\n```json\n{json.dumps(brief, indent=2)}\n```\n\n"
        f"## Progress\n_TO BE FILLED BY build-pmo-lead subagent_\n\n"
        f"## Blockers\n_TO BE FILLED_\n\n"
        f"## Velocity\n_TO BE FILLED_\n\n"
        f"## Re-prioritization\n_TO BE FILLED_\n\n"
        f"## Next up\n_TO BE FILLED_\n",
        encoding="utf-8",
    )

    render_dashboard(root_path)
    payload = {"ok": True, "sprint_number": sprint_n,
               "recap_stub": str(recap_path),
               "next": "Spawn build-pmo-lead subagent to fill in the recap stub."}
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(f"Scrum brief generated for sprint {sprint_n}.\n"
                   f"Recap stub: {recap_path}\n"
                   f"Next: spawn build-pmo-lead subagent to fill it in.")


if __name__ == "__main__":
    scrum_cmd()
