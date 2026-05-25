"""Append-only audit trail under .brains-build/audit/."""
from pathlib import Path
from importlib.resources import files

from jinja2 import Template
from pydantic import BaseModel, Field

from build_platform.paths import state_dir


class AuditEntry(BaseModel):
    wp_id: str
    timestamp: str  # ISO-8601
    persona: str
    model: str
    tier: int
    runtime_seconds: float
    result: str  # done | blocked | requested_changes | rejected
    inputs_read: list[str] = Field(default_factory=list)
    outputs_written: list[str] = Field(default_factory=list)
    decisions_logged: list[str] = Field(default_factory=list)
    tests_run: list[tuple[str, str]] = Field(default_factory=list)
    notes: str = ""


def _template() -> Template:
    src = files("build_platform.templates").joinpath("audit_entry.md.j2").read_text(encoding="utf-8")
    return Template(src, keep_trailing_newline=True)


def write_audit(project_root: Path, entry: AuditEntry) -> Path:
    audit_dir = state_dir(project_root) / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    safe_ts = entry.timestamp.replace(":", "").replace("-", "")
    filename = f"{entry.wp_id}-{safe_ts}.md"
    path = audit_dir / filename
    rendered = _template().render(**entry.model_dump())
    path.write_text(rendered, encoding="utf-8")
    return path
