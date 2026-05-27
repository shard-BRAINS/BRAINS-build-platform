"""Heuristic tier-1 vs tier-2 triage (v2.7).

Pure function. Inputs: a WP-like dict (spec, spec_files, acceptance). Output:
a recommendation with per-criterion reasoning.

The Dev Orchestrator persona is supposed to apply the tier-1 checklist
by hand. This module encodes that checklist as a heuristic so the human
or the model can get a fast suggestion before committing the WP — without
the platform forcing the answer. Explicit `--tier` always overrides.

The four criteria below mirror the platform's stated tier-1 definition:
  1. Touches <= 3 files, total < 50KB.
  2. Single well-defined mechanical transformation.
  3. No new design decisions required.
  4. Acceptance criteria are objectively checkable.
"""
from pathlib import Path
from typing import Iterable, Literal

# Verbs / phrases that signal a mechanical transformation. Matched at the
# *start* of the spec (case-insensitive), or as the first significant token.
# Keep this list short and concrete — false positives (recommending tier-1
# for actually-judgment work) are worse than false negatives.
MECHANICAL_VERBS = frozenset({
    "rename", "renames", "renaming",
    "format", "formats", "formatting",
    "bump", "bumps", "bumping",
    "scaffold", "scaffolds", "scaffolding",
    "refactor",  # only when paired with a clear before/after — see DESIGN_KEYWORDS check
    "replace", "replaces", "replacing",
    "add field", "remove field",
    "add import", "remove import",
    "doc edit", "doc update", "docstring",
    "update version", "version bump",
    "extract", "inline",  # mechanical refactors
    "delete unused", "remove unused",
})

# Words whose presence in the spec disqualifies tier-1 even if other criteria
# pass — these indicate the WP requires judgment, not mechanical execution.
DESIGN_KEYWORDS = frozenset({
    "design", "designs", "designing",
    "architecture", "architectural",
    "decide", "decision", "decisions",
    "approach", "approaches",
    "evaluate", "evaluation",
    "research", "investigate", "investigation",
    "explore", "exploration",
    "should we", "what if",
    "choose between", "trade-off", "tradeoff",
})

# Indicators that an acceptance criterion is objectively checkable.
OBJECTIVE_INDICATORS = frozenset({
    "test", "tests",
    "lint", "linter",
    "pass", "passes", "passing",
    "fail", "fails",
    "compile", "compiles",
    "match", "matches", "matching",
    "return", "returns",
    "exit", "exits", "exit code",
    "file exists",
    "file contains",
    "regex",
    "diff",          # "leaves no diff", "diff is empty"
    "succeeds", "succeed",
    "output",        # "output contains X", "output matches"
    "0 errors", "no errors",
})

TIER1_MAX_FILES = 3
TIER1_MAX_BYTES = 50_000

Tier = Literal[1, 2]


def _check_scope(spec_files: list[str], project_root: Path | None) -> tuple[bool, str]:
    """Criterion 1: <= 3 files AND total < 50KB. Files that don't exist yet
    (new file creation) count as 0 bytes — only file count is enforced for them."""
    n = len(spec_files)
    if n > TIER1_MAX_FILES:
        return False, f"{n} files declared in scope; tier-1 max is {TIER1_MAX_FILES}"
    if project_root is None:
        # Can't measure file sizes — only assert count
        return True, f"{n} file(s); sizes not measured (no project_root)"
    total = 0
    measured: list[str] = []
    for rel in spec_files:
        p = project_root / rel
        if p.exists() and p.is_file():
            size = p.stat().st_size
            total += size
            measured.append(f"{rel}={size}B")
        else:
            measured.append(f"{rel}=new")
    if total > TIER1_MAX_BYTES:
        return False, f"total {total}B exceeds {TIER1_MAX_BYTES}B cap ({', '.join(measured)})"
    return True, f"{n} file(s), {total}B total"


def _check_mechanical_verb(spec: str) -> tuple[bool, str]:
    """Criterion 2: spec begins with a mechanical verb / phrase."""
    if not spec:
        return False, "empty spec"
    head = spec.strip().lower()[:80]
    matched = [v for v in MECHANICAL_VERBS if head.startswith(v)]
    if matched:
        return True, f"matched: {matched[0]!r}"
    # Also accept "add <something>" / "remove <something>" as a soft mechanical
    # signal when paired with other passing criteria.
    if head.startswith(("add ", "remove ", "delete ")):
        return True, f"matched: leading verb {head.split()[0]!r}"
    return False, "no mechanical verb at start of spec"


def _check_no_design_keywords(spec: str) -> tuple[bool, str]:
    """Criterion 3: spec is free of judgment / design words."""
    if not spec:
        return True, "empty spec (vacuously passes)"
    lower = spec.lower()
    found = sorted(k for k in DESIGN_KEYWORDS if k in lower)
    if found:
        return False, f"found design keyword(s): {found}"
    return True, "no design keywords"


def _check_objective_acceptance(acceptance: Iterable[str]) -> tuple[bool, str]:
    """Criterion 4: every acceptance criterion mentions an objective indicator."""
    items = list(acceptance)
    if not items:
        return False, "no acceptance criteria"
    not_objective: list[str] = []
    for crit in items:
        lower = crit.lower()
        if not any(ind in lower for ind in OBJECTIVE_INDICATORS):
            not_objective.append(crit)
    if not_objective:
        return False, f"non-objective acceptance criteria: {not_objective}"
    return True, f"all {len(items)} criteria objectively checkable"


def suggest_tier(
    spec: str,
    spec_files: list[str],
    acceptance: list[str],
    *,
    project_root: Path | None = None,
) -> dict:
    """Return a tier recommendation with per-criterion verdicts.

    Returns:
        {
            "suggested_tier": 1 | 2,
            "criteria": [{"name": str, "pass": bool, "detail": str}, ...],
            "rationale": str,
        }
    """
    checks = [
        ("scope", *_check_scope(spec_files, project_root)),
        ("mechanical_verb", *_check_mechanical_verb(spec)),
        ("no_design_keywords", *_check_no_design_keywords(spec)),
        ("objective_acceptance", *_check_objective_acceptance(acceptance)),
    ]
    criteria = [{"name": n, "pass": p, "detail": d} for n, p, d in checks]
    all_pass = all(c["pass"] for c in criteria)
    suggested: Tier = 1 if all_pass else 2
    failed = [c["name"] for c in criteria if not c["pass"]]
    if all_pass:
        rationale = "All four tier-1 criteria pass."
    else:
        rationale = f"Failed criteria: {', '.join(failed)}. Recommend tier-2."
    return {
        "suggested_tier": suggested,
        "criteria": criteria,
        "rationale": rationale,
    }
