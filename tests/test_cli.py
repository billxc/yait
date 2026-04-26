from pathlib import Path

import json
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


class TestVersion:
    def test_version_flag(self, runner: CliRunner):
        result = runner.invoke(main, ["--version"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "0.3.0" in result.output


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
