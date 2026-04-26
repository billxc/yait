from yait.models import Issue, ISSUE_TYPES, PRIORITIES, Milestone, MILESTONE_STATUSES


class TestIssueDataclass:
    def test_create_with_required_fields(self):
        issue = Issue(id=1, title="bug report")
        assert issue.id == 1
        assert issue.title == "bug report"

    def test_default_status_is_open(self):
        issue = Issue(id=1, title="test")
        assert issue.status == "open"

    def test_default_type_is_misc(self):
        issue = Issue(id=1, title="t")
        assert issue.type == "misc"

    def test_create_with_type(self):
        issue = Issue(id=1, title="t", type="bug")
        assert issue.type == "bug"

    def test_issue_types_constant(self):
        assert len(ISSUE_TYPES) == 4
        assert "feature" in ISSUE_TYPES
        assert "bug" in ISSUE_TYPES
        assert "enhancement" in ISSUE_TYPES
        assert "misc" in ISSUE_TYPES

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
            type="bug",
            labels=["bug", "urgent"],
            assignee="bob",
            created_at="2026-04-26T16:00:00+08:00",
            updated_at="2026-04-26T16:30:00+08:00",
            body="Some description",
        )
        assert issue.id == 42
        assert issue.title == "full issue"
        assert issue.status == "closed"
        assert issue.type == "bug"
        assert issue.labels == ["bug", "urgent"]
        assert issue.assignee == "bob"
        assert issue.created_at == "2026-04-26T16:00:00+08:00"
        assert issue.updated_at == "2026-04-26T16:30:00+08:00"
        assert issue.body == "Some description"

    def test_default_priority_is_none(self):
        issue = Issue(id=1, title="test")
        assert issue.priority == "none"

    def test_create_with_priority(self):
        issue = Issue(id=1, title="t", priority="p0")
        assert issue.priority == "p0"

    def test_priorities_constant(self):
        assert len(PRIORITIES) == 5
        assert "p0" in PRIORITIES
        assert "p1" in PRIORITIES
        assert "p2" in PRIORITIES
        assert "p3" in PRIORITIES
        assert "none" in PRIORITIES


class TestMilestoneDataclass:
    def test_create_with_name_only(self):
        m = Milestone(name="v1.0")
        assert m.name == "v1.0"
        assert m.status == "open"
        assert m.description == ""
        assert m.due_date == ""
        assert m.created_at == ""

    def test_create_with_all_fields(self):
        m = Milestone(
            name="v1.0",
            status="closed",
            description="First release",
            due_date="2026-06-01",
            created_at="2026-04-26T12:00:00+08:00",
        )
        assert m.name == "v1.0"
        assert m.status == "closed"
        assert m.description == "First release"
        assert m.due_date == "2026-06-01"
        assert m.created_at == "2026-04-26T12:00:00+08:00"

    def test_milestone_statuses_constant(self):
        assert MILESTONE_STATUSES == ("open", "closed")

    def test_to_dict(self):
        m = Milestone(name="v1.0", description="desc", due_date="2026-06-01")
        d = m.to_dict()
        assert d == {
            "status": "open",
            "description": "desc",
            "due_date": "2026-06-01",
            "created_at": "",
        }
        assert "name" not in d

    def test_from_dict(self):
        data = {
            "status": "closed",
            "description": "Done",
            "due_date": "2026-05-15",
            "created_at": "2026-04-20T10:00:00+08:00",
        }
        m = Milestone.from_dict("v0.5", data)
        assert m.name == "v0.5"
        assert m.status == "closed"
        assert m.description == "Done"
        assert m.due_date == "2026-05-15"
        assert m.created_at == "2026-04-20T10:00:00+08:00"

    def test_from_dict_missing_fields(self):
        m = Milestone.from_dict("v2.0", {})
        assert m.name == "v2.0"
        assert m.status == "open"
        assert m.description == ""
        assert m.due_date == ""
        assert m.created_at == ""

    def test_roundtrip_to_from_dict(self):
        m = Milestone(name="v1.0", status="open", description="test", due_date="2026-06-01", created_at="2026-04-26")
        m2 = Milestone.from_dict(m.name, m.to_dict())
        assert m == m2

    def test_validate_due_date_valid(self):
        m = Milestone(name="v1.0", due_date="2026-06-01")
        m.validate_due_date()  # should not raise

    def test_validate_due_date_empty(self):
        m = Milestone(name="v1.0", due_date="")
        m.validate_due_date()  # should not raise

    def test_validate_due_date_invalid(self):
        import pytest
        m = Milestone(name="v1.0", due_date="June 1st")
        with pytest.raises(ValueError, match="Invalid due_date format"):
            m.validate_due_date()

    def test_validate_due_date_wrong_format(self):
        import pytest
        m = Milestone(name="v1.0", due_date="01-06-2026")
        with pytest.raises(ValueError, match="Invalid due_date format"):
            m.validate_due_date()
