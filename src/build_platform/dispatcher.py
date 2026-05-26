"""Core dispatch: tier-1 (Ollama) and tier-2 (Claude subagent brief)."""
import re
from importlib.resources import files
from pathlib import Path

from jinja2 import Template

from build_platform.ollama_client import OllamaClient
from build_platform.paths import state_dir
from build_platform.schemas import WorkPackage, WPState
from build_platform.state import load_project

TIER1_MAX_BYTES = 50_000


class DispatchError(RuntimeError):
    """Dispatch failed in a recoverable-by-human way (e.g., 2 retries exhausted)."""


class DiffValidationError(DispatchError):
    """Diff failed structural or scope validation."""


_DIFF_HEADER = re.compile(r"^---\s+a/(?P<path>.+)$", re.MULTILINE)
_DIFF_HEADER_PLUS = re.compile(r"^\+\+\+\s+b/(?P<path>.+)$", re.MULTILINE)
_DIFF_HUNK = re.compile(r"^@@\s+-\d+", re.MULTILINE)
_FENCE_OPEN = re.compile(r"^```[\w-]*\s*\n", re.MULTILINE)
_FENCE_CLOSE = re.compile(r"\n```\s*$")


def strip_markdown_fences(text: str) -> str:
    """Strip surrounding ```diff ... ``` / ``` ... ``` fences from LLM output.

    Ollama and other small models often wrap diffs in code fences even when
    told not to. We canonicalize before validation so the same WP doesn't
    fail twice for a purely cosmetic reason.
    """
    cleaned = text.strip()
    cleaned = _FENCE_OPEN.sub("", cleaned, count=1)
    cleaned = _FENCE_CLOSE.sub("", cleaned)
    if not cleaned.endswith("\n"):
        cleaned += "\n"
    return cleaned


def validate_diff(diff_text: str, *, allowed_files: list[str]) -> None:
    """Raise DiffValidationError if diff is malformed or touches files outside scope.

    Surrounding markdown code fences (```diff ... ```) are stripped before
    structural checks — Ollama frequently adds them despite prompt constraints.
    The first non-whitespace line after stripping must be a `--- a/<path>`
    header, otherwise prose / explanatory text snuck through.
    """
    cleaned = strip_markdown_fences(diff_text)
    first_line = cleaned.lstrip().split("\n", 1)[0] if cleaned.strip() else ""
    if not first_line.startswith("--- a/"):
        raise DiffValidationError(
            f"Diff must start with '--- a/<path>', got: {first_line!r}"
        )
    minus = _DIFF_HEADER.findall(cleaned)
    plus = _DIFF_HEADER_PLUS.findall(cleaned)
    hunks = _DIFF_HUNK.findall(cleaned)
    if not minus or not plus or not hunks:
        raise DiffValidationError("Diff lacks valid headers or hunks.")
    if minus != plus:
        raise DiffValidationError(f"Diff --- and +++ paths mismatch: {minus} vs {plus}.")
    disallowed = [p for p in minus if p not in allowed_files]
    if disallowed:
        raise DiffValidationError(
            f"Diff touches files outside scope: {disallowed}. Allowed: {allowed_files}."
        )


def _read_scope_files(project_root: Path, paths: list[str]) -> list[tuple[str, str]]:
    out = []
    total = 0
    for rel in paths:
        path = project_root / rel
        if not path.exists():
            out.append((rel, ""))
            continue
        content = path.read_text(encoding="utf-8")
        total += len(content.encode("utf-8"))
        if total > TIER1_MAX_BYTES:
            raise DispatchError(
                f"Tier-1 scope exceeds {TIER1_MAX_BYTES} bytes. "
                f"Split the WP or re-tag as tier-2."
            )
        out.append((rel, content))
    return out


def _tier1_template() -> Template:
    src = files("build_platform.templates").joinpath("tier1_executor.j2").read_text(encoding="utf-8")
    return Template(src, keep_trailing_newline=True)


PERSONA_MISSIONS = {
    "build-backend-sme": "Implement backend code per the work package, write tests, keep changes minimal.",
    "build-frontend-sme": "Implement UI per the work package, follow existing patterns, write tests.",
    "build-qa-sme": "Write or update tests to verify acceptance criteria.",
    "build-security-sme": "Read-only audit; produce findings, do not modify code.",
    "build-devops-sme": "Update CI/CD/deploy configs per the work package.",
}


def dispatch_tier1(project_root: Path, wp: WorkPackage, client: OllamaClient) -> Path:
    """Send WP to Ollama, validate diff, write to runs/<wp-id>/proposed.diff.

    Retries once with stricter prompt on validation failure. Raises DispatchError
    after second failure.
    """
    scope = _read_scope_files(project_root, wp.spec_files)
    config = client.config
    project = load_project(project_root)
    runs = state_dir(project_root) / "runs" / wp.id
    runs.mkdir(parents=True, exist_ok=True)

    review_feedback: str | None = None
    for attempt in range(2):
        prompt = _tier1_template().render(
            persona_mission=PERSONA_MISSIONS.get(wp.executor_persona, ""),
            project=project,
            wp=wp,
            files=scope,
            review_feedback=review_feedback,
        )
        (runs / f"prompt-attempt{attempt + 1}.txt").write_text(prompt, encoding="utf-8")
        raw = client.chat(model=config.models.tier1_default, prompt=prompt)
        (runs / f"raw-attempt{attempt + 1}.txt").write_text(raw, encoding="utf-8")
        try:
            validate_diff(raw, allowed_files=wp.spec_files)
        except DiffValidationError as e:
            review_feedback = (
                f"Previous attempt failed validation: {e}\n"
                f"Output a unified diff only. No prose. No backticks. Use exact paths."
            )
            continue
        diff_path = runs / "proposed.diff"
        # Persist the canonicalized form (fences stripped) so `git apply` works directly.
        diff_path.write_text(strip_markdown_fences(raw), encoding="utf-8")
        return diff_path
    raise DispatchError(
        f"Tier-1 dispatch for {wp.id} failed validation twice. "
        f"See runs/{wp.id}/ for prompts and raw outputs."
    )


def prepare_tier2_brief(project_root: Path, wp: WorkPackage) -> Path:
    """Write a structured brief file the Claude session reads when spawning the SME subagent."""
    runs = state_dir(project_root) / "runs" / wp.id
    runs.mkdir(parents=True, exist_ok=True)
    project = load_project(project_root)
    brief = f"""\
# Tier-2 dispatch brief — {wp.id}

**Executor persona:** {wp.executor_persona}
**Workstream:** {wp.workstream}
**Deliverable:** {wp.deliverable_id}
**Tier:** 2

## Project context
- Name: {project.name}
- Mission: {project.mission}
- Stack: {", ".join(project.stack)}
- Constraints: {", ".join(project.constraints) or "_None_"}

## Work package
**Title:** {wp.title}

**Spec:**
{wp.spec}

**Acceptance criteria:**
{chr(10).join(f"- {a}" for a in wp.acceptance)}

**Files in scope:**
{chr(10).join(f"- {f}" for f in wp.spec_files)}

**Consult personas:** {", ".join(wp.consult) or "_None_"}

## Instructions to the executor subagent
1. Read project context and only the files listed above.
2. Implement the spec; use Edit/Write to modify files; follow existing patterns.
3. Run the project's test command after changes; do not mark complete if tests fail.
4. Produce a result block at the end: files changed, decisions made, blockers, handoff notes.
5. Log any non-trivial decisions to `.brains-build/decisions.md` via `/build-decision`.
6. The PMO/Dev Orchestrator will write the audit entry once you return.
"""
    path = runs / "tier2-brief.md"
    path.write_text(brief, encoding="utf-8")
    return path
