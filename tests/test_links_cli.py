import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from yait.cli import main
from yait.store import load_issue


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


def _create_issue(runner, title):
    result = runner.invoke(main, ["new", "--title", title], catch_exceptions=False)
    assert result.exit_code == 0
    return result


class TestLinkCommand:
    def test_link_blocks(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "Source")
        _create_issue(runner, "Target")
        result = runner.invoke(main, ["link", "1", "blocks", "2"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Linked #1 blocks #2" in result.output
        source = load_issue(initialized_cli / ".yait", 1)
        target = load_issue(initialized_cli / ".yait", 2)
        assert {"type": "blocks", "target": 2} in source.links
        assert {"type": "blocked-by", "target": 1} in target.links

    def test_link_depends_on(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "Source")
        _create_issue(runner, "Target")
        result = runner.invoke(main, ["link", "1", "depends-on", "2"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Linked #1 depends-on #2" in result.output

    def test_link_relates_to(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "Source")
        _create_issue(runner, "Target")
        result = runner.invoke(main, ["link", "1", "relates-to", "2"], catch_exceptions=False)
        assert result.exit_code == 0
        source = load_issue(initialized_cli / ".yait", 1)
        target = load_issue(initialized_cli / ".yait", 2)
        assert {"type": "relates-to", "target": 2} in source.links
        assert {"type": "relates-to", "target": 1} in target.links

    def test_link_self_reference_error(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "Solo")
        result = runner.invoke(main, ["link", "1", "blocks", "1"])
        assert result.exit_code != 0
        assert "Cannot link an issue to itself" in result.output

    def test_link_duplicate_error(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "A")
        _create_issue(runner, "B")
        runner.invoke(main, ["link", "1", "blocks", "2"], catch_exceptions=False)
        result = runner.invoke(main, ["link", "1", "blocks", "2"])
        assert result.exit_code != 0
        assert "Link already exists" in result.output

    def test_link_target_not_found(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "A")
        result = runner.invoke(main, ["link", "1", "blocks", "99"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_link_invalid_type(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "A")
        _create_issue(runner, "B")
        result = runner.invoke(main, ["link", "1", "invalid", "2"])
        assert result.exit_code != 0


class TestUnlinkCommand:
    def test_unlink_removes_bidirectional(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "A")
        _create_issue(runner, "B")
        runner.invoke(main, ["link", "1", "blocks", "2"], catch_exceptions=False)
        result = runner.invoke(main, ["unlink", "1", "2"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Unlinked #1 and #2" in result.output
        source = load_issue(initialized_cli / ".yait", 1)
        target = load_issue(initialized_cli / ".yait", 2)
        assert source.links == []
        assert target.links == []

    def test_unlink_nonexistent_link(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "A")
        _create_issue(runner, "B")
        result = runner.invoke(main, ["unlink", "1", "2"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "No link between #1 and #2" in result.output

    def test_unlink_missing_issue(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "A")
        result = runner.invoke(main, ["unlink", "1", "99"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestShowWithLinks:
    def test_show_displays_links(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "Source issue")
        _create_issue(runner, "Target issue")
        runner.invoke(main, ["link", "1", "blocks", "2"], catch_exceptions=False)
        result = runner.invoke(main, ["show", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Links:" in result.output
        assert "blocks #2" in result.output
        assert "Target issue" in result.output

    def test_show_no_links_section_when_empty(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "No links")
        result = runner.invoke(main, ["show", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Links:" not in result.output

    def test_show_json_includes_links(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "Source")
        _create_issue(runner, "Target")
        runner.invoke(main, ["link", "1", "blocks", "2"], catch_exceptions=False)
        result = runner.invoke(main, ["show", "1", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["links"]) == 1
        link = data["links"][0]
        assert link["type"] == "blocks"
        assert link["target"] == 2
        assert link["target_status"] == "open"
        assert link["target_title"] == "Target"

    def test_show_deleted_target(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "Source")
        _create_issue(runner, "Target")
        runner.invoke(main, ["link", "1", "blocks", "2"], catch_exceptions=False)
        # Delete target issue directly
        runner.invoke(main, ["delete", "2", "-f"], catch_exceptions=False)
        result = runner.invoke(main, ["show", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "blocks #2" in result.output
        assert "(deleted)" in result.output

    def test_show_json_deleted_target(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "Source")
        _create_issue(runner, "Target")
        runner.invoke(main, ["link", "1", "blocks", "2"], catch_exceptions=False)
        runner.invoke(main, ["delete", "2", "-f"], catch_exceptions=False)
        result = runner.invoke(main, ["show", "1", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["links"][0]["target_status"] == "deleted"

    def test_show_reverse_link_on_target(self, runner: CliRunner, initialized_cli):
        _create_issue(runner, "Blocker")
        _create_issue(runner, "Blocked")
        runner.invoke(main, ["link", "1", "blocks", "2"], catch_exceptions=False)
        result = runner.invoke(main, ["show", "2"], catch_exceptions=False)
        assert "Links:" in result.output
        assert "blocked-by #1" in result.output
        assert "Blocker" in result.output
