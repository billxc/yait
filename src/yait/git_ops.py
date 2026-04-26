from __future__ import annotations

import subprocess
from pathlib import Path


def git_run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def is_git_repo(root: Path) -> bool:
    try:
        git_run(root, "rev-parse", "--is-inside-work-tree")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def git_add(root: Path, *paths: str) -> None:
    git_run(root, "add", *paths)


def git_commit(root: Path, message: str) -> None:
    """Stage .yait/ and commit. No-op if not a git repo or nothing changed."""
    if not is_git_repo(root):
        return
    yait_dir = root / ".yait"
    if yait_dir.exists():
        git_run(root, "add", ".yait")
    # Check if there is anything staged
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=root,
        capture_output=True,
    )
    if result.returncode == 0:
        return
    git_run(root, "commit", "-m", message)
