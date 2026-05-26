"""Tests for cli/dispatch_reject.py."""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.dispatch_reject import reject_cmd
from build_platform.cli.init import init_cmd
from build_platform.cli.package import package_cmd
from build_platform.paths import state_dir
from build_platform.schemas import WPState
from build_platform.state import load_wp_state, update_wp_state


def _setup(tmp_path: Path) -> str:
    runner = CliRunner()
    runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:T:why:accept", "--json",
    ])
    r = runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "thing", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "1", "--executor", "build-backend-sme",
        "--spec", "x", "--file", "src/foo.py",
        "--accept", "tests pass", "--json",
    ])
    wp_id = json.loads(r.output)["wp_id"]
    update_wp_state(tmp_path, wp_id, WPState.DISPATCHED,
                    by="build-dev-orchestrator", event="dispatched (test setup)")
    return wp_id


def test_reject_transitions_to_blocked(tmp_path: Path):
    wp_id = _setup(tmp_path)
    runner = CliRunner()
    r = runner.invoke(reject_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--reason", "out-of-scope changes to push_all", "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["new_state"] == "blocked"
    assert load_wp_state(tmp_path)[wp_id].state == WPState.BLOCKED


def test_reject_retier_transitions_to_defined(tmp_path: Path):
    wp_id = _setup(tmp_path)
    runner = CliRunner()
    r = runner.invoke(reject_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--reason", "needs human judgment; re-package as tier-2",
        "--retier", "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["new_state"] == "defined"
    assert load_wp_state(tmp_path)[wp_id].state == WPState.DEFINED


def test_reject_writes_audit_entry(tmp_path: Path):
    wp_id = _setup(tmp_path)
    runner = CliRunner()
    runner.invoke(reject_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--reason", "bad diff", "--json",
    ])
    audits = list((state_dir(tmp_path) / "audit").glob(f"{wp_id}-*.md"))
    assert len(audits) == 1
    content = audits[0].read_text(encoding="utf-8")
    assert "Result:** rejected" in content
    assert "bad diff" in content


def test_reject_refuses_wrong_state(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:T:why:accept", "--json",
    ])
    r = runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "thing", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "1", "--executor", "build-backend-sme",
        "--spec", "x", "--file", "src/foo.py",
        "--accept", "tests pass", "--json",
    ])
    wp_id = json.loads(r.output)["wp_id"]
    # WP is still in 'defined' state — reject should refuse

    r = runner.invoke(reject_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--reason", "test", "--json",
    ])
    assert r.exit_code == 1
    assert "expected 'dispatched'" in r.output


def test_reject_refuses_unknown_wp(tmp_path: Path):
    _setup(tmp_path)
    runner = CliRunner()
    r = runner.invoke(reject_cmd, [
        "--root", str(tmp_path), "--wp", "WP-9999",
        "--reason", "test", "--json",
    ])
    assert r.exit_code == 1
    assert "not found" in r.output
