from __future__ import annotations
from dataclasses import dataclass, field

ISSUE_TYPES = ("feature", "bug", "enhancement", "misc")


@dataclass
class Issue:
    id: int
    title: str
    status: str = "open"
    type: str = "misc"
    labels: list[str] = field(default_factory=list)
    assignee: str | None = None
    created_at: str = ""
    updated_at: str = ""
    body: str = ""
