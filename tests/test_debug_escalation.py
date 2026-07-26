"""Tests for the failure counter and Debug SME escalation.

The rule: two failed execution attempts mean the problem is not the one being
solved, so the WP goes to the Debug SME rather than to a third identical attempt.
These tests pin down what counts as a failure, what does not, and that dispatch
actually refuses once the threshold is reached.
"""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.dispatch import dispatch_cmd
from build_platform.cli.dispatch_reject import reject_cmd
from build_platform.cli.dispatch_request_changes import request_changes_cmd
from build_platform.cli.init import init_cmd
from build_platform.cli.package import package_cmd
from build_platform.cli.status import status_cmd
from build_platform.cli.transition import transition_cmd
from build_platform.schemas import WorkPackage, WPState
from build_platform.state import load_wp_state, update_wp_state


def _setup(tmp_path: Path, executor: str = "build-backend-sme") -> str:
    """Init project, create one WP, return its id."""
    runner = CliRunner()
    runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:Title:why:accept", "--json",
    ])
    r = runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "thing", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "1", "--executor", executor,
        "--spec", "do stuff", "--file", "src/foo.py",
        "--accept", "tests pass", "--json",
    ])
    return json.loads(r.output)["wp_id"]


def _fail(tmp_path: Path, wp_id: str, times: int) -> None:
    """Record N failed attempts directly, without a real dispatch."""
    for i in range(times):
        state = WPState.BLOCKED if i % 2 == 0 else WPState.DEFINED
        update_wp_state(tmp_path, wp_id, state,
                        by="build-backend-sme", event=f"attempt {i} failed",
                        failure=True)


# --- the counter itself ---


def test_failures_defaults_to_zero_on_records_written_before_the_field(tmp_path: Path):
    """WPs serialized before `failures` existed must still validate."""
    legacy = json.dumps({
        "id": "WP-0001", "title": "t", "workstream": "backend",
        "deliverable_id": "D-a", "tier": 1, "executor_persona": "build-backend-sme",
        "spec": "s", "acceptance": ["a"], "state": "defined",
        "created_by": "user:m", "created_at": "2026-01-01T00:00:00+00:00",
    })
    wp = WorkPackage.model_validate_json(legacy)
    assert wp.failures == 0
    assert wp.needs_debug_escalation() is False


def test_ordinary_transition_does_not_increment_failures(tmp_path: Path):
    wp_id = _setup(tmp_path)
    update_wp_state(tmp_path, wp_id, WPState.DISPATCHED,
                    by="build-dev-orchestrator", event="dispatched")
    assert load_wp_state(tmp_path)[wp_id].failures == 0


def test_failure_transition_increments(tmp_path: Path):
    wp_id = _setup(tmp_path)
    _fail(tmp_path, wp_id, 1)
    assert load_wp_state(tmp_path)[wp_id].failures == 1


# --- what escalates ---


def test_escalation_triggers_at_two_failures(tmp_path: Path):
    wp_id = _setup(tmp_path)
    _fail(tmp_path, wp_id, 1)
    assert load_wp_state(tmp_path)[wp_id].needs_debug_escalation() is False
    _fail(tmp_path, wp_id, 1)
    assert load_wp_state(tmp_path)[wp_id].needs_debug_escalation() is True


def test_debug_sme_does_not_escalate_to_itself(tmp_path: Path):
    wp_id = _setup(tmp_path, executor="build-debug-sme")
    _fail(tmp_path, wp_id, 3)
    wp = load_wp_state(tmp_path)[wp_id]
    assert wp.failures == 3
    assert wp.needs_debug_escalation() is False


# --- the CLI paths that record failures ---


def test_reject_counts_as_a_failure(tmp_path: Path):
    wp_id = _setup(tmp_path)
    update_wp_state(tmp_path, wp_id, WPState.DISPATCHED,
                    by="build-dev-orchestrator", event="dispatched")
    r = CliRunner().invoke(reject_cmd, [
        "--root", str(tmp_path), "--wp", wp_id, "--reason", "wrong file", "--json",
    ])
    assert r.exit_code == 0, r.output
    assert load_wp_state(tmp_path)[wp_id].failures == 1


def test_retier_is_not_a_failure(tmp_path: Path):
    """--retier re-classifies the WP; the attempt itself was sound."""
    wp_id = _setup(tmp_path)
    update_wp_state(tmp_path, wp_id, WPState.DISPATCHED,
                    by="build-dev-orchestrator", event="dispatched")
    r = CliRunner().invoke(reject_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--reason", "needs judgement", "--retier", "--json",
    ])
    assert r.exit_code == 0, r.output
    assert load_wp_state(tmp_path)[wp_id].failures == 0


def test_request_changes_counts_as_a_failure(tmp_path: Path):
    wp_id = _setup(tmp_path)
    update_wp_state(tmp_path, wp_id, WPState.DISPATCHED,
                    by="build-dev-orchestrator", event="dispatched")
    findings = tmp_path / "findings.txt"
    findings.write_text("naming is inconsistent\n", encoding="utf-8")
    r = CliRunner().invoke(request_changes_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--findings-file", str(findings), "--json",
    ])
    assert r.exit_code == 0, r.output
    assert load_wp_state(tmp_path)[wp_id].failures == 1


def test_transition_failure_flag_increments_and_reports_escalation(tmp_path: Path):
    """QA failures reach the counter through --failure on transition."""
    wp_id = _setup(tmp_path)
    _fail(tmp_path, wp_id, 1)
    # QA fails a WP that reached review, so put it there first.
    update_wp_state(tmp_path, wp_id, WPState.IN_REVIEW,
                    by="build-dev-orchestrator", event="awaiting QA")
    r = CliRunner().invoke(transition_cmd, [
        "--root", str(tmp_path), "--wp", wp_id, "--to", "blocked",
        "--by", "build-qa-sme", "--reason", "acceptance 2 not met",
        "--failure", "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["failures"] == 2
    assert "build-debug-sme" in payload["escalation"]


def test_transition_without_failure_flag_does_not_count(tmp_path: Path):
    wp_id = _setup(tmp_path)
    r = CliRunner().invoke(transition_cmd, [
        "--root", str(tmp_path), "--wp", wp_id, "--to", "done",
        "--by", "user:m", "--reason", "fine", "--json",
    ])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["failures"] == 0
    assert "escalation" not in json.loads(r.output)


# --- enforcement ---


def test_dispatch_refuses_a_third_attempt(tmp_path: Path):
    wp_id = _setup(tmp_path)
    _fail(tmp_path, wp_id, 2)
    # Back to defined so the only thing standing in the way is the escalation.
    update_wp_state(tmp_path, wp_id, WPState.DEFINED, by="user:m", event="reopened")
    r = CliRunner().invoke(dispatch_cmd, [
        "--root", str(tmp_path), "--wp", wp_id, "--json",
    ])
    assert r.exit_code == 7, r.output
    assert "build-debug-sme" in r.output


def test_force_bypasses_escalation(tmp_path: Path):
    """--force must get past the gate; it may still fail later for other reasons."""
    wp_id = _setup(tmp_path)
    _fail(tmp_path, wp_id, 2)
    update_wp_state(tmp_path, wp_id, WPState.DEFINED, by="user:m", event="reopened")
    r = CliRunner().invoke(dispatch_cmd, [
        "--root", str(tmp_path), "--wp", wp_id, "--force", "--json",
    ])
    assert r.exit_code != 7
    assert "build-debug-sme" not in r.output


def test_status_surfaces_the_escalation(tmp_path: Path):
    wp_id = _setup(tmp_path)
    _fail(tmp_path, wp_id, 2)
    r = CliRunner().invoke(status_cmd, [
        "--root", str(tmp_path), "--wp", wp_id, "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["failures"] == 2
    assert "build-debug-sme" in payload["escalation"]
