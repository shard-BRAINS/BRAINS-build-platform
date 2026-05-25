"""Shared pytest fixtures."""
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """An empty project directory with no .brains-build/ yet."""
    return tmp_path


@pytest.fixture
def seeded_project(tmp_path: Path) -> Path:
    """A project directory with a pre-built .brains-build/ tree."""
    fixture = Path(__file__).parent / "fixtures" / "seed_project"
    shutil.copytree(fixture, tmp_path / "project")
    return tmp_path / "project"
