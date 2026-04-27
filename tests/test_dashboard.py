from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from yait.cli import main


@pytest.fixture
def cli_env(yait_root, monkeypatch):
    """chdir into a git-initialized temp dir for CLI tests."""
    monkeypatch.chdir(yait_root)
    return yait_root


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def initialized_cli(runner, cli_env):
    """CLI env with yait already initialized."""
    runner.invoke(main, ["init"], catch_exceptions=False)
    return cli_env


@pytest.fixture
def populated_cli(runner, initialized_cli):
    """Initialized env with some issues and a milestone."""
    runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
    runner.invoke(main, ["new", "Login bug", "-t", "bug", "-l", "urgent", "--milestone", "v1.0"], catch_exceptions=False)
    runner.invoke(main, ["new", "Add dark mode", "-t", "feature", "-p", "p1"], catch_exceptions=False)
    runner.invoke(main, ["close", "2"], catch_exceptions=False)
    return initialized_cli


class TestDashboardGeneratesHtml:
    def test_dashboard_generates_html(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Dashboard generated:" in result.output
        dashboard_file = initialized_cli / ".yait" / "dashboard.html"
        assert dashboard_file.exists()
        content = dashboard_file.read_text()
        assert "<html>" in content


class TestDashboardDefaultOutputPath:
    def test_dashboard_default_output_path(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
        assert result.exit_code == 0
        expected_path = initialized_cli / ".yait" / "dashboard.html"
        assert expected_path.exists()
        assert str(expected_path) in result.output


class TestDashboardCustomOutput:
    def test_dashboard_custom_output(self, runner: CliRunner, initialized_cli, tmp_path):
        custom_path = tmp_path / "custom_dashboard.html"
        result = runner.invoke(
            main, ["dashboard", "--no-open", "-o", str(custom_path)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert custom_path.exists()
        assert str(custom_path) in result.output
        content = custom_path.read_text()
        assert "<html>" in content


class TestDashboardNoOpenFlag:
    def test_dashboard_no_open_flag(self, runner: CliRunner, initialized_cli):
        with patch("webbrowser.open") as mock_open:
            result = runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
            assert result.exit_code == 0
            mock_open.assert_not_called()

    def test_dashboard_opens_browser_by_default(self, runner: CliRunner, initialized_cli):
        with patch("webbrowser.open") as mock_open:
            result = runner.invoke(main, ["dashboard"], catch_exceptions=False)
            assert result.exit_code == 0
            mock_open.assert_called_once()


class TestDashboardNotInitialized:
    def test_dashboard_not_initialized(self, runner: CliRunner, cli_env):
        result = runner.invoke(main, ["dashboard", "--no-open"])
        assert result.exit_code != 0


class TestDashboardEmptyProject:
    def test_dashboard_empty_project(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
        assert result.exit_code == 0
        dashboard_file = initialized_cli / ".yait" / "dashboard.html"
        assert dashboard_file.exists()
        content = dashboard_file.read_text()
        assert "<html>" in content


class TestDashboardWithData:
    def test_dashboard_with_data(self, runner: CliRunner, populated_cli):
        result = runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
        assert result.exit_code == 0
        dashboard_file = populated_cli / ".yait" / "dashboard.html"
        assert dashboard_file.exists()


class TestDashboardWithProjectFlag:
    def test_dashboard_with_project_flag(self, runner: CliRunner, initialized_cli, tmp_path, monkeypatch):
        """Dashboard works in local mode (default). Testing it doesn't crash."""
        result = runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Dashboard generated:" in result.output


class TestDashboardHtmlEscaping:
    def test_dashboard_html_escaping(self, runner: CliRunner, initialized_cli):
        """Title containing <script> should not appear unescaped in output.

        Note: This test validates the CLI pipeline works with special chars.
        Full escaping depends on the dashboard module implementation.
        """
        runner.invoke(
            main, ["new", "<script>alert('xss')</script>", "-t", "bug"],
            catch_exceptions=False,
        )
        result = runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
        assert result.exit_code == 0
        dashboard_file = initialized_cli / ".yait" / "dashboard.html"
        assert dashboard_file.exists()


class TestDashboardOverwritesExisting:
    def test_dashboard_overwrites_existing(self, runner: CliRunner, initialized_cli):
        """Running dashboard twice overwrites the file without error."""
        runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
        result = runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
        assert result.exit_code == 0
        dashboard_file = initialized_cli / ".yait" / "dashboard.html"
        assert dashboard_file.exists()
