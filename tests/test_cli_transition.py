"""Tests for cli/transition.py."""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.init import init_cmd
from build_platform.cli.package import package_cmd
from build_platform.cli.transition import transition_cmd
from build_platform.paths import state_dir
from build_platform.schemas import WPState
from build_platform.audit import load_audit_index
from build_platform.state import load_wp_state


def _setup(tmp_path: Path) -> str:
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
        "--tier", "1", "--executor", "build-backend-sme",
        "--spec", "do stuff", "--file", "src/foo.py",
        "--accept", "tests pass", "--json",
    ])
    return json.loads(r.output)["wp_id"]


def test_transition_moves_wp_to_target_state(tmp_path: Path):
    wp_id = _setup(tmp_path)
    runner = CliRunner()
    r = runner.invoke(transition_cmd, [
        "--root", str(tmp_path),
        "--wp", wp_id,
        "--to", "done",
        "--by", "user:m",
        "--reason", "ok",
        "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["ok"] is True
    assert payload["new_state"] == "done"

    # WP state persisted
    wps = load_wp_state(tmp_path)
    assert wps[wp_id].state == WPState.DONE

    # History event appended with reason in event text
    history = wps[wp_id].history
    assert len(history) == 1
    assert "ok" in history[0].event

    # Audit row written
    index = load_audit_index(tmp_path)
    assert len(index) == 1
    assert index[0]["result"] == "transition_defined_to_done"
    assert index[0]["persona"] == "user:m"

    # Audit Markdown file has notes=reason
    audit_dir = state_dir(tmp_path) / "audit"
    md_files = list(audit_dir.glob(f"{wp_id}-*.md"))
    assert md_files, "No audit Markdown file found"
    audit_text = md_files[0].read_text(encoding="utf-8")
    assert "ok" in audit_text, "reason not found in audit Markdown notes"

    # Dashboard regenerated (file exists under dashboards/)
    assert any(True for _ in (state_dir(tmp_path) / "dashboards").iterdir())


def test_transition_to_same_state_rejected(tmp_path: Path):
    wp_id = _setup(tmp_path)
    runner = CliRunner()
    r = runner.invoke(transition_cmd, [
        "--root", str(tmp_path),
        "--wp", wp_id,
        "--to", "defined",   # WP starts in 'defined'
        "--by", "user:m",
        "--reason", "noop",
        "--json",
    ])
    assert r.exit_code != 0
    assert "same" in r.output.lower() or "already" in r.output.lower()


def test_transition_bad_target_rejected_by_click_choice(tmp_path: Path):
    wp_id = _setup(tmp_path)
    runner = CliRunner()
    r = runner.invoke(transition_cmd, [
        "--root", str(tmp_path),
        "--wp", wp_id,
        "--to", "not_a_real_state",
        "--by", "user:m",
        "--reason", "x",
    ])
    assert r.exit_code == 2


def test_transition_unknown_wp_exits_nonzero(tmp_path: Path):
    _setup(tmp_path)
    runner = CliRunner()
    r = runner.invoke(transition_cmd, [
        "--root", str(tmp_path),
        "--wp", "WP-9999",
        "--to", "done",
        "--by", "user:m",
        "--reason", "test",
        "--json",
    ])
    assert r.exit_code != 0
    assert "not found" in r.output.lower()


def test_transition_audit_persona_matches_by_arg(tmp_path: Path):
    wp_id = _setup(tmp_path)
    runner = CliRunner()
    r = runner.invoke(transition_cmd, [
        "--root", str(tmp_path),
        "--wp", wp_id,
        "--to", "blocked",
        "--by", "build-pmo-lead",
        "--reason", "stale",
        "--json",
    ])
    assert r.exit_code == 0, r.output
    index = load_audit_index(tmp_path)
    assert index[0]["persona"] == "build-pmo-lead"
