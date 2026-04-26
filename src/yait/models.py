from __future__ import annotations
import re
from dataclasses import dataclass, field

ISSUE_TYPES = ("feature", "bug", "enhancement", "misc")
PRIORITIES = ("p0", "p1", "p2", "p3", "none")
MILESTONE_STATUSES = ("open", "closed")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Issue:
    id: int
    title: str
    status: str = "open"
    type: str = "misc"
    priority: str = "none"
    labels: list[str] = field(default_factory=list)
    assignee: str | None = None
    milestone: str | None = None
    created_at: str = ""
    updated_at: str = ""
    body: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "type": self.type,
            "priority": self.priority,
            "labels": self.labels,
            "assignee": self.assignee,
            "milestone": self.milestone,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "body": self.body,
        }


@dataclass
class Milestone:
    name: str
    status: str = "open"
    description: str = ""
    due_date: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "description": self.description,
            "due_date": self.due_date,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, name: str, data: dict) -> Milestone:
        return cls(
            name=name,
            status=data.get("status", "open"),
            description=data.get("description", ""),
            due_date=data.get("due_date", ""),
            created_at=data.get("created_at", ""),
        )

    def validate_due_date(self) -> None:
        if self.due_date and not _DATE_RE.match(self.due_date):
            raise ValueError(
                f"Invalid due_date format: {self.due_date!r} (expected YYYY-MM-DD)"
            )


@dataclass
class Template:
    name: str
    type: str = "misc"
    priority: str = "none"
    labels: list[str] = field(default_factory=list)
    body: str = ""
