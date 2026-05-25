"""Tests for cli/dispatch.py with Ollama mocked."""
import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from build_platform.cli.dispatch import dispatch_cmd
from build_platform.cli.init import init_cmd
from build_platform.cli.package import package_cmd


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


def test_dispatch_tier2_emits_brief(tmp_path: Path):
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
    assert Path(payload["brief"]).exists()


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
        instance.chat.return_value = diff
        result = runner.invoke(dispatch_cmd, ["--root", str(tmp_path), "--wp", "WP-0001", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tier"] == 1
    assert Path(payload["diff"]).exists()
