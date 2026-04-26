from pathlib import Path

import pytest
from click.testing import CliRunner

from yait.cli import main
from yait.store import load_issue


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
