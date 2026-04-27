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


def git_log(root: Path, path: str, limit: int = 10) -> str:
    """Return git log --oneline --follow for the given path."""
    try:
        result = git_run(root, "log", "--oneline", "--follow", f"-{limit}", "--", path)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def git_commit(git_root: Path, message: str, stage_path: str = ".yait") -> None:
    """Stage files and commit. No-op if not a git repo or nothing changed."""
    if not is_git_repo(git_root):
        return
    target = git_root / stage_path
    if target.exists():
        git_run(git_root, "add", stage_path)
    # Check if there is anything staged
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=git_root,
        capture_output=True,
    )
    if result.returncode == 0:
        return
    git_run(git_root, "commit", "-m", message)
