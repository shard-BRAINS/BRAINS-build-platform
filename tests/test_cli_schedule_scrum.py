"""Tests for cli/schedule_scrum.py."""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.init import init_cmd
from build_platform.cli.schedule_scrum import schedule_scrum_cmd
from build_platform.state import load_config


def _init(tmp_path: Path):
    runner = CliRunner()
    r = runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:T:why:accept",
        "--json",
    ])
    assert r.exit_code == 0, r.output


def test_schedule_scrum_defaults_to_monday_9am(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    r = runner.invoke(schedule_scrum_cmd, [
        "--root", str(tmp_path), "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["ok"] is True
    assert payload["cron"] == "0 9 * * 1"  # Mon 9:00 UTC
    assert payload["enabled"] is True
    assert payload["project"] == "Demo"
    assert "BRAINS scrum reminder" in payload["routine_prompt"]


def test_schedule_scrum_custom_day_and_time(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    r = runner.invoke(schedule_scrum_cmd, [
        "--root", str(tmp_path),
        "--day", "fri", "--hour", "16", "--minute", "30",
        "--timezone", "Europe/London", "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["cron"] == "30 16 * * 5"
    assert payload["timezone"] == "Europe/London"


def test_schedule_scrum_persists_to_config(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    runner.invoke(schedule_scrum_cmd, [
        "--root", str(tmp_path), "--day", "wed", "--hour", "10", "--json",
    ])
    config = load_config(tmp_path)
    assert config.scrum_schedule.enabled is True
    assert config.scrum_schedule.cron == "0 10 * * 3"


def test_schedule_scrum_records_routine_id(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    r = runner.invoke(schedule_scrum_cmd, [
        "--root", str(tmp_path), "--routine-id", "rtn-abc-123", "--json",
    ])
    assert r.exit_code == 0
    payload = json.loads(r.output)
    assert payload["routine_id"] == "rtn-abc-123"
    assert load_config(tmp_path).scrum_schedule.routine_id == "rtn-abc-123"


def test_schedule_scrum_disable_flag(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    runner.invoke(schedule_scrum_cmd, ["--root", str(tmp_path), "--json"])
    r = runner.invoke(schedule_scrum_cmd, [
        "--root", str(tmp_path), "--disable", "--json",
    ])
    assert r.exit_code == 0
    payload = json.loads(r.output)
    assert payload["enabled"] is False
    assert load_config(tmp_path).scrum_schedule.enabled is False


def test_schedule_scrum_rejects_invalid_hour(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    r = runner.invoke(schedule_scrum_cmd, [
        "--root", str(tmp_path), "--hour", "25", "--json",
    ])
    assert r.exit_code != 0
