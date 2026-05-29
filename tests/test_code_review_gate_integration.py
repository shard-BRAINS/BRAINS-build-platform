"""Integration tests for the code-review gate end-to-end flow.

Exercises the full code-review-gate flow against a tmp project fixture.
Uses Click's CliRunner with real file I/O on tmp_path; no network calls.

Acceptance-criterion coverage map
──────────────────────────────────
D-code-review-gate AC-1: build-code-review-sme spawned automatically for every
    tier-2 dispatch before QA — out of scope for this test module (that is a
    Claude-session-level flow, not a CLI concern). Covered by skill-file prose;
    CLI integration is what the gate enforces.

D-code-review-gate AC-2: autonomy=review-on-complete and autonomy=auto tier-1
    WPs also trigger Code-Review SME — same caveat as AC-1; covered by skill
    prose, not CLI.

D-code-review-gate AC-3: dispatch_apply records the code-review verdict in the
    audit entry — covered by test_happy_path_approve_records_verdict_in_audit.

D-code-review-gate AC-4: request-changes verdict re-routes the WP to the
    executor with the findings — covered by
    test_request_changes_round_trip_via_apply and
    test_request_changes_loop_re_queues_wp.

Additional criterion: reject permanently gates the WP from the loop, but a
    later approve overrides the block — covered by
    test_reject_audit_row_blocks_loop and
    test_later_approve_overrides_reject_in_loop.
"""
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from build_platform.audit import load_audit_index
from build_platform.cli.dispatch import dispatch_cmd
from build_platform.cli.dispatch_apply import apply_cmd
from build_platform.cli.init import init_cmd
from build_platform.cli.loop import loop_cmd
from build_platform.cli.package import package_cmd
from build_platform.paths import state_dir
from build_platform.schemas import WPState
from build_platform.state import load_wp_state, update_wp_state

# ---------------------------------------------------------------------------
# Shared diff fixture — applies cleanly to the seeded src/foo.py below.
# ---------------------------------------------------------------------------
_DIFF = """\
--- a/src/foo.py
+++ b/src/foo.py
@@ -1 +1 @@
-def hello(): return "old"
+def hello(): return "new"
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_project(tmp_path: Path) -> None:
    """Init a BRAINS Build project at *tmp_path* (no git repo — tests use --no-test)."""
    runner = CliRunner()
    r = runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "GateTest", "--mission", "test code-review gate",
        "--stack", "python",
        "--deliverable", "D-gate:Gate:why:accept",
        "--json",
    ])
    assert r.exit_code == 0, r.output


def _init_project_with_git(tmp_path: Path) -> None:
    """Init a BRAINS Build project *and* a real git repo (needed for git apply)."""
    _init_project(tmp_path)
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "foo.py").write_text('def hello(): return "old"\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=tmp_path, check=True, capture_output=True)


def _add_wp(tmp_path: Path, tier: str = "1", autonomy: str = "auto") -> str:
    runner = CliRunner()
    r = runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "Update hello()", "--workstream", "backend",
        "--deliverable", "D-gate",
        "--tier", tier, "--executor", "build-backend-sme",
        "--spec", "change return value", "--file", "src/foo.py",
        "--accept", "returns new",
        "--autonomy", autonomy,
        "--json",
    ])
    assert r.exit_code == 0, r.output
    return json.loads(r.output)["wp_id"]


def _write_proposed_diff(tmp_path: Path, wp_id: str, diff: str = _DIFF) -> Path:
    runs = state_dir(tmp_path) / "runs" / wp_id
    runs.mkdir(parents=True, exist_ok=True)
    p = runs / "proposed.diff"
    p.write_text(diff, encoding="utf-8")
    return p


def _set_dispatched(tmp_path: Path, wp_id: str) -> None:
    update_wp_state(tmp_path, wp_id, WPState.DISPATCHED,
                    by="build-dev-orchestrator", event="setup (test)")


# ---------------------------------------------------------------------------
# Scenario 1 — Happy path: dispatch (mocked Ollama) → apply approve → in_review
# ---------------------------------------------------------------------------

def test_happy_path_approve_records_verdict_in_audit(tmp_path: Path) -> None:
    """AC-3: dispatch_apply records the code-review verdict in the audit entry.

    Flow: init → package (tier-1) → dispatch (mocked Ollama) → apply --approve.
    Assert: WP state=in_review; audit/index.jsonl row has code_review_verdict='approve'.
    """
    _init_project_with_git(tmp_path)
    wp_id = _add_wp(tmp_path)

    # Dispatch via mocked Ollama — same mock pattern as test_end_to_end.py.
    with patch("build_platform.cli.dispatch.OllamaClient") as MockClient:
        instance = MockClient.return_value
        instance.preflight.return_value = None
        instance.chat_with_metrics.return_value = (_DIFF, {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
        runner = CliRunner()
        r = runner.invoke(dispatch_cmd, [
            "--root", str(tmp_path), "--wp", wp_id, "--json",
        ])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["tier"] == 1

    # Apply with approve verdict (empty findings file).
    findings_file = tmp_path / "findings.txt"
    findings_file.write_text("", encoding="utf-8")

    runner = CliRunner()
    r = runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", wp_id, "--no-test",
        "--code-review-verdict", "approve",
        "--code-review-findings-file", str(findings_file),
        "--json",
    ])
    assert r.exit_code == 0, r.output

    # WP must be in_review.
    wps = load_wp_state(tmp_path)
    assert wps[wp_id].state == WPState.IN_REVIEW

    # Audit index row must have the verdict recorded.
    rows = load_audit_index(tmp_path)
    # Filter to rows from this WP (dispatch also writes a row).
    apply_rows = [row for row in rows if row.get("wp_id") == wp_id and row.get("result") == "applied"]
    assert apply_rows, f"No 'applied' audit row found; rows={rows}"
    assert apply_rows[-1]["code_review_verdict"] == "approve"


# ---------------------------------------------------------------------------
# Scenario 2 — Request-changes round-trip via apply_cmd
# ---------------------------------------------------------------------------

def test_request_changes_round_trip_via_apply(tmp_path: Path) -> None:
    """AC-4 (part 1): request-changes verdict re-routes WP to executor with findings.

    Flow: seed dispatched WP with proposed.diff → apply --request-changes with
    3-line findings file.
    Assert: exit 6; JSON findings_count=3; state=defined; code-review.md exists
    with verbatim content; proposed.diff is gone; audit row result='requested_changes'.
    """
    _init_project(tmp_path)
    wp_id = _add_wp(tmp_path)
    _write_proposed_diff(tmp_path, wp_id)
    _set_dispatched(tmp_path, wp_id)

    findings_file = tmp_path / "findings.txt"
    findings_file.write_text("Finding one\nFinding two\nFinding three\n", encoding="utf-8")

    runner = CliRunner()
    r = runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--code-review-verdict", "request-changes",
        "--code-review-findings-file", str(findings_file),
        "--json",
    ])

    # Exit code 6 signals request-changes.
    assert r.exit_code == 6, r.output

    # JSON payload has findings_count.
    payload = json.loads(r.output)
    assert payload["findings_count"] == 3

    # WP returned to defined.
    wps = load_wp_state(tmp_path)
    assert wps[wp_id].state == WPState.DEFINED

    # code-review.md written with verbatim findings content.
    review_md = state_dir(tmp_path) / "runs" / wp_id / "code-review.md"
    assert review_md.exists(), "code-review.md must be created"
    content = review_md.read_text(encoding="utf-8")
    assert "Finding one" in content
    assert "Finding two" in content
    assert "Finding three" in content

    # proposed.diff is gone.
    proposed_diff = state_dir(tmp_path) / "runs" / wp_id / "proposed.diff"
    assert not proposed_diff.exists(), "proposed.diff must be removed after request-changes"

    # Audit row recorded with result='requested_changes'.
    rows = load_audit_index(tmp_path)
    rc_rows = [row for row in rows if row.get("result") == "requested_changes" and row.get("wp_id") == wp_id]
    assert rc_rows, f"No requested_changes audit row found; rows={rows}"
    assert rc_rows[-1]["code_review_verdict"] == "request-changes"


def test_request_changes_loop_re_queues_wp(tmp_path: Path) -> None:
    """AC-4 (part 2): after request-changes the WP is eligible for re-dispatch.

    The loop only filters on 'reject'; request-changes returns the WP to
    state=defined, which makes it eligible again.
    Assert: after the round-trip, loop --dry-run --json includes the WP in its queue.
    """
    _init_project(tmp_path)
    wp_id = _add_wp(tmp_path)
    _write_proposed_diff(tmp_path, wp_id)
    _set_dispatched(tmp_path, wp_id)

    findings_file = tmp_path / "findings.txt"
    findings_file.write_text("Fix indentation\n", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--code-review-verdict", "request-changes",
        "--code-review-findings-file", str(findings_file),
        "--json",
    ])

    # WP is back to defined — loop must show it as eligible.
    r = runner.invoke(loop_cmd, ["--root", str(tmp_path), "--dry-run", "--json"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    ids = [item["id"] for item in payload["queue"]]
    assert wp_id in ids, f"{wp_id} should be re-queued after request-changes; queue={ids}"


# ---------------------------------------------------------------------------
# Scenario 3 — Reject blocks the loop; a later approve resurrects it
# ---------------------------------------------------------------------------

def test_reject_audit_row_blocks_loop(tmp_path: Path) -> None:
    """A WP with a reject audit row must not appear in the loop dry-run queue.

    Seeded directly (write the JSON row, don't go through the CLI) to isolate
    the loop filtering logic from other concerns.
    """
    _init_project(tmp_path)
    wp_rejected = _add_wp(tmp_path, autonomy="auto")
    wp_clean = _add_wp(tmp_path, autonomy="auto")

    # Write a reject audit row directly into audit/index.jsonl.
    audit_dir = state_dir(tmp_path) / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    index_path = audit_dir / "index.jsonl"
    reject_row = {
        "wp_id": wp_rejected,
        "timestamp": "2026-05-28T12:00:00+00:00",
        "code_review_verdict": "reject",
        "result": "rejected_by_code_review",
    }
    with index_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(reject_row) + "\n")

    runner = CliRunner()
    r = runner.invoke(loop_cmd, ["--root", str(tmp_path), "--dry-run", "--json"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    ids = [item["id"] for item in payload["queue"]]

    assert wp_rejected not in ids, f"{wp_rejected} must be excluded (reject on record); queue={ids}"
    assert wp_clean in ids, f"{wp_clean} must be included (no reject); queue={ids}"


def test_later_approve_overrides_reject_in_loop(tmp_path: Path) -> None:
    """If a later approve row exists for the same WP, the loop sees it again.

    Latest-by-timestamp wins — earlier reject must not veto a subsequent approve.
    """
    _init_project(tmp_path)
    wp_id = _add_wp(tmp_path, autonomy="auto")

    audit_dir = state_dir(tmp_path) / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    index_path = audit_dir / "index.jsonl"

    reject_row = {
        "wp_id": wp_id,
        "timestamp": "2026-05-28T10:00:00+00:00",
        "code_review_verdict": "reject",
        "result": "rejected_by_code_review",
    }
    approve_row = {
        "wp_id": wp_id,
        "timestamp": "2026-05-28T11:00:00+00:00",  # later timestamp
        "code_review_verdict": "approve",
        "result": "applied",
    }
    with index_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(reject_row) + "\n")
        fh.write(json.dumps(approve_row) + "\n")

    runner = CliRunner()
    r = runner.invoke(loop_cmd, ["--root", str(tmp_path), "--dry-run", "--json"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    ids = [item["id"] for item in payload["queue"]]

    assert wp_id in ids, (
        f"{wp_id} must be visible to the loop after later approve overrides earlier reject; queue={ids}"
    )
