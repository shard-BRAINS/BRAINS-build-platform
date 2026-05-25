"""Tests for state.py."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from build_platform.schemas import (
    Config,
    Deliverable,
    OllamaConfig,
    OllamaModels,
    Project,
    ProjectConfig,
    Workstream,
    WorkPackage,
    WPState,
    WPTier,
)
from build_platform.state import (
    StateNotInitializedError,
    append_work_package,
    init_state_tree,
    load_config,
    load_deliverables,
    load_project,
    load_work_packages,
    load_wp_state,
    load_workstreams,
    next_wp_id,
    save_config,
    save_deliverables,
    save_project,
    save_workstreams,
    update_wp_state,
)


def test_init_state_tree_creates_directories(tmp_path: Path):
    init_state_tree(tmp_path)
    assert (tmp_path / ".brains-build").is_dir()
    assert (tmp_path / ".brains-build" / "sprints").is_dir()
    assert (tmp_path / ".brains-build" / "audit").is_dir()
    assert (tmp_path / ".brains-build" / "dashboards").is_dir()
    assert (tmp_path / ".brains-build" / "runs").is_dir()


def test_save_and_load_project(tmp_path: Path):
    init_state_tree(tmp_path)
    p = Project(
        name="x", mission="y", stack=["python"], constraints=["no GPL"],
        ground_truth="local", created="2026-05-25T10:00:00Z",
    )
    save_project(tmp_path, p)
    loaded = load_project(tmp_path)
    assert loaded.name == "x"
    assert loaded.constraints == ["no GPL"]


def test_load_project_raises_when_uninitialized(tmp_path: Path):
    with pytest.raises(StateNotInitializedError):
        load_project(tmp_path)


def test_save_and_load_deliverables(tmp_path: Path):
    init_state_tree(tmp_path)
    deliverables = [
        Deliverable(id="D-a", title="Auth", why="we need auth",
                    acceptance=["users can log in"], sequence=1, state="not_started"),
        Deliverable(id="D-b", title="UI", why="needs UI",
                    acceptance=["page renders"], sequence=2, state="not_started"),
    ]
    save_deliverables(tmp_path, deliverables)
    loaded = load_deliverables(tmp_path)
    assert len(loaded) == 2
    assert loaded[0].id == "D-a"


def test_save_and_load_workstreams(tmp_path: Path):
    init_state_tree(tmp_path)
    ws = [Workstream(id="backend", owner_persona="build-backend-sme",
                     review_persona="build-dev-orchestrator", description="x")]
    save_workstreams(tmp_path, ws)
    assert load_workstreams(tmp_path)[0].id == "backend"


def test_append_and_load_work_packages(tmp_path: Path):
    init_state_tree(tmp_path)
    wp = WorkPackage(
        id="WP-0001", title="t", workstream="backend", deliverable_id="D-a",
        tier=WPTier.ONE, executor_persona="build-backend-sme", spec="s",
        spec_files=["f.py"], acceptance=["a"], depends_on=[], consult=[],
        state=WPState.DEFINED, created_by="build-dev-orchestrator",
        created_at="2026-05-25T10:00:00Z", history=[],
    )
    append_work_package(tmp_path, wp)
    loaded = load_work_packages(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].id == "WP-0001"


def test_next_wp_id_starts_at_0001(tmp_path: Path):
    init_state_tree(tmp_path)
    assert next_wp_id(tmp_path) == "WP-0001"


def test_next_wp_id_increments(tmp_path: Path):
    init_state_tree(tmp_path)
    wp = WorkPackage(
        id="WP-0001", title="t", workstream="backend", deliverable_id="D-a",
        tier=WPTier.ONE, executor_persona="build-backend-sme", spec="s",
        spec_files=[], acceptance=["a"], depends_on=[], consult=[],
        state=WPState.DEFINED, created_by="build-dev-orchestrator",
        created_at="2026-05-25T10:00:00Z", history=[],
    )
    append_work_package(tmp_path, wp)
    assert next_wp_id(tmp_path) == "WP-0002"


def test_wp_state_derived_from_history(tmp_path: Path):
    init_state_tree(tmp_path)
    wp = WorkPackage(
        id="WP-0001", title="t", workstream="backend", deliverable_id="D-a",
        tier=WPTier.ONE, executor_persona="build-backend-sme", spec="s",
        spec_files=[], acceptance=["a"], depends_on=[], consult=[],
        state=WPState.DEFINED, created_by="build-dev-orchestrator",
        created_at="2026-05-25T10:00:00Z", history=[],
    )
    append_work_package(tmp_path, wp)
    update_wp_state(tmp_path, "WP-0001", WPState.DISPATCHED,
                    by="build-dev-orchestrator", event="dispatched to tier-1")
    state = load_wp_state(tmp_path)
    assert state["WP-0001"].state == WPState.DISPATCHED
    assert len(state["WP-0001"].history) == 1


def test_config_round_trip(tmp_path: Path):
    init_state_tree(tmp_path)
    c = Config(
        ollama=OllamaConfig(models=OllamaModels()),
        project=ProjectConfig(test_command="pytest -q"),
    )
    save_config(tmp_path, c)
    loaded = load_config(tmp_path)
    assert loaded.project.test_command == "pytest -q"
    assert loaded.ollama.url == "http://localhost:11434"
