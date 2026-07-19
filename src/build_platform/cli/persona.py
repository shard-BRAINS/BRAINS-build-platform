"""`/build-persona` entry point group — register, list, and install custom personas.

Custom personas live as project-local subagent definitions at
`.brains-build/personas/<id>.md`. The `install` subcommand copies them to
`~/.claude/agents/build/` so Claude Code can discover them globally.
"""
import json
import re
import shutil
import sys
from importlib.resources import files as pkg_files
from pathlib import Path

import click
from jinja2 import Template, select_autoescape

from build_platform.paths import find_brains_build_root, state_dir

_VALID_ID = re.compile(r"^build-[a-z][a-z0-9-]+[a-z0-9]$")

_TIER_DEFAULTS = {
    "leadership": {
        "model": "claude-opus-4-8",
        "tools": "Read, Write, Edit, Grep, Glob, Bash, TodoWrite, Agent",
    },
    "executor": {
        "model": "claude-sonnet-5",
        "tools": "Read, Write, Edit, Grep, Glob, Bash",
    },
    "read-only": {
        "model": "claude-sonnet-5",
        "tools": "Read, Grep, Glob, Bash",
    },
}

_DEFAULT_STEPS = [
    "Read the tier-2 brief at `.brains-build/runs/<wp-id>/tier2-brief.md`.",
    "Read project context (`.brains-build/project.yml`) and the files listed in scope.",
    "Implement the spec; touch only the files in scope.",
    "Run the project's test command (from `.brains-build/config.yml`).",
    "Log non-trivial decisions to `decisions.md` via `/build-decision`.",
]

_DEFAULT_RULES = [
    "Touch only the files in scope unless the spec explicitly authorizes more.",
    "Do not invent dependencies; flag any required additions as blockers.",
    "Token discipline: do not read whole directories. Use Grep/Glob.",
    "If acceptance criteria conflict with existing code, escalate as a blocker.",
]


def _load_template() -> Template:
    src = pkg_files("build_platform.templates").joinpath("custom_persona.md.j2").read_text(encoding="utf-8")
    return Template(src, autoescape=select_autoescape(), keep_trailing_newline=True)


def _local_personas_dir(project_root: Path) -> Path:
    return state_dir(project_root) / "personas"


def _global_personas_dir() -> Path:
    return Path.home() / ".claude" / "agents" / "build"


def _emit(payload: dict, *, as_json: bool, exit_code: int = 0) -> None:
    if as_json:
        click.echo(json.dumps(payload))
    elif "error" in payload:
        click.echo(f"Error: {payload['error']}", err=True)
    else:
        click.echo(payload.get("message", json.dumps(payload, indent=2)))
    sys.exit(exit_code)


@click.group("persona")
def persona_group():
    """Manage custom personas for the active project."""


@persona_group.command("register")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--id", "persona_id", required=True,
              help="Persona id, e.g. 'build-data-sme'. Must start with 'build-'.")
@click.option("--tier", type=click.Choice(["leadership", "executor", "read-only"]),
              default="executor", show_default=True)
@click.option("--description", required=True,
              help="One-line description used by Claude for skill matching.")
@click.option("--mission", required=True, help="One-paragraph mission statement.")
@click.option("--when-invoked", default="Spawned per work package. Read the tier-2 brief first.",
              show_default=True)
@click.option("--model", default=None,
              help="Override default model for this tier.")
@click.option("--tools", default=None,
              help="Comma-separated tools list. Overrides tier default.")
@click.option("--step", "steps", multiple=True,
              help="Append a numbered 'What to do' step (repeatable). "
                   "If omitted, sensible defaults are used.")
@click.option("--rule", "rules", multiple=True,
              help="Append a 'Rules of engagement' bullet (repeatable). "
                   "If omitted, sensible defaults are used.")
@click.option("--force", is_flag=True, help="Overwrite if persona file already exists.")
@click.option("--json", "as_json", is_flag=True)
def register_cmd(root, persona_id, tier, description, mission, when_invoked,
                 model, tools, steps, rules, force, as_json):
    """Register a new custom persona for the active project."""
    if not _VALID_ID.match(persona_id):
        _emit({"error": f"Invalid id {persona_id!r}. Must match {_VALID_ID.pattern}"},
              as_json=as_json, exit_code=2)

    root_path = Path(root).resolve() if root else find_brains_build_root()
    personas_dir = _local_personas_dir(root_path)
    personas_dir.mkdir(parents=True, exist_ok=True)
    out = personas_dir / f"{persona_id}.md"
    if out.exists() and not force:
        _emit({"error": f"Persona {persona_id} already exists at {out}. Use --force to overwrite."},
              as_json=as_json, exit_code=3)

    defaults = _TIER_DEFAULTS[tier]
    final_tools = tools or defaults["tools"]
    final_model = model or defaults["model"]
    final_steps = list(steps) or _DEFAULT_STEPS
    final_rules = list(rules) or _DEFAULT_RULES

    rendered = _load_template().render(
        id=persona_id, description=description, tools=final_tools, model=final_model,
        mission=mission, when_invoked=when_invoked,
        steps=final_steps, rules=final_rules,
    )
    out.write_text(rendered, encoding="utf-8")

    _emit({
        "ok": True, "id": persona_id, "tier": tier, "path": str(out),
        "installed_globally": False,
        "next": f"Run `python -m build_platform.cli.persona install {persona_id}` "
                f"to make it available across projects.",
    }, as_json=as_json)


@persona_group.command("list")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--json", "as_json", is_flag=True)
def list_cmd(root, as_json):
    """List all available personas (project-local + globally installed)."""
    root_path = Path(root).resolve() if root else find_brains_build_root()
    local = sorted((_local_personas_dir(root_path)).glob("*.md")) if _local_personas_dir(root_path).exists() else []
    global_dir = _global_personas_dir()
    global_ = sorted(global_dir.glob("*.md")) if global_dir.exists() else []

    entries = []
    for path in local:
        entries.append({"id": path.stem, "scope": "local", "path": str(path)})
    seen = {e["id"] for e in entries}
    for path in global_:
        if path.stem in seen:
            continue  # local overrides global
        entries.append({"id": path.stem, "scope": "global", "path": str(path)})

    payload = {"ok": True, "count": len(entries), "personas": entries}
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(f"{len(entries)} personas:")
        for e in entries:
            click.echo(f"  [{e['scope']:6}] {e['id']}")


@persona_group.command("install")
@click.argument("persona_id")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--force", is_flag=True, help="Overwrite global if it exists.")
@click.option("--json", "as_json", is_flag=True)
def install_cmd(persona_id, root, force, as_json):
    """Copy a project-local persona to ~/.claude/agents/build/ (global)."""
    root_path = Path(root).resolve() if root else find_brains_build_root()
    src = _local_personas_dir(root_path) / f"{persona_id}.md"
    if not src.exists():
        _emit({"error": f"No local persona {persona_id!r} at {src}"},
              as_json=as_json, exit_code=1)

    global_dir = _global_personas_dir()
    global_dir.mkdir(parents=True, exist_ok=True)
    dest = global_dir / f"{persona_id}.md"
    if dest.exists() and not force:
        _emit({"error": f"Global persona already exists at {dest}. Use --force to overwrite."},
              as_json=as_json, exit_code=3)

    shutil.copyfile(src, dest)
    _emit({"ok": True, "id": persona_id, "from": str(src), "to": str(dest)},
          as_json=as_json)


if __name__ == "__main__":
    persona_group()
