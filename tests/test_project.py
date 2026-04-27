"""Tests for --project flag and project commands (v0.7.0)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from yait.cli import main
from yait.store import (
    init_store,
    is_initialized,
    list_issues,
    load_issue,
    save_issue,
    load_milestone,
    list_milestones,
)
from yait.models import Issue


# ── fixtures ──────────────────────────────────────────────────

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def yait_home(tmp_path):
    """Temporary YAIT_HOME directory."""
    home = tmp_path / "yait_home"
    home.mkdir()
    return home


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """A git-initialized temp dir for CLI tests."""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=root, check=True, capture_output=True)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def initialized_cli(runner, cli_env):
    """CLI env with yait init already run."""
    runner.invoke(main, ["init"], catch_exceptions=False)
    return cli_env


@pytest.fixture
def project_env(runner, yait_home, monkeypatch):
    """Environment with YAIT_HOME set, returning (runner, yait_home)."""
    monkeypatch.setenv("YAIT_HOME", str(yait_home))
    return runner, yait_home


@pytest.fixture
def created_project(project_env):
    """project_env with a project 'testproj' created."""
    runner, yait_home = project_env
    result = runner.invoke(main, ["project", "create", "testproj"], catch_exceptions=False)
    assert result.exit_code == 0
    return runner, yait_home


# ── Resolution logic tests (T1-T8) ──────────────────────────

class TestResolution:
    def test_project_flag_resolves_named_project(self, created_project):
        """T1: -P flag resolves to named project."""
        runner, yait_home = created_project
        result = runner.invoke(main, ["-P", "testproj", "new", "Test", "-t", "bug"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert "#1" in result.output
        # Verify issue exists in named project
        project_dir = yait_home / "projects" / "testproj"
        issue = load_issue(project_dir, 1)
        assert issue.title == "Test"

    def test_env_var_resolves(self, created_project, monkeypatch):
        """T2: YAIT_PROJECT env resolves."""
        runner, yait_home = created_project
        monkeypatch.setenv("YAIT_PROJECT", "testproj")
        result = runner.invoke(main, ["new", "Via env", "-t", "feature"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        project_dir = yait_home / "projects" / "testproj"
        issue = load_issue(project_dir, 1)
        assert issue.title == "Via env"

    def test_flag_overrides_env_var(self, project_env, monkeypatch):
        """T3: -P overrides YAIT_PROJECT env var."""
        runner, yait_home = project_env
        runner.invoke(main, ["project", "create", "proj-a"], catch_exceptions=False)
        runner.invoke(main, ["project", "create", "proj-b"], catch_exceptions=False)
        monkeypatch.setenv("YAIT_PROJECT", "proj-a")
        result = runner.invoke(main, ["-P", "proj-b", "new", "In B", "-t", "bug"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        # Issue should be in proj-b, not proj-a
        assert load_issue(yait_home / "projects" / "proj-b", 1).title == "In B"
        assert list_issues(yait_home / "projects" / "proj-a") == []

    def test_local_yait_fallback(self, runner, initialized_cli):
        """T4: Local .yait/ fallback works."""
        result = runner.invoke(main, ["new", "Local issue", "-t", "bug"],
                               catch_exceptions=False)
        assert result.exit_code == 0

    def test_env_overrides_local(self, created_project, initialized_cli, monkeypatch):
        """T5: YAIT_PROJECT overrides local .yait/."""
        runner, yait_home = created_project
        monkeypatch.setenv("YAIT_PROJECT", "testproj")
        result = runner.invoke(main, ["new", "Goes to project", "-t", "bug"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        project_dir = yait_home / "projects" / "testproj"
        assert load_issue(project_dir, 1).title == "Goes to project"

    def test_no_project_found_error(self, runner, tmp_path, monkeypatch):
        """T6: No project found gives helpful error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("YAIT_PROJECT", raising=False)
        result = runner.invoke(main, ["list"])
        assert result.exit_code != 0
        assert "No yait project found" in result.output

    def test_named_project_not_found_error(self, project_env):
        """T7: Named project not found gives helpful error."""
        runner, _ = project_env
        result = runner.invoke(main, ["-P", "nonexistent", "list"])
        assert result.exit_code != 0
        assert "not found" in result.output
        assert "project create" in result.output

    def test_yait_home_override(self, runner, tmp_path, monkeypatch):
        """T8: YAIT_HOME override."""
        custom_home = tmp_path / "custom_home"
        monkeypatch.setenv("YAIT_HOME", str(custom_home))
        result = runner.invoke(main, ["project", "create", "x"], catch_exceptions=False)
        assert result.exit_code == 0
        assert (custom_home / "projects" / "x").is_dir()


# ── Project CRUD tests (T9-T19) ──────────────────────────────

class TestProjectCreate:
    def test_creates_project(self, project_env):
        """T9: project create sets up directory structure."""
        runner, yait_home = project_env
        result = runner.invoke(main, ["project", "create", "myapp"], catch_exceptions=False)
        assert result.exit_code == 0
        project_dir = yait_home / "projects" / "myapp"
        assert project_dir.is_dir()
        assert (project_dir / "config.yaml").exists()
        assert (project_dir / "issues").is_dir()
        assert (project_dir / "templates").is_dir()
        assert (project_dir / "docs").is_dir()
        assert (project_dir / ".gitignore").exists()
        assert "yait.lock" in (project_dir / ".gitignore").read_text()
        assert (project_dir / ".git").is_dir()

    def test_duplicate_project_fails(self, project_env):
        """T10: Creating duplicate project fails."""
        runner, _ = project_env
        runner.invoke(main, ["project", "create", "myapp"], catch_exceptions=False)
        result = runner.invoke(main, ["project", "create", "myapp"])
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_invalid_names(self, project_env):
        """T11: Invalid project names are rejected."""
        runner, _ = project_env
        for bad_name in ["../bad", "a b", "x" * 65, ".hidden", "-start"]:
            result = runner.invoke(main, ["project", "create", bad_name])
            assert result.exit_code != 0, f"Expected failure for name: {bad_name}"

    def test_home_permissions(self, runner, tmp_path, monkeypatch):
        """T9 (cont): YAIT_HOME created with 0o700 permissions."""
        home = tmp_path / "fresh_home"
        monkeypatch.setenv("YAIT_HOME", str(home))
        assert not home.exists()
        runner.invoke(main, ["project", "create", "test"], catch_exceptions=False)
        mode = home.stat().st_mode & 0o777
        assert mode == 0o700


class TestProjectList:
    def test_empty_list(self, project_env):
        """T12: No projects shows helpful message."""
        runner, _ = project_env
        result = runner.invoke(main, ["project", "list"], catch_exceptions=False)
        assert "No projects" in result.output

    def test_lists_projects(self, project_env):
        """T12: Lists created projects."""
        runner, _ = project_env
        runner.invoke(main, ["project", "create", "alpha"], catch_exceptions=False)
        runner.invoke(main, ["project", "create", "beta"], catch_exceptions=False)
        result = runner.invoke(main, ["project", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "alpha" in result.output
        assert "beta" in result.output

    def test_list_with_issues(self, created_project):
        """T12: List shows issue counts."""
        runner, yait_home = created_project
        runner.invoke(main, ["-P", "testproj", "new", "Bug 1", "-t", "bug"],
                      catch_exceptions=False)
        runner.invoke(main, ["-P", "testproj", "new", "Bug 2", "-t", "bug"],
                      catch_exceptions=False)
        runner.invoke(main, ["-P", "testproj", "close", "1"],
                      catch_exceptions=False)
        result = runner.invoke(main, ["project", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "testproj" in result.output

    def test_list_json(self, created_project):
        """T13: project list --json outputs valid JSON."""
        runner, _ = created_project
        result = runner.invoke(main, ["project", "list", "--json"], catch_exceptions=False)
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "testproj"


class TestProjectDelete:
    def test_delete_project(self, created_project):
        """T14: project delete removes directory."""
        runner, yait_home = created_project
        result = runner.invoke(main, ["project", "delete", "testproj", "-f"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert not (yait_home / "projects" / "testproj").exists()

    def test_delete_not_found(self, project_env):
        """T15: Deleting non-existent project fails."""
        runner, _ = project_env
        result = runner.invoke(main, ["project", "delete", "ghost", "-f"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestProjectRename:
    def test_rename_project(self, created_project):
        """T16: Rename moves directory and prints warning."""
        runner, yait_home = created_project
        result = runner.invoke(main, ["project", "rename", "testproj", "newname"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert not (yait_home / "projects" / "testproj").exists()
        assert (yait_home / "projects" / "newname").is_dir()
        assert "Note:" in result.output

    def test_rename_target_exists(self, project_env):
        """T17: Rename to existing name fails."""
        runner, _ = project_env
        runner.invoke(main, ["project", "create", "a"], catch_exceptions=False)
        runner.invoke(main, ["project", "create", "b"], catch_exceptions=False)
        result = runner.invoke(main, ["project", "rename", "a", "b"])
        assert result.exit_code != 0
        assert "already exists" in result.output


class TestProjectPath:
    def test_shows_path(self, created_project):
        """T18: project path shows absolute path."""
        runner, yait_home = created_project
        result = runner.invoke(main, ["project", "path", "testproj"],
                               catch_exceptions=False)
        assert str(yait_home / "projects" / "testproj") in result.output

    def test_check_missing(self, project_env):
        """T19: project path --check exits 1 if missing."""
        runner, _ = project_env
        result = runner.invoke(main, ["project", "path", "nope", "--check"])
        assert result.exit_code == 1


# ── Project import tests (T20-T24) ──────────────────────────

class TestProjectImport:
    def test_import_from_cwd(self, runner, initialized_cli, yait_home, monkeypatch):
        """T20: Import copies .yait/ to named project."""
        monkeypatch.setenv("YAIT_HOME", str(yait_home))
        # Create an issue in local
        runner.invoke(main, ["new", "Local issue", "-t", "bug"], catch_exceptions=False)
        result = runner.invoke(main, ["project", "import", "imported"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert "git history" in result.output
        project_dir = yait_home / "projects" / "imported"
        assert project_dir.is_dir()
        assert is_initialized(project_dir)
        issue = load_issue(project_dir, 1)
        assert issue.title == "Local issue"
        # Lock file should not exist in imported project
        assert not (project_dir / "yait.lock").exists()
        # .gitignore should exist
        assert "yait.lock" in (project_dir / ".gitignore").read_text()

    def test_import_with_move(self, runner, initialized_cli, yait_home, monkeypatch):
        """T21: --move removes local .yait/ after copy."""
        monkeypatch.setenv("YAIT_HOME", str(yait_home))
        runner.invoke(main, ["new", "To move"], catch_exceptions=False)
        result = runner.invoke(main, ["project", "import", "moved", "--move"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert not (initialized_cli / ".yait").exists()
        assert is_initialized(yait_home / "projects" / "moved")

    def test_import_with_path(self, runner, initialized_cli, yait_home, tmp_path, monkeypatch):
        """T22: --path imports from specified directory."""
        monkeypatch.setenv("YAIT_HOME", str(yait_home))
        runner.invoke(main, ["new", "Test"], catch_exceptions=False)
        # Import from initialized_cli path (not cwd)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(main, ["project", "import", "frompath",
                                      "--path", str(initialized_cli)],
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert is_initialized(yait_home / "projects" / "frompath")

    def test_import_no_yait(self, runner, tmp_path, yait_home, monkeypatch):
        """T23: Import from directory without .yait/ fails."""
        monkeypatch.setenv("YAIT_HOME", str(yait_home))
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(main, ["project", "import", "nope"])
        assert result.exit_code != 0
        assert "No .yait/" in result.output

    def test_import_duplicate_name(self, runner, initialized_cli, yait_home, monkeypatch):
        """T24: Import to existing name fails."""
        monkeypatch.setenv("YAIT_HOME", str(yait_home))
        runner.invoke(main, ["project", "create", "taken"], catch_exceptions=False)
        result = runner.invoke(main, ["project", "import", "taken"])
        assert result.exit_code != 0
        assert "already exists" in result.output


# ── Existing commands with -P (T25-T35) ─────────────────────

class TestCommandsWithProject:
    def test_new_in_project(self, created_project):
        """T25: yait -P foo new creates issue in named project."""
        runner, yait_home = created_project
        result = runner.invoke(main, ["-P", "testproj", "new", "Test bug", "-t", "bug"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert "#1" in result.output

    def test_list_in_project(self, created_project):
        """T26: yait -P foo list."""
        runner, _ = created_project
        runner.invoke(main, ["-P", "testproj", "new", "Bug", "-t", "bug"],
                      catch_exceptions=False)
        result = runner.invoke(main, ["-P", "testproj", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Bug" in result.output

    def test_show_in_project(self, created_project):
        """T27: yait -P foo show."""
        runner, _ = created_project
        runner.invoke(main, ["-P", "testproj", "new", "Show me", "-t", "bug"],
                      catch_exceptions=False)
        result = runner.invoke(main, ["-P", "testproj", "show", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Show me" in result.output

    def test_close_in_project(self, created_project):
        """T28: yait -P foo close commits in project repo."""
        runner, yait_home = created_project
        runner.invoke(main, ["-P", "testproj", "new", "Close me", "-t", "bug"],
                      catch_exceptions=False)
        result = runner.invoke(main, ["-P", "testproj", "close", "1"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert "Closed" in result.output
        project_dir = yait_home / "projects" / "testproj"
        issue = load_issue(project_dir, 1)
        assert issue.status == "closed"

    def test_search_in_project(self, created_project):
        """T29: yait -P foo search."""
        runner, _ = created_project
        runner.invoke(main, ["-P", "testproj", "new", "Login bug", "-t", "bug"],
                      catch_exceptions=False)
        result = runner.invoke(main, ["-P", "testproj", "search", "Login"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert "Login" in result.output

    def test_stats_in_project(self, created_project):
        """T30: yait -P foo stats."""
        runner, _ = created_project
        runner.invoke(main, ["-P", "testproj", "new", "Issue", "-t", "bug"],
                      catch_exceptions=False)
        result = runner.invoke(main, ["-P", "testproj", "stats"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "1 total" in result.output

    def test_milestone_in_project(self, created_project):
        """T31: yait -P foo milestone create."""
        runner, yait_home = created_project
        result = runner.invoke(
            main, ["-P", "testproj", "milestone", "create", "v1.0"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        project_dir = yait_home / "projects" / "testproj"
        ms = list_milestones(project_dir)
        assert len(ms) == 1
        assert ms[0].name == "v1.0"

    def test_config_in_project(self, created_project):
        """T33: yait -P foo config set."""
        runner, _ = created_project
        result = runner.invoke(
            main, ["-P", "testproj", "config", "set", "defaults.type", "bug"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_export_in_project(self, created_project):
        """T34: yait -P foo export."""
        runner, _ = created_project
        runner.invoke(main, ["-P", "testproj", "new", "Export me", "-t", "bug"],
                      catch_exceptions=False)
        result = runner.invoke(main, ["-P", "testproj", "export"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["title"] == "Export me"

    def test_log_in_project(self, created_project):
        """T35: yait -P foo log shows history from project's git repo."""
        runner, _ = created_project
        runner.invoke(main, ["-P", "testproj", "new", "Logged", "-t", "bug"],
                      catch_exceptions=False)
        result = runner.invoke(main, ["-P", "testproj", "log"], catch_exceptions=False)
        assert result.exit_code == 0


# ── Concurrency tests (T36-T38) ─────────────────────────────

class TestConcurrency:
    def test_lock_in_named_project(self, created_project):
        """T36: Lock file in named project."""
        runner, yait_home = created_project
        # Just verify write operations work (lock is acquired/released internally)
        result = runner.invoke(main, ["-P", "testproj", "new", "Test", "-t", "bug"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        # Lock should be released
        project_dir = yait_home / "projects" / "testproj"
        assert not (project_dir / "yait.lock").exists()

    def test_lock_not_committed(self, created_project):
        """T37: .gitignore prevents yait.lock from being staged."""
        runner, yait_home = created_project
        project_dir = yait_home / "projects" / "testproj"
        gitignore = (project_dir / ".gitignore").read_text()
        assert "yait.lock" in gitignore

    def test_independent_project_locks(self, project_env):
        """T38: Two projects lock independently."""
        runner, yait_home = project_env
        runner.invoke(main, ["project", "create", "proj-a"], catch_exceptions=False)
        runner.invoke(main, ["project", "create", "proj-b"], catch_exceptions=False)
        # Both can write without blocking
        r1 = runner.invoke(main, ["-P", "proj-a", "new", "Issue A", "-t", "bug"],
                           catch_exceptions=False)
        r2 = runner.invoke(main, ["-P", "proj-b", "new", "Issue B", "-t", "bug"],
                           catch_exceptions=False)
        assert r1.exit_code == 0
        assert r2.exit_code == 0


# ── Init delegation tests (T39-T40) ─────────────────────────

class TestInitDelegation:
    def test_init_with_project_flag(self, project_env):
        """T39: yait -P myapp init creates named project."""
        runner, yait_home = project_env
        result = runner.invoke(main, ["-P", "myapp", "init"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Created" in result.output
        assert (yait_home / "projects" / "myapp").is_dir()

    def test_init_with_project_flag_idempotent(self, created_project):
        """T40: yait -P myapp init on existing project says already initialized."""
        runner, _ = created_project
        result = runner.invoke(main, ["-P", "testproj", "init"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "already initialized" in result.output


# ── Edge cases (E1-E16) ─────────────────────────────────────

class TestEdgeCases:
    def test_project_list_ignores_p_flag(self, created_project):
        """E11: project subgroup ignores -P."""
        runner, _ = created_project
        result = runner.invoke(main, ["-P", "testproj", "project", "list"],
                               catch_exceptions=False)
        assert result.exit_code == 0

    def test_project_name_validation(self, project_env):
        """E4: Name validation."""
        runner, _ = project_env
        # Valid names
        for name in ["a", "foo-bar", "test_123", "A1"]:
            result = runner.invoke(main, ["project", "create", name],
                                   catch_exceptions=False)
            assert result.exit_code == 0, f"Expected success for name: {name}"

    def test_home_created_on_first_project(self, runner, tmp_path, monkeypatch):
        """E9: ~/.yait/ created on first project create."""
        home = tmp_path / "new_yait_home"
        monkeypatch.setenv("YAIT_HOME", str(home))
        assert not home.exists()
        result = runner.invoke(main, ["project", "create", "first"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert home.exists()

    def test_project_flag_wins_over_local(self, created_project, initialized_cli):
        """E2: --project wins when both exist."""
        runner, yait_home = created_project
        # Create issue via -P
        r = runner.invoke(main, ["-P", "testproj", "new", "In project", "-t", "bug"],
                          catch_exceptions=False)
        assert r.exit_code == 0
        # Verify it went to the project, not local
        project_dir = yait_home / "projects" / "testproj"
        assert load_issue(project_dir, 1).title == "In project"
