"""Read-only git helpers. Safe on non-git directories."""
import subprocess
from pathlib import Path


def is_git_repo(project_root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=project_root, capture_output=True, text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def commits_since(project_root: Path, since_iso: str) -> list[dict]:
    """Return commits authored since the given ISO-8601 timestamp.

    Returns a list of {sha, author, date, message} dicts. Empty list if not a repo.
    """
    if not is_git_repo(project_root):
        return []
    fmt = "%H%x09%an%x09%aI%x09%s"
    result = subprocess.run(
        ["git", "log", f"--since={since_iso}", f"--pretty=format:{fmt}"],
        cwd=project_root, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    out: list[dict] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 3)
        if len(parts) != 4:
            continue
        sha, author, date, message = parts
        out.append({"sha": sha, "author": author, "date": date, "message": message})
    return out
