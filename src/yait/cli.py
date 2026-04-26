from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import click

from .git_ops import git_commit, is_git_repo
from .models import ISSUE_TYPES, Issue
from .store import init_store, is_initialized, list_issues, load_issue, next_id, save_issue


def _root() -> Path:
    return Path.cwd()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _require_init(root: Path) -> None:
    if not is_initialized(root):
        click.echo("Not a yait project. Run 'yait init' first.", err=True)
        raise SystemExit(1)


def _print_issue_table(issues: list[Issue]) -> None:
    if not issues:
        click.echo("No issues found.")
        return
    id_w = max(len(str(i.id)) for i in issues)
    st_w = max(len(i.status) for i in issues)
    ty_w = max(len(i.type) for i in issues)
    ti_w = max(len(i.title) for i in issues)
    header = f"{'#':<{id_w}}  {'STATUS':<{st_w}}  {'TYPE':<{ty_w}}  {'TITLE':<{ti_w}}  {'LABELS':<12}  ASSIGNEE"
    click.echo(header)
    for i in issues:
        labels = ",".join(i.labels) if i.labels else "\u2014"
        assignee = i.assignee or "\u2014"
        click.echo(f"#{i.id:<{id_w}}  {i.status:<{st_w}}  {i.type:<{ty_w}}  {i.title:<{ti_w}}  {labels:<12}  {assignee}")


def _load_or_exit(root: Path, issue_id: int) -> Issue:
    try:
        return load_issue(root, issue_id)
    except FileNotFoundError:
        click.echo(f"Issue #{issue_id} not found.", err=True)
        raise SystemExit(1)


# ── CLI Group ────────────────────────────────────────────────

@click.group()
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
@click.option("--title", required=True, help="Issue title")
@click.option("--type", "-t", default="misc", type=click.Choice(ISSUE_TYPES), help="Issue type (default: misc)")
@click.option("--label", "-l", multiple=True, help="Add label (repeatable)")
@click.option("--assign", "-a", default=None, help="Assignee")
@click.option("--body", "-b", default="", help="Issue body text")
def new(title, type, label, assign, body):
    """Create a new issue."""
    root = _root()
    _require_init(root)
    now = _now()
    nid = next_id(root)
    issue = Issue(
        id=nid,
        title=title,
        status="open",
        type=type,
        labels=list(label),
        assignee=assign,
        created_at=now,
        updated_at=now,
        body=body,
    )
    save_issue(root, issue)
    click.echo(f"Created issue #{nid}: {title}")
    git_commit(root, f"yait: create issue #{nid} \u2014 {title}")


# ── list ─────────────────────────────────────────────────────

@main.command(name="list")
@click.option(
    "--status", default="open",
    type=click.Choice(["open", "closed", "all"]),
    help="Filter by status (default: open)",
)
@click.option("--type", default=None, type=click.Choice(ISSUE_TYPES), help="Filter by type")
@click.option("--label", default=None, help="Filter by label")
@click.option("--assignee", default=None, help="Filter by assignee")
def list_cmd(status, type, label, assignee):
    """List issues (default: open only)."""
    root = _root()
    _require_init(root)
    st = None if status == "all" else status
    issues = list_issues(root, status=st, type=type)
    if label:
        issues = [i for i in issues if label in i.labels]
    if assignee:
        issues = [i for i in issues if i.assignee == assignee]
    if not issues:
        click.echo("No issues found.")
        return
    _print_issue_table(issues)


# ── show ─────────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int)
def show(id):
    """Show issue details."""
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    click.echo(f"#{issue.id}  [{issue.status}]  {issue.title}")
    click.echo(f"Type: {issue.type}")
    if issue.labels:
        click.echo(f"Labels: {', '.join(issue.labels)}")
    if issue.assignee:
        click.echo(f"Assignee: {issue.assignee}")
    click.echo(f"Created: {issue.created_at}")
    click.echo(f"Updated: {issue.updated_at}")
    if issue.body:
        click.echo(f"\n{issue.body}")


# ── close ────────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int)
def close(id):
    """Close an issue."""
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    if issue.status == "closed":
        click.echo(f"Issue #{id} is already closed.")
        return
    issue.status = "closed"
    issue.updated_at = _now()
    save_issue(root, issue)
    click.echo(f"Closed issue #{id}: {issue.title}")
    git_commit(root, f"yait: close issue #{id}")


# ── reopen ───────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int)
def reopen(id):
    """Reopen a closed issue."""
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    if issue.status == "open":
        click.echo(f"Issue #{id} is already open.")
        return
    issue.status = "open"
    issue.updated_at = _now()
    save_issue(root, issue)
    click.echo(f"Reopened issue #{id}: {issue.title}")
    git_commit(root, f"yait: reopen issue #{id}")


# ── comment ──────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int)
@click.option("--message", "-m", required=True, help="Comment text")
def comment(id, message):
    """Add a comment to an issue."""
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
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
def edit(id):
    """Edit an issue in $EDITOR."""
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
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
    "--status", default="all",
    type=click.Choice(["open", "closed", "all"]),
    help="Filter by status",
)
@click.option("--type", default=None, type=click.Choice(ISSUE_TYPES), help="Filter by type")
def search(query, status, type):
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
    if not matches:
        click.echo("No matching issues.")
        return
    _print_issue_table(matches)
