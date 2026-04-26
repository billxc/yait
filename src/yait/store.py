from __future__ import annotations

try:
    import fcntl
except ImportError:
    fcntl = None
from pathlib import Path

import yaml

from .models import Issue, Milestone, Template, Doc, LINK_TYPES, LINK_REVERSE

YAIT_DIR = ".yait"
ISSUES_DIR = "issues"
TEMPLATES_DIR = "templates"
CONFIG_FILE = "config.yaml"

# Default values for config sections
_DEFAULT_DEFAULTS = {
    "type": "misc",
    "priority": "none",
    "assignee": None,
    "labels": [],
}

_DEFAULT_DISPLAY = {
    "max_title_width": 50,
    "date_format": "short",
}


def _yait_root(root: Path) -> Path:
    return root / YAIT_DIR


def _issues_dir(root: Path) -> Path:
    return _yait_root(root) / ISSUES_DIR


def _templates_dir(root: Path) -> Path:
    return _yait_root(root) / TEMPLATES_DIR


def _config_path(root: Path) -> Path:
    return _yait_root(root) / CONFIG_FILE


def _docs_dir(root: Path) -> Path:
    return _yait_root(root) / "docs"


def init_store(root: Path) -> None:
    _issues_dir(root).mkdir(parents=True, exist_ok=True)
    _templates_dir(root).mkdir(parents=True, exist_ok=True)
    _docs_dir(root).mkdir(parents=True, exist_ok=True)
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


def get_defaults(root: Path) -> dict:
    cfg = _read_config(root)
    saved = cfg.get("defaults") or {}
    result = dict(_DEFAULT_DEFAULTS)
    result.update(saved)
    # Ensure labels is always a list
    if result["labels"] is None:
        result["labels"] = []
    return result


def get_display(root: Path) -> dict:
    cfg = _read_config(root)
    saved = cfg.get("display") or {}
    result = dict(_DEFAULT_DISPLAY)
    result.update(saved)
    return result


def get_config_value(root: Path, key: str):
    """Get a config value by dotted key (e.g. 'defaults.type')."""
    parts = key.split(".", 1)
    if len(parts) != 2:
        raise KeyError(f"Invalid config key: {key!r}. Use 'section.field' format.")
    section, field = parts
    if section == "defaults":
        defaults = get_defaults(root)
        if field not in _DEFAULT_DEFAULTS:
            raise KeyError(f"Unknown config key: {key!r}")
        return defaults[field]
    elif section == "display":
        display = get_display(root)
        if field not in _DEFAULT_DISPLAY:
            raise KeyError(f"Unknown config key: {key!r}")
        return display[field]
    else:
        raise KeyError(f"Unknown config section: {section!r}")


def set_config_value(root: Path, key: str, value: str) -> None:
    """Set a config value by dotted key."""
    parts = key.split(".", 1)
    if len(parts) != 2:
        raise KeyError(f"Invalid config key: {key!r}. Use 'section.field' format.")
    section, field = parts
    if section == "defaults":
        if field not in _DEFAULT_DEFAULTS:
            raise KeyError(f"Unknown config key: {key!r}")
    elif section == "display":
        if field not in _DEFAULT_DISPLAY:
            raise KeyError(f"Unknown config key: {key!r}")
    else:
        raise KeyError(f"Unknown config section: {section!r}")

    # Type coerce
    converted = _coerce_config_value(section, field, value)

    cfg = _read_config(root)
    if section not in cfg:
        cfg[section] = {}
    cfg[section][field] = converted
    _write_config(root, cfg)


def reset_config_value(root: Path, key: str) -> None:
    """Reset a config value to its default."""
    parts = key.split(".", 1)
    if len(parts) != 2:
        raise KeyError(f"Invalid config key: {key!r}. Use 'section.field' format.")
    section, field = parts
    if section == "defaults":
        if field not in _DEFAULT_DEFAULTS:
            raise KeyError(f"Unknown config key: {key!r}")
    elif section == "display":
        if field not in _DEFAULT_DISPLAY:
            raise KeyError(f"Unknown config key: {key!r}")
    else:
        raise KeyError(f"Unknown config section: {section!r}")

    cfg = _read_config(root)
    if section in cfg and isinstance(cfg[section], dict):
        cfg[section].pop(field, None)
        if not cfg[section]:
            del cfg[section]
    _write_config(root, cfg)


def _coerce_config_value(section: str, field: str, value: str):
    """Convert a string value to the appropriate type for the config field."""
    if section == "display" and field == "max_title_width":
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"'{field}' must be an integer, got {value!r}")
    if section == "defaults" and field == "labels":
        # Accept comma-separated or empty string
        if not value or value == "[]":
            return []
        return [v.strip() for v in value.split(",") if v.strip()]
    if section == "defaults" and field == "assignee":
        if value in ("null", "none", ""):
            return None
        return value
    return value


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
    sid = str(issue_id)
    if not sid.isdigit():
        raise ValueError(f"Invalid issue ID: {issue_id!r}")
    return _issues_dir(root) / f"{sid}.md"


def save_issue(root: Path, issue: Issue) -> None:
    fm = {
        "id": issue.id,
        "title": issue.title,
        "status": issue.status,
        "type": issue.type,
        "priority": issue.priority,
        "labels": issue.labels,
        "assignee": issue.assignee,
        "milestone": issue.milestone,
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
        "docs": issue.docs,
        "links": issue.links,
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
        milestone=fm.get("milestone") or None,
        created_at=fm.get("created_at", ""),
        updated_at=fm.get("updated_at", ""),
        body=body,
        docs=fm.get("docs") or [],
        links=fm.get("links") or [],
    )


def delete_issue(root: Path, issue_id: int) -> None:
    path = _issue_path(root, issue_id)
    if not path.exists():
        raise FileNotFoundError(f"Issue {issue_id} not found")
    path.unlink()


def list_issues(
    root: Path,
    status: str | None = None,
    type: str | None = None,
    label: str | None = None,
    assignee: str | None = None,
    priority: str | None = None,
    milestone: str | None = None,
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
        if milestone and issue.milestone != milestone:
            continue
        issues.append(issue)
    return issues


# ---------------------------------------------------------------------------
# Issue Link helpers
# ---------------------------------------------------------------------------


def add_link(root: Path, source_id: int, link_type: str, target_id: int) -> None:
    if source_id == target_id:
        raise ValueError("Cannot link an issue to itself")
    if link_type not in LINK_TYPES:
        raise ValueError(f"Invalid link type: {link_type!r}")

    source = load_issue(root, source_id)
    target = load_issue(root, target_id)

    fwd = {"type": link_type, "target": target_id}
    if fwd in source.links:
        raise ValueError(
            f"Link already exists: #{source_id} {link_type} #{target_id}"
        )

    rev_type = LINK_REVERSE[link_type]
    rev = {"type": rev_type, "target": source_id}

    source.links.append(fwd)
    target.links.append(rev)

    save_issue(root, source)
    save_issue(root, target)


def remove_link(root: Path, source_id: int, target_id: int) -> None:
    source = load_issue(root, source_id)
    target = load_issue(root, target_id)

    source.links = [l for l in source.links if l.get("target") != target_id]
    target.links = [l for l in target.links if l.get("target") != source_id]

    save_issue(root, source)
    save_issue(root, target)


# ---------------------------------------------------------------------------
# Milestone CRUD
# ---------------------------------------------------------------------------


def _get_milestones(cfg: dict) -> dict:
    return cfg.setdefault("milestones", {})


def save_milestone(root: Path, milestone: Milestone) -> None:
    milestone.validate_due_date()
    cfg = _read_config(root)
    ms = _get_milestones(cfg)
    if milestone.name in ms:
        raise ValueError(f"Milestone {milestone.name!r} already exists")
    ms[milestone.name] = milestone.to_dict()
    _write_config(root, cfg)


def load_milestone(root: Path, name: str) -> Milestone:
    cfg = _read_config(root)
    ms = _get_milestones(cfg)
    if name not in ms:
        raise KeyError(f"Milestone {name!r} not found")
    return Milestone.from_dict(name, ms[name])


def list_milestones(root: Path, status: str | None = None) -> list[Milestone]:
    cfg = _read_config(root)
    ms = _get_milestones(cfg)
    result = []
    for name, data in ms.items():
        m = Milestone.from_dict(name, data)
        if status and m.status != status:
            continue
        result.append(m)
    return result


def update_milestone(root: Path, milestone: Milestone) -> None:
    milestone.validate_due_date()
    cfg = _read_config(root)
    ms = _get_milestones(cfg)
    if milestone.name not in ms:
        raise KeyError(f"Milestone {milestone.name!r} not found")
    ms[milestone.name] = milestone.to_dict()
    _write_config(root, cfg)


def delete_milestone(root: Path, name: str, force: bool = False) -> None:
    cfg = _read_config(root)
    ms = _get_milestones(cfg)
    if name not in ms:
        raise KeyError(f"Milestone {name!r} not found")

    referencing = [
        i for i in list_issues(root) if i.milestone == name
    ]

    if referencing and not force:
        count = len(referencing)
        raise ValueError(
            f"Cannot delete milestone {name!r}: {count} issues still reference it. "
            "Use force=True to remove references."
        )

    del ms[name]
    _write_config(root, cfg)

    if force and referencing:
        for issue in referencing:
            issue.milestone = None
            save_issue(root, issue)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Template CRUD
# ---------------------------------------------------------------------------


def _template_path(root: Path, name: str) -> Path:
    return _templates_dir(root) / f"{name}.md"


def save_template(root: Path, template: Template) -> None:
    _templates_dir(root).mkdir(parents=True, exist_ok=True)
    fm = {
        "name": template.name,
        "type": template.type,
        "priority": template.priority,
        "labels": template.labels,
    }
    text = "---\n" + yaml.dump(fm, default_flow_style=False).rstrip("\n") + "\n---\n"
    if template.body:
        text += "\n" + template.body + "\n"
    _template_path(root, template.name).write_text(text)


def load_template(root: Path, name: str) -> Template:
    path = _template_path(root, name)
    if not path.exists():
        available = [t.name for t in list_templates(root)]
        avail_str = ", ".join(available) if available else "none"
        raise FileNotFoundError(
            f"Template '{name}' not found. Available: {avail_str}"
        )
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"Template '{name}': missing frontmatter opening delimiter")
    end_idx = text.index("---\n", 4)
    fm_text = text[4:end_idx]
    body = text[end_idx + 4:].strip()
    fm = yaml.safe_load(fm_text)
    return Template(
        name=fm.get("name", name),
        type=fm.get("type", "misc"),
        priority=fm.get("priority", "none"),
        labels=fm.get("labels") or [],
        body=body,
    )


def list_templates(root: Path) -> list[Template]:
    tdir = _templates_dir(root)
    if not tdir.exists():
        return []
    templates = []
    for p in sorted(tdir.glob("*.md")):
        try:
            t = load_template(root, p.stem)
            templates.append(t)
        except (ValueError, FileNotFoundError):
            continue
    return templates


def delete_template(root: Path, name: str) -> None:
    path = _template_path(root, name)
    if not path.exists():
        available = [t.name for t in list_templates(root)]
        avail_str = ", ".join(available) if available else "none"
        raise FileNotFoundError(
            f"Template '{name}' not found. Available: {avail_str}"
        )
    path.unlink()


# ---------------------------------------------------------------------------
# Doc CRUD
# ---------------------------------------------------------------------------


def _doc_path(root: Path, slug: str) -> Path:
    return _docs_dir(root) / f"{slug}.md"


def save_doc(root: Path, doc: Doc) -> None:
    fm = {
        "slug": doc.slug,
        "title": doc.title,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }
    text = "---\n" + yaml.dump(fm, default_flow_style=False).rstrip("\n") + "\n---\n"
    if doc.body:
        text += "\n" + doc.body + "\n"
    _doc_path(root, doc.slug).write_text(text)


def load_doc(root: Path, slug: str) -> Doc:
    path = _doc_path(root, slug)
    if not path.exists():
        raise FileNotFoundError(f"Doc '{slug}' not found")
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"Doc '{slug}': missing frontmatter opening delimiter")
    end_idx = text.index("---\n", 4)
    fm_text = text[4:end_idx]
    body = text[end_idx + 4:].strip()
    fm = yaml.safe_load(fm_text)
    return Doc(
        slug=fm.get("slug", slug),
        title=fm.get("title", ""),
        created_at=fm.get("created_at", ""),
        updated_at=fm.get("updated_at", ""),
        body=body,
    )


def list_docs(root: Path) -> list[Doc]:
    docs_path = _docs_dir(root)
    if not docs_path.exists():
        return []
    docs = []
    for p in sorted(docs_path.glob("*.md")):
        try:
            docs.append(load_doc(root, p.stem))
        except (ValueError, FileNotFoundError):
            continue
    return docs


def delete_doc(root: Path, slug: str) -> None:
    path = _doc_path(root, slug)
    if not path.exists():
        raise FileNotFoundError(f"Doc '{slug}' not found")
    path.unlink()
