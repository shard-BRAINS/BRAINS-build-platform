"""Tests for render_dashboard.py."""
from datetime import datetime, timezone
from pathlib import Path

from build_platform.render_dashboard import render_dashboard
from build_platform.schemas import (
    Config,
    Deliverable,
    OllamaConfig,
    OllamaModels,
    Project,
    ProjectConfig,
    WorkPackage,
    Workstream,
    WPState,
    WPTier,
)
from build_platform.state import (
    append_work_package,
    init_state_tree,
    save_config,
    save_deliverables,
    save_project,
    save_workstreams,
)


def _seed(tmp_path: Path) -> Path:
    init_state_tree(tmp_path)
    save_project(tmp_path, Project(
        name="Demo", mission="Demonstrate", stack=["python"], constraints=[],
        ground_truth="local", created="2026-05-25T10:00:00Z",
    ))
    save_deliverables(tmp_path, [
        Deliverable(id="D-auth", title="Auth", why="users", acceptance=["login works"],
                    sequence=1, state="in_progress"),
        Deliverable(id="D-ui", title="UI", why="users", acceptance=["page renders"],
                    sequence=2, state="not_started"),
    ])
    save_workstreams(tmp_path, [
        Workstream(id="backend", owner_persona="build-backend-sme",
                   review_persona="build-dev-orchestrator", description="Server"),
    ])
    save_config(tmp_path, Config(
        ollama=OllamaConfig(models=OllamaModels()),
        project=ProjectConfig(test_command="pytest"),
    ))
    append_work_package(tmp_path, WorkPackage(
        id="WP-0001", title="Login endpoint", workstream="backend", deliverable_id="D-auth",
        tier=WPTier.TWO, executor_persona="build-backend-sme", spec="implement login",
        spec_files=["src/auth/login.py"], acceptance=["test passes"], depends_on=[], consult=[],
        state=WPState.DONE, created_by="build-dev-orchestrator",
        created_at="2026-05-24T10:00:00Z", history=[],
    ))
    append_work_package(tmp_path, WorkPackage(
        id="WP-0002", title="Session refresh", workstream="backend", deliverable_id="D-auth",
        tier=WPTier.TWO, executor_persona="build-backend-sme", spec="refresh sessions",
        spec_files=["src/auth/session.py"], acceptance=["test passes"], depends_on=[], consult=[],
        state=WPState.DEFINED, created_by="build-dev-orchestrator",
        created_at="2026-05-25T10:00:00Z", history=[],
    ))
    return tmp_path


def test_render_dashboard_writes_file(tmp_path: Path):
    _seed(tmp_path)
    out = render_dashboard(tmp_path)
    assert out.exists()
    assert out.name == "current.md"
    assert out.parent.name == "dashboards"


def test_render_dashboard_includes_required_sections(tmp_path: Path):
    _seed(tmp_path)
    out = render_dashboard(tmp_path)
    text = out.read_text(encoding="utf-8")
    for section in [
        "# Demo — PMO Dashboard",
        "## Plan position",
        "## Live (right now)",
        "## Health",
        "## Deliverables",
        "## Workstreams",
        "## Persona activity",
        "## Daily completed work",
        "## Open blockers",
        "## Recent decisions",
        "## Up next",
    ]:
        assert section in text, f"Missing section: {section}"


def test_render_dashboard_lists_open_wp(tmp_path: Path):
    _seed(tmp_path)
    out = render_dashboard(tmp_path)
    assert "WP-0002" in out.read_text(encoding="utf-8")


def test_render_dashboard_empty_sections_render_as_none(tmp_path: Path):
    init_state_tree(tmp_path)
    save_project(tmp_path, Project(
        name="Empty", mission="x", stack=[], constraints=[],
        ground_truth="local", created="2026-05-25T10:00:00Z",
    ))
    save_deliverables(tmp_path, [])
    save_workstreams(tmp_path, [])
    save_config(tmp_path, Config(
        ollama=OllamaConfig(models=OllamaModels()),
        project=ProjectConfig(test_command="pytest"),
    ))
    out = render_dashboard(tmp_path)
    text = out.read_text(encoding="utf-8")
    assert "_None_" in text
