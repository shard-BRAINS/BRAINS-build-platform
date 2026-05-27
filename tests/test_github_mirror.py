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
    _blocker_banner,
    _issue_title,
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
from build_platform.state import load_config, load_wp_state, update_wp_state


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
        # v2.6 pull-side response stubs, keyed by issue number
        self.remote_issue_states: dict[int, dict] = {}  # {num: {state, closedAt, author}}
        self.remote_issue_comments: dict[int, list[dict]] = {}  # {num: [comment...]}

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
        if args[:2] == ["issue", "view"]:
            num = int(args[2])
            state = self.remote_issue_states.get(num, {"state": "OPEN", "closedAt": None, "author": {"login": "github"}})
            return json.dumps(state)
        if args[0] == "api" and "/comments" in args[1]:
            # /comments endpoint: extract issue number from path
            path = args[1]
            try:
                num = int(path.split("/")[-2])
            except (IndexError, ValueError):
                num = 0
            return json.dumps(self.remote_issue_comments.get(num, []))
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


def test_issue_title_no_prefix_when_not_blocked():
    """Finding #6: title has no [BLOCKED] prefix for non-blocked states."""
    for state in (WPState.DEFINED, WPState.DISPATCHED, WPState.IN_REVIEW, WPState.DONE):
        wp = _make_wp(state=state)
        title = _issue_title(wp)
        assert title == f"[{wp.id}] {wp.title}"
        assert "[BLOCKED]" not in title


def test_issue_title_has_blocked_prefix_when_blocked():
    """Finding #6: blocked WPs get a [BLOCKED] prefix in the issue title."""
    wp = _make_wp(state=WPState.BLOCKED)
    title = _issue_title(wp)
    assert title.startswith("[BLOCKED] ")


def test_blocker_banner_empty_when_not_blocked():
    for state in (WPState.DEFINED, WPState.DISPATCHED, WPState.IN_REVIEW, WPState.DONE):
        assert _blocker_banner(_make_wp(state=state)) == ""


def test_blocker_banner_present_when_blocked():
    """Finding #6: body has a prominent banner when blocked."""
    from build_platform.schemas import WPHistoryEvent
    wp = _make_wp(state=WPState.BLOCKED, history=[
        WPHistoryEvent(at="2026-05-27T10:00:00Z", by="build-dev-orchestrator",
                       event="rejected: out-of-scope changes")
    ])
    banner = _blocker_banner(wp)
    assert "BLOCKED" in banner
    assert "rejected: out-of-scope changes" in banner
    assert "/build-decision" in banner


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


def test_mirror_map_seen_comments_default_empty(tmp_path: Path):
    """WP-0001: seen_comments defaults to {} for fresh maps and existing maps without it."""
    _init_project(tmp_path)
    mm = MirrorMap()
    assert mm.seen_comments == {}
    # Persist + reload — pydantic should accept the missing-key case
    save_mirror_map(tmp_path, mm)
    assert load_mirror_map(tmp_path).seen_comments == {}


def test_mirror_map_seen_comments_round_trip(tmp_path: Path):
    """WP-0001: seen_comments persists round-trip with the right shape."""
    _init_project(tmp_path)
    mm = MirrorMap(
        wps={"WP-0001": 1},
        seen_comments={"1": [101, 102], "2": [201]},
    )
    save_mirror_map(tmp_path, mm)
    loaded = load_mirror_map(tmp_path)
    assert loaded.seen_comments == {"1": [101, 102], "2": [201]}


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


# ---------------------------------------------------------------------------
# Finding #5 — dry-run preview
# ---------------------------------------------------------------------------

def test_mirror_dry_run_does_not_create_issues(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    _add_wp(tmp_path, "Task two")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    r = runner.invoke(mirror_group, [
        "push", "--dry-run", "--root", str(tmp_path), "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["dry_run"] is True
    # No issue create/edit/close calls in dry-run mode
    state_changing = [c for c in mock_gh.calls
                      if c[:2] in (["issue", "create"], ["issue", "edit"],
                                   ["issue", "close"], ["issue", "reopen"],
                                   ["label", "create"])]
    assert state_changing == []


def test_mirror_dry_run_reports_planned_actions(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    _add_wp(tmp_path, "Task two")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    r = runner.invoke(mirror_group, [
        "push", "--dry-run", "--root", str(tmp_path), "--json",
    ])
    payload = json.loads(r.output)
    assert payload["counts"]["wps_to_create"] == 2
    assert payload["counts"]["wps_to_edit"] == 0
    assert payload["counts"]["labels_to_create"] > 0
    # WP plan entries name each WP with action=create
    wp_ids = {w["wp_id"] for w in payload["wps"]}
    assert wp_ids == {"WP-0001", "WP-0002"}
    assert all(w["action"] == "create" for w in payload["wps"])


def test_mirror_dry_run_after_real_push_shows_edit_actions(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    # Add a 2nd WP after the first push — dry-run should show 1 create + 1 edit.
    _add_wp(tmp_path, "Task two")
    r = runner.invoke(mirror_group, [
        "push", "--dry-run", "--root", str(tmp_path), "--json",
    ])
    payload = json.loads(r.output)
    assert payload["counts"]["wps_to_create"] == 1
    assert payload["counts"]["wps_to_edit"] == 1


def test_mirror_dry_run_refuses_when_disabled(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    # No init — mirror disabled
    runner = CliRunner()
    r = runner.invoke(mirror_group, [
        "push", "--dry-run", "--root", str(tmp_path), "--json",
    ])
    assert r.exit_code == 2
    assert "disabled" in r.output.lower()


# ===========================================================================
# v2.6 — Two-way mirror sync (PULL)
# ===========================================================================

# WP-0002: pull skeleton

def test_mirror_pull_refuses_when_disabled(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    runner = CliRunner()
    r = runner.invoke(mirror_group, ["pull", "--root", str(tmp_path), "--json"])
    assert r.exit_code == 2
    assert "disabled" in r.output.lower()


def test_mirror_pull_no_op_when_no_mapped_wps(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    r = runner.invoke(mirror_group, ["pull", "--root", str(tmp_path), "--json"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["remote_states"] == []
    assert payload["transitions"] == []
    assert payload["ingested_decisions"] == []


def test_mirror_pull_fetches_remote_states_for_mapped_wps(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    # Now WP-0001 is mapped to issue 100. Set remote state on it.
    mock_gh.remote_issue_states[100] = {
        "state": "OPEN", "closedAt": None, "author": {"login": "alice"},
    }
    r = runner.invoke(mirror_group, ["pull", "--root", str(tmp_path), "--json"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert len(payload["remote_states"]) == 1
    assert payload["remote_states"][0]["wp_id"] == "WP-0001"
    assert payload["remote_states"][0]["issue"] == 100


# WP-0003: state reconciliation

def test_pull_closed_remote_transitions_defined_wp_to_done(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    mock_gh.remote_issue_states[100] = {
        "state": "CLOSED", "closedAt": "2026-05-27T10:00:00Z",
        "author": {"login": "alice"},
    }
    r = runner.invoke(mirror_group, ["pull", "--root", str(tmp_path), "--json"])
    payload = json.loads(r.output)
    assert {"wp_id": "WP-0001", "from": "defined", "to": "done"} in payload["transitions"]
    wps = load_wp_state(tmp_path)
    assert wps["WP-0001"].state == WPState.DONE
    # History event records the github actor
    assert "github:alice" in wps["WP-0001"].history[-1].by


def test_pull_closed_remote_no_op_when_local_already_done(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    update_wp_state(tmp_path, "WP-0001", WPState.DONE,
                    by="test-setup", event="manual to DONE")
    mock_gh.remote_issue_states[100] = {
        "state": "CLOSED", "closedAt": "2026-05-27T10:00:00Z",
        "author": {"login": "alice"},
    }
    r = runner.invoke(mirror_group, ["pull", "--root", str(tmp_path), "--json"])
    payload = json.loads(r.output)
    assert payload["transitions"] == []


def test_pull_closed_remote_preserves_local_blocked(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    update_wp_state(tmp_path, "WP-0001", WPState.BLOCKED,
                    by="test-setup", event="blocked locally")
    mock_gh.remote_issue_states[100] = {
        "state": "CLOSED", "closedAt": None, "author": {"login": "alice"},
    }
    r = runner.invoke(mirror_group, ["pull", "--root", str(tmp_path), "--json"])
    payload = json.loads(r.output)
    # Skip flagged in transitions, but local state preserved
    assert any(t.get("skipped") for t in payload["transitions"])
    assert load_wp_state(tmp_path)["WP-0001"].state == WPState.BLOCKED


def test_pull_open_remote_transitions_done_wp_to_blocked(tmp_path: Path, mock_gh):
    """Someone reopened a done issue on GitHub — surface as blocked for review."""
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    update_wp_state(tmp_path, "WP-0001", WPState.DONE,
                    by="test-setup", event="locally done")
    mock_gh.remote_issue_states[100] = {
        "state": "OPEN", "closedAt": None, "author": {"login": "bob"},
    }
    r = runner.invoke(mirror_group, ["pull", "--root", str(tmp_path), "--json"])
    payload = json.loads(r.output)
    assert {"wp_id": "WP-0001", "from": "done", "to": "blocked"} in payload["transitions"]
    assert load_wp_state(tmp_path)["WP-0001"].state == WPState.BLOCKED


# WP-0004: bbp:decision comment ingestion

def test_parse_bbp_decision_comment_happy_path():
    body = (
        "bbp:decision\n"
        "title: Use Argon2 for password hashing\n"
        "owner: build-security-sme\n"
        "decision: Argon2id with t=3, m=64MB, p=4\n"
        "why: OWASP 2024 recommendation; prior bcrypt flagged\n"
        "alternatives: bcrypt:weaker, legacy; scrypt:less library support\n"
        "related-wp: WP-0041, WP-0042\n"
    )
    from build_platform.github_mirror import parse_bbp_decision_comment
    parsed = parse_bbp_decision_comment(body)
    assert parsed is not None
    assert parsed["title"] == "Use Argon2 for password hashing"
    assert parsed["owner"] == "build-security-sme"
    assert "Argon2id" in parsed["decision"]
    assert parsed["related_wps"] == ["WP-0041", "WP-0042"]


def test_parse_bbp_decision_comment_returns_none_for_non_decision():
    from build_platform.github_mirror import parse_bbp_decision_comment
    assert parse_bbp_decision_comment("just a regular comment") is None
    assert parse_bbp_decision_comment("") is None


def test_parse_bbp_decision_comment_requires_title_and_decision():
    from build_platform.github_mirror import parse_bbp_decision_comment
    # Missing decision
    assert parse_bbp_decision_comment("bbp:decision\ntitle: X\nwhy: Y") is None
    # Missing title
    assert parse_bbp_decision_comment("bbp:decision\ndecision: X\nwhy: Y") is None


def test_pull_ingests_decision_comment_into_decisions_md(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    mock_gh.remote_issue_states[100] = {
        "state": "OPEN", "closedAt": None, "author": {"login": "alice"},
    }
    mock_gh.remote_issue_comments[100] = [{
        "id": 5001,
        "author": {"login": "alice"},
        "body": (
            "bbp:decision\n"
            "title: Use Argon2 for password hashing\n"
            "owner: build-security-sme\n"
            "decision: Argon2id with t=3, m=64MB, p=4\n"
            "why: OWASP 2024 recommendation\n"
            "related-wp: WP-0001\n"
        ),
        "created_at": "2026-05-27T10:30:00Z",
        "html_url": "https://github.com/x/y/issues/100#issuecomment-5001",
    }]
    r = runner.invoke(mirror_group, ["pull", "--root", str(tmp_path), "--json"])
    payload = json.loads(r.output)
    assert len(payload["ingested_decisions"]) == 1
    assert payload["ingested_decisions"][0]["comment_id"] == 5001
    decisions = (tmp_path / ".brains-build" / "decisions.md").read_text(encoding="utf-8")
    assert "Use Argon2 for password hashing" in decisions
    assert "Argon2id" in decisions


def test_pull_decision_ingestion_is_idempotent(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    mock_gh.remote_issue_states[100] = {
        "state": "OPEN", "closedAt": None, "author": {"login": "alice"},
    }
    mock_gh.remote_issue_comments[100] = [{
        "id": 5001, "author": {"login": "alice"},
        "body": "bbp:decision\ntitle: T\ndecision: D\nwhy: W",
        "created_at": "2026-05-27T10:30:00Z",
        "html_url": "https://example/comment",
    }]
    runner.invoke(mirror_group, ["pull", "--root", str(tmp_path), "--json"])
    decisions_after_first = (tmp_path / ".brains-build" / "decisions.md").read_text(encoding="utf-8")
    r2 = runner.invoke(mirror_group, ["pull", "--root", str(tmp_path), "--json"])
    payload2 = json.loads(r2.output)
    assert payload2["ingested_decisions"] == []
    decisions_after_second = (tmp_path / ".brains-build" / "decisions.md").read_text(encoding="utf-8")
    assert decisions_after_first == decisions_after_second
    # seen_comments contains the comment id
    mm = load_mirror_map(tmp_path)
    assert 5001 in mm.seen_comments.get("100", [])


def test_pull_ignores_non_decision_comments(tmp_path: Path, mock_gh):
    _init_project(tmp_path)
    _add_wp(tmp_path, "Task one")
    runner = CliRunner()
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])
    mock_gh.remote_issue_states[100] = {
        "state": "OPEN", "closedAt": None, "author": {"login": "alice"},
    }
    mock_gh.remote_issue_comments[100] = [
        {"id": 1, "author": {"login": "x"}, "body": "Looks good!", "created_at": "2026-05-27T10:00:00Z", "html_url": ""},
        {"id": 2, "author": {"login": "x"}, "body": "lgtm 👍", "created_at": "2026-05-27T11:00:00Z", "html_url": ""},
    ]
    r = runner.invoke(mirror_group, ["pull", "--root", str(tmp_path), "--json"])
    payload = json.loads(r.output)
    assert payload["ingested_decisions"] == []
