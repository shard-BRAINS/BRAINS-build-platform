"""Tests for the deterministic codebase survey behind `/build-adopt`."""
import json
import subprocess
from pathlib import Path

import pytest

from build_platform.survey import (
    list_files,
    render_survey,
    survey_repo,
    write_survey,
)


def _mk(root: Path, rel: str, content: str = "x") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """A small polyglot repo: Python backend, TS frontend, tests, CI, docs."""
    _mk(tmp_path, "pyproject.toml", "[project]\nname='demo'\n")
    _mk(tmp_path, "src/demo/__init__.py")
    _mk(tmp_path, "src/demo/api.py", "def get(): ...\n")
    _mk(tmp_path, "src/demo/store.py")
    _mk(tmp_path, "web/app.ts", "export const a = 1;\n")
    _mk(tmp_path, "web/styles.css", "body{}")
    _mk(tmp_path, "tests/test_api.py", "def test_get(): ...\n")
    _mk(tmp_path, "tests/test_store.py")
    _mk(tmp_path, ".github/workflows/ci.yml", "name: ci\n")
    _mk(tmp_path, "README.md", "# Demo\n")
    _mk(tmp_path, "Dockerfile", "FROM python\n")
    return tmp_path


def test_survey_counts_files_and_languages(sample_repo: Path):
    s = survey_repo(sample_repo)
    assert s["file_count"] == 11
    langs = {e["language"]: e["files"] for e in s["languages"]["by_language"]}
    assert langs["Python"] == 5  # 3 under src/ + 2 test modules
    assert langs["TypeScript"] == 1
    # Python dominates, and non-code languages stay out of `primary`.
    assert s["languages"]["primary"][0] == "Python"
    assert "Markdown" not in s["languages"]["primary"]
    assert "YAML" not in s["languages"]["primary"]


def test_survey_finds_manifests_tests_ci_docs(sample_repo: Path):
    s = survey_repo(sample_repo)
    assert {m["file"] for m in s["manifests"]} == {"pyproject.toml", "Dockerfile"}
    assert s["tests"]["has_tests"] is True
    assert s["tests"]["count"] == 2
    assert "tests" in s["tests"]["directories"]
    assert s["ci"] == [".github/workflows/ci.yml"]
    assert {d["kind"] for d in s["docs"]} == {"readme"}


def test_survey_top_level_structure(sample_repo: Path):
    s = survey_repo(sample_repo)
    structure = {e["path"]: e["files"] for e in s["structure"]}
    assert structure["src"] == 3
    assert structure["tests"] == 2
    assert structure["(root files)"] == 3  # pyproject, README, Dockerfile


def test_suggested_workstreams_reflect_repo_shape(sample_repo: Path):
    s = survey_repo(sample_repo)
    by_id = {w["id"]: w["reason"] for w in s["suggested_workstreams"]}
    assert set(by_id) == {"backend", "frontend", "qa", "devops", "security"}
    assert "2 test files" in by_id["qa"]


def test_qa_suggestion_flags_missing_tests(tmp_path: Path):
    _mk(tmp_path, "main.py")
    s = survey_repo(tmp_path)
    by_id = {w["id"]: w["reason"] for w in s["suggested_workstreams"]}
    assert "No tests detected" in by_id["qa"]
    assert "frontend" not in by_id
    assert "devops" not in by_id


def test_excluded_dirs_are_not_surveyed(tmp_path: Path):
    _mk(tmp_path, "app.py")
    _mk(tmp_path, "node_modules/pkg/index.js")
    _mk(tmp_path, ".venv/lib/thing.py")
    _mk(tmp_path, "__pycache__/app.cpython-313.pyc")
    _mk(tmp_path, ".brains-build/project.yml")
    files = {str(f).replace("\\", "/") for f in list_files(tmp_path)}
    assert files == {"app.py"}


def test_test_detection_matches_multiple_conventions(tmp_path: Path):
    _mk(tmp_path, "tests/test_python.py")       # dir + test_ prefix
    _mk(tmp_path, "src/thing_test.go")          # _test suffix
    _mk(tmp_path, "web/button.spec.ts")         # .spec suffix
    _mk(tmp_path, "spec/legacy.rb")             # spec dir
    _mk(tmp_path, "src/notatest.py")
    s = survey_repo(tmp_path)
    assert s["tests"]["count"] == 4


def test_survey_on_non_git_directory(tmp_path: Path):
    """Survey must still work outside a git repo — git signals go empty, not missing."""
    _mk(tmp_path, "main.py")
    s = survey_repo(tmp_path)
    assert s["git"]["is_git_repo"] is False
    assert s["git"]["commits"] is None
    assert s["git"]["churn_top_files"] == []


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_survey_reads_git_signals(tmp_path: Path):
    try:
        _git(tmp_path, "init")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "Tester")
    _mk(tmp_path, "app.py", "v1")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "first", "--date=2020-01-15T00:00:00")
    _mk(tmp_path, "app.py", "v2")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "second", "--date=2023-06-20T00:00:00")

    s = survey_repo(tmp_path)
    assert s["git"]["is_git_repo"] is True
    assert s["git"]["commits"] == 2
    assert s["git"]["contributors"] == 1
    churn = {c["file"]: c["commits"] for c in s["git"]["churn_top_files"]}
    assert churn["app.py"] == 2


def test_first_commit_is_oldest_not_newest(tmp_path: Path):
    """Regression: `git log --reverse --max-count=1` limits before reversing,
    which yields the NEWEST commit. first_commit must be the oldest."""
    try:
        _git(tmp_path, "init")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "Tester")
    _mk(tmp_path, "a.py")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "old", "--date=2019-03-01T00:00:00")
    _mk(tmp_path, "b.py")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "new", "--date=2024-11-09T00:00:00")

    git = survey_repo(tmp_path)["git"]
    assert git["first_commit"] == "2019-03-01"
    assert git["last_commit"] == "2024-11-09"


def test_markdown_spec_docs_are_not_counted_as_tests(tmp_path: Path):
    """Regression: a `specs/` tree of design documents is not a test suite."""
    _mk(tmp_path, "docs/superpowers/specs/2026-05-25-design.md", "# Design\n")
    _mk(tmp_path, "docs/specs/notes.md")
    _mk(tmp_path, "tests/test_real.py")
    s = survey_repo(tmp_path)
    assert s["tests"]["count"] == 1
    assert s["tests"]["directories"] == ["tests"]


def test_gitignored_files_excluded_when_git_available(tmp_path: Path):
    try:
        _git(tmp_path, "init")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    _mk(tmp_path, ".gitignore", "secret.py\n")
    _mk(tmp_path, "app.py")
    _mk(tmp_path, "secret.py")
    files = {str(f).replace("\\", "/") for f in list_files(tmp_path)}
    assert "app.py" in files
    assert "secret.py" not in files


def test_render_survey_is_markdown_and_mentions_key_sections(sample_repo: Path):
    md = render_survey(survey_repo(sample_repo))
    assert md.startswith("# Codebase survey")
    for heading in ("## Languages", "## Manifests", "## Tests", "## CI",
                    "## Structure", "## History", "## Suggested workstreams"):
        assert heading in md


def test_render_survey_handles_empty_repo(tmp_path: Path):
    md = render_survey(survey_repo(tmp_path))
    assert "_None found._" in md          # manifests
    assert "_No CI configuration found._" in md
    assert "_none detected_" in md        # primary languages


def test_write_survey_emits_both_artefacts(sample_repo: Path):
    s = survey_repo(sample_repo)
    json_path, md_path = write_survey(sample_repo, s)
    assert json_path.exists() and md_path.exists()
    assert json_path.parent.name == "adopt"
    reloaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert reloaded["file_count"] == s["file_count"]
    assert md_path.read_text(encoding="utf-8").startswith("# Codebase survey")


def test_survey_does_not_mutate_repo(tmp_path: Path):
    _mk(tmp_path, "app.py")
    before = {str(p) for p in tmp_path.rglob("*")}
    survey_repo(tmp_path)
    assert {str(p) for p in tmp_path.rglob("*")} == before
