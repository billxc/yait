from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Issue:
    id: int
    title: str
    status: str = "open"
    labels: list[str] = field(default_factory=list)
    assignee: str | None = None
    created_at: str = ""
    updated_at: str = ""
    body: str = ""
