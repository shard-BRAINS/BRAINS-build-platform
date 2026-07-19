"""Core dispatch: tier-1 (Ollama) and tier-2 (Claude subagent brief).

API note (WP-0015): dispatch_tier1 now returns a (Path, dict) tuple instead of
a bare Path. The dict has keys tokens_in, tokens_out, cost_usd from the Ollama
response. The only caller, cli/dispatch.py, was updated in the same change.
"""
import re
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

from jinja2 import Template, select_autoescape

from build_platform.ollama_client import OllamaClient
from build_platform.paths import state_dir
from build_platform.schemas import WorkPackage
from build_platform.state import load_project

TIER1_MAX_BYTES = 50_000


class DispatchError(RuntimeError):
    """Dispatch failed in a recoverable-by-human way (e.g., 2 retries exhausted).

    Attributes:
        suggested_action: Optional hint for the caller (e.g. "retier-to-2").
            Set by dispatch_tier1 when classify_tier1_failure detects a
            model-capability gap across both attempts.
    """

    suggested_action: str | None = None


class DiffValidationError(DispatchError):
    """Diff failed structural or scope validation."""


_DIFF_HEADER = re.compile(r"^---\s+a/(?P<path>.+)$", re.MULTILINE)
_DIFF_HEADER_PLUS = re.compile(r"^\+\+\+\s+b/(?P<path>.+)$", re.MULTILINE)
_DIFF_HUNK = re.compile(r"^@@\s+-\d+", re.MULTILINE)
_FENCE_OPEN = re.compile(r"^```[\w-]*\s*\n", re.MULTILINE)
_FENCE_CLOSE = re.compile(r"\n```\s*$")

# Patterns used by classify_tier1_failure to detect model-capability gaps.
_UNDEF_NAME = re.compile(r"undefined\s+name|NameError.*Optional|NameError.*Literal", re.IGNORECASE)
_FENCE_ANY = re.compile(r"```")
_DUP_DEF = re.compile(r"^\+def\s+(\w+)\s*\(", re.MULTILINE)


def classify_tier1_failure(raw_outputs: list[str]) -> str | None:
    """Classify whether exhausted tier-1 retries indicate a model-capability gap.

    Returns "retier-to-2" when any of the following patterns are detected across
    the collected raw outputs, None otherwise:

    - "undefined name" / NameError referencing Optional or Literal (missing imports)
    - 3 or more backtick fence markers (``` ) in total across all outputs
    - Duplicate function definitions (same 'def name(' added multiple times in one output)
    """
    combined = "\n".join(raw_outputs)

    # Pattern 1: unresolved name / missing import markers
    if _UNDEF_NAME.search(combined):
        return "retier-to-2"

    # Pattern 2: recurrent backtick fences after the prompt explicitly forbids them.
    # Count all ``` occurrences across all outputs; 3+ suggests persistent bad habit.
    if len(_FENCE_ANY.findall(combined)) >= 3:
        return "retier-to-2"

    # Pattern 3: duplicate function definitions within any single output.
    for output in raw_outputs:
        defs = _DUP_DEF.findall(output)
        if len(defs) != len(set(defs)):
            return "retier-to-2"

    return None


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


class DiffAppliesError(DispatchError):
    """Diff is structurally valid but `git apply --check` rejects it.

    Most common cause: Ollama produced an @@ hunk header with the wrong
    line counts (B != context+removed, or D != context+added). Surfaced
    by dogfood Finding #11 (2026-05-27): the structural validator alone
    isn't sufficient — git apply is the authoritative check.
    """


def check_diff_applies_cleanly(project_root: Path, diff_text: str) -> tuple[bool, str]:
    """Run `git apply --check` against the diff in a tmp file.

    Returns (True, "") if the diff would apply cleanly (or the project
    isn't a git repo). Returns (False, stderr) if it would fail.
    """
    if not (project_root / ".git").exists():
        return True, ""  # not a git repo; skip the check
    fd, path = tempfile.mkstemp(suffix=".diff", text=True)
    try:
        with open(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(diff_text)
        result = subprocess.run(
            ["git", "apply", "--check", path],
            cwd=project_root, capture_output=True, text=True,
        )
        return result.returncode == 0, result.stderr.strip()
    finally:
        Path(path).unlink(missing_ok=True)


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
    return Template(src, autoescape=select_autoescape(), keep_trailing_newline=True)


PERSONA_MISSIONS = {
    "build-backend-sme": "Implement backend code per the work package, write tests, keep changes minimal.",
    "build-frontend-sme": "Implement UI per the work package, follow existing patterns, write tests.",
    "build-qa-sme": "Write or update tests to verify acceptance criteria.",
    "build-security-sme": "Read-only audit; produce findings, do not modify code.",
    "build-devops-sme": "Update CI/CD/deploy configs per the work package.",
    "build-debug-sme": "Reproduce the failure, prove the root cause, then fix minimally with a regression test.",
}


def dispatch_tier1(
    project_root: Path, wp: WorkPackage, client: OllamaClient
) -> tuple[Path, dict]:
    """Send WP to Ollama, validate diff, write to runs/<wp-id>/proposed.diff.

    Retries once with stricter prompt on validation failure. Raises DispatchError
    after second failure.

    Returns:
        (diff_path, metrics_dict) where metrics_dict has keys tokens_in,
        tokens_out, cost_usd (summed across all chat calls made).

    API change (WP-0015): previously returned bare Path; now returns a tuple.
    The only caller, cli/dispatch.py, was updated in the same changeset.
    """
    scope = _read_scope_files(project_root, wp.spec_files)
    config = client.config
    project = load_project(project_root)
    runs = state_dir(project_root) / "runs" / wp.id
    runs.mkdir(parents=True, exist_ok=True)

    review_feedback: str | None = None
    raw_outputs: list[str] = []
    total_metrics: dict = {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}

    for attempt in range(2):
        prompt = _tier1_template().render(
            persona_mission=PERSONA_MISSIONS.get(wp.executor_persona, ""),
            project=project,
            wp=wp,
            files=scope,
            review_feedback=review_feedback,
        )
        (runs / f"prompt-attempt{attempt + 1}.txt").write_text(prompt, encoding="utf-8")
        raw, metrics = client.chat_with_metrics(model=config.models.tier1_default, prompt=prompt)
        total_metrics["tokens_in"] += metrics.get("tokens_in", 0)
        total_metrics["tokens_out"] += metrics.get("tokens_out", 0)
        total_metrics["cost_usd"] += metrics.get("cost_usd", 0.0)
        raw_outputs.append(raw)
        (runs / f"raw-attempt{attempt + 1}.txt").write_text(raw, encoding="utf-8")
        try:
            validate_diff(raw, allowed_files=wp.spec_files)
        except DiffValidationError as e:
            review_feedback = (
                f"Previous attempt failed validation: {e}\n"
                f"Output a unified diff only. No prose. No backticks. Use exact paths."
            )
            continue

        # Finding #11: structural validation passes != `git apply` accepts.
        # Most common cause is wrong hunk @@ line counts. Run --check now so
        # we retry with feedback instead of failing later at dispatch_apply.
        cleaned = strip_markdown_fences(raw)
        applies, apply_err = check_diff_applies_cleanly(project_root, cleaned)
        if not applies:
            review_feedback = (
                f"Diff was structurally valid but `git apply --check` rejected it:\n"
                f"{apply_err}\n\n"
                f"Most common cause: the @@ hunk header line counts are wrong.\n"
                f"Format is `@@ -SOURCE_START,SOURCE_COUNT +DEST_START,DEST_COUNT @@`\n"
                f"  SOURCE_COUNT = (context lines) + (removed lines)\n"
                f"  DEST_COUNT   = (context lines) + (added lines)\n"
                f"Recompute and try again with correct counts."
            )
            continue

        diff_path = runs / "proposed.diff"
        # Persist the canonicalized form (fences stripped) so `git apply` works directly.
        diff_path.write_text(cleaned, encoding="utf-8")
        return diff_path, total_metrics

    err = DispatchError(
        f"Tier-1 dispatch for {wp.id} failed validation twice. "
        f"See runs/{wp.id}/ for prompts and raw outputs."
    )
    suggestion = classify_tier1_failure(raw_outputs)
    err.suggested_action = suggestion
    raise err


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
