"""Tests for render_dashboard.py."""
from pathlib import Path

from build_platform.render_dashboard import (
    render_dashboard,
    render_dashboard_all,
    render_dashboard_html,
)
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


def test_render_dashboard_html_writes_file(tmp_path: Path):
    _seed(tmp_path)
    out = render_dashboard_html(tmp_path)
    assert out.exists()
    assert out.name == "current.html"
    assert out.parent.name == "dashboards"


def test_render_dashboard_html_is_valid_html(tmp_path: Path):
    _seed(tmp_path)
    out = render_dashboard_html(tmp_path)
    html = out.read_text(encoding="utf-8")
    assert html.lstrip().startswith("<!doctype html>")
    assert "<title>Demo — PMO Dashboard</title>" in html
    assert "</html>" in html


def test_render_dashboard_html_uses_brand_colors(tmp_path: Path):
    """Brand: Gold Deep #D99518 on white. No raw #FCC14D body usage."""
    _seed(tmp_path)
    html = render_dashboard_html(tmp_path).read_text(encoding="utf-8")
    assert "#D99518" in html  # Gold Deep token defined
    # FCC14D is allowed as a token but only as decorative (--gold), never as body color
    # The template defines it under --gold then uses --gold-deep for text
    assert "--gold-deep" in html
    assert "Atkinson Hyperlegible" in html  # accessibility-first font
    assert "text-align: left" in html  # no justified body per brand


def test_render_dashboard_html_includes_all_sections(tmp_path: Path):
    _seed(tmp_path)
    html = render_dashboard_html(tmp_path).read_text(encoding="utf-8")
    for section in [
        "Plan position", "Live (right now)", "Health", "Deliverables",
        "Workstreams", "Persona activity", "Daily completed work",
        "Open blockers", "Recent decisions", "Up next",
    ]:
        assert section in html, f"Missing section: {section}"


def test_render_dashboard_html_lists_open_wp(tmp_path: Path):
    _seed(tmp_path)
    html = render_dashboard_html(tmp_path).read_text(encoding="utf-8")
    assert "WP-0002" in html


def test_render_dashboard_all_writes_both(tmp_path: Path):
    _seed(tmp_path)
    paths = render_dashboard_all(tmp_path)
    assert "md" in paths and "html" in paths
    assert paths["md"].exists()
    assert paths["html"].exists()
    assert paths["md"].name == "current.md"
    assert paths["html"].name == "current.html"
