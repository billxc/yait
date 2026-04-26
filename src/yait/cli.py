from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import click

from . import __version__
from .git_ops import git_commit, git_log, is_git_repo
from .models import ISSUE_TYPES, PRIORITIES, Issue
from .store import init_store, is_initialized, list_issues, load_issue, next_id, save_issue


def _root() -> Path:
    return Path.cwd()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _require_init(root: Path) -> None:
    if not is_initialized(root):
        click.echo("Not a yait project. Run 'yait init' first.", err=True)
        raise SystemExit(1)


def _status_color(status: str) -> str:
    return "green" if status == "open" else "red"


def _type_color(type: str) -> str:
    return {"bug": "red", "feature": "blue", "enhancement": "yellow"}.get(type, "white")


def _print_issue_table(issues: list[Issue]) -> None:
    if not issues:
        click.echo('No issues found. Create one with: yait new "..."')
        return
    id_w = max(len(f"#{i.id}") for i in issues)
    st_w = max(len(i.status) for i in issues)
    ty_w = max(len(i.type) for i in issues)
    ti_w = max(len(i.title) for i in issues)
    header = f"{'#':<{id_w}}  {'STATUS':<{st_w}}  {'TYPE':<{ty_w}}  {'TITLE':<{ti_w}}  {'LABELS':<12}  ASSIGNEE"
    click.echo(click.style(header, bold=True))
    for i in issues:
        labels = ",".join(i.labels) if i.labels else "\u2014"
        assignee = i.assignee or "\u2014"
        status_str = click.style(f"{i.status:<{st_w}}", fg=_status_color(i.status))
        type_str = click.style(f"{i.type:<{ty_w}}", fg=_type_color(i.type))
        click.echo(f"{'#' + str(i.id):<{id_w}}  {status_str}  {type_str}  {i.title:<{ti_w}}  {labels:<12}  {assignee}")


def _load_or_exit(root: Path, issue_id: int) -> Issue:
    try:
        return load_issue(root, issue_id)
    except FileNotFoundError:
        click.echo(f"Issue #{issue_id} not found.", err=True)
        raise SystemExit(1)


# ── CLI Group ────────────────────────────────────────────────

@click.group()
@click.version_option(version=__version__)
def main():
    """yait — Yet Another Issue Tracker"""


# ── init ─────────────────────────────────────────────────────

@main.command()
def init():
    """Initialize yait in current directory."""
    root = _root()
    if is_initialized(root):
        click.echo("yait already initialized.")
        return
    init_store(root)
    click.echo("Initialized yait in .yait/")
    git_commit(root, "yait: init")


# ── new ──────────────────────────────────────────────────────

@main.command()
@click.argument("title", required=False, default=None)
@click.option("--title", "title_opt", default=None, help="Issue title")
@click.option("--type", "-t", default="misc", type=click.Choice(ISSUE_TYPES), help="Issue type (default: misc)")
@click.option("--label", "-l", multiple=True, help="Add label (repeatable)")
@click.option("--assign", "-a", default=None, help="Assignee")
@click.option("--body", "-b", default="", help="Issue body text")
def new(title, title_opt, type, label, assign, body):
    """Create a new issue."""
    resolved = title or title_opt
    if not resolved:
        click.echo("Error: title is required", err=True)
        raise SystemExit(1)
    root = _root()
    _require_init(root)
    now = _now()
    nid = next_id(root)
    issue = Issue(
        id=nid,
        title=resolved,
        status="open",
        type=type,
        labels=list(label),
        assignee=assign,
        created_at=now,
        updated_at=now,
        body=body,
    )
    save_issue(root, issue)
    click.echo(f"Created issue #{nid}: {resolved}")
    git_commit(root, f"yait: create issue #{nid} \u2014 {resolved}")


# ── list ─────────────────────────────────────────────────────

@main.command(name="list")
@click.option(
    "--status", default="open",
    type=click.Choice(["open", "closed", "all"]),
    help="Filter by status (default: open)",
)
@click.option("--type", default=None, type=click.Choice(ISSUE_TYPES), help="Filter by type")
@click.option("--priority", default=None, type=click.Choice(PRIORITIES), help="Filter by priority")
@click.option("--label", default=None, help="Filter by label")
@click.option("--assignee", default=None, help="Filter by assignee")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.option("--sort", default="id", type=click.Choice(["id", "created", "updated"]), help="Sort order (default: id)")
def list_cmd(status, type, priority, label, assignee, as_json, sort):
    """List issues (default: open only)."""
    root = _root()
    _require_init(root)
    st = None if status == "all" else status
    issues = list_issues(root, status=st, type=type, label=label, assignee=assignee, priority=priority)
    if sort == "created":
        issues.sort(key=lambda i: i.created_at)
    elif sort == "updated":
        issues.sort(key=lambda i: i.updated_at)
    else:
        issues.sort(key=lambda i: i.id)
    if as_json:
        click.echo(json.dumps([i.to_dict() for i in issues], indent=2))
        return
    if not issues:
        click.echo('No issues found. Create one with: yait new "..."')
        return
    _print_issue_table(issues)


# ── show ─────────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int)
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def show(id, as_json):
    """Show issue details."""
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    if as_json:
        click.echo(json.dumps(issue.to_dict(), indent=2))
        return
    comment_count = issue.body.count("**Comment**") if issue.body else 0
    status_str = click.style(issue.status, fg=_status_color(issue.status))
    click.echo(f"#{issue.id}  [{status_str}]  {issue.title}")
    click.echo(f"Type: {click.style(issue.type, fg=_type_color(issue.type))}")
    if issue.labels:
        click.echo(f"Labels: {', '.join(issue.labels)}")
    if issue.assignee:
        click.echo(f"Assignee: {issue.assignee}")
    click.echo(f"Created: {issue.created_at}")
    click.echo(f"Updated: {issue.updated_at}")
    click.echo(f"Comments: {comment_count}")
    if issue.body:
        click.echo(f"\n{issue.body}")


# ── close ────────────────────────────────────────────────────

@main.command()
@click.argument("ids", nargs=-1, type=int, required=True)
def close(ids):
    """Close one or more issues."""
    root = _root()
    _require_init(root)
    for id in ids:
        issue = _load_or_exit(root, id)
        if issue.status == "closed":
            click.echo(f"Issue #{id} is already closed.")
            continue
        issue.status = "closed"
        issue.updated_at = _now()
        save_issue(root, issue)
        click.echo(f"Closed issue #{id}: {issue.title}")
        git_commit(root, f"yait: close issue #{id}")


# ── reopen ───────────────────────────────────────────────────

@main.command()
@click.argument("ids", nargs=-1, type=int, required=True)
def reopen(ids):
    """Reopen one or more closed issues."""
    root = _root()
    _require_init(root)
    for id in ids:
        issue = _load_or_exit(root, id)
        if issue.status == "open":
            click.echo(f"Issue #{id} is already open.")
            continue
        issue.status = "open"
        issue.updated_at = _now()
        save_issue(root, issue)
        click.echo(f"Reopened issue #{id}: {issue.title}")
        git_commit(root, f"yait: reopen issue #{id}")


# ── comment ──────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int)
@click.option("--message", "-m", default=None, help="Comment text")
def comment(id, message):
    """Add a comment to an issue."""
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    if message is None:
        message = click.edit()
        if not message or not message.strip():
            click.echo("Aborted: empty comment.")
            return
        message = message.strip()
    now = _now()
    separator = "\n\n---\n" if issue.body else ""
    issue.body += f"{separator}**Comment** ({now}):\n{message}"
    issue.updated_at = now
    save_issue(root, issue)
    click.echo(f"Added comment to issue #{id}")
    git_commit(root, f"yait: comment on issue #{id}")


# ── edit ─────────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int)
@click.option("--title", "-T", "new_title", default=None, help="New title")
@click.option("--type", "-t", "new_type", default=None, type=click.Choice(ISSUE_TYPES), help="New type")
@click.option("--assign", "-a", "new_assign", default=None, help="New assignee")
@click.option("--body", "-b", "new_body", default=None, help="New body")
def edit(id, new_title, new_type, new_assign, new_body):
    """Edit an issue inline or in $EDITOR."""
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    if any(v is not None for v in (new_title, new_type, new_assign, new_body)):
        if new_title is not None:
            issue.title = new_title
        if new_type is not None:
            issue.type = new_type
        if new_assign is not None:
            issue.assignee = new_assign or None
        if new_body is not None:
            issue.body = new_body
    else:
        template = f"title: {issue.title}\n\n{issue.body}"
        result = click.edit(template)
        if result is None:
            click.echo("Edit cancelled.")
            return
        lines = result.split("\n", 1)
        first_line = lines[0].strip()
        if first_line.lower().startswith("title:"):
            issue.title = first_line[len("title:"):].strip()
        else:
            issue.title = first_line
        issue.body = lines[1].strip() if len(lines) > 1 else ""
    issue.updated_at = _now()
    save_issue(root, issue)
    click.echo(f"Updated issue #{id}: {issue.title}")
    git_commit(root, f"yait: edit #{id}")


# ── label ────────────────────────────────────────────────────

@main.group()
def label():
    """Manage issue labels."""


@label.command(name="add")
@click.argument("id", type=int)
@click.argument("name")
def label_add(id, name):
    """Add a label to an issue."""
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    if name in issue.labels:
        click.echo(f"Issue #{id} already has label '{name}'.")
        return
    issue.labels.append(name)
    issue.updated_at = _now()
    save_issue(root, issue)
    click.echo(f"Added label '{name}' to issue #{id}")
    git_commit(root, f"yait: label #{id} +{name}")


@label.command(name="remove")
@click.argument("id", type=int)
@click.argument("name")
def label_remove(id, name):
    """Remove a label from an issue."""
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    if name not in issue.labels:
        click.echo(f"Issue #{id} does not have label '{name}'.")
        return
    issue.labels.remove(name)
    issue.updated_at = _now()
    save_issue(root, issue)
    click.echo(f"Removed label '{name}' from issue #{id}")
    git_commit(root, f"yait: label #{id} -{name}")


# ── search ───────────────────────────────────────────────────

@main.command()
@click.argument("query")
@click.option(
    "--status", default="open",
    type=click.Choice(["open", "closed", "all"]),
    help="Filter by status (default: open)",
)
@click.option("--type", default=None, type=click.Choice(ISSUE_TYPES), help="Filter by type")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def search(query, status, type, as_json):
    """Full-text search across issue titles and bodies."""
    root = _root()
    _require_init(root)
    st = None if status == "all" else status
    issues = list_issues(root, status=st, type=type)
    q = query.lower()
    matches = [
        i for i in issues
        if q in i.title.lower() or q in i.body.lower()
    ]
    if as_json:
        click.echo(json.dumps([i.to_dict() for i in matches], indent=2))
        return
    if not matches:
        click.echo("No matching issues.")
        return
    _print_issue_table(matches)


# ── stats ───────────────────────────────────────────────────

@main.command()
def stats():
    """Show issue statistics."""
    root = _root()
    _require_init(root)
    all_issues = list_issues(root, status=None)
    total = len(all_issues)
    if total == 0:
        click.echo("No issues.")
        return
    open_count = sum(1 for i in all_issues if i.status == "open")
    closed_count = sum(1 for i in all_issues if i.status == "closed")
    click.echo(f"Issues: {total} total ({open_count} open, {closed_count} closed)")

    type_counts = Counter(i.type for i in all_issues)
    type_str = ", ".join(f"{t}={c}" for t, c in type_counts.most_common())
    click.echo(f"By type: {type_str}")

    label_counts: Counter[str] = Counter()
    for i in all_issues:
        for lbl in i.labels:
            label_counts[lbl] += 1
    if label_counts:
        label_str = ", ".join(f"{l}={c}" for l, c in label_counts.most_common())
        click.echo(f"By label: {label_str}")


# ── assign / unassign ──────────────────────────────────────

@main.command()
@click.argument("id", type=int)
@click.argument("name")
def assign(id, name):
    """Assign an issue to someone."""
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    issue.assignee = name
    issue.updated_at = _now()
    save_issue(root, issue)
    click.echo(f"Assigned issue #{id} to {name}")
    git_commit(root, f"yait: assign #{id} to {name}")


@main.command()
@click.argument("id", type=int)
def unassign(id):
    """Remove assignee from an issue."""
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    issue.assignee = None
    issue.updated_at = _now()
    save_issue(root, issue)
    click.echo(f"Unassigned issue #{id}")
    git_commit(root, f"yait: unassign #{id}")


# ── log ─────────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int, required=False, default=None)
@click.option("--limit", "-n", default=10, help="Max entries")
def log(id, limit):
    """Show issue change history from git log."""
    root = _root()
    _require_init(root)
    if id is not None:
        path = f".yait/issues/{id}.md"
    else:
        path = ".yait/"
    output = git_log(root, path, limit)
    if output:
        click.echo(output)
    else:
        click.echo("No history found.")
