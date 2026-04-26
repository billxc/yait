import subprocess
import pytest
import yaml
from pathlib import Path

from yait.models import Issue
from yait.store import (
    init_store,
    is_initialized,
    list_issues,
    load_issue,
    next_id,
    save_issue,
)


def test_init_store(yait_root: Path):
    """init_store creates the expected directory structure."""
    init_store(yait_root)
    assert is_initialized(yait_root)
    assert (yait_root / ".yait").is_dir()
    assert (yait_root / ".yait" / "issues").is_dir()
    assert (yait_root / ".yait" / "config.yaml").exists()


def test_init_store_idempotent(yait_root: Path):
    """Calling init_store twice is idempotent — no error."""
    init_store(yait_root)
    init_store(yait_root)
    assert is_initialized(yait_root)


def test_is_initialized_false(tmp_path: Path):
    """is_initialized returns False on a bare directory."""
    assert not is_initialized(tmp_path)


def test_save_and_load_issue(initialized_root: Path):
    """Round-trip: save then load returns equivalent issue with all fields."""
    issue = Issue(
        id=1,
        title="test issue",
        status="open",
        labels=["bug", "urgent"],
        assignee="bill",
        created_at="2026-04-26T16:00:00+08:00",
        updated_at="2026-04-26T16:00:00+08:00",
        body="hello world",
    )
    save_issue(initialized_root, issue)
    loaded = load_issue(initialized_root, 1)
    assert loaded.id == issue.id
    assert loaded.title == issue.title
    assert loaded.status == issue.status
    assert loaded.labels == issue.labels
    assert loaded.assignee == issue.assignee
    assert loaded.created_at == issue.created_at
    assert loaded.updated_at == issue.updated_at
    assert loaded.body == issue.body


def test_save_issue_preserves_frontmatter(initialized_root: Path):
    """Saved issue file has correct YAML frontmatter."""
    issue = Issue(
        id=1,
        title="frontmatter test",
        status="open",
        labels=["bug"],
        assignee="alice",
    )
    save_issue(initialized_root, issue)
    issue_file = initialized_root / ".yait" / "issues" / "1.md"
    content = issue_file.read_text()
    assert content.startswith("---\n")
    parts = content.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert fm["title"] == "frontmatter test"
    assert fm["status"] == "open"
    assert fm["labels"] == ["bug"]
    assert fm["assignee"] == "alice"


def test_save_issue_no_body(initialized_root: Path):
    """Issue with empty body round-trips correctly."""
    issue = Issue(id=1, title="Empty body", body="")
    save_issue(initialized_root, issue)
    loaded = load_issue(initialized_root, 1)
    assert loaded.body == ""


def test_next_id_and_bump(initialized_root: Path):
    """next_id auto-increments on each call."""
    assert next_id(initialized_root) == 1
    assert next_id(initialized_root) == 2
    assert next_id(initialized_root) == 3


def test_next_id_increments(initialized_root: Path):
    """next_id returns incrementing IDs across saves."""
    id1 = next_id(initialized_root)
    save_issue(initialized_root, Issue(id=id1, title="first"))
    id2 = next_id(initialized_root)
    assert id2 == id1 + 1


def test_list_issues_empty(initialized_root: Path):
    """list_issues returns empty list when no issues exist."""
    assert list_issues(initialized_root) == []


def test_list_issues_returns_all(initialized_root: Path):
    """list_issues returns all issues when no filter is given."""
    for i in range(1, 4):
        save_issue(initialized_root, Issue(id=i, title=f"issue {i}"))
    issues = list_issues(initialized_root)
    assert len(issues) == 3
    assert [iss.id for iss in issues] == [1, 2, 3]


def test_list_issues_filter_status(initialized_root: Path):
    """list_issues filters by status."""
    save_issue(initialized_root, Issue(id=1, title="open one", status="open"))
    save_issue(initialized_root, Issue(id=2, title="closed one", status="closed"))
    save_issue(initialized_root, Issue(id=3, title="open two", status="open"))
    open_issues = list_issues(initialized_root, status="open")
    assert len(open_issues) == 2
    assert all(i.status == "open" for i in open_issues)
    closed_issues = list_issues(initialized_root, status="closed")
    assert len(closed_issues) == 1
    assert closed_issues[0].id == 2


def test_list_issues_filter_by_label(initialized_root: Path):
    """list_issues filters by label."""
    save_issue(initialized_root, Issue(id=1, title="Bug", labels=["bug"]))
    save_issue(initialized_root, Issue(id=2, title="Feature", labels=["feature"]))
    save_issue(initialized_root, Issue(id=3, title="Bug+Feature", labels=["bug", "feature"]))
    bugs = list_issues(initialized_root, label="bug")
    assert len(bugs) == 2
    assert {b.id for b in bugs} == {1, 3}


def test_list_issues_filter_by_assignee(initialized_root: Path):
    """list_issues filters by assignee."""
    save_issue(initialized_root, Issue(id=1, title="A", assignee="alice"))
    save_issue(initialized_root, Issue(id=2, title="B", assignee="bob"))
    save_issue(initialized_root, Issue(id=3, title="C", assignee="alice"))
    alice = list_issues(initialized_root, assignee="alice")
    assert len(alice) == 2
    assert {a.id for a in alice} == {1, 3}


def test_list_issues_combined_filters(initialized_root: Path):
    """list_issues with multiple filters ANDs them."""
    save_issue(initialized_root, Issue(id=1, title="A", status="open", labels=["bug"], assignee="alice"))
    save_issue(initialized_root, Issue(id=2, title="B", status="closed", labels=["bug"], assignee="alice"))
    save_issue(initialized_root, Issue(id=3, title="C", status="open", labels=["feature"], assignee="alice"))
    result = list_issues(initialized_root, status="open", label="bug", assignee="alice")
    assert len(result) == 1
    assert result[0].id == 1


def test_load_nonexistent_issue(initialized_root: Path):
    """Loading a non-existent issue raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_issue(initialized_root, 999)


def test_issue_with_comments(initialized_root: Path):
    """Body containing comment separators round-trips correctly."""
    body_with_comments = (
        "Original body.\n\n"
        "---\n"
        "**Comment** (2026-04-26 16:30):\n"
        "First comment.\n\n"
        "---\n"
        "**Comment** (2026-04-26 17:00):\n"
        "Second comment."
    )
    issue = Issue(id=1, title="With comments", body=body_with_comments)
    save_issue(initialized_root, issue)
    loaded = load_issue(initialized_root, 1)
    assert "Original body." in loaded.body
    assert "First comment." in loaded.body
    assert "Second comment." in loaded.body


def test_roundtrip_yaml_frontmatter(initialized_root: Path):
    """YAML special characters in title/labels survive roundtrip."""
    issue = Issue(
        id=1,
        title='Fix "quotes" & colons: here',
        status="open",
        labels=["bug: critical", "needs-triage"],
        assignee="o'brien",
        body="Line 1\nLine 2\n\nSpecial chars: !@#$%^&*()",
    )
    save_issue(initialized_root, issue)
    loaded = load_issue(initialized_root, 1)
    assert loaded.title == issue.title
    assert loaded.labels == issue.labels
    assert loaded.assignee == issue.assignee
    assert loaded.body == issue.body


def test_list_issues_uninitialised_dir(tmp_path: Path):
    """list_issues on a dir without .yait returns empty list."""
    assert list_issues(tmp_path) == []


def test_save_and_load_issue_with_type(initialized_root: Path):
    """Round-trip preserves issue type."""
    issue = Issue(id=1, title="bug report", type="bug")
    save_issue(initialized_root, issue)
    loaded = load_issue(initialized_root, 1)
    assert loaded.type == "bug"


def test_load_issue_missing_type_defaults_to_misc(initialized_root: Path):
    """Loading an issue file without a type field defaults to misc."""
    # Manually write an issue file without the type field
    issue_file = initialized_root / ".yait" / "issues" / "1.md"
    issue_file.write_text(
        "---\n"
        "id: 1\n"
        "title: old issue\n"
        "status: open\n"
        "labels: []\n"
        "assignee: ''\n"
        "created_at: ''\n"
        "updated_at: ''\n"
        "---\n"
    )
    loaded = load_issue(initialized_root, 1)
    assert loaded.type == "misc"


def test_list_issues_filter_by_type(initialized_root: Path):
    """list_issues filters by type."""
    save_issue(initialized_root, Issue(id=1, title="A", type="bug"))
    save_issue(initialized_root, Issue(id=2, title="B", type="feature"))
    save_issue(initialized_root, Issue(id=3, title="C", type="bug"))
    save_issue(initialized_root, Issue(id=4, title="D", type="misc"))
    bugs = list_issues(initialized_root, type="bug")
    assert len(bugs) == 2
    assert {b.id for b in bugs} == {1, 3}
    features = list_issues(initialized_root, type="feature")
    assert len(features) == 1
    assert features[0].id == 2


def test_save_issue_type_in_frontmatter(initialized_root: Path):
    """Saved issue file has type in YAML frontmatter."""
    issue = Issue(id=1, title="typed", type="enhancement")
    save_issue(initialized_root, issue)
    issue_file = initialized_root / ".yait" / "issues" / "1.md"
    content = issue_file.read_text()
    parts = content.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert fm["type"] == "enhancement"


def test_load_issue_body_with_horizontal_rule(initialized_root: Path):
    """Body containing --- horizontal rule survives roundtrip."""
    body = "Some text\n\n---\n\nMore text after rule"
    issue = Issue(id=1, title="HR test", body=body)
    save_issue(initialized_root, issue)
    loaded = load_issue(initialized_root, 1)
    assert loaded.body == body


def test_load_issue_body_with_multiple_separators(initialized_root: Path):
    """Body with multiple --- separators roundtrips correctly."""
    body = (
        "Section 1\n\n"
        "---\n\n"
        "Section 2\n\n"
        "---\n\n"
        "Section 3"
    )
    issue = Issue(id=1, title="Multi-sep", body=body)
    save_issue(initialized_root, issue)
    loaded = load_issue(initialized_root, 1)
    assert loaded.body == body


def test_next_id_file_locking(initialized_root: Path):
    """next_id uses file locking for atomic read-modify-write."""
    import fcntl
    from yait.store import _config_path

    cfg_path = _config_path(initialized_root)
    # Hold an exclusive lock and verify next_id blocks (via subprocess timeout)
    # Basic test: sequential calls still produce unique IDs
    ids = [next_id(initialized_root) for _ in range(10)]
    assert ids == list(range(1, 11))
    assert len(set(ids)) == 10

    # Verify the lock is used by checking fcntl.flock is called on the config file
    # We do this by holding a lock and running next_id in a subprocess
    script = f"""
import sys, fcntl, time
f = open("{cfg_path}", "r+")
fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
# Hold lock for 2 seconds
time.sleep(2)
f.close()
"""
    # Start a process that holds the lock
    proc = subprocess.Popen(
        ["python3", "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    import time
    time.sleep(0.3)  # Let subprocess grab the lock

    # next_id should block until the lock is released, so it should take >1s
    start = time.monotonic()
    nid = next_id(initialized_root)
    elapsed = time.monotonic() - start
    proc.wait()

    assert nid == 11
    assert elapsed > 1.0, f"next_id returned too quickly ({elapsed:.2f}s), lock not effective"
