"""Tests for paths.py."""
from pathlib import Path

import pytest

from build_platform.paths import (
    BrainsBuildNotFoundError,
    find_brains_build_root,
    state_dir,
)


def test_find_brains_build_root_walks_up(tmp_path: Path):
    root = tmp_path / "project"
    (root / ".brains-build").mkdir(parents=True)
    nested = root / "src" / "deep" / "dir"
    nested.mkdir(parents=True)

    found = find_brains_build_root(nested)
    assert found == root


def test_find_brains_build_root_returns_at_root(tmp_path: Path):
    (tmp_path / ".brains-build").mkdir()
    assert find_brains_build_root(tmp_path) == tmp_path


def test_find_brains_build_root_raises_when_missing(tmp_path: Path):
    with pytest.raises(BrainsBuildNotFoundError):
        find_brains_build_root(tmp_path)


def test_state_dir_returns_brains_build_subdir(tmp_path: Path):
    (tmp_path / ".brains-build").mkdir()
    assert state_dir(tmp_path) == tmp_path / ".brains-build"
