"""Render the markdown PMO dashboard from current state."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

from jinja2 import Template

from build_platform.paths import state_dir
from build_platform.schemas import WPState
from build_platform.state import (
    load_deliverables,
    load_project,
    load_work_packages,
    load_workstreams,
)


def _template(filename: str = "dashboard.md.j2") -> Template:
    src = files("build_platform.templates").joinpath(filename).read_text(encoding="utf-8")
    return Template(src, keep_trailing_newline=True)


def _sprint_number(project_root: Path) -> int:
    sprints = sorted((state_dir(project_root) / "sprints").glob("sprint-*.md"))
    return len(sprints) + 1 if not sprints else len(sprints)


def _day_of_sprint(project_root: Path) -> int:
    sprints = sorted((state_dir(project_root) / "sprints").glob("sprint-*.md"))
    if not sprints:
        return 1
    last = sprints[-1].stat().st_mtime
    delta = (datetime.now(timezone.utc).timestamp() - last) / 86400
    return max(1, int(delta) + 1)


def _live(project_root: Path) -> list[str]:
    runs = state_dir(project_root) / "runs"
    if not runs.exists():
        return []
    out = []
    cutoff = datetime.now(timezone.utc).timestamp() - 3600  # 1h sliding window
    for run_dir in runs.iterdir():
        if not run_dir.is_dir():
            continue
        if run_dir.stat().st_mtime < cutoff:
            continue
        out.append(f"{run_dir.name} · started {datetime.fromtimestamp(run_dir.stat().st_mtime).isoformat(timespec='seconds')}")
    return out


def _assemble_context(project_root: Path) -> dict:
    """Compute the data the dashboard templates render. Shared between md + html."""
    project = load_project(project_root)
    deliverables = load_deliverables(project_root)
    workstreams = load_workstreams(project_root)
    wps = load_work_packages(project_root)

    by_state = Counter(wp.state for wp in wps)
    health = {
        "active": by_state.get(WPState.DEFINED, 0) + by_state.get(WPState.DISPATCHED, 0) + by_state.get(WPState.IN_REVIEW, 0),
        "blocked": by_state.get(WPState.BLOCKED, 0),
        "done_this_sprint": by_state.get(WPState.DONE, 0),
        "velocity": 0,
        "user_blockers": by_state.get(WPState.BLOCKED, 0),
    }

    sorted_deliverables = sorted(deliverables, key=lambda d: d.sequence)
    deliverable_sequence = " ▶ ".join(d.id for d in sorted_deliverables) or None
    done_count = sum(1 for d in sorted_deliverables if d.state == "done")
    progress_pct = int(done_count * 100 / len(sorted_deliverables)) if sorted_deliverables else 0
    current_focus_d = next((d for d in sorted_deliverables if d.state == "in_progress"), None)
    current_focus = f"{current_focus_d.id} ({current_focus_d.title})" if current_focus_d else None
    next_milestone = None
    if current_focus_d:
        open_wps = [wp for wp in wps if wp.deliverable_id == current_focus_d.id and wp.state != WPState.DONE]
        if open_wps:
            next_milestone = f"{current_focus_d.id} acceptance review (est. on {', '.join(w.id for w in open_wps[:2])} completion)"
    next_action = None
    next_defined = next((wp for wp in wps if wp.state == WPState.DEFINED), None)
    if next_defined:
        next_action = f"dispatch {next_defined.id} ({next_defined.title})"

    wp_by_deliverable: dict[str, list] = defaultdict(list)
    for wp in wps:
        wp_by_deliverable[wp.deliverable_id].append(wp)
    deliverable_rows = []
    for d in sorted_deliverables:
        d_wps = wp_by_deliverable.get(d.id, [])
        deliverable_rows.append({
            "id": d.id,
            "title": d.title,
            "acceptance_met": 0,
            "acceptance_total": len(d.acceptance),
            "wp_done": sum(1 for w in d_wps if w.state == WPState.DONE),
            "wp_total": len(d_wps),
            "state": d.state,
        })

    workstream_rows = []
    for ws in workstreams:
        ws_wps = [wp for wp in wps if wp.workstream == ws.id]
        next_up = next((wp for wp in ws_wps if wp.state == WPState.DEFINED), None)
        workstream_rows.append({
            "id": ws.id,
            "owner": ws.owner_persona,
            "done": sum(1 for w in ws_wps if w.state == WPState.DONE),
            "in_review": sum(1 for w in ws_wps if w.state == WPState.IN_REVIEW),
            "blocked": sum(1 for w in ws_wps if w.state == WPState.BLOCKED),
            "next_up": next_up.id if next_up else None,
        })

    persona_activity: list[dict] = []
    daily: list[dict] = []
    blockers = [{
        "wp_id": wp.id, "workstream": wp.workstream,
        "reason": (wp.history[-1].event if wp.history else "unknown"),
        "needs_user": True, "suggestion": "investigate via audit log",
    } for wp in wps if wp.state == WPState.BLOCKED]
    decisions: list[dict] = []
    up_next = [{
        "id": wp.id, "title": wp.title, "workstream": wp.workstream, "tier": int(wp.tier.value),
    } for wp in sorted(wps, key=lambda w: w.id) if wp.state == WPState.DEFINED][:10]

    return dict(
        project=project,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        sprint_number=_sprint_number(project_root),
        day_of_sprint=_day_of_sprint(project_root),
        deliverable_sequence=deliverable_sequence,
        deliverables_total=len(sorted_deliverables),
        deliverables_done=done_count,
        progress_pct=progress_pct,
        current_focus=current_focus,
        next_milestone=next_milestone,
        next_action=next_action,
        live=_live(project_root),
        health=health,
        deliverables=deliverable_rows,
        workstreams=workstream_rows,
        persona_activity=persona_activity,
        daily=daily,
        blockers=blockers,
        decisions=decisions,
        up_next=up_next,
    )


def render_dashboard(project_root: Path) -> Path:
    """Render the markdown dashboard. Returns its path."""
    ctx = _assemble_context(project_root)
    rendered = _template("dashboard.md.j2").render(**ctx)
    out_dir = state_dir(project_root) / "dashboards"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "current.md"
    out.write_text(rendered, encoding="utf-8")
    return out


def render_dashboard_html(project_root: Path) -> Path:
    """Render the HTML dashboard. Returns its path."""
    ctx = _assemble_context(project_root)
    rendered = _template("dashboard.html.j2").render(**ctx)
    out_dir = state_dir(project_root) / "dashboards"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "current.html"
    out.write_text(rendered, encoding="utf-8")
    return out


def render_dashboard_all(project_root: Path) -> dict[str, Path]:
    """Render markdown + HTML side by side. Returns a {format: path} map."""
    return {
        "md": render_dashboard(project_root),
        "html": render_dashboard_html(project_root),
    }
