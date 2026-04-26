"""Tests for config enhancement (T11 + T12)."""
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from yait.cli import main
from yait.store import (
    get_defaults,
    get_display,
    get_config_value,
    set_config_value,
    reset_config_value,
    load_issue,
    _read_config,
    _write_config,
    _DEFAULT_DEFAULTS,
    _DEFAULT_DISPLAY,
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


# ---------------------------------------------------------------------------
# Store-level config tests
# ---------------------------------------------------------------------------


class TestGetDefaults:
    def test_returns_hardcoded_defaults_when_none_set(self, initialized_cli):
        defaults = get_defaults(initialized_cli)
        assert defaults["type"] == "misc"
        assert defaults["priority"] == "none"
        assert defaults["assignee"] is None
        assert defaults["labels"] == []

    def test_returns_custom_values(self, initialized_cli):
        cfg = _read_config(initialized_cli)
        cfg["defaults"] = {"type": "bug", "priority": "p2"}
        _write_config(initialized_cli, cfg)
        defaults = get_defaults(initialized_cli)
        assert defaults["type"] == "bug"
        assert defaults["priority"] == "p2"
        # Unset fields still have defaults
        assert defaults["assignee"] is None
        assert defaults["labels"] == []

    def test_labels_none_becomes_empty_list(self, initialized_cli):
        cfg = _read_config(initialized_cli)
        cfg["defaults"] = {"labels": None}
        _write_config(initialized_cli, cfg)
        defaults = get_defaults(initialized_cli)
        assert defaults["labels"] == []


class TestGetDisplay:
    def test_returns_hardcoded_defaults_when_none_set(self, initialized_cli):
        display = get_display(initialized_cli)
        assert display["max_title_width"] == 50
        assert display["date_format"] == "short"

    def test_returns_custom_values(self, initialized_cli):
        cfg = _read_config(initialized_cli)
        cfg["display"] = {"max_title_width": 80}
        _write_config(initialized_cli, cfg)
        display = get_display(initialized_cli)
        assert display["max_title_width"] == 80
        assert display["date_format"] == "short"  # still default


class TestGetConfigValue:
    def test_get_defaults_type(self, initialized_cli):
        assert get_config_value(initialized_cli, "defaults.type") == "misc"

    def test_get_display_max_title_width(self, initialized_cli):
        assert get_config_value(initialized_cli, "display.max_title_width") == 50

    def test_invalid_key_no_dot(self, initialized_cli):
        with pytest.raises(KeyError, match="section.field"):
            get_config_value(initialized_cli, "nope")

    def test_unknown_section(self, initialized_cli):
        with pytest.raises(KeyError, match="Unknown config section"):
            get_config_value(initialized_cli, "foo.bar")

    def test_unknown_field(self, initialized_cli):
        with pytest.raises(KeyError, match="Unknown config key"):
            get_config_value(initialized_cli, "defaults.foo")


class TestSetConfigValue:
    def test_set_defaults_type(self, initialized_cli):
        set_config_value(initialized_cli, "defaults.type", "bug")
        assert get_config_value(initialized_cli, "defaults.type") == "bug"

    def test_set_display_max_title_width(self, initialized_cli):
        set_config_value(initialized_cli, "display.max_title_width", "80")
        assert get_config_value(initialized_cli, "display.max_title_width") == 80

    def test_set_max_title_width_non_int_raises(self, initialized_cli):
        with pytest.raises(ValueError, match="must be an integer"):
            set_config_value(initialized_cli, "display.max_title_width", "abc")

    def test_set_defaults_labels(self, initialized_cli):
        set_config_value(initialized_cli, "defaults.labels", "bug,urgent")
        assert get_config_value(initialized_cli, "defaults.labels") == ["bug", "urgent"]

    def test_set_defaults_labels_empty(self, initialized_cli):
        set_config_value(initialized_cli, "defaults.labels", "")
        assert get_config_value(initialized_cli, "defaults.labels") == []

    def test_set_defaults_assignee(self, initialized_cli):
        set_config_value(initialized_cli, "defaults.assignee", "alice")
        assert get_config_value(initialized_cli, "defaults.assignee") == "alice"

    def test_set_defaults_assignee_null(self, initialized_cli):
        set_config_value(initialized_cli, "defaults.assignee", "alice")
        set_config_value(initialized_cli, "defaults.assignee", "null")
        assert get_config_value(initialized_cli, "defaults.assignee") is None

    def test_set_unknown_key_raises(self, initialized_cli):
        with pytest.raises(KeyError):
            set_config_value(initialized_cli, "defaults.foo", "bar")

    def test_persisted_in_yaml(self, initialized_cli):
        set_config_value(initialized_cli, "defaults.type", "bug")
        cfg = yaml.safe_load((initialized_cli / ".yait" / "config.yaml").read_text())
        assert cfg["defaults"]["type"] == "bug"


class TestResetConfigValue:
    def test_reset_removes_from_yaml(self, initialized_cli):
        set_config_value(initialized_cli, "defaults.type", "bug")
        reset_config_value(initialized_cli, "defaults.type")
        assert get_config_value(initialized_cli, "defaults.type") == "misc"
        cfg = yaml.safe_load((initialized_cli / ".yait" / "config.yaml").read_text())
        assert "defaults" not in cfg or "type" not in cfg.get("defaults", {})

    def test_reset_unknown_key_raises(self, initialized_cli):
        with pytest.raises(KeyError):
            reset_config_value(initialized_cli, "foo.bar")

    def test_reset_cleans_empty_section(self, initialized_cli):
        set_config_value(initialized_cli, "defaults.type", "bug")
        reset_config_value(initialized_cli, "defaults.type")
        cfg = yaml.safe_load((initialized_cli / ".yait" / "config.yaml").read_text())
        assert "defaults" not in cfg


class TestBackwardCompat:
    def test_old_config_without_new_sections(self, initialized_cli):
        """Config file without defaults/display sections works fine."""
        cfg_path = initialized_cli / ".yait" / "config.yaml"
        cfg = yaml.safe_load(cfg_path.read_text())
        cfg.pop("defaults", None)
        cfg.pop("display", None)
        cfg_path.write_text(yaml.dump(cfg, default_flow_style=False))
        defaults = get_defaults(initialized_cli)
        assert defaults == _DEFAULT_DEFAULTS
        display = get_display(initialized_cli)
        assert display == _DEFAULT_DISPLAY


# ---------------------------------------------------------------------------
# CLI config command tests
# ---------------------------------------------------------------------------


class TestConfigCLI:
    def test_config_show(self, runner, initialized_cli):
        result = runner.invoke(main, ["config"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "defaults:" in result.output
        assert "display:" in result.output
        assert "type: misc" in result.output
        assert "max_title_width: 50" in result.output

    def test_config_show_custom(self, runner, initialized_cli):
        set_config_value(initialized_cli, "defaults.type", "bug")
        result = runner.invoke(main, ["config"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "type: bug" in result.output

    def test_config_set(self, runner, initialized_cli):
        result = runner.invoke(main, ["config", "set", "defaults.type", "bug"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Set defaults.type = bug" in result.output
        assert get_config_value(initialized_cli, "defaults.type") == "bug"

    def test_config_set_invalid_key(self, runner, initialized_cli):
        result = runner.invoke(main, ["config", "set", "bad.key", "val"])
        assert result.exit_code != 0

    def test_config_reset(self, runner, initialized_cli):
        set_config_value(initialized_cli, "defaults.type", "bug")
        result = runner.invoke(main, ["config", "reset", "defaults.type"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Reset defaults.type to default" in result.output
        assert get_config_value(initialized_cli, "defaults.type") == "misc"

    def test_config_reset_invalid_key(self, runner, initialized_cli):
        result = runner.invoke(main, ["config", "reset", "bad.key"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Integration: new command uses config defaults
# ---------------------------------------------------------------------------


class TestNewWithConfigDefaults:
    def test_new_uses_default_type(self, runner, initialized_cli):
        set_config_value(initialized_cli, "defaults.type", "bug")
        result = runner.invoke(main, ["new", "--title", "Test"], catch_exceptions=False)
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.type == "bug"

    def test_new_uses_default_priority(self, runner, initialized_cli):
        set_config_value(initialized_cli, "defaults.priority", "p2")
        result = runner.invoke(main, ["new", "--title", "Test"], catch_exceptions=False)
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.priority == "p2"

    def test_new_uses_default_assignee(self, runner, initialized_cli):
        set_config_value(initialized_cli, "defaults.assignee", "alice")
        result = runner.invoke(main, ["new", "--title", "Test"], catch_exceptions=False)
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.assignee == "alice"

    def test_new_uses_default_labels(self, runner, initialized_cli):
        set_config_value(initialized_cli, "defaults.labels", "triage,review")
        result = runner.invoke(main, ["new", "--title", "Test"], catch_exceptions=False)
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.labels == ["triage", "review"]

    def test_cli_args_override_config_defaults(self, runner, initialized_cli):
        set_config_value(initialized_cli, "defaults.type", "bug")
        set_config_value(initialized_cli, "defaults.priority", "p2")
        set_config_value(initialized_cli, "defaults.assignee", "alice")
        result = runner.invoke(
            main,
            ["new", "--title", "Override", "-t", "feature", "-p", "p0", "-a", "bob"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.type == "feature"
        assert issue.priority == "p0"
        assert issue.assignee == "bob"

    def test_no_config_defaults_uses_hardcoded(self, runner, initialized_cli):
        """Without any config defaults set, uses hardcoded values."""
        result = runner.invoke(main, ["new", "--title", "Plain"], catch_exceptions=False)
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.type == "misc"
        assert issue.priority == "none"
        assert issue.assignee is None
        assert issue.labels == []

    def test_template_overrides_config_defaults(self, runner, initialized_cli):
        """Template values take precedence over config defaults."""
        from yait.store import save_template
        from yait.models import Template
        set_config_value(initialized_cli, "defaults.type", "enhancement")
        set_config_value(initialized_cli, "defaults.priority", "p3")
        save_template(initialized_cli, Template(
            name="bug-tmpl", type="bug", priority="p0", labels=["crash"],
        ))
        result = runner.invoke(
            main,
            ["new", "--title", "From template", "--template", "bug-tmpl"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        issue = load_issue(initialized_cli, 1)
        assert issue.type == "bug"
        assert issue.priority == "p0"
        assert issue.labels == ["crash"]
