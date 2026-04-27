"""Tests for status-related CLI commands and workflow integration."""
from pathlib import Path

import json
import yaml
import pytest
from click.testing import CliRunner

from yait.cli import main
from yait.store import load_issue, _read_config


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


def _set_extended_workflow(root):
    """Set an extended workflow config on the data dir (.yait/)."""
    config_path = root / ".yait" / "config.yaml"
    cfg = yaml.safe_load(config_path.read_text())
    cfg["workflow"] = {
        "statuses": ["backlog", "open", "in-progress", "in-review", "done", "wontfix"],
        "closed_statuses": ["done", "wontfix"],
    }
    config_path.write_text(yaml.dump(cfg, default_flow_style=False))


@pytest.fixture
def extended_cli(runner, initialized_cli):
    """Initialized CLI env with extended workflow."""
    _set_extended_workflow(initialized_cli)
    return initialized_cli


# ── status command ──────────────────────────────────────────


class TestStatusView:
    def test_status_view(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Test issue"], catch_exceptions=False)
        result = runner.invoke(main, ["status", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "open" in result.output


class TestStatusChange:
    def test_status_change(self, runner: CliRunner, extended_cli):
        runner.invoke(main, ["new", "Test issue"], catch_exceptions=False)
        result = runner.invoke(main, ["status", "1", "in-progress"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "in-progress" in result.output
        issue = load_issue(extended_cli / ".yait", 1)
        assert issue.status == "in-progress"


class TestStatusInvalid:
    def test_status_invalid(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Test issue"], catch_exceptions=False)
        result = runner.invoke(main, ["status", "1", "invalid"])
        assert result.exit_code != 0
        assert "Invalid status" in result.output


class TestStatusJson:
    def test_status_json(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Test issue"], catch_exceptions=False)
        result = runner.invoke(main, ["status", "1", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == 1
        assert data["status"] == "open"


# ── close/reopen with workflow ──────────────────────────────


class TestCloseDefaultWorkflow:
    def test_close_default_workflow(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Test issue"], catch_exceptions=False)
        result = runner.invoke(main, ["close", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Closed" in result.output
        issue = load_issue(initialized_cli / ".yait", 1)
        assert issue.status == "closed"


class TestCloseExtendedWorkflow:
    def test_close_extended_workflow(self, runner: CliRunner, extended_cli):
        runner.invoke(main, ["new", "Test issue"], catch_exceptions=False)
        result = runner.invoke(main, ["close", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Closed" in result.output
        issue = load_issue(extended_cli / ".yait", 1)
        assert issue.status == "done"


class TestReopenDefaultWorkflow:
    def test_reopen_default_workflow(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Test issue"], catch_exceptions=False)
        runner.invoke(main, ["close", "1"], catch_exceptions=False)
        result = runner.invoke(main, ["reopen", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Reopened" in result.output
        issue = load_issue(initialized_cli / ".yait", 1)
        assert issue.status == "open"


class TestReopenExtendedWorkflow:
    def test_reopen_extended_workflow(self, runner: CliRunner, extended_cli):
        runner.invoke(main, ["new", "Test issue"], catch_exceptions=False)
        runner.invoke(main, ["close", "1"], catch_exceptions=False)
        result = runner.invoke(main, ["reopen", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Reopened" in result.output
        issue = load_issue(extended_cli / ".yait", 1)
        assert issue.status == "backlog"


# ── edit with status ──────────────────────────────────────


class TestEditStatus:
    def test_edit_status(self, runner: CliRunner, extended_cli):
        runner.invoke(main, ["new", "Test issue"], catch_exceptions=False)
        result = runner.invoke(main, ["edit", "1", "-s", "in-review"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated" in result.output
        issue = load_issue(extended_cli / ".yait", 1)
        assert issue.status == "in-review"

    def test_edit_status_invalid(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Test issue"], catch_exceptions=False)
        result = runner.invoke(main, ["edit", "1", "-s", "invalid"])
        assert result.exit_code != 0
        assert "Invalid status" in result.output


# ── list with status filter ──────────────────────────────


class TestListStatusFilter:
    def test_list_status_filter(self, runner: CliRunner, extended_cli):
        runner.invoke(main, ["new", "Issue A"], catch_exceptions=False)
        runner.invoke(main, ["status", "1", "in-progress"], catch_exceptions=False)
        runner.invoke(main, ["new", "Issue B"], catch_exceptions=False)
        result = runner.invoke(main, ["list", "--status", "in-progress"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Issue A" in result.output
        assert "Issue B" not in result.output


class TestListStatusOpenExtended:
    def test_list_status_open_extended(self, runner: CliRunner, extended_cli):
        """In extended workflow, --status open should match all non-closed statuses."""
        runner.invoke(main, ["new", "Backlog item"], catch_exceptions=False)
        # New issues start as "open", move one to in-progress
        runner.invoke(main, ["new", "In progress item"], catch_exceptions=False)
        runner.invoke(main, ["status", "2", "in-progress"], catch_exceptions=False)
        runner.invoke(main, ["new", "Done item"], catch_exceptions=False)
        runner.invoke(main, ["close", "3"], catch_exceptions=False)

        result = runner.invoke(main, ["list", "--status", "open"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Backlog item" in result.output
        assert "In progress item" in result.output
        assert "Done item" not in result.output


# ── bulk status ──────────────────────────────────────────


class TestBulkStatus:
    def test_bulk_status(self, runner: CliRunner, extended_cli):
        runner.invoke(main, ["new", "Issue A"], catch_exceptions=False)
        runner.invoke(main, ["new", "Issue B"], catch_exceptions=False)
        runner.invoke(main, ["new", "Issue C"], catch_exceptions=False)
        result = runner.invoke(main, ["bulk", "status", "done", "1", "2", "3"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 3 issues." in result.output
        for i in range(1, 4):
            assert load_issue(extended_cli / ".yait", i).status == "done"

    def test_bulk_status_invalid(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Issue A"], catch_exceptions=False)
        result = runner.invoke(main, ["bulk", "status", "invalid", "1"])
        assert result.exit_code != 0
        assert "Invalid status" in result.output

    def test_bulk_status_nonexistent_id(self, runner: CliRunner, extended_cli):
        runner.invoke(main, ["new", "Issue A"], catch_exceptions=False)
        result = runner.invoke(main, ["bulk", "status", "done", "1", "999"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 1 issues. Failed: 1." in result.output


# ── stats with extended workflow ──────────────────────────


class TestStatsExtendedWorkflow:
    def test_stats_extended_workflow(self, runner: CliRunner, extended_cli):
        runner.invoke(main, ["new", "Issue A"], catch_exceptions=False)
        runner.invoke(main, ["new", "Issue B"], catch_exceptions=False)
        runner.invoke(main, ["status", "1", "in-progress"], catch_exceptions=False)
        runner.invoke(main, ["close", "2"], catch_exceptions=False)

        result = runner.invoke(main, ["stats"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "2 total" in result.output
        assert "1 open" in result.output
        assert "1 closed" in result.output

    def test_stats_json_has_by_status(self, runner: CliRunner, extended_cli):
        runner.invoke(main, ["new", "Issue A"], catch_exceptions=False)
        runner.invoke(main, ["status", "1", "in-progress"], catch_exceptions=False)
        result = runner.invoke(main, ["stats", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "by_status" in data
        assert "in-progress" in data["by_status"]
