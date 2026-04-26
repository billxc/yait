import subprocess
from pathlib import Path

import pytest

from yait.store import init_store


@pytest.fixture
def yait_root(tmp_path: Path) -> Path:
    """Create a temporary directory with git init."""
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


@pytest.fixture
def initialized_root(yait_root: Path) -> Path:
    """yait_root with init_store already called."""
    init_store(yait_root)
    return yait_root
