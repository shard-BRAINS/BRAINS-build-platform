"""Tests for `python -m build_platform.cli.adopt`."""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.adopt import adopt_cmd


def _mk(root: Path, rel: str, content: str = "x") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_adopt_text_output_and_writes_artefacts(tmp_path: Path):
    _mk(tmp_path, "pyproject.toml")
    _mk(tmp_path, "src/app.py")
    _mk(tmp_path, "tests/test_app.py")

    result = CliRunner().invoke(adopt_cmd, ["--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "# Codebase survey" in result.output
    assert "Suggested workstreams" in result.output
    assert (tmp_path / ".brains-build" / "adopt" / "survey.json").exists()
    assert (tmp_path / ".brains-build" / "adopt" / "survey.md").exists()


def test_adopt_json_output(tmp_path: Path):
    _mk(tmp_path, "main.py")
    result = CliRunner().invoke(adopt_cmd, ["--root", str(tmp_path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["survey"]["file_count"] == 1
    assert payload["written"]["json"] == ".brains-build/adopt/survey.json"


def test_adopt_no_write_leaves_repo_untouched(tmp_path: Path):
    _mk(tmp_path, "main.py")
    result = CliRunner().invoke(adopt_cmd, ["--root", str(tmp_path), "--no-write"])
    assert result.exit_code == 0
    assert not (tmp_path / ".brains-build").exists()


def test_adopt_rejects_non_directory(tmp_path: Path):
    missing = tmp_path / "nope"
    result = CliRunner().invoke(adopt_cmd, ["--root", str(missing), "--json"])
    assert result.exit_code == 1
    assert "error" in json.loads(result.output)


def test_adopt_next_step_differs_when_already_initialised(tmp_path: Path):
    _mk(tmp_path, "main.py")
    fresh = CliRunner().invoke(adopt_cmd, ["--root", str(tmp_path), "--no-write"])
    assert "/build-init" in fresh.output

    _mk(tmp_path, ".brains-build/project.yml", "name: demo\n")
    existing = CliRunner().invoke(adopt_cmd, ["--root", str(tmp_path), "--no-write"])
    assert "deliverables.yml" in existing.output
    assert "/build-init" not in existing.output
