from pathlib import Path

import json
import pytest
from click.testing import CliRunner

from yait.cli import main
from yait.store import load_issue, load_milestone, list_milestones, save_template, load_template, list_templates


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


class TestInit:
    def test_init_creates_store(self, runner: CliRunner, cli_env):
        result = runner.invoke(main, ["init"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Initialized" in result.output
        assert (cli_env / ".yait" / "issues").is_dir()
        assert (cli_env / ".yait" / "config.yaml").exists()


class TestNew:
    def test_new_creates_issue(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(
            main, ["new", "--title", "test issue"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert "#1" in result.output

    def test_new_with_body_and_labels(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(
            main,
            ["new", "--title", "Labeled", "-b", "body text", "-l", "bug", "-l", "urgent", "-a", "alice"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.labels == ["bug", "urgent"]
        assert issue.assignee == "alice"
        assert issue.body == "body text"

    def test_new_without_title_fails(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["new"])
        assert result.exit_code != 0

    def test_new_with_type(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(
            main, ["new", "--title", "A bug", "--type", "bug"], catch_exceptions=False
        )
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.type == "bug"

    def test_new_default_type(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(
            main, ["new", "--title", "Something"], catch_exceptions=False
        )
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.type == "misc"


class TestList:
    def test_list_shows_issues(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "my issue"], catch_exceptions=False)
        result = runner.invoke(main, ["list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "my issue" in result.output
        assert "#1" in result.output

    def test_list_empty(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "No issues found" in result.output

    def test_list_filter_by_status(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Bug A", "-l", "bug"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Feature B", "-l", "feature"], catch_exceptions=False)
        runner.invoke(main, ["close", "1"], catch_exceptions=False)

        result = runner.invoke(main, ["list", "--status", "open"], catch_exceptions=False)
        assert "Feature B" in result.output
        assert "Bug A" not in result.output

        result = runner.invoke(main, ["list", "--status", "closed"], catch_exceptions=False)
        assert "Bug A" in result.output
        assert "Feature B" not in result.output

    def test_list_filter_by_type(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "A bug", "--type", "bug"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "A feature", "--type", "feature"], catch_exceptions=False)
        result = runner.invoke(main, ["list", "--type", "bug"], catch_exceptions=False)
        assert "A bug" in result.output
        assert "A feature" not in result.output

    def test_list_shows_type_column(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Test", "--type", "bug"], catch_exceptions=False)
        result = runner.invoke(main, ["list"], catch_exceptions=False)
        assert "TYPE" in result.output


class TestShow:
    def test_show_displays_details(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["new", "--title", "detail test", "-b", "Details here"], catch_exceptions=False
        )
        result = runner.invoke(main, ["show", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "detail test" in result.output
        assert "Details here" in result.output

    def test_show_nonexistent(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["show", "999"])
        assert result.exit_code != 0

    def test_show_displays_type(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["new", "--title", "Typed issue", "--type", "bug"], catch_exceptions=False
        )
        result = runner.invoke(main, ["show", "1"], catch_exceptions=False)
        assert "Type: bug" in result.output


class TestCloseReopen:
    def test_close_and_reopen(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "To close"], catch_exceptions=False)

        result = runner.invoke(main, ["close", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Closed" in result.output
        assert load_issue(initialized_cli, 1).status == "closed"

        result = runner.invoke(main, ["reopen", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Reopened" in result.output
        assert load_issue(initialized_cli, 1).status == "open"


class TestComment:
    def test_comment_appends(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Commentable"], catch_exceptions=False)
        result = runner.invoke(
            main, ["comment", "1", "-m", "This is a note"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert "comment" in result.output.lower()
        issue = load_issue(initialized_cli, 1)
        assert "This is a note" in issue.body


class TestLabel:
    def test_label_add(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Needs labels"], catch_exceptions=False)
        result = runner.invoke(main, ["label", "add", "1", "bug"], catch_exceptions=False)
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert "bug" in issue.labels

    def test_label_remove(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["new", "--title", "Has label", "-l", "bug"], catch_exceptions=False
        )
        result = runner.invoke(main, ["label", "remove", "1", "bug"], catch_exceptions=False)
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert "bug" not in issue.labels

    def test_label_add_duplicate(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Test"], catch_exceptions=False)
        runner.invoke(main, ["label", "add", "1", "bug"], catch_exceptions=False)
        result = runner.invoke(main, ["label", "add", "1", "bug"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "already" in result.output.lower()
        issue = load_issue(initialized_cli, 1)
        assert issue.labels.count("bug") == 1


class TestSearch:
    def test_search_by_title(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["new", "--title", "Login bug", "-b", "Safari crashes"], catch_exceptions=False
        )
        runner.invoke(main, ["new", "--title", "Signup feature"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "login"], catch_exceptions=False)
        assert "Login bug" in result.output
        assert "Signup" not in result.output

    def test_search_no_match(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Something"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "nonexistent"], catch_exceptions=False)
        assert "No matching" in result.output

    def test_search_with_type_filter(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["new", "--title", "Login bug", "--type", "bug"], catch_exceptions=False
        )
        runner.invoke(
            main, ["new", "--title", "Login feature", "--type", "feature"], catch_exceptions=False
        )
        result = runner.invoke(
            main, ["search", "login", "--type", "bug"], catch_exceptions=False
        )
        assert "Login bug" in result.output
        assert "Login feature" not in result.output


class TestCloseMultiple:
    def test_close_multiple(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Issue A"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Issue B"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Issue C"], catch_exceptions=False)

        result = runner.invoke(main, ["close", "1", "2", "3"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Closed issue #1" in result.output
        assert "Closed issue #2" in result.output
        assert "Closed issue #3" in result.output
        assert load_issue(initialized_cli, 1).status == "closed"
        assert load_issue(initialized_cli, 2).status == "closed"
        assert load_issue(initialized_cli, 3).status == "closed"


class TestReopenMultiple:
    def test_reopen_multiple(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Issue A"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Issue B"], catch_exceptions=False)
        runner.invoke(main, ["close", "1", "2"], catch_exceptions=False)

        result = runner.invoke(main, ["reopen", "1", "2"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Reopened issue #1" in result.output
        assert "Reopened issue #2" in result.output
        assert load_issue(initialized_cli, 1).status == "open"
        assert load_issue(initialized_cli, 2).status == "open"


class TestListJson:
    def test_list_json(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "JSON test", "--type", "bug", "-l", "urgent"], catch_exceptions=False)
        result = runner.invoke(main, ["list", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["title"] == "JSON test"
        assert data[0]["type"] == "bug"
        assert data[0]["labels"] == ["urgent"]
        assert data[0]["status"] == "open"


class TestShowJson:
    def test_show_json(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Detail JSON", "-b", "body text", "--type", "feature"], catch_exceptions=False)
        result = runner.invoke(main, ["show", "1", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == 1
        assert data["title"] == "Detail JSON"
        assert data["body"] == "body text"
        assert data["type"] == "feature"


class TestSearchJson:
    def test_search_json(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Login bug"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Signup feature"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "login", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["title"] == "Login bug"


class TestStats:
    def test_stats(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Bug 1", "--type", "bug", "-l", "urgent"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Bug 2", "--type", "bug", "-l", "urgent", "-l", "backend"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Feature 1", "--type", "feature"], catch_exceptions=False)
        runner.invoke(main, ["close", "3"], catch_exceptions=False)

        result = runner.invoke(main, ["stats"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "3 total" in result.output
        assert "2 open" in result.output
        assert "1 closed" in result.output
        assert "bug=2" in result.output
        assert "feature=1" in result.output
        assert "urgent=2" in result.output
        assert "backend=1" in result.output
        # Enhanced: priority and assignee/milestone dimensions
        assert "By priority:" in result.output
        assert "By milestone:" in result.output
        assert "By assignee:" in result.output

    def test_stats_with_priority_milestone_assignee(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "A", "--type", "bug", "--priority", "p0"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "B", "--type", "feature", "--priority", "p1", "--milestone", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "C", "--type", "bug", "--priority", "p0", "--milestone", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["assign", "1", "alice"], catch_exceptions=False)
        runner.invoke(main, ["assign", "2", "alice"], catch_exceptions=False)
        runner.invoke(main, ["assign", "3", "bob"], catch_exceptions=False)
        runner.invoke(main, ["close", "2"], catch_exceptions=False)

        result = runner.invoke(main, ["stats"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "3 total" in result.output
        assert "p0=2" in result.output
        assert "p1=1" in result.output
        assert "v1.0" in result.output
        assert "alice" in result.output
        assert "bob" in result.output

    def test_stats_json(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "A", "--type", "bug", "--priority", "p0"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "B", "--type", "feature", "--milestone", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["close", "1"], catch_exceptions=False)

        result = runner.invoke(main, ["stats", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 2
        assert data["open"] == 1
        assert data["closed"] == 1
        assert "bug" in data["by_type"]
        assert "p0" in data["by_priority"]
        assert "v1.0" in data["by_milestone"]
        assert "(none)" in data["by_assignee"]

    def test_stats_json_empty(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["stats", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 0

    def test_stats_by_milestone(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "A", "--milestone", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "B", "--milestone", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "C"], catch_exceptions=False)
        runner.invoke(main, ["close", "2"], catch_exceptions=False)

        result = runner.invoke(main, ["stats", "--by", "milestone"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "v1.0" in result.output
        assert "(none)" in result.output
        assert "50%" in result.output

    def test_stats_by_assignee(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "A"], catch_exceptions=False)
        runner.invoke(main, ["assign", "1", "alice"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "B"], catch_exceptions=False)

        result = runner.invoke(main, ["stats", "--by", "assignee"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "alice" in result.output
        assert "(none)" in result.output

    def test_stats_by_priority(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "A", "--priority", "p0"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "B", "--priority", "p1"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "C", "--priority", "p1"], catch_exceptions=False)

        result = runner.invoke(main, ["stats", "--by", "priority"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "p0=1" in result.output
        assert "p1=2" in result.output

    def test_stats_by_type(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "A", "--type", "bug"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "B", "--type", "feature"], catch_exceptions=False)

        result = runner.invoke(main, ["stats", "--by", "type"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "bug=1" in result.output
        assert "feature=1" in result.output

    def test_stats_by_json_dimension(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "A", "--priority", "p0"], catch_exceptions=False)

        result = runner.invoke(main, ["stats", "--json", "--by", "priority"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "by_priority" in data
        assert data["by_priority"]["p0"] == 1


class TestListSort:
    def test_list_sort_by_created(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "First"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Second"], catch_exceptions=False)
        result = runner.invoke(main, ["list", "--sort", "created", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["title"] == "First"
        assert data[1]["title"] == "Second"


class TestPositionalTitle:
    def test_new_positional_title(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["new", "Fix bug"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "#1" in result.output
        issue = load_issue(initialized_cli, 1)
        assert issue.title == "Fix bug"

    def test_new_option_title_compat(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["new", "--title", "Option title"], catch_exceptions=False)
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.title == "Option title"

    def test_new_no_title_fails(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["new"])
        assert result.exit_code != 0


class TestAssignUnassign:
    def test_assign(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Test"], catch_exceptions=False)
        result = runner.invoke(main, ["assign", "1", "alice"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Assigned" in result.output
        issue = load_issue(initialized_cli, 1)
        assert issue.assignee == "alice"

    def test_unassign(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Test", "-a", "alice"], catch_exceptions=False)
        result = runner.invoke(main, ["unassign", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Unassigned" in result.output
        issue = load_issue(initialized_cli, 1)
        assert issue.assignee is None


class TestInlineEdit:
    def test_edit_inline_title(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Old title"], catch_exceptions=False)
        result = runner.invoke(main, ["edit", "1", "-T", "New title"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated" in result.output
        issue = load_issue(initialized_cli, 1)
        assert issue.title == "New title"

    def test_edit_inline_type(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Test"], catch_exceptions=False)
        result = runner.invoke(main, ["edit", "1", "-t", "bug"], catch_exceptions=False)
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.type == "bug"


class TestSearchDefaultOpen:
    def test_search_defaults_to_open(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Open issue"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Closed issue"], catch_exceptions=False)
        runner.invoke(main, ["close", "2"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "issue"], catch_exceptions=False)
        assert "Open issue" in result.output
        assert "Closed issue" not in result.output

    def test_search_all_status(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Open issue"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Closed issue"], catch_exceptions=False)
        runner.invoke(main, ["close", "2"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "issue", "--status", "all"], catch_exceptions=False)
        assert "Open issue" in result.output
        assert "Closed issue" in result.output


class TestAdvancedSearch:
    """Tests for advanced search features: filters, regex, title-only, count."""

    def test_search_with_label_filter(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Auth bug", "-l", "auth"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Auth feature", "-l", "ui"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "auth", "--label", "auth"], catch_exceptions=False)
        assert "Auth bug" in result.output
        assert "Auth feature" not in result.output

    def test_search_with_priority_filter(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Critical crash", "--priority", "p0"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Minor crash", "--priority", "p2"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "crash", "--priority", "p0"], catch_exceptions=False)
        assert "Critical crash" in result.output
        assert "Minor crash" not in result.output

    def test_search_with_assignee_filter(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Alice task"], catch_exceptions=False)
        runner.invoke(main, ["assign", "1", "alice"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Bob task"], catch_exceptions=False)
        runner.invoke(main, ["assign", "2", "bob"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "task", "--assignee", "alice"], catch_exceptions=False)
        assert "Alice task" in result.output
        assert "Bob task" not in result.output

    def test_search_with_milestone_filter(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "V1 bug", "--milestone", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "V2 bug", "--milestone", "v2.0"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "bug", "--milestone", "v1.0"], catch_exceptions=False)
        assert "V1 bug" in result.output
        assert "V2 bug" not in result.output

    def test_search_combined_filters(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Login crash", "--type", "bug", "--priority", "p0", "-l", "auth"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Login slow", "--type", "bug", "--priority", "p2", "-l", "auth"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Login redesign", "--type", "feature", "--priority", "p0", "-l", "ui"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "login", "--type", "bug", "--priority", "p0", "--label", "auth"], catch_exceptions=False)
        assert "Login crash" in result.output
        assert "Login slow" not in result.output
        assert "Login redesign" not in result.output

    def test_search_regex(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "OOM error"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "crash dump"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "slow query"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "crash|oom", "--regex", "--status", "all"], catch_exceptions=False)
        assert "OOM error" in result.output
        assert "crash dump" in result.output
        assert "slow query" not in result.output

    def test_search_regex_invalid(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["search", "[invalid", "--regex"], catch_exceptions=False)
        assert result.exit_code != 0
        assert "Invalid regex" in result.output

    def test_search_regex_in_body(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Normal title", "-b", "segfault at 0x0"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Other issue", "-b", "nothing special"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "seg.*0x", "--regex"], catch_exceptions=False)
        assert "Normal title" in result.output
        assert "Other issue" not in result.output

    def test_search_title_only(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Login page", "-b", "crash on submit"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Crash handler", "-b", "login related"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "login", "--title-only"], catch_exceptions=False)
        assert "Login page" in result.output
        assert "Crash handler" not in result.output

    def test_search_title_only_with_regex(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "OOM bug", "-b", "crash details"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Normal bug", "-b", "OOM in logs"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "oom", "--regex", "--title-only"], catch_exceptions=False)
        assert "OOM bug" in result.output
        assert "Normal bug" not in result.output

    def test_search_count(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Bug one"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Bug two"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Feature one"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "bug", "--count"], catch_exceptions=False)
        assert result.exit_code == 0
        assert '2 issues match "bug"' in result.output

    def test_search_count_no_query(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Issue A"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "Issue B"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "--count", "--label", "nonexistent"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "0 issues match" in result.output

    def test_search_no_query_with_filters(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "P0 issue", "--priority", "p0"], catch_exceptions=False)
        runner.invoke(main, ["new", "--title", "P2 issue", "--priority", "p2"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "--priority", "p0"], catch_exceptions=False)
        assert "P0 issue" in result.output
        assert "P2 issue" not in result.output


class TestVersion:
    def test_version_flag(self, runner: CliRunner):
        result = runner.invoke(main, ["--version"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "0.3.1" in result.output


class TestShowCommentCount:
    def test_show_comment_count(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Commentable"], catch_exceptions=False)
        runner.invoke(main, ["comment", "1", "-m", "First note"], catch_exceptions=False)
        runner.invoke(main, ["comment", "1", "-m", "Second note"], catch_exceptions=False)
        result = runner.invoke(main, ["show", "1"], catch_exceptions=False)
        assert "Comments: 2" in result.output

    def test_show_zero_comments(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "No comments"], catch_exceptions=False)
        result = runner.invoke(main, ["show", "1"], catch_exceptions=False)
        assert "Comments: 0" in result.output


class TestEmptyStateGuidance:
    def test_list_empty_shows_guidance(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "yait new" in result.output


class TestLog:
    def test_log_command(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "Log test"], catch_exceptions=False)
        result = runner.invoke(main, ["log", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0

    def test_log_all(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "--title", "First"], catch_exceptions=False)
        result = runner.invoke(main, ["log"], catch_exceptions=False)
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0


class TestBodyFile:
    def test_body_from_file(self, runner: CliRunner, initialized_cli, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("Body from file")
        result = runner.invoke(
            main, ["new", "file test", "--body-file", str(body_file)], catch_exceptions=False
        )
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.body == "Body from file"

    def test_body_from_stdin(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(
            main, ["new", "stdin test", "--body", "-"], input="Body from stdin\n", catch_exceptions=False
        )
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.body == "Body from stdin"

    def test_body_and_body_file_conflict(self, runner: CliRunner, initialized_cli, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("file body")
        result = runner.invoke(
            main, ["new", "test", "--body", "inline", "--body-file", str(body_file)]
        )
        assert result.exit_code != 0
        assert "Cannot use both" in result.output

    def test_comment_from_file(self, runner: CliRunner, initialized_cli, tmp_path):
        runner.invoke(main, ["new", "test"], catch_exceptions=False)
        msg_file = tmp_path / "comment.md"
        msg_file.write_text("Comment from file")
        result = runner.invoke(
            main, ["comment", "1", "--message-file", str(msg_file)], catch_exceptions=False
        )
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert "Comment from file" in issue.body

    def test_comment_from_stdin(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "test"], catch_exceptions=False)
        result = runner.invoke(
            main, ["comment", "1", "-m", "-"], input="Comment from stdin\n", catch_exceptions=False
        )
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert "Comment from stdin" in issue.body

    def test_message_and_message_file_conflict(self, runner: CliRunner, initialized_cli, tmp_path):
        runner.invoke(main, ["new", "test"], catch_exceptions=False)
        msg_file = tmp_path / "comment.md"
        msg_file.write_text("file msg")
        result = runner.invoke(
            main, ["comment", "1", "-m", "inline", "--message-file", str(msg_file)]
        )
        assert result.exit_code != 0
        assert "Cannot use both" in result.output


class TestExport:
    def test_export_json_stdout(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Bug A", "-t", "bug"], catch_exceptions=False)
        runner.invoke(main, ["new", "Feature B", "-t", "feature"], catch_exceptions=False)
        result = runner.invoke(main, ["export"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["title"] == "Bug A"
        assert data[1]["title"] == "Feature B"

    def test_export_csv_stdout(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Bug A", "-t", "bug", "-l", "urgent"], catch_exceptions=False)
        result = runner.invoke(main, ["export", "--format", "csv"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Bug A" in result.output
        assert "urgent" in result.output
        assert "id,title,status" in result.output

    def test_export_to_file(self, runner: CliRunner, initialized_cli, tmp_path):
        runner.invoke(main, ["new", "Test"], catch_exceptions=False)
        outfile = tmp_path / "out.json"
        result = runner.invoke(main, ["export", "-o", str(outfile)], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Exported 1 issues" in result.output
        data = json.loads(outfile.read_text())
        assert len(data) == 1


class TestImport:
    def _export_json(self, runner, initialized_cli):
        result = runner.invoke(main, ["export"], catch_exceptions=False)
        return result.output

    def test_import_json(self, runner: CliRunner, initialized_cli, yait_root, tmp_path, monkeypatch):
        runner.invoke(main, ["new", "Issue 1", "-t", "bug"], catch_exceptions=False)
        runner.invoke(main, ["new", "Issue 2", "-t", "feature"], catch_exceptions=False)
        export_data = self._export_json(runner, initialized_cli)

        # Create a new yait repo in tmp dir
        import subprocess
        new_root = tmp_path / "import_test"
        new_root.mkdir()
        subprocess.run(["git", "init"], cwd=new_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=new_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=new_root, check=True, capture_output=True)
        monkeypatch.chdir(new_root)
        runner.invoke(main, ["init"], catch_exceptions=False)

        import_file = tmp_path / "issues.json"
        import_file.write_text(export_data)
        result = runner.invoke(main, ["import", str(import_file)], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Imported 2" in result.output
        issue = load_issue(new_root, 1)
        assert issue.title == "Issue 1"

    def test_import_skip_duplicates(self, runner: CliRunner, initialized_cli, tmp_path):
        runner.invoke(main, ["new", "Existing"], catch_exceptions=False)
        data = [{"id": 1, "title": "Duplicate", "status": "open", "type": "misc",
                 "priority": "none", "labels": [], "assignee": None,
                 "created_at": "", "updated_at": "", "body": ""},
                {"id": 2, "title": "New one", "status": "open", "type": "misc",
                 "priority": "none", "labels": [], "assignee": None,
                 "created_at": "", "updated_at": "", "body": ""}]
        import_file = tmp_path / "issues.json"
        import_file.write_text(json.dumps(data))
        result = runner.invoke(main, ["import", str(import_file)], catch_exceptions=False)
        assert result.exit_code == 0
        assert "skipped 1" in result.output
        assert "Imported 1" in result.output


# ---------------------------------------------------------------------------
# Milestone CLI tests
# ---------------------------------------------------------------------------


class TestMilestoneCreate:
    def test_create(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(
            main,
            ["milestone", "create", "v1.0", "--description", "First release", "--due", "2026-06-01"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Created milestone 'v1.0'" in result.output
        m = load_milestone(initialized_cli, "v1.0")
        assert m.description == "First release"
        assert m.due_date == "2026-06-01"

    def test_create_minimal(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(
            main, ["milestone", "create", "v2.0"], catch_exceptions=False,
        )
        assert result.exit_code == 0
        m = load_milestone(initialized_cli, "v2.0")
        assert m.status == "open"
        assert m.description == ""

    def test_create_duplicate(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_create_invalid_due_date(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(
            main, ["milestone", "create", "v1.0", "--due", "not-a-date"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "Invalid due_date" in result.output


class TestMilestoneList:
    def test_list_empty(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["milestone", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "No milestones found" in result.output

    def test_list_with_milestones(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0", "--due", "2026-06-01"], catch_exceptions=False)
        runner.invoke(main, ["milestone", "create", "v2.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "v1.0" in result.output
        assert "v2.0" in result.output
        assert "MILESTONE" in result.output

    def test_list_filter_status(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["milestone", "create", "v2.0"], catch_exceptions=False)
        runner.invoke(main, ["milestone", "close", "v2.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "list", "--status", "open"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "v1.0" in result.output
        assert "v2.0" not in result.output

    def test_list_json(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "list", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "v1.0"

    def test_list_shows_issue_counts(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["new", "Issue A", "--milestone", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["new", "Issue B", "--milestone", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["close", "2"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        # Should show 1 open, 1 closed, 50%
        assert "1" in result.output
        assert "50%" in result.output


class TestMilestoneShow:
    def test_show(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main,
            ["milestone", "create", "v1.0", "--description", "Release", "--due", "2026-06-01"],
            catch_exceptions=False,
        )
        runner.invoke(main, ["new", "Task A", "--milestone", "v1.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "show", "v1.0"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Milestone: v1.0" in result.output
        assert "Release" in result.output
        assert "2026-06-01" in result.output
        assert "1 total" in result.output
        assert "Task A" in result.output

    def test_show_not_found(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["milestone", "show", "nope"], catch_exceptions=False)
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_show_json(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["new", "Task A", "--milestone", "v1.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "show", "v1.0", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "v1.0"
        assert data["issues"]["total"] == 1
        assert data["issues"]["open"] == 1

    def test_show_no_issues(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "show", "v1.0"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "0 total" in result.output


class TestMilestoneClose:
    def test_close(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "close", "v1.0"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Closed milestone" in result.output
        m = load_milestone(initialized_cli, "v1.0")
        assert m.status == "closed"

    def test_close_already_closed(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["milestone", "close", "v1.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "close", "v1.0"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "already closed" in result.output

    def test_close_not_found(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["milestone", "close", "nope"], catch_exceptions=False)
        assert result.exit_code != 0
        assert "not found" in result.output


class TestMilestoneReopen:
    def test_reopen(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["milestone", "close", "v1.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "reopen", "v1.0"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Reopened milestone" in result.output
        m = load_milestone(initialized_cli, "v1.0")
        assert m.status == "open"

    def test_reopen_already_open(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "reopen", "v1.0"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "already open" in result.output

    def test_reopen_not_found(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["milestone", "reopen", "nope"], catch_exceptions=False)
        assert result.exit_code != 0
        assert "not found" in result.output


class TestMilestoneEdit:
    def test_edit_description(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0", "--description", "Old"], catch_exceptions=False)
        result = runner.invoke(
            main, ["milestone", "edit", "v1.0", "--description", "Updated"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Updated milestone" in result.output
        m = load_milestone(initialized_cli, "v1.0")
        assert m.description == "Updated"

    def test_edit_due(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        result = runner.invoke(
            main, ["milestone", "edit", "v1.0", "--due", "2026-07-01"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        m = load_milestone(initialized_cli, "v1.0")
        assert m.due_date == "2026-07-01"

    def test_edit_nothing(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "edit", "v1.0"], catch_exceptions=False)
        assert result.exit_code != 0
        assert "Nothing to edit" in result.output

    def test_edit_not_found(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(
            main, ["milestone", "edit", "nope", "--description", "x"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_edit_invalid_due(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        result = runner.invoke(
            main, ["milestone", "edit", "v1.0", "--due", "bad"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "Invalid due_date" in result.output


class TestMilestoneDelete:
    def test_delete_no_refs(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "delete", "v1.0"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Deleted milestone" in result.output
        assert list_milestones(initialized_cli) == []

    def test_delete_with_refs_fails(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["new", "Task A", "--milestone", "v1.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "delete", "v1.0"], catch_exceptions=False)
        assert result.exit_code != 0
        assert "Cannot delete" in result.output
        assert "--force" in result.output

    def test_delete_force(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
        runner.invoke(main, ["new", "Task A", "--milestone", "v1.0"], catch_exceptions=False)
        result = runner.invoke(main, ["milestone", "delete", "v1.0", "--force"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Deleted milestone" in result.output
        assert list_milestones(initialized_cli) == []
        issue = load_issue(initialized_cli, 1)
        assert issue.milestone is None

    def test_delete_not_found(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["milestone", "delete", "nope"], catch_exceptions=False)
        assert result.exit_code != 0
        assert "not found" in result.output

# ── Bulk Commands ──────────────────────────────────────────


def _create_issues(runner, n=3):
    """Helper: create n issues."""
    for i in range(1, n + 1):
        runner.invoke(main, ["new", f"Issue {i}"], catch_exceptions=False)


class TestBulkLabelAdd:
    def test_basic(self, runner: CliRunner, initialized_cli):
        _create_issues(runner, 3)
        result = runner.invoke(main, ["bulk", "label", "add", "urgent", "1", "2", "3"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 3 issues. Failed: 0." in result.output
        for i in range(1, 4):
            assert "urgent" in load_issue(initialized_cli, i).labels

    def test_skip_duplicate(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Test", "-l", "urgent"], catch_exceptions=False)
        result = runner.invoke(main, ["bulk", "label", "add", "urgent", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "already" in result.output
        assert "Updated 0 issues. Failed: 0." in result.output
        assert load_issue(initialized_cli, 1).labels.count("urgent") == 1

    def test_nonexistent_id(self, runner: CliRunner, initialized_cli):
        _create_issues(runner, 1)
        result = runner.invoke(main, ["bulk", "label", "add", "urgent", "1", "999"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 1 issues. Failed: 1." in result.output
        assert "urgent" in load_issue(initialized_cli, 1).labels


class TestBulkLabelRemove:
    def test_basic(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "A", "-l", "urgent"], catch_exceptions=False)
        runner.invoke(main, ["new", "B", "-l", "urgent"], catch_exceptions=False)
        result = runner.invoke(main, ["bulk", "label", "remove", "urgent", "1", "2"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 2 issues. Failed: 0." in result.output
        for i in range(1, 3):
            assert "urgent" not in load_issue(initialized_cli, i).labels

    def test_skip_missing_label(self, runner: CliRunner, initialized_cli):
        _create_issues(runner, 1)
        result = runner.invoke(main, ["bulk", "label", "remove", "nope", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "does not have" in result.output
        assert "Updated 0 issues. Failed: 0." in result.output

    def test_nonexistent_id(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["bulk", "label", "remove", "x", "999"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 0 issues. Failed: 1." in result.output


class TestBulkAssign:
    def test_basic(self, runner: CliRunner, initialized_cli):
        _create_issues(runner, 3)
        result = runner.invoke(main, ["bulk", "assign", "alice", "1", "2", "3"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 3 issues. Failed: 0." in result.output
        for i in range(1, 4):
            assert load_issue(initialized_cli, i).assignee == "alice"

    def test_nonexistent_id(self, runner: CliRunner, initialized_cli):
        _create_issues(runner, 1)
        result = runner.invoke(main, ["bulk", "assign", "bob", "1", "999"], catch_exceptions=False)
        assert "Updated 1 issues. Failed: 1." in result.output


class TestBulkUnassign:
    def test_basic(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "A", "-a", "alice"], catch_exceptions=False)
        runner.invoke(main, ["new", "B", "-a", "bob"], catch_exceptions=False)
        result = runner.invoke(main, ["bulk", "unassign", "1", "2"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 2 issues. Failed: 0." in result.output
        for i in range(1, 3):
            assert load_issue(initialized_cli, i).assignee is None

    def test_nonexistent_id(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["bulk", "unassign", "999"], catch_exceptions=False)
        assert "Updated 0 issues. Failed: 1." in result.output


class TestBulkPriority:
    def test_basic(self, runner: CliRunner, initialized_cli):
        _create_issues(runner, 2)
        result = runner.invoke(main, ["bulk", "priority", "p0", "1", "2"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 2 issues. Failed: 0." in result.output
        for i in range(1, 3):
            assert load_issue(initialized_cli, i).priority == "p0"

    def test_invalid_priority(self, runner: CliRunner, initialized_cli):
        _create_issues(runner, 1)
        result = runner.invoke(main, ["bulk", "priority", "invalid", "1"])
        assert result.exit_code != 0

    def test_nonexistent_id(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["bulk", "priority", "p1", "999"], catch_exceptions=False)
        assert "Updated 0 issues. Failed: 1." in result.output


class TestBulkMilestone:
    def test_basic(self, runner: CliRunner, initialized_cli):
        _create_issues(runner, 2)
        result = runner.invoke(main, ["bulk", "milestone", "v1.0", "1", "2"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 2 issues. Failed: 0." in result.output
        for i in range(1, 3):
            assert load_issue(initialized_cli, i).milestone == "v1.0"

    def test_nonexistent_id(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["bulk", "milestone", "v2.0", "999"], catch_exceptions=False)
        assert "Updated 0 issues. Failed: 1." in result.output


class TestBulkType:
    def test_basic(self, runner: CliRunner, initialized_cli):
        _create_issues(runner, 2)
        result = runner.invoke(main, ["bulk", "type", "bug", "1", "2"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 2 issues. Failed: 0." in result.output
        for i in range(1, 3):
            assert load_issue(initialized_cli, i).type == "bug"

    def test_invalid_type(self, runner: CliRunner, initialized_cli):
        _create_issues(runner, 1)
        result = runner.invoke(main, ["bulk", "type", "invalid", "1"])
        assert result.exit_code != 0

    def test_nonexistent_id(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["bulk", "type", "feature", "999"], catch_exceptions=False)
        assert "Updated 0 issues. Failed: 1." in result.output


# ── Bulk Filter Mode ──────────────────────────────────────


def _create_typed_issues(runner):
    """Create a set of issues with varied attributes for filter testing."""
    runner.invoke(main, ["new", "Bug A", "-t", "bug", "-p", "p0", "-l", "urgent", "-a", "alice"], catch_exceptions=False)
    runner.invoke(main, ["new", "Bug B", "-t", "bug", "-p", "p1", "-l", "urgent", "-a", "bob"], catch_exceptions=False)
    runner.invoke(main, ["new", "Feature C", "-t", "feature", "-p", "p2", "-a", "alice"], catch_exceptions=False)
    runner.invoke(main, ["new", "Enhancement D", "-t", "enhancement", "-l", "deferred"], catch_exceptions=False)
    # Close issue #3
    runner.invoke(main, ["close", "3"], catch_exceptions=False)


class TestBulkFilterLabelAdd:
    def test_filter_by_type(self, runner: CliRunner, initialized_cli):
        _create_typed_issues(runner)
        result = runner.invoke(main, [
            "bulk", "label", "add", "release-blocker", "--filter-type", "bug",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 2 issues." in result.output
        assert "release-blocker" in load_issue(initialized_cli, 1).labels
        assert "release-blocker" in load_issue(initialized_cli, 2).labels
        assert "release-blocker" not in load_issue(initialized_cli, 3).labels

    def test_filter_by_priority_and_status(self, runner: CliRunner, initialized_cli):
        _create_typed_issues(runner)
        result = runner.invoke(main, [
            "bulk", "label", "add", "critical",
            "--filter-priority", "p0", "--filter-status", "open",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 1 issues." in result.output
        assert "critical" in load_issue(initialized_cli, 1).labels

    def test_filter_no_match(self, runner: CliRunner, initialized_cli):
        _create_typed_issues(runner)
        result = runner.invoke(main, [
            "bulk", "label", "add", "x", "--filter-priority", "p3",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        assert "No issues match the filter criteria." in result.output

    def test_filter_and_ids_conflict(self, runner: CliRunner, initialized_cli):
        _create_typed_issues(runner)
        result = runner.invoke(main, [
            "bulk", "label", "add", "x", "1", "--filter-type", "bug",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Cannot use both issue IDs and --filter options." in result.output

    def test_filter_skips_duplicate_label(self, runner: CliRunner, initialized_cli):
        _create_typed_issues(runner)
        result = runner.invoke(main, [
            "bulk", "label", "add", "urgent", "--filter-type", "bug",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Skipped: 2." in result.output
        assert "Updated 0 issues." in result.output


class TestBulkFilterLabelRemove:
    def test_filter_remove(self, runner: CliRunner, initialized_cli):
        _create_typed_issues(runner)
        result = runner.invoke(main, [
            "bulk", "label", "remove", "urgent", "--filter-type", "bug",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 2 issues." in result.output
        assert "urgent" not in load_issue(initialized_cli, 1).labels
        assert "urgent" not in load_issue(initialized_cli, 2).labels


class TestBulkFilterAssign:
    def test_filter_assign(self, runner: CliRunner, initialized_cli):
        _create_typed_issues(runner)
        result = runner.invoke(main, [
            "bulk", "assign", "charlie",
            "--filter-milestone", "v1.0",
        ], catch_exceptions=False)
        # No issues have milestone v1.0
        assert "No issues match the filter criteria." in result.output

    def test_filter_assign_by_label(self, runner: CliRunner, initialized_cli):
        _create_typed_issues(runner)
        result = runner.invoke(main, [
            "bulk", "assign", "charlie", "--filter-label", "deferred",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 1 issues." in result.output
        assert load_issue(initialized_cli, 4).assignee == "charlie"


class TestBulkFilterUnassign:
    def test_filter_unassign(self, runner: CliRunner, initialized_cli):
        _create_typed_issues(runner)
        result = runner.invoke(main, [
            "bulk", "unassign", "--filter-assignee", "alice", "--filter-status", "open",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        # Issue #1 is open and assigned to alice; #3 is closed
        assert "Updated 1 issues." in result.output
        assert load_issue(initialized_cli, 1).assignee is None


class TestBulkFilterPriority:
    def test_filter_priority(self, runner: CliRunner, initialized_cli):
        _create_typed_issues(runner)
        result = runner.invoke(main, [
            "bulk", "priority", "p0", "--filter-type", "bug", "--filter-status", "open",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 2 issues." in result.output
        assert load_issue(initialized_cli, 1).priority == "p0"
        assert load_issue(initialized_cli, 2).priority == "p0"


class TestBulkFilterMilestone:
    def test_filter_milestone(self, runner: CliRunner, initialized_cli):
        _create_typed_issues(runner)
        result = runner.invoke(main, [
            "bulk", "milestone", "v2.0", "--filter-label", "deferred",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Updated 1 issues." in result.output
        assert load_issue(initialized_cli, 4).milestone == "v2.0"


class TestBulkFilterType:
    def test_filter_type(self, runner: CliRunner, initialized_cli):
        _create_typed_issues(runner)
        result = runner.invoke(main, [
            "bulk", "type", "enhancement", "--filter-label", "deferred",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        # Issue #4 already is enhancement, but the command still sets it
        assert "Updated 1 issues." in result.output
        assert load_issue(initialized_cli, 4).type == "enhancement"

    def test_filter_and_ids_conflict(self, runner: CliRunner, initialized_cli):
        _create_typed_issues(runner)
        result = runner.invoke(main, [
            "bulk", "type", "bug", "1", "--filter-status", "open",
        ], catch_exceptions=False)
        assert "Cannot use both issue IDs and --filter options." in result.output


# ── Template CLI Tests ──────────────────────────────────────


from yait.models import Template


def _setup_bug_template(root):
    """Helper: save a bug template directly via store."""
    save_template(root, Template(
        name="bug",
        type="bug",
        priority="p1",
        labels=["needs-triage"],
        body="## Description\n\n[Describe the bug]",
    ))


class TestTemplateList:
    def test_list_empty(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["template", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "No templates found." in result.output

    def test_list_shows_templates(self, runner: CliRunner, initialized_cli):
        _setup_bug_template(initialized_cli)
        save_template(initialized_cli, Template(name="feature", type="feature"))
        result = runner.invoke(main, ["template", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "bug" in result.output
        assert "feature" in result.output
        assert "needs-triage" in result.output


class TestTemplateDelete:
    def test_delete_template(self, runner: CliRunner, initialized_cli):
        _setup_bug_template(initialized_cli)
        result = runner.invoke(main, ["template", "delete", "bug"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Deleted template 'bug'" in result.output
        assert list_templates(initialized_cli) == []

    def test_delete_nonexistent(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["template", "delete", "nope"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestTemplateCreate:
    def test_create_via_editor(self, runner: CliRunner, initialized_cli, monkeypatch):
        """Simulate editor returning a valid template."""
        template_text = (
            "---\nname: bug\ntype: bug\npriority: p1\nlabels:\n- needs-triage\n---\n\n"
            "## Description\n\n[Describe the bug]\n"
        )
        monkeypatch.setattr("click.edit", lambda text=None: template_text)
        result = runner.invoke(main, ["template", "create", "bug"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Saved template 'bug'" in result.output
        tmpl = load_template(initialized_cli, "bug")
        assert tmpl.type == "bug"
        assert tmpl.priority == "p1"
        assert tmpl.labels == ["needs-triage"]

    def test_create_aborted(self, runner: CliRunner, initialized_cli, monkeypatch):
        """Editor returning None aborts."""
        monkeypatch.setattr("click.edit", lambda text=None: None)
        result = runner.invoke(main, ["template", "create", "bug"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Aborted" in result.output


class TestNewWithTemplate:
    def test_new_with_template(self, runner: CliRunner, initialized_cli):
        """--template fills type, priority, labels, body from template."""
        _setup_bug_template(initialized_cli)
        result = runner.invoke(main, [
            "new", "Login crash", "--template", "bug",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.type == "bug"
        assert issue.priority == "p1"
        assert issue.labels == ["needs-triage"]
        assert "Description" in issue.body

    def test_template_cli_overrides(self, runner: CliRunner, initialized_cli):
        """CLI args override template values."""
        _setup_bug_template(initialized_cli)
        result = runner.invoke(main, [
            "new", "Login crash", "--template", "bug",
            "-t", "feature", "-p", "p0", "-l", "custom",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.type == "feature"
        assert issue.priority == "p0"
        assert issue.labels == ["custom"]

    def test_template_body_overridden(self, runner: CliRunner, initialized_cli):
        """--body overrides template body."""
        _setup_bug_template(initialized_cli)
        result = runner.invoke(main, [
            "new", "Login crash", "--template", "bug", "-b", "custom body",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.body == "custom body"

    def test_template_not_found(self, runner: CliRunner, initialized_cli):
        """--template with nonexistent name fails with helpful message."""
        result = runner.invoke(main, [
            "new", "test", "--template", "nope",
        ])
        assert result.exit_code != 0
        assert "not found" in result.output
        assert "Available:" in result.output

    def test_new_without_template_defaults(self, runner: CliRunner, initialized_cli):
        """Without --template, defaults are misc/none as before."""
        result = runner.invoke(main, [
            "new", "plain issue",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.type == "misc"
        assert issue.priority == "none"
        assert issue.labels == []
