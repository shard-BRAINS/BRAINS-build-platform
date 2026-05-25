"""`/build-init` entry point — scaffolds a project."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from build_platform.schemas import (
    Config,
    Deliverable,
    OllamaConfig,
    OllamaModels,
    Project,
    ProjectConfig,
    Workstream,
)
from build_platform.state import (
    init_state_tree,
    save_config,
    save_deliverables,
    save_project,
    save_workstreams,
)

DEFAULT_WORKSTREAMS = [
    Workstream(id="backend", owner_persona="build-backend-sme",
               review_persona="build-dev-orchestrator",
               description="Server-side code, data layer, APIs"),
    Workstream(id="frontend", owner_persona="build-frontend-sme",
               review_persona="build-dev-orchestrator",
               description="UI, components, styling"),
    Workstream(id="qa", owner_persona="build-qa-sme",
               review_persona="build-pmo-lead",
               description="Tests, regression matrices, bug repro"),
    Workstream(id="security", owner_persona="build-security-sme",
               review_persona="build-dev-orchestrator",
               description="Threat modeling, dependency audit, OWASP review"),
    Workstream(id="devops", owner_persona="build-devops-sme",
               review_persona="build-dev-orchestrator",
               description="CI/CD, build, deploy, environment management"),
]


def _emit(payload: dict, *, as_json: bool, exit_code: int = 0) -> None:
    if as_json:
        click.echo(json.dumps(payload))
    else:
        if "error" in payload:
            click.echo(f"Error: {payload['error']}", err=True)
        else:
            click.echo(payload.get("message", ""))
    sys.exit(exit_code)


@click.command("init")
@click.option("--root", type=click.Path(file_okay=False), default=".",
              help="Project root directory.")
@click.option("--name", required=True, help="Project name.")
@click.option("--mission", required=True, help="One-sentence mission.")
@click.option("--stack", "stack", multiple=True, required=True,
              help="Stack element (repeatable).")
@click.option("--constraint", "constraints", multiple=True, default=(),
              help="Constraint (repeatable).")
@click.option("--deliverable", "deliverables", multiple=True, required=True,
              help="Deliverable as 'id:title:why:acceptance' (repeatable). "
                   "Use ';' to separate multiple acceptance criteria.")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
def init_cmd(root, name, mission, stack, constraints, deliverables, as_json):
    """Initialize a new build project."""
    root_path = Path(root).resolve()
    if (root_path / ".brains-build").exists():
        _emit({"error": f".brains-build/ already exists at {root_path}. Use /build-status."},
              as_json=as_json, exit_code=1)

    parsed_deliverables = []
    for i, raw in enumerate(deliverables, start=1):
        parts = raw.split(":", 3)
        if len(parts) != 4:
            _emit({"error": f"Invalid deliverable format: {raw!r}"}, as_json=as_json, exit_code=2)
        d_id, title, why, accept = parts
        acceptance = [a.strip() for a in accept.split(";") if a.strip()]
        parsed_deliverables.append(Deliverable(
            id=d_id, title=title, why=why, acceptance=acceptance,
            sequence=i, state="not_started",
        ))

    init_state_tree(root_path)
    project = Project(
        name=name, mission=mission, stack=list(stack), constraints=list(constraints),
        ground_truth="local",
        created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    save_project(root_path, project)
    save_deliverables(root_path, parsed_deliverables)
    save_workstreams(root_path, DEFAULT_WORKSTREAMS)
    save_config(root_path, Config(
        ollama=OllamaConfig(models=OllamaModels()),
        project=ProjectConfig(test_command="pytest"),
    ))

    decisions = root_path / ".brains-build" / "decisions.md"
    decisions.write_text(
        f"# Decisions\n\n"
        f"## {datetime.now(timezone.utc).date().isoformat()} — Project initialized\n"
        f"**Owner:** user\n"
        f"**Decision:** Initialized BRAINS Build Platform for project '{name}'.\n"
        f"**Why:** {mission}\n",
        encoding="utf-8",
    )

    next_steps = (
        f"Initialized at {root_path}\n"
        f"Next:\n"
        f"  1. Pull Ollama models: `ollama pull qwen2.5-coder:7b && ollama pull llama3.2:3b`\n"
        f"  2. Run /build-package to break a deliverable into work packages."
    )
    _emit({"ok": True, "message": next_steps, "root": str(root_path)}, as_json=as_json)


if __name__ == "__main__":
    init_cmd()
