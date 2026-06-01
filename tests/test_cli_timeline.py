"""Tests for `python -m build_platform.cli.timeline`."""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.timeline import timeline_cmd


def _write_audit_index(root: Path, entries: list[dict]) -> None:
    audit_dir = root / ".brains-build" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    index = audit_dir / "index.jsonl"
    with index.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _entry(wp_id: str, ts: str, persona: str = "build-backend-sme", result: str = "done") -> dict:
    return {
        "wp_id": wp_id,
        "timestamp": ts,
        "persona": persona,
        "model": "claude-sonnet-4-6",
        "tier": 2,
        "runtime_seconds": 120.5,
        "result": result,
        "inputs_read": [],
        "outputs_written": [],
        "decisions_logged": [],
        "tests_run": [],
        "code_review_verdict": None,
        "code_review_findings": [],
        "tokens_in": 1000,
        "tokens_out": 500,
        "cost_usd": 0.05,
    }


def test_timeline_empty_audit_text(tmp_path):
    """No audit/index.jsonl yet → friendly message, exit 0."""
    runner = CliRunner()
    result = runner.invoke(timeline_cmd, ["--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "No audit entries found" in result.output


def test_timeline_empty_audit_json(tmp_path):
    """No audit entries + --json → empty JSON list, exit 0."""
    runner = CliRunner()
    result = runner.invoke(timeline_cmd, ["--root", str(tmp_path), "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == []


def test_timeline_single_entry(tmp_path):
    """One entry → displays WP id and persona."""
    _write_audit_index(tmp_path, [_entry("WP-0001", "2026-06-01T10:00:00Z")])
    runner = CliRunner()
    result = runner.invoke(timeline_cmd, ["--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "WP-0001" in result.output
    assert "build-backend-sme" in result.output


def test_timeline_count_limits_window(tmp_path):
    """10 entries, count=3 → window contains the 3 most-recent only."""
    entries = [_entry(f"WP-{i:04d}", f"2026-06-01T{i:02d}:00:00Z") for i in range(10)]
    _write_audit_index(tmp_path, entries)
    runner = CliRunner()
    result = runner.invoke(timeline_cmd, ["--root", str(tmp_path), "--count", "3"])
    assert result.exit_code == 0
    # Three most recent are WP-0007, WP-0008, WP-0009 (highest hour)
    assert "WP-0007" in result.output
    assert "WP-0008" in result.output
    assert "WP-0009" in result.output
    # Earlier entries must not appear
    assert "WP-0000" not in result.output
    assert "WP-0006" not in result.output


def test_timeline_window_sorted_chronological(tmp_path):
    """Within the window, output is oldest-first regardless of input order."""
    entries = [
        _entry("WP-0003", "2026-06-01T12:00:00Z"),
        _entry("WP-0001", "2026-06-01T10:00:00Z"),
        _entry("WP-0002", "2026-06-01T11:00:00Z"),
    ]
    _write_audit_index(tmp_path, entries)
    runner = CliRunner()
    result = runner.invoke(timeline_cmd, ["--root", str(tmp_path)])
    assert result.exit_code == 0
    out = result.output
    assert out.index("WP-0001") < out.index("WP-0002") < out.index("WP-0003")


def test_timeline_json_emits_chronological_list(tmp_path):
    """--json emits a parseable list, oldest-first."""
    _write_audit_index(
        tmp_path,
        [
            _entry("WP-0002", "2026-06-01T11:00:00Z"),
            _entry("WP-0001", "2026-06-01T10:00:00Z"),
        ],
    )
    runner = CliRunner()
    result = runner.invoke(timeline_cmd, ["--root", str(tmp_path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert [e["wp_id"] for e in payload] == ["WP-0001", "WP-0002"]


def test_timeline_rejects_zero_count(tmp_path):
    """--count 0 exits non-zero with a usable error."""
    runner = CliRunner()
    result = runner.invoke(timeline_cmd, ["--root", str(tmp_path), "--count", "0"])
    assert result.exit_code != 0
    assert "positive" in result.output.lower() or "positive" in (result.stderr or "").lower()


def test_timeline_rejects_negative_count(tmp_path):
    """--count -5 exits non-zero."""
    runner = CliRunner()
    result = runner.invoke(timeline_cmd, ["--root", str(tmp_path), "--count", "-5"])
    assert result.exit_code != 0
