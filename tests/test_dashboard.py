"""Tests for yait.dashboard — multi-page snapshot generator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from yait.cli import main
from yait.dashboard import generate_dashboard, _esc
from yait.models import Issue, Milestone
from yait.store import save_issue, save_milestone, next_id


@pytest.fixture
def dashboard_root(initialized_root: Path) -> Path:
    root = initialized_root
    issues = [
        Issue(id=next_id(root), title="Login page broken", status="open",
              type="bug", priority="p0", assignee="alice", labels=["urgent"],
              milestone="v1.0", created_at="2026-04-01", updated_at="2026-04-01",
              body="# Reproduction\n\n1. Open `/login`\n2. Click submit\n\n```python\nprint('boom')\n```"),
        Issue(id=next_id(root), title="Add dark mode", status="open",
              type="feature", priority="p1", assignee="bob",
              milestone="v1.0", created_at="2026-04-02", updated_at="2026-04-02",
              body="**Goal:** support dark theme."),
        Issue(id=next_id(root), title="Fix typo in README", status="closed",
              type="misc", priority="p3",
              created_at="2026-03-15", updated_at="2026-04-10"),
        Issue(id=next_id(root), title="Improve performance", status="closed",
              type="enhancement", priority="p2", assignee="alice",
              milestone="v1.0", created_at="2026-03-20", updated_at="2026-04-15"),
        Issue(id=next_id(root), title="API docs", status="open",
              type="misc", priority="none",
              created_at="2026-04-05", updated_at="2026-04-05"),
    ]
    for issue in issues:
        save_issue(root, issue)

    save_milestone(root, Milestone(name="v1.0", status="open", due_date="2026-05-01", created_at="2026-03-01"))
    save_milestone(root, Milestone(name="v2.0", status="open", due_date="2026-08-01", created_at="2026-03-01"))
    save_milestone(root, Milestone(name="legacy", status="closed", created_at="2025-01-01"))
    return root


# --- Snapshot structure ---

class TestSnapshotStructure:
    def test_returns_index_path(self, dashboard_root: Path, tmp_path):
        out = tmp_path / "snap"
        index = generate_dashboard(dashboard_root, output_dir=out)
        assert index == out / "index.html"
        assert index.exists()

    def test_default_output_under_root(self, dashboard_root: Path):
        index = generate_dashboard(dashboard_root)
        assert index == dashboard_root / "dashboard" / "index.html"
        assert index.exists()

    def test_creates_per_issue_pages(self, dashboard_root: Path, tmp_path):
        out = tmp_path / "snap"
        generate_dashboard(dashboard_root, output_dir=out)
        for n in range(1, 6):
            assert (out / "issues" / f"{n}.html").exists()

    def test_writes_gitignore(self, dashboard_root: Path, tmp_path):
        out = tmp_path / "snap"
        generate_dashboard(dashboard_root, output_dir=out)
        gi = out / ".gitignore"
        assert gi.exists()
        assert gi.read_text().strip() == "*"

    def test_writes_shared_stylesheet(self, dashboard_root: Path, tmp_path):
        out = tmp_path / "snap"
        generate_dashboard(dashboard_root, output_dir=out)
        css = out / "assets" / "style.css"
        assert css.exists()
        assert ".md-body" in css.read_text()

    def test_overwrites_existing_snapshot(self, dashboard_root: Path, tmp_path):
        out = tmp_path / "snap"
        generate_dashboard(dashboard_root, output_dir=out)
        stale = out / "issues" / "999.html"
        stale.write_text("stale")
        generate_dashboard(dashboard_root, output_dir=out)
        assert not stale.exists()
        assert (out / "issues" / "1.html").exists()


# --- Index page contents ---

class TestIndexPage:
    def _index(self, dashboard_root, tmp_path) -> str:
        out = tmp_path / "snap"
        generate_dashboard(dashboard_root, output_dir=out)
        return (out / "index.html").read_text()

    def test_doctype_and_title(self, dashboard_root, tmp_path):
        idx = self._index(dashboard_root, tmp_path)
        assert idx.startswith("<!DOCTYPE html>")
        assert "YAIT Dashboard" in idx

    def test_project_name_in_title(self, dashboard_root, tmp_path):
        out = tmp_path / "snap"
        generate_dashboard(dashboard_root, output_dir=out, project_name="MyProject")
        idx = (out / "index.html").read_text()
        assert "YAIT Dashboard — MyProject" in idx

    def test_summary_cards(self, dashboard_root, tmp_path):
        idx = self._index(dashboard_root, tmp_path)
        assert ">5</div>" in idx     # total
        assert ">3</div>" in idx     # open
        assert ">2</div>" in idx     # closed
        assert ">40%</div>" in idx   # close rate

    def test_breakdown_present(self, dashboard_root, tmp_path):
        idx = self._index(dashboard_root, tmp_path)
        assert "By Type" in idx
        assert "By Priority" in idx
        assert "bug" in idx and "feature" in idx and "p0" in idx

    def test_milestone_progress(self, dashboard_root, tmp_path):
        idx = self._index(dashboard_root, tmp_path)
        assert "Milestone Progress" in idx
        assert "v1.0" in idx and "v2.0" in idx
        assert "1/3 closed (33%)" in idx
        assert "0/0 closed (0%)" in idx
        assert "legacy" not in idx
        assert "2026-05-01" in idx

    def test_open_issues_table(self, dashboard_root, tmp_path):
        idx = self._index(dashboard_root, tmp_path)
        assert "Open Issues" in idx
        assert "Login page broken" in idx
        assert "Add dark mode" in idx
        assert "API docs" in idx

    def test_assignees_shown(self, dashboard_root, tmp_path):
        idx = self._index(dashboard_root, tmp_path)
        assert "alice" in idx and "bob" in idx

    def test_recently_closed(self, dashboard_root, tmp_path):
        idx = self._index(dashboard_root, tmp_path)
        assert "Recently Closed" in idx
        assert "Fix typo in README" in idx
        assert "Improve performance" in idx

    def test_links_use_relative_paths(self, dashboard_root, tmp_path):
        idx = self._index(dashboard_root, tmp_path)
        assert 'href="issues/1.html"' in idx
        assert 'href="issues/5.html"' in idx

    def test_filter_bar(self, dashboard_root, tmp_path):
        idx = self._index(dashboard_root, tmp_path)
        for marker in ("filter-search", "filter-type", "filter-priority", "filter-assignee", "applyFilters()"):
            assert marker in idx

    def test_milestone_accordion(self, dashboard_root, tmp_path):
        idx = self._index(dashboard_root, tmp_path)
        assert "accordion-toggle" in idx
        assert "toggleAccordion" in idx

    def test_data_attributes(self, dashboard_root, tmp_path):
        idx = self._index(dashboard_root, tmp_path)
        assert 'data-type="bug"' in idx
        assert 'data-priority="p0"' in idx
        assert 'data-assignee="alice"' in idx

    def test_empty_project(self, initialized_root: Path, tmp_path):
        out = tmp_path / "snap"
        generate_dashboard(initialized_root, output_dir=out)
        idx = (out / "index.html").read_text()
        assert ">0</div>" in idx
        assert ">0%</div>" in idx
        assert "No open milestones" in idx
        assert "No open issues" in idx
        assert "No closed issues" in idx
        assert not list((out / "issues").iterdir())

    def test_recently_closed_capped_at_10(self, initialized_root: Path, tmp_path):
        for n in range(15):
            save_issue(initialized_root, Issue(
                id=next_id(initialized_root), title=f"Closed issue {n}", status="closed",
                type="bug", priority="p1",
                created_at="2026-04-01", updated_at=f"2026-04-{n+1:02d}",
            ))
        out = tmp_path / "snap"
        generate_dashboard(initialized_root, output_dir=out)
        idx = (out / "index.html").read_text()
        section = idx.split("Recently Closed")[1].split("</section>")[0]
        assert section.count("Closed issue") == 10
        assert "Closed issue 14" in section


# --- Issue page contents ---

class TestIssuePage:
    def _page(self, dashboard_root, tmp_path, issue_id) -> str:
        out = tmp_path / "snap"
        generate_dashboard(dashboard_root, output_dir=out)
        return (out / "issues" / f"{issue_id}.html").read_text()

    def test_issue_page_has_title(self, dashboard_root, tmp_path):
        page = self._page(dashboard_root, tmp_path, 1)
        assert "Login page broken" in page
        assert "#1" in page

    def test_issue_page_has_metadata(self, dashboard_root, tmp_path):
        page = self._page(dashboard_root, tmp_path, 1)
        assert "alice" in page
        assert "v1.0" in page
        assert "urgent" in page
        assert "p0" in page

    def test_issue_body_embedded_for_markdown_render(self, dashboard_root, tmp_path):
        page = self._page(dashboard_root, tmp_path, 1)
        # Body is JSON-embedded so client-side marked.js can render it
        assert "const BODY=" in page
        assert "Reproduction" in page
        # CDN scripts loaded
        assert "marked" in page and "DOMPurify" in page
        # Render target
        assert 'id="md-body"' in page

    def test_back_link_to_index(self, dashboard_root, tmp_path):
        page = self._page(dashboard_root, tmp_path, 2)
        assert 'href="../index.html"' in page

    def test_prev_next_navigation(self, dashboard_root, tmp_path):
        # Issue 2 has both prev (1) and next (3)
        page = self._page(dashboard_root, tmp_path, 2)
        assert 'href="1.html"' in page
        assert 'href="3.html"' in page

    def test_first_issue_disables_prev(self, dashboard_root, tmp_path):
        page = self._page(dashboard_root, tmp_path, 1)
        assert 'href="2.html"' in page
        assert 'class="nav-btn disabled">‹' in page

    def test_last_issue_disables_next(self, dashboard_root, tmp_path):
        page = self._page(dashboard_root, tmp_path, 5)
        assert 'href="4.html"' in page
        assert 'class="nav-btn disabled">›' in page

    def test_quick_commands_present(self, dashboard_root, tmp_path):
        page = self._page(dashboard_root, tmp_path, 1)
        assert "Quick Commands" in page
        assert "yait show 1" in page
        assert "yait close 1" in page
        assert "copyCmd" in page
        assert "navigator.clipboard.writeText" in page

    def test_commands_with_project_flag(self, dashboard_root, tmp_path):
        out = tmp_path / "snap"
        generate_dashboard(dashboard_root, output_dir=out, project_name="myproj")
        page = (out / "issues" / "1.html").read_text()
        assert "yait -P myproj show 1" in page

    def test_uses_shared_stylesheet(self, dashboard_root, tmp_path):
        page = self._page(dashboard_root, tmp_path, 1)
        assert 'href="../assets/style.css"' in page


# --- XSS / escaping ---

class TestEscaping:
    def test_xss_in_issue_title_escaped_on_index(self, initialized_root: Path, tmp_path):
        save_issue(initialized_root, Issue(
            id=next_id(initialized_root), title='<script>alert("xss")</script>',
            status="open", type="bug", priority="p0", created_at="2026-04-01",
        ))
        out = tmp_path / "snap"
        generate_dashboard(initialized_root, output_dir=out)
        idx = (out / "index.html").read_text()
        assert "&lt;script&gt;" in idx
        assert '<script>alert("xss")</script>' not in idx

    def test_xss_in_body_safely_embedded(self, initialized_root: Path, tmp_path):
        save_issue(initialized_root, Issue(
            id=next_id(initialized_root), title="t", status="open",
            type="bug", priority="p0", created_at="2026-04-01",
            body='</script><script>alert(1)</script>',
        ))
        out = tmp_path / "snap"
        generate_dashboard(initialized_root, output_dir=out)
        page = (out / "issues" / "1.html").read_text()
        # </script> in body must be escaped to <\/script> inside the JSON literal
        assert "</script><script>alert(1)" not in page
        assert r"<\/script>" in page

    def test_xss_in_project_name(self, initialized_root: Path, tmp_path):
        out = tmp_path / "snap"
        generate_dashboard(initialized_root, output_dir=out, project_name='<img onerror="alert(1)">')
        idx = (out / "index.html").read_text()
        assert 'onerror="alert(1)"' not in idx
        assert "&lt;img" in idx


class TestEscapeHelper:
    def test_escapes_angle_brackets(self):
        assert _esc("<div>") == "&lt;div&gt;"

    def test_escapes_ampersand(self):
        assert _esc("a & b") == "a &amp; b"

    def test_escapes_quotes(self):
        assert _esc('"x"') == "&quot;x&quot;"

    def test_handles_none(self):
        assert _esc(None) == "None"


# --- CLI tests ---

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
    runner.invoke(main, ["milestone", "create", "v1.0"], catch_exceptions=False)
    runner.invoke(main, ["new", "Login bug", "-t", "bug", "-l", "urgent", "--milestone", "v1.0"], catch_exceptions=False)
    runner.invoke(main, ["new", "Add dark mode", "-t", "feature", "-p", "p1"], catch_exceptions=False)
    runner.invoke(main, ["close", "2"], catch_exceptions=False)
    return initialized_cli


class TestDashboardCli:
    def test_generates_directory_snapshot(self, runner: CliRunner, initialized_cli):
        result = runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Dashboard generated:" in result.output
        out = initialized_cli / ".yait" / "dashboard"
        assert (out / "index.html").exists()
        assert (out / ".gitignore").exists()
        assert (out / "assets" / "style.css").exists()
        assert (out / "issues").is_dir()

    def test_with_data_creates_issue_pages(self, runner: CliRunner, populated_cli):
        result = runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
        assert result.exit_code == 0
        out = populated_cli / ".yait" / "dashboard"
        assert (out / "issues" / "1.html").exists()
        assert (out / "issues" / "2.html").exists()

    def test_custom_output_directory(self, runner: CliRunner, initialized_cli, tmp_path):
        custom = tmp_path / "custom_snap"
        result = runner.invoke(main, ["dashboard", "--no-open", "-o", str(custom)], catch_exceptions=False)
        assert result.exit_code == 0
        assert (custom / "index.html").exists()

    def test_no_open_flag(self, runner: CliRunner, initialized_cli):
        with patch("webbrowser.open") as m:
            result = runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
        assert result.exit_code == 0
        m.assert_not_called()

    def test_opens_browser_by_default(self, runner: CliRunner, initialized_cli):
        with patch("webbrowser.open") as m:
            result = runner.invoke(main, ["dashboard"], catch_exceptions=False)
        assert result.exit_code == 0
        m.assert_called_once()

    def test_requires_init(self, runner: CliRunner, cli_env):
        result = runner.invoke(main, ["dashboard", "--no-open"])
        assert result.exit_code != 0

    def test_overwrites_existing(self, runner: CliRunner, populated_cli):
        runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
        out = populated_cli / ".yait" / "dashboard"
        stale = out / "issues" / "999.html"
        stale.write_text("stale")
        result = runner.invoke(main, ["dashboard", "--no-open"], catch_exceptions=False)
        assert result.exit_code == 0
        assert not stale.exists()
