"""Tests for cli/dispatch.py with Ollama mocked."""
import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from build_platform.audit import load_audit_index
from build_platform.cli.dispatch import dispatch_cmd
from build_platform.cli.init import init_cmd
from build_platform.cli.package import package_cmd
from build_platform.dispatcher import DispatchError


def _init_project(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:T:why:accept",
        "--json",
    ])
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "foo.py").write_text('def hello(): return "old"\n', encoding="utf-8")


def test_dispatch_tier2_emits_brief(tmp_path: Path, monkeypatch):
    # Make the persona-install check find the file so no warning is emitted.
    fake_home = tmp_path / "home"
    agents = fake_home / ".claude" / "agents" / "build"
    agents.mkdir(parents=True)
    (agents / "build-backend-sme.md").write_text("stub", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    _init_project(tmp_path)
    runner = CliRunner()
    runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "WP2 task", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "2", "--executor", "build-backend-sme",
        "--spec", "Implement hello new", "--file", "src/foo.py",
        "--accept", "returns new", "--json",
    ])
    result = runner.invoke(dispatch_cmd, ["--root", str(tmp_path), "--wp", "WP-0001", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tier"] == 2
    assert payload["warnings"] == []  # persona installed -> no warning
    assert Path(payload["brief"]).exists()


def test_dispatch_tier2_warns_when_persona_not_installed(tmp_path: Path, monkeypatch):
    """Finding #9: tier-2 dispatch surfaces a warning when the persona's
    subagent file isn't installed at ~/.claude/agents/build/."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()  # but DON'T create the persona file
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    _init_project(tmp_path)
    runner = CliRunner()
    runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "WP", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "2", "--executor", "build-backend-sme",
        "--spec", "x", "--file", "src/foo.py",
        "--accept", "tests pass", "--json",
    ])
    result = runner.invoke(dispatch_cmd, ["--root", str(tmp_path), "--wp", "WP-0001", "--json"])
    assert result.exit_code == 0, result.output  # warning, not fatal
    payload = json.loads(result.output)
    assert len(payload["warnings"]) == 1
    assert "build-backend-sme.md" in payload["warnings"][0]
    assert "install.ps1" in payload["warnings"][0]


def test_dispatch_tier1_calls_ollama(tmp_path: Path):
    _init_project(tmp_path)
    runner = CliRunner()
    runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "WP1 task", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "1", "--executor", "build-backend-sme",
        "--spec", "Replace old with new", "--file", "src/foo.py",
        "--accept", "returns new", "--json",
    ])
    diff = (
        "--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1,1 +1,1 @@\n"
        '-def hello(): return "old"\n+def hello(): return "new"\n'
    )
    with patch("build_platform.cli.dispatch.OllamaClient") as MockClient:
        instance = MockClient.return_value
        instance.preflight.return_value = None
        instance.chat_with_metrics.return_value = (diff, {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
        result = runner.invoke(dispatch_cmd, ["--root", str(tmp_path), "--wp", "WP-0001", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tier"] == 1
    assert Path(payload["diff"]).exists()


# ---------------------------------------------------------------------------
# WP-0014: suggested_action surfaces in JSON payload on capability-gap failure
# ---------------------------------------------------------------------------

def _setup_tier1_wp(tmp_path: Path):
    _init_project(tmp_path)
    runner = CliRunner()
    runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "WP1 task", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "1", "--executor", "build-backend-sme",
        "--spec", "Replace old with new", "--file", "src/foo.py",
        "--accept", "returns new", "--json",
    ])
    return runner


def test_dispatch_tier1_json_includes_suggested_action_on_retier(tmp_path: Path):
    """When dispatcher raises DispatchError with suggested_action='retier-to-2',
    cli/dispatch --json payload must include suggested_action and exit code 3."""
    runner = _setup_tier1_wp(tmp_path)

    err = DispatchError("Tier-1 dispatch failed twice.")
    err.suggested_action = "retier-to-2"  # type: ignore[attr-defined]

    with patch("build_platform.cli.dispatch.OllamaClient") as MockClient:
        instance = MockClient.return_value
        instance.preflight.return_value = None
        with patch("build_platform.cli.dispatch.dispatch_tier1", side_effect=err):
            result = runner.invoke(dispatch_cmd, ["--root", str(tmp_path), "--wp", "WP-0001", "--json"])

    assert result.exit_code == 3
    payload = json.loads(result.output)
    assert payload.get("suggested_action") == "retier-to-2"


def test_dispatch_tier1_human_output_includes_retier_hint(tmp_path: Path):
    """Human output must include a hint line when suggested_action is set."""
    runner = _setup_tier1_wp(tmp_path)

    err = DispatchError("Tier-1 dispatch failed twice.")
    err.suggested_action = "retier-to-2"  # type: ignore[attr-defined]

    with patch("build_platform.cli.dispatch.OllamaClient") as MockClient:
        instance = MockClient.return_value
        instance.preflight.return_value = None
        with patch("build_platform.cli.dispatch.dispatch_tier1", side_effect=err):
            result = runner.invoke(dispatch_cmd, ["--root", str(tmp_path), "--wp", "WP-0001"])

    assert result.exit_code == 3
    assert "re-tier" in result.output.lower() or "retier" in result.output.lower() or "Suggested next step" in result.output


# ---------------------------------------------------------------------------
# WP-0015: audit row includes token counts
# ---------------------------------------------------------------------------

def test_cli_dispatch_audit_row_includes_token_counts(tmp_path: Path):
    """Full path: mock Ollama with non-zero token counts -> audit/index.jsonl row
    has tokens_in > 0 and tokens_out > 0."""
    runner = _setup_tier1_wp(tmp_path)

    diff = (
        "--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1,1 +1,1 @@\n"
        '-def hello(): return "old"\n+def hello(): return "new"\n'
    )
    with patch("build_platform.cli.dispatch.OllamaClient") as MockClient:
        instance = MockClient.return_value
        instance.preflight.return_value = None
        instance.chat_with_metrics.return_value = (
            diff, {"tokens_in": 250, "tokens_out": 80, "cost_usd": 0.0}
        )
        result = runner.invoke(dispatch_cmd, ["--root", str(tmp_path), "--wp", "WP-0001", "--json"])

    assert result.exit_code == 0, result.output
    rows = load_audit_index(tmp_path)
    assert len(rows) == 1
    assert rows[0]["tokens_in"] == 250
    assert rows[0]["tokens_out"] == 80
    assert rows[0]["cost_usd"] == 0.0
