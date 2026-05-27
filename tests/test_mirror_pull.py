"""Integration test for the v2.6 mirror pull loop (WP-0005).

End-to-end exercise of the full two-way sync loop with `gh` fully mocked:

  1. Init a build project with 3 WPs.
  2. Configure the mirror; push so each WP gets a mapped issue number.
  3. Simulate three independent remote state changes:
       a. WP-A's issue is closed by someone on GitHub.
       b. WP-B's issue receives a `bbp:decision` comment.
       c. WP-C's issue is reopened after being locally DONE.
  4. Run `mirror pull` ONCE.
  5. Assert all three reconciliations happened in the single invocation:
       - WP-A transitioned defined -> done with by=github:<actor>.
       - decisions.md contains the new entry, mirror_map.seen_comments
         records the comment id.
       - WP-C transitioned done -> blocked.
  6. Run pull a second time with no new remote changes — must be a no-op
     (idempotent).
"""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform import github_mirror
from build_platform.cli.init import init_cmd
from build_platform.cli.mirror import mirror_group
from build_platform.cli.package import package_cmd
from build_platform.github_mirror import load_mirror_map
from build_platform.schemas import WPState
from build_platform.state import load_wp_state, update_wp_state


class _GhMock:
    """Same shape as the fixture in test_github_mirror.py, lifted here so the
    integration test stands alone and is easy to read top-to-bottom."""
    def __init__(self):
        self.calls: list[list[str]] = []
        self.next_issue_number = 100
        self.next_milestone_number = 1
        self.existing_labels: list[str] = []
        self.existing_milestones: list[dict] = []
        self.remote_issue_states: dict[int, dict] = {}
        self.remote_issue_comments: dict[int, list[dict]] = {}

    def __call__(self, args, *, input_=None):
        self.calls.append(args)
        if args[:2] == ["label", "list"]:
            return json.dumps([{"name": n} for n in self.existing_labels])
        if args[:2] == ["label", "create"]:
            self.existing_labels.append(args[2])
            return ""
        if args[:2] == ["issue", "create"]:
            n = self.next_issue_number
            self.next_issue_number += 1
            return f"https://github.com/owner/repo/issues/{n}\n"
        if args[:2] == ["issue", "edit"]:
            return ""
        if args[:2] == ["issue", "close"]:
            return ""
        if args[:2] == ["issue", "reopen"]:
            return ""
        if args[:2] == ["issue", "view"]:
            n = int(args[2])
            return json.dumps(self.remote_issue_states.get(n, {
                "state": "OPEN", "closedAt": None, "author": {"login": "github"}}))
        if args[0] == "api" and "/comments" in args[1]:
            n = int(args[1].split("/")[-2])
            return json.dumps(self.remote_issue_comments.get(n, []))
        if args[0] == "api" and args[1].endswith("/milestones") and "-f" not in args:
            return json.dumps(self.existing_milestones)
        if args[0] == "api" and args[1].endswith("/milestones"):
            n = self.next_milestone_number
            self.next_milestone_number += 1
            return json.dumps({"number": n})
        raise AssertionError(f"Unexpected gh call in integration test: {args}")


def _init_three_wps(tmp_path: Path) -> CliRunner:
    runner = CliRunner()
    runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Integration", "--mission", "test", "--stack", "python",
        "--deliverable", "D-a:T:why:accept",
        "--json",
    ])
    for title in ("WP A — closed remotely", "WP B — gets decision comment", "WP C — reopened"):
        runner.invoke(package_cmd, [
            "--root", str(tmp_path),
            "--title", title, "--workstream", "backend", "--deliverable", "D-a",
            "--tier", "2", "--executor", "build-backend-sme",
            "--spec", "x", "--file", "src/x.py",
            "--accept", "tests pass", "--json",
        ])
    return runner


def test_full_pull_loop_with_three_independent_remote_changes(tmp_path: Path, monkeypatch):
    gh = _GhMock()
    monkeypatch.setattr(github_mirror, "_run_gh", lambda args, **kw: gh(args, **kw))

    runner = _init_three_wps(tmp_path)
    # Mirror init + first push: maps WP-0001, WP-0002, WP-0003 to issues 100, 101, 102.
    runner.invoke(mirror_group, [
        "init", "--root", str(tmp_path),
        "--owner", "shard-BRAINS", "--repo", "demo", "--json",
    ])
    runner.invoke(mirror_group, ["push", "--root", str(tmp_path), "--json"])

    mm = load_mirror_map(tmp_path)
    assert mm.wps == {"WP-0001": 100, "WP-0002": 101, "WP-0003": 102}

    # Prep local state for WP-C: mark it DONE locally so the remote-reopen
    # case has something to transition out of.
    update_wp_state(tmp_path, "WP-0003", WPState.DONE,
                    by="test-setup", event="locally done before integration scenario")

    # Three independent remote changes:
    gh.remote_issue_states[100] = {  # WP-A closed
        "state": "CLOSED", "closedAt": "2026-05-27T11:00:00Z",
        "author": {"login": "alice"},
    }
    gh.remote_issue_states[101] = {  # WP-B still open (just got a comment)
        "state": "OPEN", "closedAt": None, "author": {"login": "carol"},
    }
    gh.remote_issue_comments[101] = [{
        "id": 9001,
        "author": {"login": "carol"},
        "body": (
            "bbp:decision\n"
            "title: Adopt FastAPI over Flask\n"
            "owner: build-product-owner\n"
            "decision: FastAPI for v2 backend\n"
            "why: async + Pydantic + OpenAPI for free\n"
            "alternatives: Flask:no async; Django:too heavy for v2\n"
            "related-wp: WP-0002\n"
        ),
        "created_at": "2026-05-27T11:30:00Z",
        "html_url": "https://github.com/shard-BRAINS/demo/issues/101#issuecomment-9001",
    }]
    gh.remote_issue_states[102] = {  # WP-C reopened
        "state": "OPEN", "closedAt": None, "author": {"login": "bob"},
    }

    # FIRST PULL — should reconcile all three.
    r = runner.invoke(mirror_group, ["pull", "--root", str(tmp_path), "--json"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)

    # Three state transitions named explicitly (preserving order doesn't matter).
    transitions = {(t["wp_id"], t["from"], t["to"])
                   for t in payload["transitions"] if "skipped" not in t}
    assert ("WP-0001", "defined", "done") in transitions
    assert ("WP-0003", "done", "blocked") in transitions

    # One decision ingested.
    assert len(payload["ingested_decisions"]) == 1
    assert payload["ingested_decisions"][0]["comment_id"] == 9001
    assert payload["ingested_decisions"][0]["from_wp"] == "WP-0002"

    # Verify local state on disk.
    wps = load_wp_state(tmp_path)
    assert wps["WP-0001"].state == WPState.DONE
    assert wps["WP-0001"].history[-1].by == "github:alice"
    assert wps["WP-0003"].state == WPState.BLOCKED
    assert wps["WP-0003"].history[-1].by == "github:bob"

    decisions = (tmp_path / ".brains-build" / "decisions.md").read_text(encoding="utf-8")
    assert "Adopt FastAPI over Flask" in decisions
    assert "FastAPI for v2 backend" in decisions
    assert "WP-0002" in decisions

    # seen_comments recorded for idempotency.
    mm = load_mirror_map(tmp_path)
    assert 9001 in mm.seen_comments.get("101", [])

    # SECOND PULL — no new remote changes. Must be a no-op.
    r2 = runner.invoke(mirror_group, ["pull", "--root", str(tmp_path), "--json"])
    payload2 = json.loads(r2.output)
    # Nothing transitioned (state already matches), nothing new ingested.
    assert all("skipped" in t or t.get("to") is None
               for t in payload2["transitions"]) or payload2["transitions"] == []
    assert payload2["ingested_decisions"] == []
    decisions_after_second = (tmp_path / ".brains-build" / "decisions.md").read_text(encoding="utf-8")
    assert decisions_after_second == decisions  # no append
