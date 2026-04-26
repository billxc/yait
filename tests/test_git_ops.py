import subprocess
from pathlib import Path

import pytest

from yait.git_ops import git_add, git_commit, git_run, is_git_repo


def test_is_git_repo(yait_root: Path):
    """Detects a valid git repository."""
    assert is_git_repo(yait_root) is True


def test_is_not_git_repo(tmp_path: Path):
    """Returns False for a non-git directory."""
    assert is_git_repo(tmp_path) is False


def test_git_add_and_commit(yait_root: Path):
    """git_add + git_commit creates a commit visible in git log."""
    (yait_root / "hello.txt").write_text("hello")
    git_add(yait_root, "hello.txt")
    git_commit(yait_root, "add hello")
    result = git_run(yait_root, "log", "--oneline")
    assert "add hello" in result.stdout


def test_git_run_returns_completed_process(yait_root: Path):
    """git_run returns a CompletedProcess with returncode 0."""
    result = git_run(yait_root, "status")
    assert result.returncode == 0


def test_git_commit_without_staged_changes_is_noop(yait_root: Path):
    """git_commit with nothing staged is a no-op (no error)."""
    # Should not raise — just silently skip
    git_commit(yait_root, "empty commit")
    result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=yait_root,
        capture_output=True,
        text=True,
    )
    assert "empty commit" not in result.stdout
