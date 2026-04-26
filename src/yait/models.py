from __future__ import annotations
from dataclasses import dataclass, field

ISSUE_TYPES = ("feature", "bug", "enhancement", "misc")
PRIORITIES = ("p0", "p1", "p2", "p3", "none")


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
