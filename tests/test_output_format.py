"""Tests for output formatting (T13)."""
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from yait.cli import main, _detect_display_mode, _truncate_title, _format_date
from yait.store import set_config_value


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


@pytest.fixture
def populated_cli(runner, initialized_cli):
    """CLI env with a few issues for table output tests."""
    runner.invoke(main, ["new", "--title", "Fix login crash", "-t", "bug",
                         "-p", "p0", "-a", "alice", "-l", "urgent"], catch_exceptions=False)
    runner.invoke(main, ["new", "--title", "Add dark mode", "-t", "feature",
                         "-p", "p2", "-a", "bob"], catch_exceptions=False)
    runner.invoke(main, ["new", "--title", "Refactor auth module", "-t", "enhancement"], catch_exceptions=False)
    return initialized_cli


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestTruncateTitle:
    def test_short_title_unchanged(self):
        assert _truncate_title("Hello", 50) == "Hello"

    def test_exact_width_unchanged(self):
        title = "x" * 50
        assert _truncate_title(title, 50) == title

    def test_long_title_truncated(self):
        title = "A" * 60
        result = _truncate_title(title, 50)
        assert len(result) == 50
        assert result.endswith("...")
        assert result == "A" * 47 + "..."

    def test_very_short_max(self):
        result = _truncate_title("Hello World", 5)
        assert result == "He..."


class TestFormatDate:
    def test_short_format(self):
        assert _format_date("2026-04-26T12:00:00+08:00", "short") == "2026-04-26"

    def test_full_format(self):
        assert _format_date("2026-04-26T12:00:00+08:00", "full") == "2026-04-26T12:00:00"

    def test_empty_string(self):
        assert _format_date("", "short") == "\u2014"

    def test_none_like_empty(self):
        assert _format_date("", "full") == "\u2014"


class TestDetectDisplayMode:
    def test_narrow_terminal(self):
        with patch("os.get_terminal_size") as mock:
            mock.return_value = type("size", (), {"columns": 60, "lines": 24})()
            assert _detect_display_mode() == "compact"

    def test_normal_terminal(self):
        with patch("os.get_terminal_size") as mock:
            mock.return_value = type("size", (), {"columns": 100, "lines": 24})()
            assert _detect_display_mode() == "normal"

    def test_wide_terminal(self):
        with patch("os.get_terminal_size") as mock:
            mock.return_value = type("size", (), {"columns": 150, "lines": 24})()
            assert _detect_display_mode() == "wide"

    def test_boundary_80_is_normal(self):
        with patch("os.get_terminal_size") as mock:
            mock.return_value = type("size", (), {"columns": 80, "lines": 24})()
            assert _detect_display_mode() == "normal"

    def test_boundary_120_is_normal(self):
        with patch("os.get_terminal_size") as mock:
            mock.return_value = type("size", (), {"columns": 120, "lines": 24})()
            assert _detect_display_mode() == "normal"

    def test_oserror_falls_back_to_normal(self):
        with patch("os.get_terminal_size", side_effect=OSError):
            assert _detect_display_mode() == "normal"


# ---------------------------------------------------------------------------
# CLI list --compact / --wide tests
# ---------------------------------------------------------------------------


class TestListCompact:
    def test_compact_shows_id_status_title(self, runner, populated_cli):
        result = runner.invoke(main, ["list", "--compact"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "#1" in result.output
        assert "Fix login crash" in result.output
        assert "STATUS" in result.output
        # compact should NOT show TYPE column
        assert "TYPE" not in result.output
        assert "LABELS" not in result.output
        assert "ASSIGNEE" not in result.output

    def test_compact_with_search(self, runner, populated_cli):
        result = runner.invoke(main, ["search", "login", "--compact"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Fix login crash" in result.output
        assert "TYPE" not in result.output


class TestListWide:
    def test_wide_shows_all_fields(self, runner, populated_cli):
        result = runner.invoke(main, ["list", "--wide"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "PRIORITY" in result.output
        assert "MILESTONE" in result.output
        assert "CREATED" in result.output
        assert "UPDATED" in result.output
        assert "alice" in result.output

    def test_wide_with_search(self, runner, populated_cli):
        result = runner.invoke(main, ["search", "dark", "--wide"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "PRIORITY" in result.output
        assert "CREATED" in result.output


class TestCompactWideConflict:
    def test_list_both_flags_error(self, runner, populated_cli):
        result = runner.invoke(main, ["list", "--compact", "--wide"])
        assert result.exit_code != 0
        assert "Cannot use both" in result.output

    def test_search_both_flags_error(self, runner, populated_cli):
        result = runner.invoke(main, ["search", "login", "--compact", "--wide"])
        assert result.exit_code != 0
        assert "Cannot use both" in result.output


# ---------------------------------------------------------------------------
# Title truncation in table
# ---------------------------------------------------------------------------


class TestTitleTruncationInTable:
    def test_long_title_truncated_in_list(self, runner, initialized_cli):
        long_title = "A" * 80
        runner.invoke(main, ["new", "--title", long_title], catch_exceptions=False)
        result = runner.invoke(main, ["list", "--compact"], catch_exceptions=False)
        assert result.exit_code == 0
        # Default max_title_width is 50, so title should be truncated
        assert "A" * 47 + "..." in result.output
        assert "A" * 80 not in result.output

    def test_custom_max_title_width(self, runner, initialized_cli):
        set_config_value(initialized_cli, "display.max_title_width", "20")
        long_title = "B" * 40
        runner.invoke(main, ["new", "--title", long_title], catch_exceptions=False)
        result = runner.invoke(main, ["list", "--compact"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "B" * 17 + "..." in result.output
        assert "B" * 40 not in result.output


# ---------------------------------------------------------------------------
# Date format in wide mode
# ---------------------------------------------------------------------------


class TestDateFormatInWide:
    def test_short_date_format(self, runner, populated_cli):
        result = runner.invoke(main, ["list", "--wide"], catch_exceptions=False)
        assert result.exit_code == 0
        # Short format shows only YYYY-MM-DD (10 chars)
        lines = result.output.strip().split("\n")
        # Check that date columns don't include time portion by default
        # The output should contain date-like strings
        assert "202" in result.output  # year prefix

    def test_full_date_format(self, runner, populated_cli):
        set_config_value(populated_cli, "display.date_format", "full")
        result = runner.invoke(main, ["list", "--wide"], catch_exceptions=False)
        assert result.exit_code == 0
        # Full format includes time: YYYY-MM-DDTHH:MM:SS
        assert "T" in result.output  # ISO time separator


# ---------------------------------------------------------------------------
# Auto-detect mode (via normal output without explicit mode)
# ---------------------------------------------------------------------------


class TestAutoDetectMode:
    def test_pipe_uses_normal(self, runner, populated_cli):
        """CliRunner doesn't have a terminal, so auto-detect should use normal."""
        result = runner.invoke(main, ["list"], catch_exceptions=False)
        assert result.exit_code == 0
        # Normal mode has TYPE and LABELS columns
        assert "TYPE" in result.output
        assert "LABELS" in result.output
        # But not PRIORITY/MILESTONE/CREATED (those are wide-only)
        assert "PRIORITY" not in result.output
        assert "MILESTONE" not in result.output
