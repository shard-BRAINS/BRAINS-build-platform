"""Read/write state files under .brains-build/."""
import json
from pathlib import Path
from typing import Iterable

from ruamel.yaml import YAML

from build_platform.paths import STATE_DIR_NAME, state_dir
from build_platform.schemas import (
    Config,
    Deliverable,
    Project,
    Workstream,
    WorkPackage,
    WPHistoryEvent,
    WPState,
)

_yaml = YAML(typ="safe")
_yaml.default_flow_style = False


class StateNotInitializedError(RuntimeError):
    """Raised when expected state file is missing."""


def init_state_tree(project_root: Path) -> None:
    sd = state_dir(project_root)
    for sub in ("", "sprints", "audit", "dashboards", "runs"):
        (sd / sub).mkdir(parents=True, exist_ok=True)
    wp_log = sd / "work-packages.jsonl"
    if not wp_log.exists():
        wp_log.write_text("", encoding="utf-8")
    decisions = sd / "decisions.md"
    if not decisions.exists():
        decisions.write_text("# Decisions\n\n", encoding="utf-8")


def _require(path: Path) -> Path:
    if not path.exists():
        raise StateNotInitializedError(
            f"Missing {path}. Run /build-init to set up the project."
        )
    return path


def save_project(project_root: Path, project: Project) -> None:
    path = state_dir(project_root) / "project.yml"
    with path.open("w", encoding="utf-8") as f:
        _yaml.dump(project.model_dump(mode="json"), f)


def load_project(project_root: Path) -> Project:
    path = _require(state_dir(project_root) / "project.yml")
    with path.open("r", encoding="utf-8") as f:
        return Project.model_validate(_yaml.load(f))


def save_deliverables(project_root: Path, deliverables: Iterable[Deliverable]) -> None:
    path = state_dir(project_root) / "deliverables.yml"
    payload = {"deliverables": [d.model_dump(mode="json") for d in deliverables]}
    with path.open("w", encoding="utf-8") as f:
        _yaml.dump(payload, f)


def load_deliverables(project_root: Path) -> list[Deliverable]:
    path = _require(state_dir(project_root) / "deliverables.yml")
    with path.open("r", encoding="utf-8") as f:
        data = _yaml.load(f)
    return [Deliverable.model_validate(d) for d in data.get("deliverables", [])]


def save_workstreams(project_root: Path, workstreams: Iterable[Workstream]) -> None:
    path = state_dir(project_root) / "workstreams.yml"
    payload = {"workstreams": [w.model_dump(mode="json") for w in workstreams]}
    with path.open("w", encoding="utf-8") as f:
        _yaml.dump(payload, f)


def load_workstreams(project_root: Path) -> list[Workstream]:
    path = _require(state_dir(project_root) / "workstreams.yml")
    with path.open("r", encoding="utf-8") as f:
        data = _yaml.load(f)
    return [Workstream.model_validate(w) for w in data.get("workstreams", [])]


def append_work_package(project_root: Path, wp: WorkPackage) -> None:
    path = state_dir(project_root) / "work-packages.jsonl"
    line = json.dumps(wp.model_dump(mode="json"), separators=(",", ":"))
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_work_packages(project_root: Path) -> list[WorkPackage]:
    path = state_dir(project_root) / "work-packages.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(WorkPackage.model_validate_json(line))
    return out


def next_wp_id(project_root: Path) -> str:
    existing = load_work_packages(project_root)
    if not existing:
        return "WP-0001"
    max_n = max(int(wp.id.split("-")[1]) for wp in existing)
    return f"WP-{max_n + 1:04d}"


def update_wp_state(
    project_root: Path,
    wp_id: str,
    new_state: WPState,
    *,
    by: str,
    event: str,
    at: str | None = None,
) -> WorkPackage:
    """Mutate a WP's state by appending a history event; rewrite the JSONL line.

    Returns the updated WorkPackage.
    """
    from datetime import datetime, timezone

    at = at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = state_dir(project_root) / "work-packages.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out_lines: list[str] = []
    updated: WorkPackage | None = None
    for raw in lines:
        if not raw.strip():
            continue
        wp = WorkPackage.model_validate_json(raw)
        if wp.id == wp_id:
            wp = wp.model_copy(update={
                "state": new_state,
                "history": [*wp.history, WPHistoryEvent(at=at, by=by, event=event)],
            })
            updated = wp
        out_lines.append(json.dumps(wp.model_dump(mode="json"), separators=(",", ":")))
    if updated is None:
        raise KeyError(f"WP {wp_id} not found")
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return updated


def load_wp_state(project_root: Path) -> dict[str, WorkPackage]:
    """Derived view: current state of every WP."""
    return {wp.id: wp for wp in load_work_packages(project_root)}


def save_config(project_root: Path, config: Config) -> None:
    path = state_dir(project_root) / "config.yml"
    with path.open("w", encoding="utf-8") as f:
        _yaml.dump(config.model_dump(mode="json"), f)


def load_config(project_root: Path) -> Config:
    path = _require(state_dir(project_root) / "config.yml")
    with path.open("r", encoding="utf-8") as f:
        return Config.model_validate(_yaml.load(f))
