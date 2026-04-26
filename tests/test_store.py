import subprocess
import pytest
import yaml
from pathlib import Path

from yait.models import Issue
from yait.store import (
    _read_config,
    init_store,
    is_initialized,
    list_issues,
    load_issue,
    next_id,
    save_issue,
    save_milestone,
    load_milestone,
    list_milestones,
    delete_milestone,
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


def test_save_and_load_issue_with_priority(initialized_root: Path):
    """Round-trip preserves issue priority."""
    issue = Issue(id=1, title="urgent bug", priority="p0")
    save_issue(initialized_root, issue)
    loaded = load_issue(initialized_root, 1)
    assert loaded.priority == "p0"


def test_load_issue_missing_priority_defaults_to_none(initialized_root: Path):
    """Loading an issue file without a priority field defaults to none."""
    issue_file = initialized_root / ".yait" / "issues" / "1.md"
    issue_file.write_text(
        "---\n"
        "id: 1\n"
        "title: old issue\n"
        "status: open\n"
        "type: misc\n"
        "labels: []\n"
        "assignee: ''\n"
        "created_at: ''\n"
        "updated_at: ''\n"
        "---\n"
    )
    loaded = load_issue(initialized_root, 1)
    assert loaded.priority == "none"


def test_list_issues_filter_by_priority(initialized_root: Path):
    """list_issues filters by priority."""
    save_issue(initialized_root, Issue(id=1, title="A", priority="p0"))
    save_issue(initialized_root, Issue(id=2, title="B", priority="p1"))
    save_issue(initialized_root, Issue(id=3, title="C", priority="p0"))
    save_issue(initialized_root, Issue(id=4, title="D", priority="p3"))
    p0 = list_issues(initialized_root, priority="p0")
    assert len(p0) == 2
    assert {i.id for i in p0} == {1, 3}
    p1 = list_issues(initialized_root, priority="p1")
    assert len(p1) == 1
    assert p1[0].id == 2


def test_list_issues_skips_non_numeric_md(initialized_root: Path):
    """list_issues ignores .md files with non-numeric names."""
    save_issue(initialized_root, Issue(id=1, title="Real issue"))
    # Create a non-numeric .md file in issues dir
    bogus = initialized_root / ".yait" / "issues" / "README.md"
    bogus.write_text("This is not an issue file")
    issues = list_issues(initialized_root)
    assert len(issues) == 1
    assert issues[0].id == 1


def test_read_config_corrupted(initialized_root: Path):
    """_read_config raises ValueError on corrupted config."""
    cfg = initialized_root / ".yait" / "config.yaml"
    cfg.write_text("")
    with pytest.raises(ValueError, match="corrupted or empty"):
        _read_config(initialized_root)


def test_save_issue_assignee_none_roundtrip(initialized_root: Path):
    """Assignee=None roundtrips without becoming empty string."""
    issue = Issue(id=1, title="no assignee", assignee=None)
    save_issue(initialized_root, issue)
    loaded = load_issue(initialized_root, 1)
    assert loaded.assignee is None


# ---------------------------------------------------------------------------
# Milestone store tests
# ---------------------------------------------------------------------------

from yait.models import Milestone


def test_save_and_load_milestone(initialized_root: Path):
    """Round-trip: save then load returns equivalent milestone."""
    m = Milestone(name="v1.0", description="First release", due_date="2026-06-01",
                  created_at="2026-04-26T12:00:00+08:00")
    save_milestone(initialized_root, m)
    loaded = load_milestone(initialized_root, "v1.0")
    assert loaded.name == "v1.0"
    assert loaded.status == "open"
    assert loaded.description == "First release"
    assert loaded.due_date == "2026-06-01"
    assert loaded.created_at == "2026-04-26T12:00:00+08:00"


def test_save_milestone_duplicate_raises(initialized_root: Path):
    """Creating a milestone with a duplicate name raises ValueError."""
    save_milestone(initialized_root, Milestone(name="v1.0"))
    with pytest.raises(ValueError, match="already exists"):
        save_milestone(initialized_root, Milestone(name="v1.0"))


def test_load_milestone_not_found(initialized_root: Path):
    """Loading a non-existent milestone raises KeyError."""
    with pytest.raises(KeyError, match="not found"):
        load_milestone(initialized_root, "nope")


def test_list_milestones_empty(initialized_root: Path):
    """list_milestones returns empty list when none exist."""
    assert list_milestones(initialized_root) == []


def test_list_milestones_all(initialized_root: Path):
    """list_milestones returns all milestones."""
    save_milestone(initialized_root, Milestone(name="v1.0"))
    save_milestone(initialized_root, Milestone(name="v2.0", status="closed"))
    ms = list_milestones(initialized_root)
    assert len(ms) == 2
    assert {m.name for m in ms} == {"v1.0", "v2.0"}


def test_list_milestones_filter_status(initialized_root: Path):
    """list_milestones filters by status."""
    save_milestone(initialized_root, Milestone(name="v1.0", status="open"))
    save_milestone(initialized_root, Milestone(name="v2.0", status="closed"))
    save_milestone(initialized_root, Milestone(name="v3.0", status="open"))
    open_ms = list_milestones(initialized_root, status="open")
    assert len(open_ms) == 2
    assert all(m.status == "open" for m in open_ms)
    closed_ms = list_milestones(initialized_root, status="closed")
    assert len(closed_ms) == 1
    assert closed_ms[0].name == "v2.0"


def test_delete_milestone_no_references(initialized_root: Path):
    """delete_milestone removes an unreferenced milestone."""
    save_milestone(initialized_root, Milestone(name="v1.0"))
    delete_milestone(initialized_root, "v1.0")
    assert list_milestones(initialized_root) == []


def test_delete_milestone_not_found(initialized_root: Path):
    """delete_milestone raises KeyError for non-existent milestone."""
    with pytest.raises(KeyError, match="not found"):
        delete_milestone(initialized_root, "nope")


def test_delete_milestone_with_references_no_force(initialized_root: Path):
    """delete_milestone raises ValueError when issues reference it."""
    save_milestone(initialized_root, Milestone(name="v1.0"))
    save_issue(initialized_root, Issue(id=1, title="A", milestone="v1.0"))
    save_issue(initialized_root, Issue(id=2, title="B", milestone="v1.0"))
    with pytest.raises(ValueError, match="2 issues still reference it"):
        delete_milestone(initialized_root, "v1.0")
    # milestone should still exist
    assert load_milestone(initialized_root, "v1.0").name == "v1.0"


def test_delete_milestone_force_clears_references(initialized_root: Path):
    """delete_milestone with force removes milestone and clears issue refs."""
    save_milestone(initialized_root, Milestone(name="v1.0"))
    save_issue(initialized_root, Issue(id=1, title="A", milestone="v1.0"))
    save_issue(initialized_root, Issue(id=2, title="B", milestone="v1.0"))
    save_issue(initialized_root, Issue(id=3, title="C", milestone="v2.0"))
    delete_milestone(initialized_root, "v1.0", force=True)
    assert list_milestones(initialized_root) == []
    assert load_issue(initialized_root, 1).milestone is None
    assert load_issue(initialized_root, 2).milestone is None
    assert load_issue(initialized_root, 3).milestone == "v2.0"


def test_save_milestone_invalid_due_date(initialized_root: Path):
    """save_milestone rejects invalid due_date format."""
    m = Milestone(name="v1.0", due_date="not-a-date")
    with pytest.raises(ValueError, match="Invalid due_date format"):
        save_milestone(initialized_root, m)


def test_backward_compat_no_milestones_field(initialized_root: Path):
    """Old config without milestones field works (defaults to empty dict)."""
    cfg_path = initialized_root / ".yait" / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg.pop("milestones", None)
    cfg_path.write_text(yaml.dump(cfg, default_flow_style=False))
    assert list_milestones(initialized_root) == []
    save_milestone(initialized_root, Milestone(name="v1.0"))
    assert len(list_milestones(initialized_root)) == 1


def test_milestone_persisted_in_config_yaml(initialized_root: Path):
    """Milestone data is stored in config.yaml milestones section."""
    save_milestone(initialized_root, Milestone(name="v1.0", description="test"))
    cfg = yaml.safe_load((initialized_root / ".yait" / "config.yaml").read_text())
    assert "milestones" in cfg
    assert "v1.0" in cfg["milestones"]
    assert cfg["milestones"]["v1.0"]["description"] == "test"
