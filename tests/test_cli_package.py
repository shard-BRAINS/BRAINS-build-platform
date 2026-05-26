"""Tests for cli/package.py."""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.init import init_cmd
from build_platform.cli.package import package_cmd


def _init(tmp_path: Path):
    runner = CliRunner()
    r = runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:T:why:accept",
        "--json",
    ])
    assert r.exit_code == 0, r.output


def _make(tmp_path: Path, title: str, *extra_args: str) -> dict:
    runner = CliRunner()
    r = runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", title, "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "2", "--executor", "build-backend-sme",
        "--spec", "do thing", "--file", "src/x.py",
        "--accept", "tests pass",
        *extra_args,
        "--json",
    ])
    return {"exit": r.exit_code, "output": r.output}


def test_package_creates_wp_with_no_deps(tmp_path: Path):
    _init(tmp_path)
    r = _make(tmp_path, "First WP")
    assert r["exit"] == 0
    assert json.loads(r["output"])["wp_id"] == "WP-0001"


def test_package_accepts_valid_dep(tmp_path: Path):
    _init(tmp_path)
    _make(tmp_path, "First WP")  # creates WP-0001
    r = _make(tmp_path, "Second WP", "--depends-on", "WP-0001")
    assert r["exit"] == 0
    assert json.loads(r["output"])["wp_id"] == "WP-0002"


def test_package_rejects_orphan_dep(tmp_path: Path):
    """Finding #1: --depends-on must reject IDs that don't exist in the log."""
    _init(tmp_path)
    r = _make(tmp_path, "Orphan WP", "--depends-on", "WP-9999")
    assert r["exit"] == 2
    payload = json.loads(r["output"])
    assert "Unknown WP IDs" in payload["error"]
    assert "WP-9999" in payload["error"]


def test_package_rejects_orphan_dep_with_some_valid(tmp_path: Path):
    _init(tmp_path)
    _make(tmp_path, "First WP")
    r = _make(tmp_path, "Mixed deps", "--depends-on", "WP-0001",
              "--depends-on", "WP-0099")
    assert r["exit"] == 2
    payload = json.loads(r["output"])
    assert "WP-0099" in payload["error"]
    # And WP-0001 should NOT appear in the error since it's valid
    assert "WP-0001" not in payload["error"]


def test_package_tier1_rejects_more_than_three_files(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    r = runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "Too wide", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "1", "--executor", "build-backend-sme",
        "--spec", "do thing",
        "--file", "a.py", "--file", "b.py", "--file", "c.py", "--file", "d.py",
        "--accept", "tests pass", "--json",
    ])
    assert r.exit_code == 2
    assert "<= 3 files" in r.output
