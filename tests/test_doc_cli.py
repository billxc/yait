import json
import pytest
from pathlib import Path
from click.testing import CliRunner

from yait.cli import main
from yait.store import load_issue, save_doc, load_doc, list_docs
from yait.models import Doc


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


class TestDocCreate:
    def test_create_basic(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "Auth PRD", "-b", "Hello"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Created doc 'auth-prd'" in result.output
        doc = load_doc(initialized_cli / ".yait", "auth-prd")
        assert doc.title == "Auth PRD"
        assert doc.body == "Hello"

    def test_create_from_body_file(self, runner: CliRunner, initialized_cli, tmp_path):
        body_file = tmp_path / "draft.md"
        body_file.write_text("Content from file")
        result = runner.invoke(
            main, ["doc", "create", "spec", "--title", "Spec", "--body-file", str(body_file)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        doc = load_doc(initialized_cli / ".yait", "spec")
        assert doc.body == "Content from file"

    def test_create_slug_with_slash_fails(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(
            main, ["doc", "create", "docs/bad", "--title", "Bad"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "cannot contain '/'" in result.output

    def test_create_duplicate_fails(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "Auth PRD", "-b", "v1"],
            catch_exceptions=False,
        )
        result = runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "Auth PRD v2", "-b", "v2"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "already exists" in result.output


class TestDocShow:
    def test_show_basic(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "Auth PRD", "-b", "Body content"],
            catch_exceptions=False,
        )
        result = runner.invoke(main, ["doc", "show", "auth-prd"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "auth-prd: Auth PRD" in result.output
        assert "Body content" in result.output

    def test_show_with_linked_issues(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "Auth PRD", "-b", "x"],
            catch_exceptions=False,
        )
        runner.invoke(main, ["new", "Issue 1"], catch_exceptions=False)
        runner.invoke(main, ["doc", "link", "1", "auth-prd"], catch_exceptions=False)
        result = runner.invoke(main, ["doc", "show", "auth-prd"], catch_exceptions=False)
        assert "Linked issues:" in result.output
        assert "#1" in result.output

    def test_show_json(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "Auth PRD", "-b", "x"],
            catch_exceptions=False,
        )
        result = runner.invoke(main, ["doc", "show", "auth-prd", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["slug"] == "auth-prd"
        assert data["title"] == "Auth PRD"

    def test_show_not_found(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["doc", "show", "nope"], catch_exceptions=False)
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_show_external_ref_rejected(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["doc", "show", "docs/arch.md"], catch_exceptions=False)
        assert result.exit_code != 0
        assert "external reference" in result.output


class TestDocList:
    def test_list_empty(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["doc", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "No documents found" in result.output

    def test_list_with_docs(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "Auth PRD", "-b", "x"],
            catch_exceptions=False,
        )
        runner.invoke(
            main, ["doc", "create", "tech-spec", "--title", "Tech Spec", "-b", "x"],
            catch_exceptions=False,
        )
        result = runner.invoke(main, ["doc", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "auth-prd" in result.output
        assert "tech-spec" in result.output
        assert "SLUG" in result.output

    def test_list_json(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "Auth PRD", "-b", "x"],
            catch_exceptions=False,
        )
        result = runner.invoke(main, ["doc", "list", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["slug"] == "auth-prd"


class TestDocEdit:
    def test_edit_title(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "Old Title", "-b", "x"],
            catch_exceptions=False,
        )
        result = runner.invoke(
            main, ["doc", "edit", "auth-prd", "--title", "New Title"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Updated doc 'auth-prd'" in result.output
        doc = load_doc(initialized_cli / ".yait", "auth-prd")
        assert doc.title == "New Title"

    def test_edit_body(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "Title", "-b", "old body"],
            catch_exceptions=False,
        )
        result = runner.invoke(
            main, ["doc", "edit", "auth-prd", "-b", "new body"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        doc = load_doc(initialized_cli / ".yait", "auth-prd")
        assert doc.body == "new body"

    def test_edit_not_found(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(
            main, ["doc", "edit", "nope", "--title", "x"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "not found" in result.output


class TestDocDelete:
    def test_delete_force(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "Auth PRD", "-b", "x"],
            catch_exceptions=False,
        )
        result = runner.invoke(
            main, ["doc", "delete", "auth-prd", "-f"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Deleted doc 'auth-prd'" in result.output
        assert list_docs(initialized_cli / ".yait") == []

    def test_delete_with_linked_issues_warns(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "Auth PRD", "-b", "x"],
            catch_exceptions=False,
        )
        runner.invoke(main, ["new", "Issue 1"], catch_exceptions=False)
        runner.invoke(main, ["doc", "link", "1", "auth-prd"], catch_exceptions=False)
        # Without -f, prompted for confirmation. Input 'y' to confirm.
        result = runner.invoke(
            main, ["doc", "delete", "auth-prd"],
            input="y\n",
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Warning:" in result.output
        assert "Deleted doc 'auth-prd'" in result.output

    def test_delete_not_found(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(
            main, ["doc", "delete", "nope", "-f"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "not found" in result.output


class TestDocLink:
    def test_link_single(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Issue 1"], catch_exceptions=False)
        result = runner.invoke(
            main, ["doc", "link", "1", "auth-prd"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Linked doc 'auth-prd' to issue #1" in result.output
        issue = load_issue(initialized_cli / ".yait", 1)
        assert "auth-prd" in issue.docs

    def test_link_external_path(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Issue 1"], catch_exceptions=False)
        result = runner.invoke(
            main, ["doc", "link", "1", "docs/arch.md"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Linked doc 'docs/arch.md' to issue #1" in result.output
        issue = load_issue(initialized_cli / ".yait", 1)
        assert "docs/arch.md" in issue.docs

    def test_link_multiple_issues(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Issue 1"], catch_exceptions=False)
        runner.invoke(main, ["new", "Issue 2"], catch_exceptions=False)
        runner.invoke(main, ["new", "Issue 3"], catch_exceptions=False)
        result = runner.invoke(
            main, ["doc", "link", "1", "2", "3", "auth-prd"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Linked doc 'auth-prd' to issues #1, #2, #3" in result.output
        for i in range(1, 4):
            assert "auth-prd" in load_issue(initialized_cli / ".yait", i).docs

    def test_link_duplicate_skipped(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Issue 1"], catch_exceptions=False)
        runner.invoke(main, ["doc", "link", "1", "auth-prd"], catch_exceptions=False)
        result = runner.invoke(
            main, ["doc", "link", "1", "auth-prd"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "already linked" in result.output
        issue = load_issue(initialized_cli / ".yait", 1)
        assert issue.docs.count("auth-prd") == 1


class TestDocUnlink:
    def test_unlink(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Issue 1"], catch_exceptions=False)
        runner.invoke(main, ["doc", "link", "1", "auth-prd"], catch_exceptions=False)
        result = runner.invoke(
            main, ["doc", "unlink", "1", "auth-prd"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Unlinked doc 'auth-prd' from issue #1" in result.output
        issue = load_issue(initialized_cli / ".yait", 1)
        assert "auth-prd" not in issue.docs

    def test_unlink_not_linked(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Issue 1"], catch_exceptions=False)
        result = runner.invoke(
            main, ["doc", "unlink", "1", "auth-prd"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "not linked" in result.output


class TestShowWithDocs:
    def test_show_displays_docs(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "Auth PRD", "-b", "x"],
            catch_exceptions=False,
        )
        runner.invoke(main, ["new", "Issue 1"], catch_exceptions=False)
        runner.invoke(main, ["doc", "link", "1", "auth-prd"], catch_exceptions=False)
        result = runner.invoke(main, ["show", "1"], catch_exceptions=False)
        assert "Docs:" in result.output
        assert "auth-prd (Auth PRD)" in result.output

    def test_show_doc_not_found(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Issue 1"], catch_exceptions=False)
        runner.invoke(main, ["doc", "link", "1", "missing-doc"], catch_exceptions=False)
        result = runner.invoke(main, ["show", "1"], catch_exceptions=False)
        assert "missing-doc (not found)" in result.output

    def test_show_json_includes_docs(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Issue 1"], catch_exceptions=False)
        runner.invoke(main, ["doc", "link", "1", "auth-prd"], catch_exceptions=False)
        result = runner.invoke(main, ["show", "1", "--json"], catch_exceptions=False)
        data = json.loads(result.output)
        assert data["docs"] == ["auth-prd"]


class TestListWithDocFilters:
    def test_has_doc(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "With doc"], catch_exceptions=False)
        runner.invoke(main, ["new", "Without doc"], catch_exceptions=False)
        runner.invoke(main, ["doc", "link", "1", "auth-prd"], catch_exceptions=False)
        result = runner.invoke(main, ["list", "--has-doc"], catch_exceptions=False)
        assert "With doc" in result.output
        assert "Without doc" not in result.output

    def test_no_doc(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "With doc"], catch_exceptions=False)
        runner.invoke(main, ["new", "Without doc"], catch_exceptions=False)
        runner.invoke(main, ["doc", "link", "1", "auth-prd"], catch_exceptions=False)
        result = runner.invoke(main, ["list", "--no-doc"], catch_exceptions=False)
        assert "Without doc" in result.output
        assert "With doc" not in result.output

    def test_doc_filter(self, runner: CliRunner, initialized_cli):
        runner.invoke(main, ["new", "Issue A"], catch_exceptions=False)
        runner.invoke(main, ["new", "Issue B"], catch_exceptions=False)
        runner.invoke(main, ["doc", "link", "1", "auth-prd"], catch_exceptions=False)
        runner.invoke(main, ["doc", "link", "2", "tech-spec"], catch_exceptions=False)
        result = runner.invoke(main, ["list", "--doc", "auth-prd"], catch_exceptions=False)
        assert "Issue A" in result.output
        assert "Issue B" not in result.output


class TestSearchWithDocTitles:
    def test_search_matches_doc_title(self, runner: CliRunner, initialized_cli):
        runner.invoke(
            main, ["doc", "create", "auth-prd", "--title", "认证系统 PRD", "-b", "x"],
            catch_exceptions=False,
        )
        runner.invoke(main, ["new", "Some task"], catch_exceptions=False)
        runner.invoke(main, ["doc", "link", "1", "auth-prd"], catch_exceptions=False)
        result = runner.invoke(main, ["search", "认证", "--status", "all"], catch_exceptions=False)
        assert "Some task" in result.output
