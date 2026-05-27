"""Tests for cli/package_edit.py."""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.init import init_cmd
from build_platform.cli.package import package_cmd
from build_platform.cli.package_edit import edit_cmd
from build_platform.paths import state_dir
from build_platform.state import load_wp_state


def _init_and_make_wp(tmp_path: Path) -> str:
    runner = CliRunner()
    runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:T:why:accept",
        "--deliverable", "D-b:Other:why:accept",
        "--json",
    ])
    r = runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "Original", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "2", "--executor", "build-backend-sme",
        "--spec", "do thing", "--file", "src/x.py",
        "--accept", "tests pass", "--json",
    ])
    return json.loads(r.output)["wp_id"]


def test_edit_changes_title(tmp_path: Path):
    wp_id = _init_and_make_wp(tmp_path)
    runner = CliRunner()
    r = runner.invoke(edit_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--title", "Renamed", "--json",
    ])
    assert r.exit_code == 0, r.output
    wps = load_wp_state(tmp_path)
    assert wps[wp_id].title == "Renamed"
    # History event appended
    last = wps[wp_id].history[-1]
    assert "title" in last.event
    assert "Renamed" in last.event


def test_edit_changes_deliverable(tmp_path: Path):
    wp_id = _init_and_make_wp(tmp_path)
    runner = CliRunner()
    r = runner.invoke(edit_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--deliverable", "D-b", "--json",
    ])
    assert r.exit_code == 0, r.output
    assert load_wp_state(tmp_path)[wp_id].deliverable_id == "D-b"


def test_edit_changes_tier(tmp_path: Path):
    wp_id = _init_and_make_wp(tmp_path)
    runner = CliRunner()
    r = runner.invoke(edit_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--tier", "1", "--json",
    ])
    assert r.exit_code == 0, r.output
    assert load_wp_state(tmp_path)[wp_id].tier.value == 1


def test_edit_adds_and_removes_files(tmp_path: Path):
    wp_id = _init_and_make_wp(tmp_path)
    runner = CliRunner()
    r = runner.invoke(edit_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--add-file", "src/y.py", "--remove-file", "src/x.py", "--json",
    ])
    assert r.exit_code == 0, r.output
    wps = load_wp_state(tmp_path)
    assert wps[wp_id].spec_files == ["src/y.py"]


def test_edit_tier1_rejects_more_than_3_files_after_edit(tmp_path: Path):
    wp_id = _init_and_make_wp(tmp_path)
    runner = CliRunner()
    runner.invoke(edit_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--tier", "1", "--json",
    ])
    # Try adding 3 more files (would make 4 total)
    r = runner.invoke(edit_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--add-file", "a.py", "--add-file", "b.py", "--add-file", "c.py",
        "--json",
    ])
    assert r.exit_code == 2
    assert "Tier-1 WP must touch" in r.output


def test_edit_rejects_orphan_dep(tmp_path: Path):
    wp_id = _init_and_make_wp(tmp_path)
    runner = CliRunner()
    r = runner.invoke(edit_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--add-dep", "WP-9999", "--json",
    ])
    assert r.exit_code == 2
    assert "Unknown WP IDs" in r.output


def test_edit_accepts_valid_dep(tmp_path: Path):
    _init_and_make_wp(tmp_path)  # WP-0001
    runner = CliRunner()
    runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "Second", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "2", "--executor", "build-backend-sme",
        "--spec", "x", "--file", "src/y.py",
        "--accept", "tests pass", "--json",
    ])  # WP-0002
    r = runner.invoke(edit_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0002",
        "--add-dep", "WP-0001", "--json",
    ])
    assert r.exit_code == 0, r.output
    assert load_wp_state(tmp_path)["WP-0002"].depends_on == ["WP-0001"]


def test_edit_refuses_no_changes(tmp_path: Path):
    wp_id = _init_and_make_wp(tmp_path)
    runner = CliRunner()
    r = runner.invoke(edit_cmd, [
        "--root", str(tmp_path), "--wp", wp_id, "--json",
    ])
    assert r.exit_code == 1
    assert "No editable changes" in r.output


def test_edit_refuses_unknown_wp(tmp_path: Path):
    _init_and_make_wp(tmp_path)
    runner = CliRunner()
    r = runner.invoke(edit_cmd, [
        "--root", str(tmp_path), "--wp", "WP-9999",
        "--title", "x", "--json",
    ])
    assert r.exit_code == 1
    assert "not found" in r.output


def test_edit_writes_audit_entry(tmp_path: Path):
    wp_id = _init_and_make_wp(tmp_path)
    runner = CliRunner()
    runner.invoke(edit_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--title", "Renamed", "--json",
    ])
    audits = list((state_dir(tmp_path) / "audit").glob(f"{wp_id}-*.md"))
    assert len(audits) == 1
    content = audits[0].read_text(encoding="utf-8")
    assert "Result:** edited" in content
    assert "Renamed" in content


def test_package_edit_can_change_autonomy(tmp_path: Path):
    from build_platform.schemas import Autonomy
    wp_id = _init_and_make_wp(tmp_path)
    runner = CliRunner()
    r = runner.invoke(edit_cmd, [
        "--root", str(tmp_path), "--wp", wp_id,
        "--autonomy", "review-on-complete", "--json",
    ])
    assert r.exit_code == 0, r.output
    assert load_wp_state(tmp_path)[wp_id].autonomy == Autonomy.REVIEW_ON_COMPLETE
