from __future__ import annotations

try:
    import fcntl
except ImportError:
    fcntl = None
from pathlib import Path

import yaml

from .models import Issue

YAIT_DIR = ".yait"
ISSUES_DIR = "issues"
CONFIG_FILE = "config.yaml"


def _yait_root(root: Path) -> Path:
    return root / YAIT_DIR


def _issues_dir(root: Path) -> Path:
    return _yait_root(root) / ISSUES_DIR


def _config_path(root: Path) -> Path:
    return _yait_root(root) / CONFIG_FILE


def init_store(root: Path) -> None:
    _issues_dir(root).mkdir(parents=True, exist_ok=True)
    cfg = _config_path(root)
    if not cfg.exists():
        cfg.write_text(yaml.dump({"version": 1, "next_id": 1}, default_flow_style=False))


def is_initialized(root: Path) -> bool:
    return _config_path(root).exists()


def _read_config(root: Path) -> dict:
    data = yaml.safe_load(_config_path(root).read_text())
    if not isinstance(data, dict):
        raise ValueError(".yait/config.yaml is corrupted or empty")
    return data


def _write_config(root: Path, cfg: dict) -> None:
    _config_path(root).write_text(yaml.dump(cfg, default_flow_style=False))


def next_id(root: Path) -> int:
    cfg_path = _config_path(root)
    with open(cfg_path, 'r+') as f:
        if fcntl is not None:
            fcntl.flock(f, fcntl.LOCK_EX)
        cfg = yaml.safe_load(f.read())
        nid = cfg["next_id"]
        cfg["next_id"] = nid + 1
        f.seek(0)
        f.truncate()
        f.write(yaml.dump(cfg, default_flow_style=False))
    return nid


def _issue_path(root: Path, issue_id: int) -> Path:
    return _issues_dir(root) / f"{issue_id}.md"


def save_issue(root: Path, issue: Issue) -> None:
    fm = {
        "id": issue.id,
        "title": issue.title,
        "status": issue.status,
        "type": issue.type,
        "priority": issue.priority,
        "labels": issue.labels,
        "assignee": issue.assignee,
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
    }
    text = "---\n" + yaml.dump(fm, default_flow_style=False).rstrip("\n") + "\n---\n"
    if issue.body:
        text += "\n" + issue.body + "\n"
    _issue_path(root, issue.id).write_text(text)


def load_issue(root: Path, issue_id: int) -> Issue:
    path = _issue_path(root, issue_id)
    if not path.exists():
        raise FileNotFoundError(f"Issue {issue_id} not found")
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"Issue {issue_id}: missing frontmatter opening delimiter")
    end_idx = text.index("---\n", 4)
    fm_text = text[4:end_idx]
    body = text[end_idx + 4:].strip()
    fm = yaml.safe_load(fm_text)
    return Issue(
        id=fm["id"],
        title=fm["title"],
        status=fm["status"],
        type=fm.get("type", "misc"),
        priority=fm.get("priority", "none"),
        labels=fm.get("labels") or [],
        assignee=fm.get("assignee") or None,
        created_at=fm.get("created_at", ""),
        updated_at=fm.get("updated_at", ""),
        body=body,
    )


def list_issues(
    root: Path,
    status: str | None = None,
    type: str | None = None,
    label: str | None = None,
    assignee: str | None = None,
    priority: str | None = None,
) -> list[Issue]:
    issues_path = _issues_dir(root)
    if not issues_path.exists():
        return []
    issues = []
    for p in sorted(issues_path.glob("*.md")):
        if not p.stem.isdigit():
            continue
        issue = load_issue(root, int(p.stem))
        if status and issue.status != status:
            continue
        if type and issue.type != type:
            continue
        if label and label not in issue.labels:
            continue
        if assignee and issue.assignee != assignee:
            continue
        if priority and issue.priority != priority:
            continue
        issues.append(issue)
    return issues
