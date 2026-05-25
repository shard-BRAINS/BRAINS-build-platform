"""Tests for git_utils.py."""
import subprocess
from pathlib import Path

from build_platform.git_utils import commits_since, is_git_repo


def _init_git(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True, capture_output=True)


def test_is_git_repo_false_for_non_repo(tmp_path: Path):
    assert is_git_repo(tmp_path) is False


def test_is_git_repo_true_after_init(tmp_path: Path):
    _init_git(tmp_path)
    assert is_git_repo(tmp_path) is True


def test_commits_since_returns_empty_for_non_repo(tmp_path: Path):
    assert commits_since(tmp_path, "2026-01-01T00:00:00Z") == []


def test_commits_since_returns_commits(tmp_path: Path):
    _init_git(tmp_path)
    (tmp_path / "a.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "first"], cwd=tmp_path, check=True, capture_output=True)
    commits = commits_since(tmp_path, "2020-01-01T00:00:00Z")
    assert len(commits) == 1
    assert "first" in commits[0]["message"]
