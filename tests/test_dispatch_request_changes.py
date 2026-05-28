"""Tests for cli/dispatch_request_changes.py."""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.audit import load_audit_index
from build_platform.cli.dispatch_request_changes import request_changes_cmd
from build_platform.cli.init import init_cmd
from build_platform.cli.package import package_cmd
from build_platform.paths import state_dir
from build_platform.schemas import WPState
from build_platform.state import load_wp_state, update_wp_state


def _setup(tmp_path: Path, state: WPState = WPState.DISPATCHED) -> str:
    runner = CliRunner()
    runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:T:why:accept", "--json",
    ])
    r = runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "thing", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "2", "--executor", "build-backend-sme",
        "--spec", "x", "--file", "src/foo.py",
        "--accept", "tests pass", "--json",
    ])
    wp_id = json.loads(r.output)["wp_id"]
    update_wp_state(tmp_path, wp_id, state,
                    by="build-dev-orchestrator", event="setup (test)")
    return wp_id


def _findings_file(tmp_path: Path, lines: list[str]) -> Path:
    p = tmp_path / "findings.txt"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_request_changes_resets_diff_and_returns_to_defined(tmp_path: Path):
    wp_id = _setup(tmp_path, WPState.DISPATCHED)
    # Plant a proposed.diff
    run_dir = state_dir(tmp_path) / "runs" / wp_id
    run_dir.mkdir(parents=True, exist_ok=True)
    diff_file = run_dir / "proposed.diff"
    diff_file.write_text("--- a/foo.py\n+++ b/foo.py\n", encoding="utf-8")

    findings_path = _findings_file(tmp_path, ["Line too long", "Missing test"])
    runner = CliRunner()
    r = runner.invoke(request_changes_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--findings-file", str(findings_path), "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["ok"] is True
    assert payload["new_state"] == "defined"

    # WP state is defined
    assert load_wp_state(tmp_path)[wp_id].state == WPState.DEFINED

    # code-review.md written with verbatim content
    review_file = run_dir / "code-review.md"
    assert review_file.exists()
    assert "Line too long" in review_file.read_text(encoding="utf-8")
    assert "Missing test" in review_file.read_text(encoding="utf-8")

    # proposed.diff removed
    assert not diff_file.exists()

    # audit index has a row
    rows = load_audit_index(tmp_path)
    assert any(r["result"] == "requested_changes" for r in rows)


def test_request_changes_audit_records_findings_list(tmp_path: Path):
    wp_id = _setup(tmp_path, WPState.DISPATCHED)
    findings_path = _findings_file(tmp_path, ["Finding A", "Finding B", "Finding C"])
    runner = CliRunner()
    r = runner.invoke(request_changes_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--findings-file", str(findings_path), "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["findings_count"] == 3

    rows = load_audit_index(tmp_path)
    row = next(r for r in rows if r["result"] == "requested_changes")
    assert len(row["code_review_findings"]) == 3
    assert row["code_review_verdict"] == "request-changes"


def test_request_changes_missing_findings_file_exits_nonzero(tmp_path: Path):
    wp_id = _setup(tmp_path, WPState.DISPATCHED)
    runner = CliRunner()
    r = runner.invoke(request_changes_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--findings-file", str(tmp_path / "nonexistent.txt"), "--json",
    ])
    assert r.exit_code != 0


def test_request_changes_rejects_done_wp(tmp_path: Path):
    wp_id = _setup(tmp_path, WPState.DONE)
    findings_path = _findings_file(tmp_path, ["Something wrong"])
    runner = CliRunner()
    r = runner.invoke(request_changes_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--findings-file", str(findings_path), "--json",
    ])
    assert r.exit_code == 1
    # State unchanged
    assert load_wp_state(tmp_path)[wp_id].state == WPState.DONE


def test_request_changes_accepts_in_review_state(tmp_path: Path):
    wp_id = _setup(tmp_path, WPState.IN_REVIEW)
    findings_path = _findings_file(tmp_path, ["Fix the indentation"])
    runner = CliRunner()
    r = runner.invoke(request_changes_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--findings-file", str(findings_path), "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["new_state"] == "defined"
    assert load_wp_state(tmp_path)[wp_id].state == WPState.DEFINED
