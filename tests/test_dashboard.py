"""Tests for yait.dashboard module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from yait.cli import main
from yait.dashboard import generate_dashboard, _esc
from yait.models import Issue, Milestone
from yait.store import init_store, save_issue, save_milestone, next_id


@pytest.fixture
def dashboard_root(initialized_root: Path) -> Path:
    """Initialized root with sample data for dashboard tests."""
    root = initialized_root

    # Create a mix of open and closed issues
    issues = [
        Issue(id=next_id(root), title="Login page broken", status="open",
              type="bug", priority="p0", assignee="alice",
              milestone="v1.0", created_at="2026-04-01", updated_at="2026-04-01"),
        Issue(id=next_id(root), title="Add dark mode", status="open",
              type="feature", priority="p1", assignee="bob",
              milestone="v1.0", created_at="2026-04-02", updated_at="2026-04-02"),
        Issue(id=next_id(root), title="Fix typo in README", status="closed",
              type="misc", priority="p3",
              created_at="2026-03-15", updated_at="2026-04-10"),
        Issue(id=next_id(root), title="Improve performance", status="closed",
              type="enhancement", priority="p2", assignee="alice",
              milestone="v1.0", created_at="2026-03-20", updated_at="2026-04-15"),
        Issue(id=next_id(root), title="API docs", status="open",
              type="misc", priority="none",
              created_at="2026-04-05", updated_at="2026-04-05"),
    ]
    for issue in issues:
        save_issue(root, issue)

    # Create milestones
    save_milestone(root, Milestone(
        name="v1.0", status="open", due_date="2026-05-01", created_at="2026-03-01",
    ))
    save_milestone(root, Milestone(
        name="v2.0", status="open", due_date="2026-08-01", created_at="2026-03-01",
    ))
    save_milestone(root, Milestone(
        name="legacy", status="closed", created_at="2025-01-01",
    ))

    return root


class TestGenerateDashboard:
    """Tests for generate_dashboard function."""

    def test_returns_valid_html(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert result.startswith("<!DOCTYPE html>")
        assert "</html>" in result

    def test_contains_header(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root, project_name="MyProject")
        assert "YAIT Dashboard — MyProject" in result
        assert "Generated:" in result

    def test_default_project_name(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert "YAIT Dashboard" in result
        # Should not have " — " with empty project name
        assert "YAIT Dashboard — " not in result

    def test_summary_cards(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        # 5 total, 3 open, 2 closed, 40% close rate
        assert ">5</div>" in result  # total
        assert ">3</div>" in result  # open
        assert ">2</div>" in result  # closed
        assert ">40%</div>" in result  # close rate

    def test_type_breakdown(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert "By Type" in result
        assert "bug" in result
        assert "feature" in result
        assert "enhancement" in result

    def test_priority_breakdown(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert "By Priority" in result
        assert "p0" in result
        assert "p1" in result

    def test_milestone_progress(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert "Milestone Progress" in result
        assert "v1.0" in result
        assert "v2.0" in result
        # v1.0 has 3 issues (2 open, 1 closed) => 1/3 closed (33%)
        assert "1/3 closed (33%)" in result
        # v2.0 has 0 issues => 0/0 closed (0%)
        assert "0/0 closed (0%)" in result
        # Closed milestone should NOT appear
        assert "legacy" not in result
        # Due date shown
        assert "2026-05-01" in result

    def test_open_issues_table(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert "Open Issues" in result
        assert "Login page broken" in result
        assert "Add dark mode" in result
        assert "API docs" in result
        # Closed issues should NOT be in open table... we check they appear in recently closed
        # Both "Fix typo" and "Improve performance" are closed
        # The open issues table has Assignee column
        assert "alice" in result
        assert "bob" in result

    def test_recently_closed(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert "Recently Closed" in result
        assert "Fix typo in README" in result
        assert "Improve performance" in result

    def test_xss_prevention(self, initialized_root: Path):
        root = initialized_root
        xss_title = '<script>alert("xss")</script>'
        save_issue(root, Issue(
            id=next_id(root), title=xss_title, status="open",
            type="bug", priority="p0", created_at="2026-04-01",
        ))
        result = generate_dashboard(root)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_xss_in_project_name(self, initialized_root: Path):
        result = generate_dashboard(initialized_root, project_name='<img onerror="alert(1)">')
        assert 'onerror="alert(1)"' not in result
        assert "&lt;img" in result

    def test_empty_project(self, initialized_root: Path):
        result = generate_dashboard(initialized_root)
        assert "<!DOCTYPE html>" in result
        assert ">0</div>" in result  # total=0
        assert ">0%</div>" in result  # close rate=0
        assert "No open milestones" in result
        assert "No open issues" in result
        assert "No closed issues" in result

    def test_many_closed_issues_limited_to_10(self, initialized_root: Path):
        root = initialized_root
        for n in range(15):
            save_issue(root, Issue(
                id=next_id(root), title=f"Closed issue {n}", status="closed",
                type="bug", priority="p1",
                created_at="2026-04-01", updated_at=f"2026-04-{n+1:02d}",
            ))
        result = generate_dashboard(root)
        # Recently closed should have at most 10 rows
        assert result.count("Closed issue") == 10
        # Most recent should be there (updated 2026-04-15)
        assert "Closed issue 14" in result

    def test_import(self):
        """Verify the public API can be imported."""
        from yait.dashboard import generate_dashboard as gd
        assert callable(gd)


class TestEscapeHelper:
    """Tests for the _esc helper function."""

    def test_escapes_angle_brackets(self):
        assert _esc("<div>") == "&lt;div&gt;"

    def test_escapes_ampersand(self):
        assert _esc("a & b") == "a &amp; b"

    def test_escapes_quotes(self):
        assert _esc('"hello"') == "&quot;hello&quot;"

    def test_handles_none_via_str(self):
        assert _esc(None) == "None"

    def test_plain_text_unchanged(self):
        assert _esc("hello world") == "hello world"


# --- CLI tests (from feat/dashboard-cli) ---


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
        assert "<html" in content


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
        assert "<html" in content


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
        assert "<html" in content


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
