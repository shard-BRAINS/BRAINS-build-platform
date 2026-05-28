"""Tests for cli/dispatch_apply.py.

Uses real tmp_path git repos + real diffs (no subprocess mocks) so the
git apply --check / apply path is exercised honestly.
"""
import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from build_platform.audit import load_audit_index
from build_platform.cli.dispatch_apply import apply_cmd
from build_platform.cli.init import init_cmd
from build_platform.cli.package import package_cmd
from build_platform.paths import state_dir
from build_platform.schemas import WPState
from build_platform.state import load_wp_state, update_wp_state

# A diff that flips a one-liner from "old" to "new" — applies cleanly to the
# test fixture below.
GOOD_DIFF = """\
--- a/src/foo.py
+++ b/src/foo.py
@@ -1 +1 @@
-def hello(): return "old"
+def hello(): return "new"
"""

# Same shape but expects "different-old" at line 1 — will fail --check.
STALE_DIFF = """\
--- a/src/foo.py
+++ b/src/foo.py
@@ -1 +1 @@
-def hello(): return "different-old"
+def hello(): return "new"
"""


def _setup_project(tmp_path: Path, *, test_command: str = "") -> Path:
    """Init a build project + a real git repo with one source file + one queued WP."""
    runner = CliRunner()
    runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:T:why:accept",
        "--json",
    ])
    if test_command:
        # Override the default `pytest` test_command to something predictable.
        from build_platform.state import load_config, save_config
        cfg = load_config(tmp_path)
        cfg.project.test_command = test_command
        save_config(tmp_path, cfg)

    # Real git repo (so git apply works).
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "foo.py").write_text('def hello(): return "old"\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=tmp_path, check=True, capture_output=True)

    # Create a WP + put it in "dispatched" state with a proposed.diff.
    runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "Update hello()", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "1", "--executor", "build-backend-sme",
        "--spec", "...", "--file", "src/foo.py",
        "--accept", "returns new", "--json",
    ])
    return tmp_path


def _write_proposed(tmp_path: Path, wp_id: str, diff: str) -> Path:
    runs = state_dir(tmp_path) / "runs" / wp_id
    runs.mkdir(parents=True, exist_ok=True)
    p = runs / "proposed.diff"
    p.write_text(diff, encoding="utf-8")
    return p


def _set_dispatched(tmp_path: Path, wp_id: str) -> None:
    update_wp_state(tmp_path, wp_id, WPState.DISPATCHED,
                    by="build-dev-orchestrator", event="ready for apply (test setup)")


# ---------------------------------------------------------------------------

def test_apply_clean_diff_transitions_to_in_review(tmp_path: Path):
    _setup_project(tmp_path, test_command="")  # empty test_command -> skip tests
    _write_proposed(tmp_path, "WP-0001", GOOD_DIFF)
    _set_dispatched(tmp_path, "WP-0001")

    runner = CliRunner()
    r = runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0001", "--no-test", "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["tests"] == "skipped"
    # WP transitioned to in_review
    wps = load_wp_state(tmp_path)
    assert wps["WP-0001"].state == WPState.IN_REVIEW
    # File on disk is updated
    assert (tmp_path / "src" / "foo.py").read_text(encoding="utf-8").strip() == 'def hello(): return "new"'
    # Audit entry written
    audit_files = list((state_dir(tmp_path) / "audit").glob("WP-0001-*.md"))
    assert len(audit_files) == 1


def test_apply_failing_check_blocks_wp(tmp_path: Path):
    _setup_project(tmp_path)
    _write_proposed(tmp_path, "WP-0001", STALE_DIFF)  # will fail --check
    _set_dispatched(tmp_path, "WP-0001")

    runner = CliRunner()
    r = runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0001", "--no-test", "--json",
    ])
    assert r.exit_code == 3
    wps = load_wp_state(tmp_path)
    assert wps["WP-0001"].state == WPState.BLOCKED
    # Source file untouched
    assert (tmp_path / "src" / "foo.py").read_text(encoding="utf-8").strip() == 'def hello(): return "old"'


def test_apply_refuses_wrong_state(tmp_path: Path):
    _setup_project(tmp_path)
    _write_proposed(tmp_path, "WP-0001", GOOD_DIFF)
    # WP is still in 'defined' state, not 'dispatched'

    runner = CliRunner()
    r = runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0001", "--json",
    ])
    assert r.exit_code == 1
    assert "expected 'dispatched'" in r.output


def test_apply_refuses_when_no_diff(tmp_path: Path):
    _setup_project(tmp_path)
    _set_dispatched(tmp_path, "WP-0001")
    # No proposed.diff written

    runner = CliRunner()
    r = runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0001", "--json",
    ])
    assert r.exit_code == 1
    assert "No proposed diff" in r.output


def test_apply_failing_tests_blocks_wp(tmp_path: Path):
    # Configure a test_command that always fails (cross-platform: 'python -c "import sys; sys.exit(1)"')
    _setup_project(tmp_path, test_command='python -c "import sys; sys.exit(1)"')
    _write_proposed(tmp_path, "WP-0001", GOOD_DIFF)
    _set_dispatched(tmp_path, "WP-0001")

    runner = CliRunner()
    r = runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0001", "--json",
    ])
    assert r.exit_code == 4
    wps = load_wp_state(tmp_path)
    assert wps["WP-0001"].state == WPState.BLOCKED
    # Diff was applied first (it's only the tests that failed)
    assert (tmp_path / "src" / "foo.py").read_text(encoding="utf-8").strip() == 'def hello(): return "new"'


def test_apply_passing_tests_succeeds(tmp_path: Path):
    _setup_project(tmp_path, test_command='python -c "print(\'ok\')"')
    _write_proposed(tmp_path, "WP-0001", GOOD_DIFF)
    _set_dispatched(tmp_path, "WP-0001")

    runner = CliRunner()
    r = runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0001", "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["tests"] == "passed"
    wps = load_wp_state(tmp_path)
    assert wps["WP-0001"].state == WPState.IN_REVIEW


# ---------------------------------------------------------------------------
# Code-review verdict tests (WP-0008)
# ---------------------------------------------------------------------------

def test_apply_with_code_review_verdict_approve_records_verdict_in_audit_index(tmp_path: Path):
    """verdict='approve' goes through normal apply; audit/index.jsonl has both fields."""
    _setup_project(tmp_path, test_command="")
    _write_proposed(tmp_path, "WP-0001", GOOD_DIFF)
    _set_dispatched(tmp_path, "WP-0001")

    runner = CliRunner()
    r = runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0001", "--no-test",
        "--code-review-verdict", "approve",
        "--json",
    ])
    assert r.exit_code == 0, r.output
    wps = load_wp_state(tmp_path)
    assert wps["WP-0001"].state == WPState.IN_REVIEW

    rows = load_audit_index(tmp_path)
    assert rows, "audit index should have at least one entry"
    row = rows[-1]
    assert row["code_review_verdict"] == "approve"
    assert row["code_review_findings"] == []


def test_apply_with_code_review_verdict_reject_blocks_wp_and_does_not_apply(tmp_path: Path):
    """verdict='reject' with a 2-line findings file: WP blocked, diff NOT applied, exit 5."""
    _setup_project(tmp_path, test_command="")
    _write_proposed(tmp_path, "WP-0001", GOOD_DIFF)
    _set_dispatched(tmp_path, "WP-0001")

    findings_file = tmp_path / "findings.txt"
    findings_file.write_text("Finding one\nFinding two\n", encoding="utf-8")

    runner = CliRunner()
    r = runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0001", "--no-test",
        "--code-review-verdict", "reject",
        "--code-review-findings-file", str(findings_file),
        "--json",
    ])
    assert r.exit_code == 5, r.output

    # WP transitioned to blocked
    wps = load_wp_state(tmp_path)
    assert wps["WP-0001"].state == WPState.BLOCKED

    # Diff was NOT applied — source file still contains original content
    assert (tmp_path / "src" / "foo.py").read_text(encoding="utf-8").strip() == \
        'def hello(): return "old"', "diff must not be applied on reject"

    # Audit entry written with correct fields
    rows = load_audit_index(tmp_path)
    assert rows, "audit index should have at least one entry"
    row = rows[-1]
    assert row["result"] == "rejected_by_code_review"
    assert row["code_review_verdict"] == "reject"
    assert row["code_review_findings"] == ["Finding one", "Finding two"]


def test_apply_with_findings_file_populates_findings_list_in_audit(tmp_path: Path):
    """3-line findings file → audit row has code_review_findings of length 3."""
    _setup_project(tmp_path, test_command="")
    _write_proposed(tmp_path, "WP-0001", GOOD_DIFF)
    _set_dispatched(tmp_path, "WP-0001")

    findings_file = tmp_path / "findings.txt"
    findings_file.write_text("Alpha\nBeta\nGamma\n", encoding="utf-8")

    runner = CliRunner()
    r = runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0001", "--no-test",
        "--code-review-verdict", "approve",
        "--code-review-findings-file", str(findings_file),
        "--json",
    ])
    assert r.exit_code == 0, r.output

    rows = load_audit_index(tmp_path)
    row = rows[-1]
    assert len(row["code_review_findings"]) == 3


def test_apply_without_code_review_flags_preserves_existing_behavior(tmp_path: Path):
    """No code-review flags → identical to today's behavior."""
    _setup_project(tmp_path, test_command="")
    _write_proposed(tmp_path, "WP-0001", GOOD_DIFF)
    _set_dispatched(tmp_path, "WP-0001")

    runner = CliRunner()
    r = runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0001", "--no-test", "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["tests"] == "skipped"
    wps = load_wp_state(tmp_path)
    assert wps["WP-0001"].state == WPState.IN_REVIEW

    rows = load_audit_index(tmp_path)
    row = rows[-1]
    assert row["code_review_verdict"] is None
    assert row["code_review_findings"] == []


def test_apply_with_request_changes_delegates_to_dispatch_request_changes(tmp_path: Path):
    """verdict='request-changes' with a 2-line findings file: WP back to defined, exit 6,
    JSON has findings_count=2, code-review.md written."""
    _setup_project(tmp_path, test_command="")
    _write_proposed(tmp_path, "WP-0001", GOOD_DIFF)
    _set_dispatched(tmp_path, "WP-0001")

    findings_file = tmp_path / "findings.txt"
    findings_file.write_text("Finding alpha\nFinding beta\n", encoding="utf-8")

    runner = CliRunner()
    r = runner.invoke(apply_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0001",
        "--code-review-verdict", "request-changes",
        "--code-review-findings-file", str(findings_file),
        "--json",
    ])
    assert r.exit_code == 6, r.output

    # JSON payload emitted on stdout
    payload = json.loads(r.output)
    assert payload["findings_count"] == 2

    # WP returned to defined
    wps = load_wp_state(tmp_path)
    assert wps["WP-0001"].state == WPState.DEFINED

    # code-review.md written with findings file contents
    code_review_md = state_dir(tmp_path) / "runs" / "WP-0001" / "code-review.md"
    assert code_review_md.exists()
    assert "Finding alpha" in code_review_md.read_text(encoding="utf-8")
