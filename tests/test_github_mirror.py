"""Tests for github_mirror.py and cli/mirror.py.

All `gh` subprocess calls are mocked — these tests never hit the network.
"""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from build_platform import github_mirror
from build_platform.cli.init import init_cmd
from build_platform.cli.mirror import mirror_group
from build_platform.cli.package import package_cmd
from build_platform.github_mirror import (
    MirrorError,
    MirrorMap,
    _wp_body,
    _wp_labels,
    load_mirror_map,
    save_mirror_map,
)
from build_platform.schemas import (
    GitHubMirrorConfig,
    WorkPackage,
    WPState,
    WPTier,
)
from build_platform.state import load_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_project(tmp_path: Path):
    runner = CliRunner()
    r = runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:Title:Why:accept",
        "--json",
    ])
    assert r.exit_code == 0, r.output


def _add_wp(tmp_path: Path, title: str, tier: str = "2",
            executor: str = "build-backend-sme"):
    runner = CliRunner()
    r = runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", title, "--workstream", "backend", "--deliverable", "D-a",
        "--tier", tier, "--executor", executor,
        "--spec", "do thing", "--file", "src/x.py",
        "--accept", "tests pass", "--json",
    ])
    assert r.exit_code == 0, r.output
    return json.loads(r.output)["wp_id"]


class GhRecorder:
    """Records every gh invocation. Returns canned responses per arg signature."""
    def __init__(self):
        self.calls: list[list[str]] = []
        self.next_issue_number = 100
        self.next_milestone_number = 1
        self.existing_labels: list[str] = []
        self.existing_milestones: list[dict] = []

    def __call__(self, args: list[str], *, input_: str | None = None) -> str:
        self.calls.append(args)
        if args[:2] == ["label", "list"]:
            return json.dumps([{"name": n} for n in self.existing_labels])
        if args[:2] == ["label", "create"]:
            self.existing_labels.append(args[2])
            return ""
        if args[:2] == ["issue", "create"]:
            num = self.next_issue_number
            self.next_issue_number += 1
            return f"https://github.com/owner/repo/issues/{num}\n"
        if args[:2] == ["issue", "edit"]:
            return ""
        if args[:2] == ["issue", "close"]:
            return ""
        if args[:2] == ["issue", "reopen"]:
            return ""
        if args[0] == "api" and args[1].endswith("/milestones") and "-f" not in args:
            return json.dumps(self.existing_milestones)
        if args[0] == "api" and args[1].endswith("/milestones"):
            num = self.next_milestone_number
            self.next_milestone_number += 1
            title = next((args[i + 1] for i, a in enumerate(args)
                          if a == "-f" and args[i + 1].startswith("title=")), "title=Untitled")
            self.existing_milestones.append({"number": num, "title": title.split("=", 1)[1]})
            return json.dumps({"number": num})
        raise AssertionError(f"Unexpected gh call: {args}")


@pytest.fixture
def mock_gh(monkeypatch):
    recorder = GhRecorder()
    monkeypatch.setattr(github_mirror, "_run_gh",
                        lambda args, **kw: recorder(args, **kw))
    return recorder


# ---------------------------------------------------------------------------
# Unit tests: body + labels
# ---------------------------------------------------------------------------

def _make_wp(**overrides) -> WorkPackage:
    base = dict(
        id="WP-0001", title="t", workstream="backend", deliverable_id="D-a",
        tier=WPTier.TWO, executor_persona="build-backend-sme",
        spec="implement thing", spec_files=["src/x.py"], acceptance=["tests pass"],
        depends_on=[], consult=[], state=WPState.DEFINED,
        created_by="build-dev-orchestrator", created_at="2026-05-25T10:00:00Z",
        history=[],
    )
    base.update(overrides)
    return WorkPackage(**base)


def test_wp_labels_include_all_dimensions():
    wp = _make_wp()
    labels = _wp_labels("bbp:", wp)
    assert "bbp:state-defined" in labels
    assert "bbp:tier-2" in labels
    assert "bbp:workstream-backend" in labels
    assert "bbp:deliverable-D-a" in labels
    assert "bbp:persona-build-backend-sme" in labels


def test_wp_body_contains_managed_marker_and_sections():
    wp = _make_wp()
    body = _wp_body(wp)
    assert "managed by BRAINS Build Platform" in body
    assert "## Spec" in body
    assert "## Acceptance criteria" in body
    assert "## Files in scope" in body
    assert "## History" in body
    assert "implement thing" in body


# ---------------------------------------------------------------------------
# Mirror map persistence
# ---------------------------------------------------------------------------

def test_mirror_map_round_trip(tmp_path: Path):
    _init_project(tmp_path)
    mm = MirrorMap(wps={"WP-0001": 42}, sprints={"sprint-01": 3}, labels_seeded=True)
    save_mirror_map(tmp_path, mm)
    loaded = load_mirror_map(tmp_path)
    assert loaded.wps == {"WP-0001": 42}
    assert loaded.sprints == {"sprint-01": 3}
    assert loaded.labels_seeded is True


def test_load_mirror_map_default_when_missing(tmp_path: Path):
    _init_project(tmp_path)
    mm = load_mirror_map(tmp_path)
    assert mm.wps == {}
    assert mm.labels_seeded is False


# ---------------------------------------------------------------------------
# CLI: init
# ---------------------------------------------------------------------------

def test_mirror_init_writes_config(tmp_path: Path):
    _init_project(tmp_path)
    runner = CliRunner()
    r = runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo-proj", "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["enabled"] is True
    cfg = load_config(tmp_path)
    assert cfg.github.enabled is True
    assert cfg.github.owner == "shard-BRAINS"
    assert cfg.github.repo == "demo-proj"


def test_mirror_init_disable(tmp_path: Path):
    _init_project(tmp_path)
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "x", "--repo", "y", "--json",
    ])
    r = runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "x", "--repo", "y", "--disable", "--json",
    ])
    assert r.exit_code == 0
    assert json.loads(r.output)["enabled"] is False


# ---------------------------------------------------------------------------
# CLI: push (with gh mocked)
# ---------------------------------------------------------------------------

def test_mirror_push_creates_issues_and_records_map(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    _add_wp(tmp_path, "Task two")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    r = runner.invoke(mirror_group, [
        "push", "--root", str(tmp_path), "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["wps_pushed"] == 2
    mm = load_mirror_map(tmp_path)
    assert mm.wps == {"WP-0001": 100, "WP-0002": 101}
    assert mm.labels_seeded is True
    # Cross-check that gh issue create was called twice
    create_calls = [c for c in mock_gh.calls if c[:2] == ["issue", "create"]]
    assert len(create_calls) == 2


def test_mirror_push_is_idempotent_on_existing_wp(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    mock_gh.calls.clear()
    r = runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    assert r.exit_code == 0, r.output
    # Second push should use issue edit, not issue create
    edit_calls = [c for c in mock_gh.calls if c[:2] == ["issue", "edit"]]
    create_calls = [c for c in mock_gh.calls if c[:2] == ["issue", "create"]]
    assert len(edit_calls) == 1
    assert len(create_calls) == 0


def test_mirror_push_refuses_when_not_enabled(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    # Do NOT run mirror init
    runner = CliRunner()
    r = runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    assert r.exit_code == 2
    assert "disabled" in r.output.lower()


def test_mirror_push_sets_last_synced_at(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    cfg = load_config(tmp_path)
    assert cfg.github.last_synced_at is not None


# ---------------------------------------------------------------------------
# CLI: status
# ---------------------------------------------------------------------------

def test_mirror_status_reports_config_and_map(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    r = runner.invoke(mirror_group, ["status", "--root", str(tmp_path), "--json"])
    assert r.exit_code == 0
    payload = json.loads(r.output)
    assert payload["enabled"] is True
    assert payload["wps_mirrored"] == 1
    assert payload["labels_seeded"] is True


def test_mirror_status_when_disabled(tmp_path: Path):
    _init_project(tmp_path)
    runner = CliRunner()
    r = runner.invoke(mirror_group, ["status", "--root", str(tmp_path), "--json"])
    assert r.exit_code == 0
    payload = json.loads(r.output)
    assert payload["enabled"] is False
    assert payload["wps_mirrored"] == 0
