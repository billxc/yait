import pytest
from pathlib import Path

from yait.models import Issue, LINK_TYPES, LINK_REVERSE
from yait.store import (
    init_store,
    save_issue,
    load_issue,
    add_link,
    remove_link,
)


class TestLinkConstants:
    def test_link_types(self):
        assert "blocks" in LINK_TYPES
        assert "blocked-by" in LINK_TYPES
        assert "depends-on" in LINK_TYPES
        assert "depended-by" in LINK_TYPES
        assert "relates-to" in LINK_TYPES

    def test_reverse_mapping_symmetric(self):
        for lt in LINK_TYPES:
            rev = LINK_REVERSE[lt]
            assert LINK_REVERSE[rev] == lt

    def test_relates_to_self_symmetric(self):
        assert LINK_REVERSE["relates-to"] == "relates-to"


class TestIssueLinksField:
    def test_default_links_empty(self):
        issue = Issue(id=1, title="t")
        assert issue.links == []

    def test_links_not_shared(self):
        a = Issue(id=1, title="a")
        b = Issue(id=2, title="b")
        a.links.append({"type": "blocks", "target": 2})
        assert b.links == []

    def test_to_dict_includes_links(self):
        issue = Issue(id=1, title="t", links=[{"type": "blocks", "target": 2}])
        d = issue.to_dict()
        assert d["links"] == [{"type": "blocks", "target": 2}]


class TestSaveLoadLinks:
    def test_roundtrip_with_links(self, initialized_root: Path):
        issue = Issue(
            id=1,
            title="source",
            links=[{"type": "blocks", "target": 2}],
        )
        save_issue(initialized_root, issue)
        loaded = load_issue(initialized_root, 1)
        assert loaded.links == [{"type": "blocks", "target": 2}]

    def test_backward_compat_no_links(self, initialized_root: Path):
        issue = Issue(id=1, title="old issue")
        save_issue(initialized_root, issue)
        # Manually strip links from frontmatter to simulate old data
        path = initialized_root / ".yait" / "issues" / "1.md"
        text = path.read_text()
        text = "\n".join(
            line for line in text.splitlines() if not line.startswith("links:")
        )
        path.write_text(text + "\n")
        loaded = load_issue(initialized_root, 1)
        assert loaded.links == []


class TestAddLink:
    def _make_pair(self, root: Path):
        save_issue(root, Issue(id=1, title="source"))
        save_issue(root, Issue(id=2, title="target"))

    def test_add_blocks_link(self, initialized_root: Path):
        self._make_pair(initialized_root)
        add_link(initialized_root, 1, "blocks", 2)
        s = load_issue(initialized_root, 1)
        t = load_issue(initialized_root, 2)
        assert {"type": "blocks", "target": 2} in s.links
        assert {"type": "blocked-by", "target": 1} in t.links

    def test_add_depends_on_link(self, initialized_root: Path):
        self._make_pair(initialized_root)
        add_link(initialized_root, 1, "depends-on", 2)
        s = load_issue(initialized_root, 1)
        t = load_issue(initialized_root, 2)
        assert {"type": "depends-on", "target": 2} in s.links
        assert {"type": "depended-by", "target": 1} in t.links

    def test_add_relates_to_link(self, initialized_root: Path):
        self._make_pair(initialized_root)
        add_link(initialized_root, 1, "relates-to", 2)
        s = load_issue(initialized_root, 1)
        t = load_issue(initialized_root, 2)
        assert {"type": "relates-to", "target": 2} in s.links
        assert {"type": "relates-to", "target": 1} in t.links

    def test_self_reference_error(self, initialized_root: Path):
        save_issue(initialized_root, Issue(id=1, title="solo"))
        with pytest.raises(ValueError, match="Cannot link an issue to itself"):
            add_link(initialized_root, 1, "blocks", 1)

    def test_duplicate_link_error(self, initialized_root: Path):
        self._make_pair(initialized_root)
        add_link(initialized_root, 1, "blocks", 2)
        with pytest.raises(ValueError, match="Link already exists"):
            add_link(initialized_root, 1, "blocks", 2)

    def test_target_not_found(self, initialized_root: Path):
        save_issue(initialized_root, Issue(id=1, title="solo"))
        with pytest.raises(FileNotFoundError, match="Issue 99 not found"):
            add_link(initialized_root, 1, "blocks", 99)

    def test_invalid_link_type(self, initialized_root: Path):
        self._make_pair(initialized_root)
        with pytest.raises(ValueError, match="Invalid link type"):
            add_link(initialized_root, 1, "invalid", 2)


class TestRemoveLink:
    def test_remove_link_bidirectional(self, initialized_root: Path):
        save_issue(initialized_root, Issue(id=1, title="a"))
        save_issue(initialized_root, Issue(id=2, title="b"))
        add_link(initialized_root, 1, "blocks", 2)
        remove_link(initialized_root, 1, 2)
        s = load_issue(initialized_root, 1)
        t = load_issue(initialized_root, 2)
        assert s.links == []
        assert t.links == []

    def test_remove_nonexistent_link_noop(self, initialized_root: Path):
        save_issue(initialized_root, Issue(id=1, title="a"))
        save_issue(initialized_root, Issue(id=2, title="b"))
        remove_link(initialized_root, 1, 2)
        s = load_issue(initialized_root, 1)
        assert s.links == []

    def test_remove_preserves_other_links(self, initialized_root: Path):
        save_issue(initialized_root, Issue(id=1, title="a"))
        save_issue(initialized_root, Issue(id=2, title="b"))
        save_issue(initialized_root, Issue(id=3, title="c"))
        add_link(initialized_root, 1, "blocks", 2)
        add_link(initialized_root, 1, "relates-to", 3)
        remove_link(initialized_root, 1, 2)
        s = load_issue(initialized_root, 1)
        assert len(s.links) == 1
        assert s.links[0] == {"type": "relates-to", "target": 3}
