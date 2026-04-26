from yait.models import Issue


class TestIssueDataclass:
    def test_create_with_required_fields(self):
        issue = Issue(id=1, title="bug report")
        assert issue.id == 1
        assert issue.title == "bug report"

    def test_default_status_is_open(self):
        issue = Issue(id=1, title="test")
        assert issue.status == "open"

    def test_default_labels_empty_list(self):
        issue = Issue(id=1, title="test")
        assert issue.labels == []

    def test_default_assignee_none(self):
        issue = Issue(id=1, title="test")
        assert issue.assignee is None

    def test_default_timestamps_empty(self):
        issue = Issue(id=1, title="test")
        assert issue.created_at == ""
        assert issue.updated_at == ""

    def test_default_body_empty(self):
        issue = Issue(id=1, title="test")
        assert issue.body == ""

    def test_labels_not_shared_between_instances(self):
        a = Issue(id=1, title="a")
        b = Issue(id=2, title="b")
        a.labels.append("bug")
        assert b.labels == []

    def test_status_change(self):
        issue = Issue(id=1, title="test")
        assert issue.status == "open"
        issue.status = "closed"
        assert issue.status == "closed"
        issue.status = "open"
        assert issue.status == "open"

    def test_modify_fields(self):
        issue = Issue(id=1, title="original")
        issue.title = "updated"
        issue.status = "closed"
        issue.assignee = "alice"
        assert issue.title == "updated"
        assert issue.status == "closed"
        assert issue.assignee == "alice"

    def test_create_with_all_fields(self):
        issue = Issue(
            id=42,
            title="full issue",
            status="closed",
            labels=["bug", "urgent"],
            assignee="bob",
            created_at="2026-04-26T16:00:00+08:00",
            updated_at="2026-04-26T16:30:00+08:00",
            body="Some description",
        )
        assert issue.id == 42
        assert issue.title == "full issue"
        assert issue.status == "closed"
        assert issue.labels == ["bug", "urgent"]
        assert issue.assignee == "bob"
        assert issue.created_at == "2026-04-26T16:00:00+08:00"
        assert issue.updated_at == "2026-04-26T16:30:00+08:00"
        assert issue.body == "Some description"
