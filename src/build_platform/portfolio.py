"""Cross-project portfolio: registry + aggregation logic.

Registry lives at ~/.brains-build-portfolio.yml. The CLI manipulates it;
this module provides load/save + project-scan helpers.
"""
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from build_platform.paths import STATE_DIR_NAME
from build_platform.schemas import WPState
from build_platform.state import (
    load_deliverables,
    load_project,
    load_work_packages,
)

_yaml = YAML(typ="safe")
_yaml.default_flow_style = False


class Portfolio(BaseModel):
    projects: list[str] = Field(default_factory=list)


def registry_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".brains-build-portfolio.yml"


def load_portfolio(home: Path | None = None) -> Portfolio:
    path = registry_path(home)
    if not path.exists():
        return Portfolio()
    with path.open("r", encoding="utf-8") as f:
        data = _yaml.load(f) or {}
    return Portfolio.model_validate(data)


def save_portfolio(portfolio: Portfolio, home: Path | None = None) -> Path:
    path = registry_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        _yaml.dump(portfolio.model_dump(mode="json"), f)
    return path


def is_brains_project(path: Path) -> bool:
    return (path / STATE_DIR_NAME).is_dir() and (path / STATE_DIR_NAME / "project.yml").exists()


def scan_project(project_root: Path) -> dict:
    """Aggregate one project's high-level state. Returns row dict or {error: ...}."""
    if not is_brains_project(project_root):
        return {"path": str(project_root), "error": "not a build project"}
    try:
        project = load_project(project_root)
        deliverables = load_deliverables(project_root)
        wps = load_work_packages(project_root)
    except Exception as e:
        return {"path": str(project_root), "error": f"load failed: {e}"}

    done_d = sum(1 for d in deliverables if d.state == "done")
    total_d = len(deliverables)
    active = sum(1 for wp in wps if wp.state in (WPState.DEFINED, WPState.DISPATCHED, WPState.IN_REVIEW))
    blocked = sum(1 for wp in wps if wp.state == WPState.BLOCKED)
    done_wp = sum(1 for wp in wps if wp.state == WPState.DONE)

    # Last activity: most recent audit file or wp-log mtime
    audit_dir = project_root / STATE_DIR_NAME / "audit"
    audits = list(audit_dir.glob("*.md")) if audit_dir.exists() else []
    if audits:
        last_mtime = max(a.stat().st_mtime for a in audits)
    else:
        wp_log = project_root / STATE_DIR_NAME / "work-packages.jsonl"
        last_mtime = wp_log.stat().st_mtime if wp_log.exists() else 0.0
    last_iso = datetime.fromtimestamp(last_mtime, tz=timezone.utc).isoformat(timespec="seconds") if last_mtime else None

    progress_pct = int(done_d * 100 / total_d) if total_d else 0
    return {
        "path": str(project_root),
        "name": project.name,
        "mission": project.mission,
        "deliverables_done": done_d,
        "deliverables_total": total_d,
        "progress_pct": progress_pct,
        "wps_active": active,
        "wps_blocked": blocked,
        "wps_done": done_wp,
        "last_activity": last_iso,
        "dashboard": str(project_root / STATE_DIR_NAME / "dashboards" / "current.md"),
    }


def scan_portfolio(portfolio: Portfolio) -> list[dict]:
    """Return a row per registered project, including error rows for missing ones."""
    return [scan_project(Path(p)) for p in portfolio.projects]
