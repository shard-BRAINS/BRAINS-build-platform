"""`/build-package` entry point — add a WP. Heavy lifting is done by the Dev Orchestrator
subagent in the Claude session; this CLI validates and writes."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from build_platform.paths import find_brains_build_root
from build_platform.schemas import WorkPackage, WPState, WPTier
from build_platform.state import append_work_package, next_wp_id


@click.command("package")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--title", required=True)
@click.option("--workstream", required=True)
@click.option("--deliverable", "deliverable_id", required=True)
@click.option("--tier", type=click.Choice(["1", "2"]), required=True)
@click.option("--executor", "executor_persona", required=True)
@click.option("--spec", required=True)
@click.option("--file", "spec_files", multiple=True)
@click.option("--accept", "acceptance", multiple=True, required=True)
@click.option("--depends-on", "depends_on", multiple=True, default=())
@click.option("--consult", multiple=True, default=())
@click.option("--created-by", default="build-dev-orchestrator")
@click.option("--json", "as_json", is_flag=True)
def package_cmd(root, title, workstream, deliverable_id, tier, executor_persona,
                spec, spec_files, acceptance, depends_on, consult, created_by, as_json):
    root_path = Path(root).resolve() if root else find_brains_build_root()
    wp_id = next_wp_id(root_path)
    wp = WorkPackage(
        id=wp_id, title=title, workstream=workstream, deliverable_id=deliverable_id,
        tier=WPTier(int(tier)), executor_persona=executor_persona,
        spec=spec, spec_files=list(spec_files), acceptance=list(acceptance),
        depends_on=list(depends_on), consult=list(consult),
        state=WPState.DEFINED, created_by=created_by,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        history=[],
    )
    if wp.tier == WPTier.ONE:
        if len(wp.spec_files) > 3:
            payload = {"error": f"Tier-1 WP must touch <= 3 files; got {len(wp.spec_files)}"}
            click.echo(json.dumps(payload) if as_json else payload["error"], err=True)
            sys.exit(2)
    append_work_package(root_path, wp)
    payload = {"ok": True, "wp_id": wp.id}
    click.echo(json.dumps(payload) if as_json else f"Created {wp.id}: {title}")


if __name__ == "__main__":
    package_cmd()
