import pytest
from pathlib import Path

from yait.models import Issue, Doc
from yait.store import (
    init_store,
    save_issue,
    load_issue,
    save_doc,
    load_doc,
    list_docs,
    delete_doc,
    _docs_dir,
)


def test_init_creates_docs_dir(yait_root: Path):
    data_dir = yait_root / ".yait"
    init_store(data_dir)
    assert (yait_root / ".yait" / "docs").is_dir()


def test_save_and_load_doc(initialized_root: Path):
    doc = Doc(slug="auth-prd", title="Auth PRD", created_at="2026-01-01", updated_at="2026-01-01", body="Hello")
    save_doc(initialized_root, doc)
    loaded = load_doc(initialized_root, "auth-prd")
    assert loaded.slug == "auth-prd"
    assert loaded.title == "Auth PRD"
    assert loaded.body == "Hello"
    assert loaded.created_at == "2026-01-01"


def test_save_doc_no_body(initialized_root: Path):
    doc = Doc(slug="empty", title="Empty Doc")
    save_doc(initialized_root, doc)
    loaded = load_doc(initialized_root, "empty")
    assert loaded.body == ""


def test_load_doc_not_found(initialized_root: Path):
    with pytest.raises(FileNotFoundError, match="not found"):
        load_doc(initialized_root, "nope")


def test_list_docs_empty(initialized_root: Path):
    assert list_docs(initialized_root) == []


def test_list_docs(initialized_root: Path):
    save_doc(initialized_root, Doc(slug="aaa", title="AAA"))
    save_doc(initialized_root, Doc(slug="bbb", title="BBB"))
    docs = list_docs(initialized_root)
    assert len(docs) == 2
    assert docs[0].slug == "aaa"
    assert docs[1].slug == "bbb"


def test_delete_doc(initialized_root: Path):
    save_doc(initialized_root, Doc(slug="tmp", title="Temp"))
    delete_doc(initialized_root, "tmp")
    with pytest.raises(FileNotFoundError):
        load_doc(initialized_root, "tmp")


def test_delete_doc_not_found(initialized_root: Path):
    with pytest.raises(FileNotFoundError, match="not found"):
        delete_doc(initialized_root, "nope")


def test_issue_docs_roundtrip(initialized_root: Path):
    issue = Issue(id=1, title="Test", docs=["auth-prd", "docs/arch.md"])
    save_issue(initialized_root, issue)
    loaded = load_issue(initialized_root, 1)
    assert loaded.docs == ["auth-prd", "docs/arch.md"]


def test_issue_docs_default_empty(initialized_root: Path):
    issue = Issue(id=1, title="No docs")
    save_issue(initialized_root, issue)
    loaded = load_issue(initialized_root, 1)
    assert loaded.docs == []


def test_old_issue_without_docs_field(initialized_root: Path):
    """Old issue files without docs field default to []."""
    issue_file = initialized_root / "issues" / "1.md"
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
    assert loaded.docs == []
