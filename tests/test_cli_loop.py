"""Tests for cli/loop.py."""
import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from build_platform.cli.init import init_cmd
from build_platform.cli.loop import loop_cmd
from build_platform.cli.package import package_cmd
from build_platform.schemas import Autonomy, WPState, WPTier, WorkPackage
from build_platform.state import (
    append_work_package,
    init_state_tree,
    load_wp_state,
)


def _full_init(tmp_path: Path) -> None:
    runner = CliRunner()
    r = runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "LoopTest", "--mission", "test loop",
        "--stack", "python",
        "--deliverable", "D-core:Core:why:tests pass",
        "--json",
    ])
    assert r.exit_code == 0, r.output


def _add_wp(tmp_path: Path, title: str, tier: str = "1",
            autonomy: str = "auto", depends_on: list[str] | None = None) -> str:
    runner = CliRunner()
    args = [
        "--root", str(tmp_path),
        "--title", title, "--workstream", "backend", "--deliverable", "D-core",
        "--tier", tier, "--executor", "build-backend-sme",
        "--spec", "do thing", "--file", "src/x.py",
        "--accept", "tests pass",
        "--autonomy", autonomy,
        "--json",
    ]
    for dep in (depends_on or []):
        args += ["--depends-on", dep]
    r = runner.invoke(package_cmd, args)
    assert r.exit_code == 0, r.output
    return json.loads(r.output)["wp_id"]


def test_loop_dry_run_lists_eligible_auto_tier1_wps(tmp_path: Path):
    _full_init(tmp_path)
    wp1 = _add_wp(tmp_path, "Auto job 1")
    wp2 = _add_wp(tmp_path, "Manual job", autonomy="manual")
    wp3 = _add_wp(tmp_path, "Auto job 2")

    runner = CliRunner()
    r = runner.invoke(loop_cmd, ["--root", str(tmp_path), "--dry-run", "--json"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    ids = [item["id"] for item in payload["queue"]]
    assert wp1 in ids
    assert wp3 in ids
    assert wp2 not in ids


def test_loop_skips_wps_with_unmet_deps(tmp_path: Path):
    _full_init(tmp_path)
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "x.py").write_text("old\n", encoding="utf-8")
    wp1 = _add_wp(tmp_path, "First job")
    wp2 = _add_wp(tmp_path, "Dependent job", depends_on=[wp1])

    runner = CliRunner()
    r = runner.invoke(loop_cmd, ["--root", str(tmp_path), "--dry-run", "--json"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    ids = [item["id"] for item in payload["queue"]]
    # wp2 depends on wp1 (not DONE) — should not be in queue
    assert wp2 not in ids


def test_loop_skips_non_auto_wps(tmp_path: Path):
    _full_init(tmp_path)
    wp_manual = _add_wp(tmp_path, "Manual job", autonomy="manual")
    wp_review = _add_wp(tmp_path, "Review job", autonomy="review-on-complete")

    runner = CliRunner()
    r = runner.invoke(loop_cmd, ["--root", str(tmp_path), "--dry-run", "--json"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    ids = [item["id"] for item in payload["queue"]]
    assert wp_manual not in ids
    assert wp_review not in ids


def test_loop_skips_tier2_wps_even_if_marked_auto(tmp_path: Path):
    """Defensive: loop must filter tier-2 WPs regardless of autonomy field."""
    _full_init(tmp_path)
    init_state_tree(tmp_path)
    append_work_package(tmp_path, WorkPackage(
        id="WP-0001", title="Sneaky T2 auto", workstream="backend",
        deliverable_id="D-core", tier=WPTier.TWO,
        executor_persona="build-backend-sme", spec="s",
        spec_files=["src/x.py"], acceptance=["ok"], depends_on=[], consult=[],
        state=WPState.DEFINED, created_by="user",
        created_at="2026-05-25T10:00:00Z", history=[],
        autonomy=Autonomy.AUTO,
    ))
    runner = CliRunner()
    r = runner.invoke(loop_cmd, ["--root", str(tmp_path), "--dry-run", "--json"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert len(payload["queue"]) == 0


def test_loop_stops_on_first_failure(tmp_path: Path):
    """If dispatch fails (Ollama returns bad diff), loop stops and reports WP."""
    _full_init(tmp_path)
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "x.py").write_text("old\n", encoding="utf-8")
    wp1 = _add_wp(tmp_path, "Failing job")
    wp2 = _add_wp(tmp_path, "Should not run")

    runner = CliRunner()
    with patch("build_platform.cli.dispatch.OllamaClient") as MockClient:
        instance = MockClient.return_value
        instance.preflight.return_value = None
        # Return garbage — dispatcher will fail to produce a valid diff
        instance.chat.return_value = "not a diff"
        r = runner.invoke(loop_cmd, ["--root", str(tmp_path), "--json"])

    # loop exits with non-zero and/or reports stopped_at in JSON
    output = r.output.strip()
    if output:
        payload = json.loads(output)
        assert payload.get("stopped_at") == wp1
    else:
        # exception path — loop still must not have dispatched wp2
        assert r.exit_code != 0

    # wp2 must NOT have been dispatched
    wps = load_wp_state(tmp_path)
    assert wps[wp2].state == WPState.DEFINED
