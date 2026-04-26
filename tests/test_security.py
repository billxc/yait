"""Security tests for command injection and path traversal prevention."""

import pytest
from pathlib import Path
from click.testing import CliRunner

from yait.cli import main
from yait.store import _issue_path, init_store


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli_env(yait_root, monkeypatch):
    monkeypatch.chdir(yait_root)
    return yait_root


@pytest.fixture
def initialized_cli(runner, cli_env):
    runner.invoke(main, ["init"], catch_exceptions=False)
    return cli_env


class TestIssuePathTraversal:
    """_issue_path must reject non-numeric issue IDs."""

    def test_valid_id(self, initialized_root: Path):
        path = _issue_path(initialized_root, 1)
        assert path.name == "1.md"

    def test_path_traversal_dotdot(self, initialized_root: Path):
        with pytest.raises(ValueError, match="Invalid issue ID"):
            _issue_path(initialized_root, "../../etc/passwd")

    def test_path_traversal_slash(self, initialized_root: Path):
        with pytest.raises(ValueError, match="Invalid issue ID"):
            _issue_path(initialized_root, "../foo")

    def test_negative_id(self, initialized_root: Path):
        with pytest.raises(ValueError, match="Invalid issue ID"):
            _issue_path(initialized_root, -1)

    def test_string_id(self, initialized_root: Path):
        with pytest.raises(ValueError, match="Invalid issue ID"):
            _issue_path(initialized_root, "abc")

    def test_empty_string_id(self, initialized_root: Path):
        with pytest.raises(ValueError, match="Invalid issue ID"):
            _issue_path(initialized_root, "")


class TestLogCommandInjection:
    """log command must reject non-numeric IDs to prevent injection."""

    def test_log_normal_id(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Test"], catch_exceptions=False)
        result = runner.invoke(main, ["log", "1"], catch_exceptions=False)
        assert result.exit_code == 0

    def test_log_injection_semicolon(self, runner: CliRunner, initialized_cli):
        """Semicolon-based shell injection should be rejected by click's int type."""
        result = runner.invoke(main, ["log", "1; rm -rf /"])
        assert result.exit_code != 0

    def test_log_injection_backtick(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["log", "`whoami`"])
        assert result.exit_code != 0

    def test_log_injection_dollar(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["log", "$(cat /etc/passwd)"])
        assert result.exit_code != 0

    def test_log_injection_pipe(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["log", "1|cat /etc/passwd"])
        assert result.exit_code != 0

    def test_log_path_traversal(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["log", "../../etc/passwd"])
        assert result.exit_code != 0
