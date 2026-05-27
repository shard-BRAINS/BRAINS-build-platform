"""Tests for cli/triage.py."""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.init import init_cmd
from build_platform.cli.package import package_cmd
from build_platform.cli.triage import triage_cmd


def _init(tmp_path: Path):
    runner = CliRunner()
    r = runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:T:why:accept",
        "--json",
    ])
    assert r.exit_code == 0, r.output


def test_triage_ad_hoc_tier_1():
    """Ad-hoc mode (no --wp): run on inline spec/files/accept."""
    runner = CliRunner()
    r = runner.invoke(triage_cmd, [
        "--root", ".",  # cwd; ad-hoc mode doesn't load WPs
        "--spec", "Rename helper function.",
        "--file", "src/utils.py",
        "--accept", "tests pass",
        "--json",
    ])
    # We pass cwd as root but no WP is required — should succeed
    # In ad-hoc mode the WP load is skipped; project_root is only used for
    # file-size measurement (and missing files are treated as new = 0 bytes).
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["suggested_tier"] == 1
    assert payload["wp_id"] is None


def test_triage_ad_hoc_tier_2():
    runner = CliRunner()
    r = runner.invoke(triage_cmd, [
        "--root", ".",
        "--spec", "Decide which auth approach to use.",
        "--file", "src/auth.py",
        "--accept", "tests pass",
        "--json",
    ])
    assert r.exit_code == 0
    payload = json.loads(r.output)
    assert payload["suggested_tier"] == 2


def test_triage_by_wp_id(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "Rename get_cwd", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "1", "--executor", "build-backend-sme",
        "--spec", "Rename get_cwd to get_current_working_directory across utils.",
        "--file", "src/utils.py",
        "--accept", "tests pass", "--accept", "lint passes",
        "--json",
    ])
    r = runner.invoke(triage_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0001", "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["wp_id"] == "WP-0001"
    assert payload["suggested_tier"] == 1
    assert payload["current_tier"] == 1
    assert payload["matches_current_tier"] is True


def test_triage_flags_mismatch_with_current_tier(tmp_path: Path):
    """WP was created as tier-1 but a fresh triage thinks it should be tier-2."""
    _init(tmp_path)
    runner = CliRunner()
    # Create a WP with tier=1 but a spec that triage would reject
    runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "Implement login", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "1", "--executor", "build-backend-sme",
        "--spec", "Decide between bcrypt and Argon2; implement chosen approach.",
        "--file", "src/auth.py",
        "--accept", "tests pass",
        "--json",
    ])
    r = runner.invoke(triage_cmd, [
        "--root", str(tmp_path), "--wp", "WP-0001", "--json",
    ])
    payload = json.loads(r.output)
    assert payload["suggested_tier"] == 2
    assert payload["current_tier"] == 1
    assert payload["matches_current_tier"] is False


def test_triage_refuses_unknown_wp(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    r = runner.invoke(triage_cmd, [
        "--root", str(tmp_path), "--wp", "WP-9999", "--json",
    ])
    assert r.exit_code == 1
    assert "not found" in r.output


def test_triage_refuses_when_no_inputs(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    r = runner.invoke(triage_cmd, [
        "--root", str(tmp_path), "--json",
    ])
    assert r.exit_code == 1
    assert "--wp or --spec is required" in r.output


def test_triage_human_output_includes_marks(tmp_path: Path):
    """Non-JSON output renders criteria with ✓/✗ marks for quick scanning."""
    runner = CliRunner()
    r = runner.invoke(triage_cmd, [
        "--root", ".",
        "--spec", "Decide complex thing.",
        "--file", "a.py",
        "--accept", "code is nice",
    ])
    assert r.exit_code == 0
    assert "Suggested tier: 2" in r.output
    assert "✗" in r.output  # at least one failing criterion
