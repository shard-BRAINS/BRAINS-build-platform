"""Tests for audit.py."""
from pathlib import Path

from build_platform.audit import AuditEntry, write_audit
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
