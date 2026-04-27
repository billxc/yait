"""Tests for board (kanban) view, update alias, and workflow config."""

from pathlib import Path

import json
import pytest
from click.testing import CliRunner

from yait.cli import main
from yait.board import render_board
from yait.models import Issue
from yait.store import (
    init_store, save_issue, get_workflow, _read_config, _write_config,
)


@pytest.fixture
def cli_env(yait_root, monkeypatch):
    monkeypatch.chdir(yait_root)
    return yait_root


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def initialized_cli(runner, cli_env):
    runner.invoke(main, ["init"], catch_exceptions=False)
    return cli_env


def _make_issue(id, title, status="open", priority="none", **kw):
    return Issue(
        id=id,
        title=title,
        status=status,
        type=kw.get("type", "misc"),
        priority=priority,
        labels=kw.get("labels", []),
        assignee=kw.get("assignee"),
        milestone=kw.get("milestone"),
        created_at="2026-04-27T00:00:00+08:00",
        updated_at="2026-04-27T00:00:00+08:00",
        body="",
    )


# ── render_board unit tests ──────────────────────────────────────


class TestRenderBoardDefaultWorkflow:
    def test_render_board_default_workflow(self):
        """Default 2-column (open/closed) rendering."""
        wf = {"statuses": ["open", "closed"], "closed_statuses": ["closed"]}
        issues = [
            _make_issue(1, "Fix bug", status="open"),
            _make_issue(2, "Setup env", status="closed"),
            _make_issue(3, "Add tests", status="open"),
        ]
        result = render_board(issues, wf, terminal_width=80)
        assert "open (2)" in result
        assert "closed (1)" in result
        assert "#1" in result
        assert "#2" in result
        assert "#3" in result


class TestRenderBoardExtendedWorkflow:
    def test_render_board_extended_workflow(self):
        """6-column extended workflow rendering."""
        statuses = ["backlog", "ready", "in-progress", "in-review", "done", "archive"]
        wf = {"statuses": statuses, "closed_statuses": ["done", "archive"]}
        issues = [
            _make_issue(1, "Task A", status="backlog"),
            _make_issue(2, "Task B", status="in-progress"),
            _make_issue(3, "Task C", status="done"),
        ]
        result = render_board(issues, wf, terminal_width=120)
        assert "backlog (1)" in result
        assert "in-progress (1)" in result
        assert "done (1)" in result
        assert "ready (0)" in result
        # Empty columns should show (empty)
        assert "(empty)" in result


class TestRenderBoardEmpty:
    def test_render_board_empty(self):
        """No issues: every column shows (empty)."""
        wf = {"statuses": ["open", "closed"], "closed_statuses": ["closed"]}
        result = render_board([], wf, terminal_width=80)
        assert "open (0)" in result
        assert "closed (0)" in result
        assert "(empty)" in result


class TestRenderBoardNarrowTerminal:
    def test_render_board_narrow_terminal(self):
        """Narrow terminal (40 cols) doesn't crash, min col width is 20."""
        wf = {"statuses": ["open", "closed"], "closed_statuses": ["closed"]}
        issues = [_make_issue(1, "A very long title that should be truncated", status="open")]
        result = render_board(issues, wf, terminal_width=40)
        assert "#1" in result
        # Should not crash
        assert len(result) > 0


class TestRenderBoardWideTerminal:
    def test_render_board_wide_terminal(self):
        """Wide terminal (200 cols) uses more space."""
        wf = {"statuses": ["open", "closed"], "closed_statuses": ["closed"]}
        issues = [_make_issue(1, "Short", status="open")]
        result = render_board(issues, wf, terminal_width=200)
        # Lines should be wider than narrow render
        first_line = result.split("\n")[0]
        assert len(first_line) > 80


class TestRenderBoardIssueGrouping:
    def test_render_board_issue_grouping(self):
        """Issues are correctly grouped by status."""
        wf = {"statuses": ["open", "closed"], "closed_statuses": ["closed"]}
        issues = [
            _make_issue(1, "Open A", status="open"),
            _make_issue(2, "Closed B", status="closed"),
            _make_issue(3, "Open C", status="open"),
        ]
        result = render_board(issues, wf, terminal_width=80)
        lines = result.split("\n")
        # Header should show correct counts
        assert "open (2)" in lines[0]
        assert "closed (1)" in lines[0]


class TestRenderBoardTitleTruncation:
    def test_render_board_title_truncation(self):
        """Long titles are truncated with ellipsis."""
        wf = {"statuses": ["open", "closed"], "closed_statuses": ["closed"]}
        long_title = "A" * 200
        issues = [_make_issue(1, long_title, status="open")]
        result = render_board(issues, wf, terminal_width=60)
        # The full title should NOT appear
        assert long_title not in result
        # But the issue ID should
        assert "#1" in result


# ── CLI tests ────────────────────────────────────────────────────


class TestBoardCLI:
    def _create_issues(self, runner, cli_env):
        runner.invoke(main, ["new", "--title", "Bug fix", "-t", "bug"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Feature A", "-t", "feature"], catch_exceptions=False)
        runner.invoke(main, ["close", "1"], catch_exceptions=False)

    def test_board_cli_command(self, runner, initialized_cli):
        """yait board outputs status column headers."""
        self._create_issues(runner, initialized_cli)
        result = runner.invoke(main, ["board"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "open" in result.output
        assert "closed" in result.output

    def test_board_cli_json(self, runner, initialized_cli):
        """yait board --json outputs valid JSON."""
        self._create_issues(runner, initialized_cli)
        result = runner.invoke(main, ["board", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "open" in data
        assert "closed" in data
        assert isinstance(data["open"], list)
        assert isinstance(data["closed"], list)

    def test_board_not_initialized(self, runner, cli_env):
        """yait board without init reports error."""
        result = runner.invoke(main, ["board"])
        assert result.exit_code != 0


class TestUpdateAlias:
    def test_update_alias(self, runner, initialized_cli):
        """yait update works the same as yait edit."""
        runner.invoke(main, ["new", "--title", "Original title"], catch_exceptions=False)
        result = runner.invoke(
            main, ["update", "1", "--title", "New title"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Updated" in result.output
        # Verify the change took effect
        from yait.store import load_issue
        issue = load_issue(initialized_cli / ".yait", 1)
        assert issue.title == "New title"


class TestWorkflowConfig:
    def test_workflow_config(self, runner, initialized_cli):
        """Set workflow.statuses via config set, then verify board uses them."""
        # Set custom workflow
        result = runner.invoke(
            main,
            ["config", "set", "workflow.statuses", "backlog,ready,in-progress,done,closed"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Set workflow.statuses" in result.output

        # Create issue and check board shows new columns
        runner.invoke(main, ["new", "--title", "Test"], catch_exceptions=False)
        result = runner.invoke(main, ["board", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "backlog" in data
        assert "ready" in data
        assert "in-progress" in data
        assert "done" in data
        assert "closed" in data

    def test_workflow_config_closed_statuses(self, runner, initialized_cli):
        """Set workflow.closed_statuses via config set."""
        result = runner.invoke(
            main,
            ["config", "set", "workflow.closed_statuses", "done,archive"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        # Verify it was saved
        wf = get_workflow(initialized_cli / ".yait")
        assert "done" in wf["closed_statuses"]
        assert "archive" in wf["closed_statuses"]

    def test_workflow_config_invalid_key(self, runner, initialized_cli):
        """Setting an unknown workflow field fails."""
        result = runner.invoke(
            main,
            ["config", "set", "workflow.bogus", "value"],
        )
        assert result.exit_code != 0
