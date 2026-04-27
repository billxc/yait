"""Tests for yait.dashboard module."""

from __future__ import annotations

from pathlib import Path

import pytest

from yait.dashboard import generate_dashboard, _esc
from yait.models import Issue, Milestone
from yait.store import init_store, save_issue, save_milestone, next_id


@pytest.fixture
def dashboard_root(initialized_root: Path) -> Path:
    """Initialized root with sample data for dashboard tests."""
    root = initialized_root

    # Create a mix of open and closed issues
    issues = [
        Issue(id=next_id(root), title="Login page broken", status="open",
              type="bug", priority="p0", assignee="alice",
              milestone="v1.0", created_at="2026-04-01", updated_at="2026-04-01"),
        Issue(id=next_id(root), title="Add dark mode", status="open",
              type="feature", priority="p1", assignee="bob",
              milestone="v1.0", created_at="2026-04-02", updated_at="2026-04-02"),
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

    # Create milestones
    save_milestone(root, Milestone(
        name="v1.0", status="open", due_date="2026-05-01", created_at="2026-03-01",
    ))
    save_milestone(root, Milestone(
        name="v2.0", status="open", due_date="2026-08-01", created_at="2026-03-01",
    ))
    save_milestone(root, Milestone(
        name="legacy", status="closed", created_at="2025-01-01",
    ))

    return root


class TestGenerateDashboard:
    """Tests for generate_dashboard function."""

    def test_returns_valid_html(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert result.startswith("<!DOCTYPE html>")
        assert "</html>" in result

    def test_contains_header(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root, project_name="MyProject")
        assert "YAIT Dashboard — MyProject" in result
        assert "Generated:" in result

    def test_default_project_name(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert "YAIT Dashboard" in result
        # Should not have " — " with empty project name
        assert "YAIT Dashboard — " not in result

    def test_summary_cards(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        # 5 total, 3 open, 2 closed, 40% close rate
        assert ">5</div>" in result  # total
        assert ">3</div>" in result  # open
        assert ">2</div>" in result  # closed
        assert ">40%</div>" in result  # close rate

    def test_type_breakdown(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert "By Type" in result
        assert "bug" in result
        assert "feature" in result
        assert "enhancement" in result

    def test_priority_breakdown(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert "By Priority" in result
        assert "p0" in result
        assert "p1" in result

    def test_milestone_progress(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert "Milestone Progress" in result
        assert "v1.0" in result
        assert "v2.0" in result
        # v1.0 has 3 issues (2 open, 1 closed) => 1/3 closed (33%)
        assert "1/3 closed (33%)" in result
        # v2.0 has 0 issues => 0/0 closed (0%)
        assert "0/0 closed (0%)" in result
        # Closed milestone should NOT appear
        assert "legacy" not in result
        # Due date shown
        assert "2026-05-01" in result

    def test_open_issues_table(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert "Open Issues" in result
        assert "Login page broken" in result
        assert "Add dark mode" in result
        assert "API docs" in result
        # Closed issues should NOT be in open table... we check they appear in recently closed
        # Both "Fix typo" and "Improve performance" are closed
        # The open issues table has Assignee column
        assert "alice" in result
        assert "bob" in result

    def test_recently_closed(self, dashboard_root: Path):
        result = generate_dashboard(dashboard_root)
        assert "Recently Closed" in result
        assert "Fix typo in README" in result
        assert "Improve performance" in result

    def test_xss_prevention(self, initialized_root: Path):
        root = initialized_root
        xss_title = '<script>alert("xss")</script>'
        save_issue(root, Issue(
            id=next_id(root), title=xss_title, status="open",
            type="bug", priority="p0", created_at="2026-04-01",
        ))
        result = generate_dashboard(root)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_xss_in_project_name(self, initialized_root: Path):
        result = generate_dashboard(initialized_root, project_name='<img onerror="alert(1)">')
        assert 'onerror="alert(1)"' not in result
        assert "&lt;img" in result

    def test_empty_project(self, initialized_root: Path):
        result = generate_dashboard(initialized_root)
        assert "<!DOCTYPE html>" in result
        assert ">0</div>" in result  # total=0
        assert ">0%</div>" in result  # close rate=0
        assert "No open milestones" in result
        assert "No open issues" in result
        assert "No closed issues" in result

    def test_many_closed_issues_limited_to_10(self, initialized_root: Path):
        root = initialized_root
        for n in range(15):
            save_issue(root, Issue(
                id=next_id(root), title=f"Closed issue {n}", status="closed",
                type="bug", priority="p1",
                created_at="2026-04-01", updated_at=f"2026-04-{n+1:02d}",
            ))
        result = generate_dashboard(root)
        # Recently closed should have at most 10 rows
        assert result.count("Closed issue") == 10
        # Most recent should be there (updated 2026-04-15)
        assert "Closed issue 14" in result

    def test_import(self):
        """Verify the public API can be imported."""
        from yait.dashboard import generate_dashboard as gd
        assert callable(gd)


class TestEscapeHelper:
    """Tests for the _esc helper function."""

    def test_escapes_angle_brackets(self):
        assert _esc("<div>") == "&lt;div&gt;"

    def test_escapes_ampersand(self):
        assert _esc("a & b") == "a &amp; b"

    def test_escapes_quotes(self):
        assert _esc('"hello"') == "&quot;hello&quot;"

    def test_handles_none_via_str(self):
        assert _esc(None) == "None"

    def test_plain_text_unchanged(self):
        assert _esc("hello world") == "hello world"
