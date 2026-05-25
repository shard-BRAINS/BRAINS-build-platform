"""Tests for cli/init.py."""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.init import init_cmd


def test_init_refuses_when_already_initialized(tmp_path: Path):
    (tmp_path / ".brains-build").mkdir()
    runner = CliRunner()
    result = runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "x", "--mission", "y", "--stack", "python",
        "--constraint", "none", "--deliverable", "D-a:Title:why:acceptance",
        "--json",
    ])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"]


def test_init_creates_state_tree(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "Demonstrate the platform",
        "--stack", "python", "--stack", "react",
        "--constraint", "no GPL",
        "--deliverable", "D-auth:Authentication:users need to log in:login works",
        "--deliverable", "D-ui:Onboarding UI:users need an interface:page renders",
        "--json",
    ])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert (tmp_path / ".brains-build" / "project.yml").exists()
    assert (tmp_path / ".brains-build" / "deliverables.yml").exists()
    assert (tmp_path / ".brains-build" / "workstreams.yml").exists()
    assert (tmp_path / ".brains-build" / "config.yml").exists()
    assert (tmp_path / ".brains-build" / "work-packages.jsonl").exists()
    assert (tmp_path / ".brains-build" / "decisions.md").exists()
