from pathlib import Path

import json
import pytest
from click.testing import CliRunner

from yait.cli import main
from yait.store import load_issue, load_milestone, list_milestones


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
