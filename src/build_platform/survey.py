"""Deterministic survey of an existing codebase, for `/build-adopt`.

Spec mining has two halves. This is the half a machine should do: enumerate what
is actually in the repo — languages, entry points, manifests, tests, CI, churn —
with no inference and no LLM call. The other half (deciding what those facts mean
and what the deliverables are) belongs to build-business-analyst and the user.

Nothing here reads the network or mutates the repo.
"""
import json
import subprocess
from collections import Counter
from pathlib import Path

# Extension -> language. Deliberately not exhaustive; unknown extensions are
# counted under "other" rather than guessed at.
_LANG_BY_EXT = {
    ".py": "Python", ".pyi": "Python",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C", ".h": "C",
    ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".cxx": "C++",
    ".swift": "Swift",
    ".m": "Objective-C",
    ".scala": "Scala",
    ".ex": "Elixir", ".exs": "Elixir",
    ".sh": "Shell", ".bash": "Shell",
    ".ps1": "PowerShell",
    ".sql": "SQL",
    ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "CSS", ".sass": "CSS", ".less": "CSS",
    ".vue": "Vue", ".svelte": "Svelte",
    ".md": "Markdown", ".rst": "Markdown",
    ".yml": "YAML", ".yaml": "YAML",
    ".json": "JSON", ".toml": "TOML",
    ".tf": "Terraform",
    ".dart": "Dart",
}

# Languages that are content/config rather than implementation. Counted, but not
# used to infer the project's primary stack.
_NON_CODE_LANGS = {"Markdown", "YAML", "JSON", "TOML", "HTML", "CSS"}

_MANIFESTS = {
    "pyproject.toml": "Python", "requirements.txt": "Python", "setup.py": "Python",
    "setup.cfg": "Python", "Pipfile": "Python", "poetry.lock": "Python",
    "package.json": "JavaScript/TypeScript", "pnpm-lock.yaml": "JavaScript/TypeScript",
    "yarn.lock": "JavaScript/TypeScript", "package-lock.json": "JavaScript/TypeScript",
    "go.mod": "Go", "Cargo.toml": "Rust", "pom.xml": "Java", "build.gradle": "Java",
    "build.gradle.kts": "Kotlin", "Gemfile": "Ruby", "composer.json": "PHP",
    "Dockerfile": "Container", "docker-compose.yml": "Container",
    "Makefile": "Build", "justfile": "Build",
}

_DOC_FILES = {
    "readme.md": "readme", "readme.rst": "readme", "readme": "readme",
    "contributing.md": "contributing", "architecture.md": "architecture",
    "changelog.md": "changelog", "license": "license", "license.md": "license",
    "security.md": "security", "adr": "decision-records",
}

_EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".tox",
    "dist", "build", "target", "vendor", ".next", ".nuxt", ".idea", ".vscode",
    ".gradle", "bin", "obj", ".terraform", "coverage", ".brains-build",
}

_TEST_DIR_NAMES = {"test", "tests", "spec", "specs", "__tests__", "e2e", "it"}

# Bound git history reads so a huge repo cannot stall the survey.
_CHURN_COMMIT_LIMIT = 500
_GIT_TIMEOUT_SECONDS = 20


def _run_git(root: Path, args: list[str]) -> str | None:
    """Run a git command, returning stdout or None if git/repo unavailable."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True,
            timeout=_GIT_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _is_excluded(rel: Path) -> bool:
    return any(part in _EXCLUDED_DIRS for part in rel.parts)


def list_files(root: Path) -> list[Path]:
    """Repo-relative file paths, respecting .gitignore when git is available.

    Falls back to a filtered walk so the survey still works on a directory that
    is not a git repo (or when git is not installed).
    """
    out = _run_git(root, ["ls-files", "--cached", "--others", "--exclude-standard"])
    if out is not None:
        paths = [Path(line) for line in out.splitlines() if line.strip()]
        return [p for p in paths if not _is_excluded(p)]

    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if not _is_excluded(rel):
            found.append(rel)
    return found


def _classify_languages(files: list[Path]) -> dict:
    counts: Counter[str] = Counter()
    for f in files:
        counts[_LANG_BY_EXT.get(f.suffix.lower(), "other")] += 1
    ranked = [{"language": k, "files": v} for k, v in counts.most_common()]
    primary = [
        r["language"] for r in ranked
        if r["language"] not in _NON_CODE_LANGS and r["language"] != "other"
    ][:3]
    return {"by_language": ranked, "primary": primary}


def _find_manifests(root: Path, files: list[Path]) -> list[dict]:
    names = {f.name for f in files}
    return [
        {"file": name, "ecosystem": eco}
        for name, eco in sorted(_MANIFESTS.items())
        if name in names or (root / name).exists()
    ]


def _is_code(path: Path) -> bool:
    lang = _LANG_BY_EXT.get(path.suffix.lower())
    return lang is not None and lang not in _NON_CODE_LANGS


def _find_tests(files: list[Path]) -> dict:
    # Code files only. A `specs/` tree full of markdown design documents is not a
    # test suite, and counting it as one badly skews the QA workstream suggestion.
    test_files = [
        f for f in files
        if _is_code(f)
        and (
            any(part.lower() in _TEST_DIR_NAMES for part in f.parts[:-1])
            or f.name.startswith("test_")
            or f.stem.endswith(("_test", ".test", ".spec"))
        )
    ]
    dirs = sorted({str(f.parent).replace("\\", "/") for f in test_files})
    return {
        "count": len(test_files),
        "directories": dirs[:20],
        "has_tests": bool(test_files),
    }


def _find_ci(files: list[Path]) -> list[str]:
    ci = []
    for f in files:
        parts = [p.lower() for p in f.parts]
        if parts[:2] == [".github", "workflows"]:
            ci.append(str(f).replace("\\", "/"))
        elif f.name in {".gitlab-ci.yml", "Jenkinsfile", ".circleci/config.yml", "azure-pipelines.yml"}:
            ci.append(str(f).replace("\\", "/"))
    return sorted(ci)


def _find_docs(files: list[Path]) -> list[dict]:
    docs = []
    for f in files:
        key = f.name.lower()
        if key in _DOC_FILES and len(f.parts) <= 2:
            docs.append({"file": str(f).replace("\\", "/"), "kind": _DOC_FILES[key]})
    if any(f.parts and f.parts[0].lower() == "docs" for f in files):
        docs.append({"file": "docs/", "kind": "docs-tree"})
    return docs


def _top_level_structure(files: list[Path]) -> list[dict]:
    counts: Counter[str] = Counter()
    for f in files:
        top = f.parts[0] if len(f.parts) > 1 else "(root files)"
        counts[top] += 1
    return [{"path": k, "files": v} for k, v in counts.most_common()]


def _git_signals(root: Path) -> dict:
    """History-derived signals. All keys None/empty when git is unavailable."""
    signals: dict = {
        "is_git_repo": False, "commits": None, "contributors": None,
        "first_commit": None, "last_commit": None, "churn_top_files": [],
    }
    count = _run_git(root, ["rev-list", "--count", "HEAD"])
    if count is None or not count.strip().isdigit():
        return signals

    signals["is_git_repo"] = True
    signals["commits"] = int(count.strip())

    authors = _run_git(root, ["log", "--format=%an"])
    if authors:
        signals["contributors"] = len({a for a in authors.splitlines() if a.strip()})

    # One pass, newest-first. Note `--reverse` cannot be combined with
    # `--max-count=1` to get the first commit: git applies the limit *before*
    # reversing, so that returns the newest commit, not the oldest.
    dates = _run_git(root, ["log", "--format=%as"])
    if dates and dates.strip():
        lines = [d.strip() for d in dates.splitlines() if d.strip()]
        if lines:
            signals["last_commit"] = lines[0]
            signals["first_commit"] = lines[-1]

    names = _run_git(root, ["log", "--format=", "--name-only", f"-n{_CHURN_COMMIT_LIMIT}"])
    if names:
        churn: Counter[str] = Counter()
        for line in names.splitlines():
            line = line.strip()
            if line and not _is_excluded(Path(line)):
                churn[line] += 1
        signals["churn_top_files"] = [
            {"file": f, "commits": c} for f, c in churn.most_common(15)
        ]
    return signals


def _suggest_workstreams(langs: dict, tests: dict, ci: list[str], files: list[Path]) -> list[dict]:
    """Which of the default workstreams this repo plausibly needs.

    Advisory only — the analyst and the user decide. Reasons are included so a
    suggestion can be argued with rather than taken on faith.
    """
    present = {entry["language"] for entry in langs["by_language"]}
    suggestions = [{
        "id": "backend",
        "reason": "Server-side or library code is the bulk of the repo.",
    }] if present & {"Python", "Go", "Rust", "Java", "C#", "Ruby", "PHP", "Scala", "Elixir"} else []

    if present & {"TypeScript", "JavaScript", "Vue", "Svelte", "CSS", "HTML", "Dart", "Swift", "Kotlin"}:
        suggestions.append({"id": "frontend", "reason": "UI or client-side code present."})
    if tests["has_tests"]:
        suggestions.append({
            "id": "qa",
            "reason": f"{tests['count']} test files already present — QA has a baseline to extend.",
        })
    else:
        suggestions.append({
            "id": "qa",
            "reason": "No tests detected. QA workstream should start with a baseline suite.",
        })
    if ci or any(f.name in {"Dockerfile", "docker-compose.yml"} for f in files):
        suggestions.append({"id": "devops", "reason": "CI workflows or container config present."})
    suggestions.append({
        "id": "security",
        "reason": "Always suggested; the SME calibrates depth to the project's exposure.",
    })
    return suggestions


def survey_repo(root: Path) -> dict:
    """Enumerate what is in the repo at `root`. Pure read; no mutation."""
    files = list_files(root)
    langs = _classify_languages(files)
    tests = _find_tests(files)
    ci = _find_ci(files)

    return {
        "root": str(root),
        "file_count": len(files),
        "languages": langs,
        "manifests": _find_manifests(root, files),
        "tests": tests,
        "ci": ci,
        "docs": _find_docs(files),
        "structure": _top_level_structure(files),
        "git": _git_signals(root),
        "suggested_workstreams": _suggest_workstreams(langs, tests, ci, files),
    }


def render_survey(survey: dict) -> str:
    """Human/analyst-readable brief. The input to spec inference, not the output."""
    lines = [
        "# Codebase survey",
        "",
        f"**Root:** `{survey['root']}`  ",
        f"**Files:** {survey['file_count']}",
        "",
        "## Languages",
        "",
    ]
    primary = survey["languages"]["primary"]
    lines.append(f"Primary: {', '.join(primary) if primary else '_none detected_'}")
    lines.append("")
    lines.append("| Language | Files |")
    lines.append("|---|---|")
    for entry in survey["languages"]["by_language"][:12]:
        lines.append(f"| {entry['language']} | {entry['files']} |")

    lines += ["", "## Manifests", ""]
    if survey["manifests"]:
        for m in survey["manifests"]:
            lines.append(f"- `{m['file']}` — {m['ecosystem']}")
    else:
        lines.append("_None found._")

    tests = survey["tests"]
    lines += ["", "## Tests", ""]
    n_dirs = len(tests["directories"])
    lines.append(
        f"{tests['count']} test files across {n_dirs} director{'y' if n_dirs == 1 else 'ies'}."
    )
    if tests["directories"]:
        lines.append("")
        for d in tests["directories"][:10]:
            lines.append(f"- `{d}`")

    lines += ["", "## CI", ""]
    lines += [f"- `{c}`" for c in survey["ci"]] or ["_No CI configuration found._"]

    lines += ["", "## Docs", ""]
    lines += [f"- `{d['file']}` ({d['kind']})" for d in survey["docs"]] or ["_No docs found._"]

    lines += ["", "## Structure", "", "| Path | Files |", "|---|---|"]
    for entry in survey["structure"][:15]:
        lines.append(f"| `{entry['path']}` | {entry['files']} |")

    git = survey["git"]
    lines += ["", "## History", ""]
    if git["is_git_repo"]:
        lines.append(
            f"{git['commits']} commits by {git['contributors']} contributor(s), "
            f"{git['first_commit']} to {git['last_commit']}."
        )
        if git["churn_top_files"]:
            lines += ["", "Most-changed files (recent history) — likely where the work is:", ""]
            for c in git["churn_top_files"][:10]:
                lines.append(f"- `{c['file']}` ({c['commits']} commits)")
    else:
        lines.append("_Not a git repository, or git unavailable._")

    lines += ["", "## Suggested workstreams", ""]
    for s in survey["suggested_workstreams"]:
        lines.append(f"- **{s['id']}** — {s['reason']}")

    lines += [
        "", "---", "",
        "_Facts only. Deliverables and acceptance criteria are inferred from this "
        "by `build-business-analyst` and confirmed by the user._", "",
    ]
    return "\n".join(lines)


def write_survey(root: Path, survey: dict) -> tuple[Path, Path]:
    """Write survey.json + survey.md under .brains-build/adopt/. Returns both paths."""
    out_dir = root / ".brains-build" / "adopt"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "survey.json"
    md_path = out_dir / "survey.md"
    json_path.write_text(json.dumps(survey, indent=2), encoding="utf-8")
    md_path.write_text(render_survey(survey), encoding="utf-8")
    return json_path, md_path
