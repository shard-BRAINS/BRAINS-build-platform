"""Resolve .brains-build/ root for the current project."""
from pathlib import Path

STATE_DIR_NAME = ".brains-build"


class BrainsBuildNotFoundError(RuntimeError):
    """Raised when no .brains-build/ directory found walking up from cwd."""


def find_brains_build_root(start: Path | None = None) -> Path:
    """Walk up from `start` (default cwd) until a .brains-build/ dir is found.

    Returns the directory CONTAINING .brains-build/, not .brains-build/ itself.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / STATE_DIR_NAME).is_dir():
            return candidate
    raise BrainsBuildNotFoundError(
        f"No {STATE_DIR_NAME}/ found in {current} or parents. "
        f"Run /build-init to set up a new build project."
    )


def state_dir(project_root: Path) -> Path:
    """Return the .brains-build/ subdirectory for a project root."""
    return project_root / STATE_DIR_NAME
