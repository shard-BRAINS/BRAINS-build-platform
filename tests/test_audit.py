"""Tests for audit.py."""
import json
from pathlib import Path

from build_platform.audit import AuditEntry, load_audit_index, write_audit
from build_platform.state import init_state_tree


def test_write_audit_creates_file(tmp_path: Path):
    init_state_tree(tmp_path)
    entry = AuditEntry(
        wp_id="WP-0001",
        timestamp="2026-05-25T14:02:00Z",
        persona="build-backend-sme",
        model="claude-sonnet-4-6",
        tier=2,
        runtime_seconds=401,
        result="done",
        inputs_read=["src/auth/login.py"],
        outputs_written=["src/auth/login.py", "tests/test_login.py"],
        decisions_logged=["D-2026-05-25-argon2"],
        tests_run=[("pytest tests/auth/", "14 passed")],
        notes="Legacy bcrypt in src/auth/legacy.py left untouched.",
    )
    path = write_audit(tmp_path, entry)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "WP-0001" in content
    assert "build-backend-sme" in content
    assert "claude-sonnet-4-6" in content
    assert "argon2" in content


def test_write_audit_filename_uses_wp_id_and_timestamp(tmp_path: Path):
    init_state_tree(tmp_path)
    entry = AuditEntry(
        wp_id="WP-0042", timestamp="2026-05-25T14:02:00Z",
        persona="build-frontend-sme", model="claude-sonnet-4-6", tier=2,
        runtime_seconds=120, result="done",
        inputs_read=[], outputs_written=[], decisions_logged=[],
        tests_run=[], notes="",
    )
    path = write_audit(tmp_path, entry)
    assert "WP-0042" in path.name
    assert path.parent.name == "audit"


# --- Token/cost meter tests ---

def _make_entry(**kwargs) -> AuditEntry:
    defaults = dict(
        wp_id="WP-0001", timestamp="2026-05-25T14:00:00Z",
        persona="build-backend-sme", model="claude-sonnet-4-6",
        tier=2, runtime_seconds=10.0, result="done",
    )
    return AuditEntry(**{**defaults, **kwargs})


def test_audit_entry_token_cost_defaults():
    e = _make_entry()
    assert e.tokens_in == 0
    assert e.tokens_out == 0
    assert e.cost_usd == 0.0


def test_audit_entry_includes_tokens_and_cost_in_markdown(tmp_path: Path):
    init_state_tree(tmp_path)
    e = _make_entry(tokens_in=1000, tokens_out=500, cost_usd=0.0025)
    path = write_audit(tmp_path, e)
    text = path.read_text(encoding="utf-8")
    assert "1000" in text
    assert "500" in text
    assert "0.0025" in text


def test_write_audit_appends_to_index_jsonl(tmp_path: Path):
    init_state_tree(tmp_path)
    e = _make_entry(wp_id="WP-0007", persona="build-qa-sme", cost_usd=0.0042)
    write_audit(tmp_path, e)
    index_path = tmp_path / ".brains-build" / "audit" / "index.jsonl"
    assert index_path.exists()
    lines = [ln for ln in index_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["wp_id"] == "WP-0007"
    assert rec["persona"] == "build-qa-sme"
    assert abs(rec["cost_usd"] - 0.0042) < 1e-9
    assert "notes" not in rec


def test_load_audit_index_returns_empty_for_missing(tmp_path: Path):
    assert load_audit_index(tmp_path) == []


def test_load_audit_index_round_trips_two_entries(tmp_path: Path):
    init_state_tree(tmp_path)
    e1 = _make_entry(wp_id="WP-0001", tokens_in=100, tokens_out=50, cost_usd=0.001)
    e2 = _make_entry(wp_id="WP-0002", tokens_in=200, tokens_out=80, cost_usd=0.002)
    write_audit(tmp_path, e1)
    write_audit(tmp_path, e2)
    rows = load_audit_index(tmp_path)
    assert len(rows) == 2
    assert rows[0]["wp_id"] == "WP-0001"
    assert rows[1]["wp_id"] == "WP-0002"


# --- Code review fields tests (WP-0007) ---

def test_audit_entry_code_review_defaults_to_none():
    e = _make_entry()
    assert e.code_review_verdict is None
    assert e.code_review_findings == []


def test_audit_entry_code_review_round_trips():
    e = _make_entry(code_review_verdict="approve", code_review_findings=["ok"])
    dumped = e.model_dump()
    assert dumped["code_review_verdict"] == "approve"
    assert dumped["code_review_findings"] == ["ok"]
    e2 = AuditEntry.model_validate(dumped)
    assert e2.code_review_verdict == "approve"
    assert e2.code_review_findings == ["ok"]


def test_write_audit_renders_code_review_section_when_verdict_set(tmp_path: Path):
    init_state_tree(tmp_path)
    e = _make_entry(code_review_verdict="request-changes", code_review_findings=["missing docstring"])
    path = write_audit(tmp_path, e)
    content = path.read_text(encoding="utf-8")
    assert "## Code Review" in content
    assert "request-changes" in content
    assert "missing docstring" in content


def test_write_audit_omits_code_review_section_when_verdict_none(tmp_path: Path):
    init_state_tree(tmp_path)
    e = _make_entry()
    path = write_audit(tmp_path, e)
    content = path.read_text(encoding="utf-8")
    assert "## Code Review" not in content


def test_audit_index_jsonl_contains_code_review_keys(tmp_path: Path):
    init_state_tree(tmp_path)
    e = _make_entry(code_review_verdict="approve", code_review_findings=["lgtm"])
    write_audit(tmp_path, e)
    rows = load_audit_index(tmp_path)
    assert len(rows) == 1
    rec = rows[0]
    assert "code_review_verdict" in rec
    assert "code_review_findings" in rec
    assert rec["code_review_verdict"] == "approve"
    assert rec["code_review_findings"] == ["lgtm"]
