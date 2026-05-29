"""Tests for state.py."""
import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from build_platform.schemas import (
    Config,
    Deliverable,
    GitHubMirrorConfig,
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
    append_work_package_with_new_id,
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


# ---------------------------------------------------------------------------
# WP-0013: atomic id allocation
# ---------------------------------------------------------------------------

def _partial_wp() -> dict:
    """Minimal WP fields — everything except 'id'."""
    return {
        "title": "t", "workstream": "backend", "deliverable_id": "D-a",
        "tier": WPTier.ONE, "executor_persona": "build-backend-sme", "spec": "s",
        "spec_files": [], "acceptance": ["a"], "depends_on": [], "consult": [],
        "state": WPState.DEFINED, "created_by": "build-dev-orchestrator",
        "created_at": "2026-05-25T10:00:00Z", "history": [],
    }


def test_append_work_package_with_new_id_assigns_sequential_ids(tmp_path: Path):
    init_state_tree(tmp_path)
    wp1 = append_work_package_with_new_id(tmp_path, _partial_wp())
    wp2 = append_work_package_with_new_id(tmp_path, _partial_wp())
    wp3 = append_work_package_with_new_id(tmp_path, _partial_wp())
    assert wp1.id == "WP-0001"
    assert wp2.id == "WP-0002"
    assert wp3.id == "WP-0003"


def test_append_work_package_with_new_id_no_collisions_under_threads(tmp_path: Path):
    init_state_tree(tmp_path)
    results: list[str] = []
    errors: list[Exception] = []

    def worker():
        try:
            wp = append_work_package_with_new_id(tmp_path, _partial_wp())
            results.append(wp.id)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread errors: {errors}"
    # All 5 ids are distinct
    assert len(set(results)) == 5, f"Collisions detected: {results}"

    # All JSONL lines are well-formed
    jsonl = (tmp_path / ".brains-build" / "work-packages.jsonl").read_text(encoding="utf-8")
    for line in jsonl.splitlines():
        if line.strip():
            json.loads(line)  # raises if malformed

    # All returned ids appear in the file
    written_ids = {json.loads(line)["id"] for line in jsonl.splitlines() if line.strip()}
    for wp_id in results:
        assert wp_id in written_ids


def test_legacy_next_wp_id_still_works(tmp_path: Path):
    """Back-compat smoke: next_wp_id remains importable and correct."""
    init_state_tree(tmp_path)
    assert next_wp_id(tmp_path) == "WP-0001"
    wp = WorkPackage(
        id="WP-0001", title="t", workstream="backend", deliverable_id="D-a",
        tier=WPTier.ONE, executor_persona="build-backend-sme", spec="s",
        spec_files=[], acceptance=["a"], depends_on=[], consult=[],
        state=WPState.DEFINED, created_by="build-dev-orchestrator",
        created_at="2026-05-25T10:00:00Z", history=[],
    )
    append_work_package(tmp_path, wp)
    assert next_wp_id(tmp_path) == "WP-0002"


# ---------------------------------------------------------------------------
# WP-0017: auto-mirror push hook
# ---------------------------------------------------------------------------

def _make_wp_mirror(wp_id: str = "WP-0001") -> WorkPackage:
    return WorkPackage(
        id=wp_id, title="t", workstream="backend", deliverable_id="D-a",
        tier=WPTier.ONE, executor_persona="build-backend-sme", spec="s",
        spec_files=[], acceptance=["a"], depends_on=[], consult=[],
        state=WPState.DEFINED, created_by="build-dev-orchestrator",
        created_at="2026-05-25T10:00:00Z", history=[],
    )


def _setup_github_config(
    tmp_path: Path,
    *,
    enabled: bool,
    auto_push: bool,
) -> None:
    """Init state tree + config with the given GitHub mirror settings."""
    init_state_tree(tmp_path)
    cfg = Config(
        ollama=OllamaConfig(models=OllamaModels()),
        project=ProjectConfig(),
        github=GitHubMirrorConfig(
            enabled=enabled,
            owner="test-owner",
            repo="test-repo",
            auto_push_on_state_change=auto_push,
        ),
    )
    save_config(tmp_path, cfg)
    append_work_package(tmp_path, _make_wp_mirror())


def test_github_mirror_config_auto_push_defaults_false():
    """Back-compat: GitHubMirrorConfig.auto_push_on_state_change defaults False."""
    cfg = GitHubMirrorConfig()
    assert cfg.auto_push_on_state_change is False


def test_update_wp_state_invokes_mirror_push_when_auto_push_enabled(tmp_path: Path):
    """When enabled=True and auto_push_on_state_change=True, push_all is called once."""
    _setup_github_config(tmp_path, enabled=True, auto_push=True)

    with patch("build_platform.github_mirror.push_all") as mock_push:
        mock_push.return_value = {}
        update_wp_state(tmp_path, "WP-0001", WPState.DISPATCHED,
                        by="test", event="pushed")

    mock_push.assert_called_once_with(tmp_path, dry_run=False)


def test_update_wp_state_does_not_invoke_mirror_push_when_disabled(tmp_path: Path):
    """Default config (auto_push=False): push_all must NOT be called."""
    _setup_github_config(tmp_path, enabled=True, auto_push=False)

    with patch("build_platform.github_mirror.push_all") as mock_push:
        update_wp_state(tmp_path, "WP-0001", WPState.DISPATCHED,
                        by="test", event="no push")

    mock_push.assert_not_called()


def test_update_wp_state_does_not_invoke_mirror_push_when_github_not_enabled(
    tmp_path: Path,
):
    """enabled=False, auto_push=True (defensive): push_all must NOT be called."""
    _setup_github_config(tmp_path, enabled=False, auto_push=True)

    with patch("build_platform.github_mirror.push_all") as mock_push:
        update_wp_state(tmp_path, "WP-0001", WPState.DISPATCHED,
                        by="test", event="no push")

    mock_push.assert_not_called()


def test_update_wp_state_swallows_mirror_push_exceptions(tmp_path: Path):
    """If push_all raises, update_wp_state must still return updated WP without raising."""
    _setup_github_config(tmp_path, enabled=True, auto_push=True)

    with patch("build_platform.github_mirror.push_all",
               side_effect=RuntimeError("network gone")):
        result = update_wp_state(tmp_path, "WP-0001", WPState.DISPATCHED,
                                 by="test", event="push explodes")

    # Must return the updated WP normally despite the mirror failure
    assert result.state == WPState.DISPATCHED
    # Confirm state was actually persisted
    loaded = load_wp_state(tmp_path)
    assert loaded["WP-0001"].state == WPState.DISPATCHED
