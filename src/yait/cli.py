from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import csv
import io
import sys

import click

from . import __version__
from .git_ops import git_commit, git_log, is_git_repo
from .models import ISSUE_TYPES, PRIORITIES, MILESTONE_STATUSES, Issue, Milestone, Doc, _SLUG_RE
from .store import (
    init_store, is_initialized, list_issues, load_issue, next_id, save_issue, delete_issue,
    save_milestone, load_milestone, list_milestones, update_milestone, delete_milestone,
    save_doc, load_doc, list_docs, delete_doc, _docs_dir,
)


def _read_body(body: str | None, body_file: str | None) -> str:
    """Resolve body text from --body and --body-file options.

    --body - reads from stdin. --body-file reads from a file path.
    Raises ClickException if both are provided.
    """
    if body is not None and body_file is not None:
        raise click.ClickException("Cannot use both --body and --body-file.")
    if body_file is not None:
        return Path(body_file).read_text().rstrip("\n")
    if body == "-":
        return sys.stdin.read().rstrip("\n")
    return body or ""


def _read_message(message: str | None, message_file: str | None) -> str | None:
    """Resolve message text from --message and --message-file options."""
    if message is not None and message_file is not None:
        raise click.ClickException("Cannot use both --message and --message-file.")
    if message_file is not None:
        return Path(message_file).read_text().rstrip("\n")
    if message == "-":
        return sys.stdin.read().rstrip("\n")
    return message


def _root() -> Path:
    return Path.cwd()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _require_init(root: Path) -> None:
    if not is_initialized(root):
        raise click.ClickException("Not a yait project. Run 'yait init' first.")


def _status_color(status: str) -> str:
    return "green" if status == "open" else "red"


def _type_color(type: str) -> str:
    return {"bug": "red", "feature": "blue", "enhancement": "yellow"}.get(type, "white")


def _highlight_text(text: str, query: str) -> str:
    """Highlight query matches in text with bold yellow ANSI (case-insensitive)."""
    if not query or os.environ.get("NO_COLOR") is not None:
        return text
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    return pattern.sub(lambda m: click.style(m.group(), bold=True, fg="yellow"), text)


def _print_issue_table(issues: list[Issue], highlight: str | None = None) -> None:
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
        title = _highlight_text(i.title, highlight) if highlight else i.title
        # Pad after highlighting to keep columns aligned (ANSI codes don't take visual width)
        pad = ti_w - len(i.title)
        title_padded = title + " " * max(pad, 0)
        click.echo(f"{'#' + str(i.id):<{id_w}}  {status_str}  {type_str}  {title_padded}  {labels:<12}  {assignee}")


def _load_or_exit(root: Path, issue_id: int) -> Issue:
    try:
        return load_issue(root, issue_id)
    except (FileNotFoundError, ValueError):
        raise click.ClickException(f"Issue #{issue_id} not found.")


# ── CLI Group ────────────────────────────────────────────────

@click.group(epilog="""\b
Quick start:
  yait init
  yait new "Fix login bug" -t bug -l urgent
  yait list
  yait search "login"
  yait show 1
  yait close 1
""")
@click.version_option(version=__version__)
def main():
    """yait — Yet Another Issue Tracker

    A lightweight, git-backed issue tracker that lives in your repo.
    Issues are stored as Markdown files and every change is auto-committed.
    """


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

@main.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("title", required=False, default=None)
@click.option("--title", "title_opt", default=None, help="Issue title")
@click.option("--type", "-t", default="misc", type=click.Choice(ISSUE_TYPES), help="Issue type (default: misc)")
@click.option("--priority", "-p", default="none", type=click.Choice(PRIORITIES), help="Priority (default: none)")
@click.option("--label", "-l", multiple=True, help="Add label (repeatable)")
@click.option("--assign", "-a", default=None, help="Assignee")
@click.option("--body", "-b", default=None, help="Issue body text (use '-' for stdin)")
@click.option("--body-file", default=None, help="Read body from file")
@click.option("--milestone", "-m", default=None, help="Milestone (e.g. v1.0)")
def new(title, title_opt, type, priority, label, assign, body, body_file, milestone):
    """Create a new issue.

    \b
    Examples:
      yait new "Fix login bug"
      yait new "Add dark mode" -t feature -l ui
      yait new "Crash on startup" -t bug -a alice -b "Repro: open app"
      yait new "Critical bug" -t bug --priority p0
      yait new "Release prep" --milestone v1.0
      yait new "Long desc" --body-file notes.md
      echo "body" | yait new "From stdin" --body -
    """
    resolved = title or title_opt
    if not resolved or not resolved.strip():
        raise click.ClickException("Title cannot be empty or whitespace only")
    root = _root()
    _require_init(root)
    resolved_body = _read_body(body, body_file)
    now = _now()
    nid = next_id(root)
    issue = Issue(
        id=nid,
        title=resolved,
        status="open",
        type=type,
        priority=priority,
        labels=list(label),
        assignee=assign,
        milestone=milestone,
        created_at=now,
        updated_at=now,
        body=resolved_body,
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
@click.option("--milestone", default=None, help="Filter by milestone")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.option("--sort", default="id", type=click.Choice(["id", "created", "updated"]), help="Sort order (default: id)")
@click.option("--has-doc", is_flag=True, default=False, help="Only issues with linked docs")
@click.option("--no-doc", is_flag=True, default=False, help="Only issues without linked docs")
@click.option("--doc", "doc_filter", default=None, help="Only issues linked to this doc slug/path")
def list_cmd(status, type, priority, label, assignee, milestone, as_json, sort, has_doc, no_doc, doc_filter):
    """List issues (default: open only).

    \b
    Examples:
      yait list
      yait list --status all
      yait list --type bug --label urgent
      yait list --milestone v1.0
      yait list --assignee alice --sort updated --json
    """
    root = _root()
    _require_init(root)
    st = None if status == "all" else status
    issues = list_issues(root, status=st, type=type, label=label, assignee=assignee, priority=priority, milestone=milestone)
    if has_doc:
        issues = [i for i in issues if i.docs]
    if no_doc:
        issues = [i for i in issues if not i.docs]
    if doc_filter:
        issues = [i for i in issues if doc_filter in i.docs]
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
    """Show issue details.

    \b
    Examples:
      yait show 1
      yait show 1 --json
    """
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
    if issue.priority and issue.priority != "none":
        click.echo(f"Priority: {issue.priority}")
    if issue.labels:
        click.echo(f"Labels: {', '.join(issue.labels)}")
    if issue.milestone:
        click.echo(f"Milestone: {issue.milestone}")
    if issue.assignee:
        click.echo(f"Assignee: {issue.assignee}")
    if issue.docs:
        click.echo("Docs:")
        for doc_ref in issue.docs:
            if "/" not in doc_ref:
                try:
                    d = load_doc(root, doc_ref)
                    click.echo(f"  - {doc_ref} ({d.title})")
                except FileNotFoundError:
                    click.echo(f"  - {doc_ref} (not found)")
            else:
                doc_file = root / doc_ref
                if doc_file.exists():
                    click.echo(f"  - {doc_ref}")
                else:
                    click.echo(f"  - {doc_ref} (file not found)")
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


# ── delete ──────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int)
@click.option("--force", "-f", is_flag=True, default=False, help="Skip confirmation prompt")
def delete(id, force):
    """Delete an issue permanently.

    \b
    Examples:
      yait delete 1
      yait delete 1 -f   # skip confirmation
    """
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    if not force:
        click.confirm(f"Are you sure you want to delete issue #{id}?", abort=True)
    delete_issue(root, id)
    click.echo(f"Deleted issue #{id}: {issue.title}")
    git_commit(root, f"yait: delete issue #{id}")


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
@click.option("--message", "-m", default=None, help="Comment text (use '-' for stdin)")
@click.option("--message-file", default=None, help="Read comment from file")
def comment(id, message, message_file):
    """Add a comment to an issue."""
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    message = _read_message(message, message_file)
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
@click.option("--priority", "-p", "new_priority", default=None, type=click.Choice(PRIORITIES), help="New priority")
@click.option("--assign", "-a", "new_assign", default=None, help="New assignee")
@click.option("--body", "-b", "new_body", default=None, help="New body (use '-' for stdin)")
@click.option("--body-file", "new_body_file", default=None, help="Read new body from file")
@click.option("--milestone", "-m", "new_milestone", default=None, help="New milestone")
def edit(id, new_title, new_type, new_priority, new_assign, new_body, new_body_file, new_milestone):
    """Edit an issue inline or in $EDITOR.

    \b
    Examples:
      yait edit 1 -T "New title"
      yait edit 1 -t bug -a bob
      yait edit 1 --priority p0
      yait edit 1 --milestone v2.0
      yait edit 1 --body-file updated.md
      yait edit 1                  # opens $EDITOR
    """
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    if new_body is not None or new_body_file is not None:
        resolved_body = _read_body(new_body, new_body_file)
        new_body = resolved_body
    if any(v is not None for v in (new_title, new_type, new_priority, new_assign, new_body, new_milestone)):
        if new_title is not None:
            issue.title = new_title
        if new_type is not None:
            issue.type = new_type
        if new_priority is not None:
            issue.priority = new_priority
        if new_assign is not None:
            issue.assignee = new_assign or None
        if new_body is not None:
            issue.body = new_body
        if new_milestone is not None:
            issue.milestone = new_milestone or None
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


# ── milestone ───────────────────────────────────────────────

@main.group()
def milestone():
    """Manage milestones."""


@milestone.command(name="create")
@click.argument("name")
@click.option("--description", "-d", default="", help="Milestone description")
@click.option("--due", default=None, help="Due date (YYYY-MM-DD)")
def milestone_create(name, description, due):
    """Create a new milestone.

    \b
    Examples:
      yait milestone create v1.0
      yait milestone create v1.0 --description "First release" --due 2026-06-01
    """
    root = _root()
    _require_init(root)
    m = Milestone(
        name=name,
        description=description,
        due_date=due or "",
        created_at=_now(),
    )
    try:
        save_milestone(root, m)
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f"Created milestone '{name}'")
    git_commit(root, f"yait: create milestone '{name}'")


@milestone.command(name="list")
@click.option("--status", default=None, type=click.Choice(list(MILESTONE_STATUSES)), help="Filter by status")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def milestone_list(status, as_json):
    """List milestones.

    \b
    Examples:
      yait milestone list
      yait milestone list --status open
      yait milestone list --json
    """
    root = _root()
    _require_init(root)
    milestones = list_milestones(root, status=status)
    if as_json:
        data = []
        for m in milestones:
            d = m.to_dict()
            d["name"] = m.name
            data.append(d)
        click.echo(json.dumps(data, indent=2))
        return
    if not milestones:
        click.echo("No milestones found.")
        return
    all_issues = list_issues(root, status=None)
    header = f"{'MILESTONE':<16}  {'STATUS':<8}  {'DUE':<12}  {'OPEN':>4}  {'CLOSED':>6}  PROGRESS"
    click.echo(click.style(header, bold=True))
    for m in milestones:
        refs = [i for i in all_issues if i.milestone == m.name]
        open_c = sum(1 for i in refs if i.status == "open")
        closed_c = sum(1 for i in refs if i.status == "closed")
        total = open_c + closed_c
        pct = f"{closed_c * 100 // total}%" if total else "\u2014"
        due_str = m.due_date or "\u2014"
        status_str = click.style(f"{m.status:<8}", fg=_status_color(m.status))
        click.echo(f"{m.name:<16}  {status_str}  {due_str:<12}  {open_c:>4}  {closed_c:>6}  {pct}")


@milestone.command(name="show")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def milestone_show(name, as_json):
    """Show milestone details.

    \b
    Examples:
      yait milestone show v1.0
      yait milestone show v1.0 --json
    """
    root = _root()
    _require_init(root)
    try:
        m = load_milestone(root, name)
    except KeyError:
        raise click.ClickException(f"Milestone '{name}' not found.")
    all_refs = [i for i in list_issues(root, status=None) if i.milestone == name]
    open_issues = [i for i in all_refs if i.status == "open"]
    closed_issues = [i for i in all_refs if i.status == "closed"]
    total = len(all_refs)
    pct = closed_issues.__len__() * 100 // total if total else 0

    if as_json:
        d = m.to_dict()
        d["name"] = m.name
        d["issues"] = {
            "total": total,
            "open": len(open_issues),
            "closed": len(closed_issues),
            "progress": pct,
        }
        d["open_issues"] = [i.to_dict() for i in open_issues]
        click.echo(json.dumps(d, indent=2))
        return

    status_str = click.style(m.status, fg=_status_color(m.status))
    click.echo(f"Milestone: {m.name}")
    click.echo(f"Status: {status_str}")
    if m.description:
        click.echo(f"Description: {m.description}")
    click.echo(f"Due: {m.due_date or '\u2014'}")
    click.echo(f"Issues: {total} total ({len(open_issues)} open, {len(closed_issues)} closed, {pct}% done)")

    if open_issues:
        click.echo(f"\nOpen issues:")
        for i in open_issues:
            assignee = i.assignee or "\u2014"
            click.echo(f"  #{i.id}  {click.style(i.type, fg=_type_color(i.type))}  {i.title}  {i.priority}  {assignee}")


@milestone.command(name="close")
@click.argument("name")
def milestone_close(name):
    """Close a milestone.

    \b
    Examples:
      yait milestone close v1.0
    """
    root = _root()
    _require_init(root)
    try:
        m = load_milestone(root, name)
    except KeyError:
        raise click.ClickException(f"Milestone '{name}' not found.")
    if m.status == "closed":
        click.echo(f"Milestone '{name}' is already closed.")
        return
    m.status = "closed"
    update_milestone(root, m)
    click.echo(f"Closed milestone '{name}'")
    git_commit(root, f"yait: close milestone '{name}'")


@milestone.command(name="reopen")
@click.argument("name")
def milestone_reopen(name):
    """Reopen a closed milestone.

    \b
    Examples:
      yait milestone reopen v1.0
    """
    root = _root()
    _require_init(root)
    try:
        m = load_milestone(root, name)
    except KeyError:
        raise click.ClickException(f"Milestone '{name}' not found.")
    if m.status == "open":
        click.echo(f"Milestone '{name}' is already open.")
        return
    m.status = "open"
    update_milestone(root, m)
    click.echo(f"Reopened milestone '{name}'")
    git_commit(root, f"yait: reopen milestone '{name}'")


@milestone.command(name="edit")
@click.argument("name")
@click.option("--description", "-d", default=None, help="New description")
@click.option("--due", default=None, help="New due date (YYYY-MM-DD)")
def milestone_edit(name, description, due):
    """Edit a milestone.

    \b
    Examples:
      yait milestone edit v1.0 --description "Updated"
      yait milestone edit v1.0 --due 2026-07-01
    """
    root = _root()
    _require_init(root)
    try:
        m = load_milestone(root, name)
    except KeyError:
        raise click.ClickException(f"Milestone '{name}' not found.")
    if description is None and due is None:
        raise click.ClickException("Nothing to edit. Use --description or --due.")
    if description is not None:
        m.description = description
    if due is not None:
        m.due_date = due
    try:
        update_milestone(root, m)
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f"Updated milestone '{name}'")
    git_commit(root, f"yait: edit milestone '{name}'")


@milestone.command(name="delete")
@click.argument("name")
@click.option("--force", "-f", is_flag=True, default=False, help="Force delete and clear issue references")
def milestone_delete(name, force):
    """Delete a milestone.

    \b
    Fails if issues reference it unless --force is used.
    With --force, clears the milestone field from all referencing issues.

    \b
    Examples:
      yait milestone delete v1.0
      yait milestone delete v1.0 --force
    """
    root = _root()
    _require_init(root)
    try:
        delete_milestone(root, name, force=force)
    except KeyError:
        raise click.ClickException(f"Milestone '{name}' not found.")
    except ValueError as e:
        raise click.ClickException(str(e).replace("force=True", "--force"))
    click.echo(f"Deleted milestone '{name}'")
    git_commit(root, f"yait: delete milestone '{name}'")


# ── search ───────────────────────────────────────────────────

@main.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("query")
@click.option(
    "--status", default="open",
    type=click.Choice(["open", "closed", "all"]),
    help="Filter by status (default: open)",
)
@click.option("--type", default=None, type=click.Choice(ISSUE_TYPES), help="Filter by type")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def search(query, status, type, as_json):
    """Full-text search across issue titles and bodies.

    \b
    Examples:
      yait search "login"
      yait search "crash" --status all
      yait search "api" --type bug --json
    """
    root = _root()
    _require_init(root)
    st = None if status == "all" else status
    issues = list_issues(root, status=st, type=type)
    q = query.lower()
    # Build doc title cache for search matching
    doc_titles = {}
    for d in list_docs(root):
        doc_titles[d.slug] = d.title.lower()
    matches = []
    for i in issues:
        if q in i.title.lower() or q in i.body.lower():
            matches.append(i)
            continue
        for doc_ref in i.docs:
            if "/" not in doc_ref and doc_ref in doc_titles and q in doc_titles[doc_ref]:
                matches.append(i)
                break
    if as_json:
        click.echo(json.dumps([i.to_dict() for i in matches], indent=2))
        return
    if not matches:
        click.echo("No matching issues.")
        return
    _print_issue_table(matches, highlight=query)


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
        sid = str(id)
        if not sid.isdigit():
            raise click.BadParameter(f"Invalid issue ID: {id!r}")
        path = f".yait/issues/{sid}.md"
    else:
        path = ".yait/"
    output = git_log(root, path, limit)
    if output:
        click.echo(output)
    else:
        click.echo("No history found.")


# ── export ──────────────────────────────────────────────────

@main.command(name="export")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "csv"]), help="Output format (default: json)")
@click.option("-o", "--output", "outfile", default=None, help="Output file path (default: stdout)")
def export_cmd(fmt, outfile):
    """Export all issues.

    \b
    Examples:
      yait export
      yait export --format csv
      yait export -o issues.json
      yait export --format csv -o issues.csv
    """
    root = _root()
    _require_init(root)
    issues = list_issues(root, status=None)
    issues.sort(key=lambda i: i.id)
    data = [i.to_dict() for i in issues]

    if fmt == "json":
        text = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        buf = io.StringIO()
        fieldnames = ["id", "title", "status", "type", "priority", "labels", "assignee", "milestone", "created_at", "updated_at", "body", "docs"]
        writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in data:
            row = dict(row)
            row["labels"] = ",".join(row["labels"]) if row["labels"] else ""
            row["docs"] = ",".join(row["docs"]) if row["docs"] else ""
            writer.writerow(row)
        text = buf.getvalue()

    if outfile:
        Path(outfile).write_text(text)
        click.echo(f"Exported {len(issues)} issues to {outfile}")
    else:
        click.echo(text, nl=False)


# ── import ──────────────────────────────────────────────────

@main.command(name="import")
@click.argument("file", type=click.Path(exists=True))
def import_cmd(file):
    """Import issues from a JSON file.

    \b
    Examples:
      yait import issues.json
    """
    root = _root()
    _require_init(root)
    data = json.loads(Path(file).read_text())
    if not isinstance(data, list):
        raise click.ClickException("Expected a JSON array of issues.")

    existing_ids = {i.id for i in list_issues(root, status=None)}
    imported = 0
    skipped = 0

    for item in data:
        issue_id = item.get("id")
        if issue_id in existing_ids:
            click.echo(f"Warning: skipping issue #{issue_id} (already exists)", err=True)
            skipped += 1
            continue
        issue = Issue(
            id=issue_id,
            title=item["title"],
            status=item.get("status", "open"),
            type=item.get("type", "misc"),
            priority=item.get("priority", "none"),
            labels=item.get("labels") or [],
            assignee=item.get("assignee"),
            milestone=item.get("milestone"),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
            body=item.get("body", ""),
        )
        save_issue(root, issue)
        imported += 1

    # Update next_id to be above the highest imported ID
    if imported > 0:
        from .store import _read_config, _write_config
        all_issues = list_issues(root, status=None)
        max_id = max(i.id for i in all_issues)
        cfg = _read_config(root)
        if cfg["next_id"] <= max_id:
            cfg["next_id"] = max_id + 1
            _write_config(root, cfg)
        git_commit(root, f"yait: import {imported} issues")

    click.echo(f"Imported {imported} issues, skipped {skipped}.")


# ── doc ────────────────────────────────────────────────────

@main.group()
def doc():
    """Manage documents linked to issues."""


@doc.command(name="create")
@click.argument("slug")
@click.option("--title", "-T", required=True, help="Document title")
@click.option("--body", "-b", default=None, help="Document body text")
@click.option("--body-file", default=None, help="Read body from file")
def doc_create(slug, title, body, body_file):
    """Create a managed document.

    \b
    Examples:
      yait doc create auth-prd --title "Auth PRD"
      yait doc create auth-prd --title "Auth PRD" -b "## Overview"
      yait doc create auth-prd --title "Auth PRD" --body-file draft.md
    """
    root = _root()
    _require_init(root)
    if "/" in slug:
        raise click.ClickException("Doc slug cannot contain '/'. Use a simple name like 'auth-prd'.")
    if not _SLUG_RE.match(slug):
        raise click.ClickException(f"Invalid slug: {slug!r}. Use letters, digits, hyphens, underscores.")
    if (_docs_dir(root) / f"{slug}.md").exists():
        raise click.ClickException(f"Doc '{slug}' already exists.")
    resolved_body = _read_body(body, body_file)
    if body is None and body_file is None:
        resolved_body = click.edit("") or ""
        resolved_body = resolved_body.strip()
    now = _now()
    d = Doc(slug=slug, title=title, created_at=now, updated_at=now, body=resolved_body)
    save_doc(root, d)
    click.echo(f"Created doc '{slug}': {title}")
    git_commit(root, f"yait: create doc '{slug}'")


@doc.command(name="show")
@click.argument("slug")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def doc_show(slug, as_json):
    """Show a managed document.

    \b
    Examples:
      yait doc show auth-prd
      yait doc show auth-prd --json
    """
    root = _root()
    _require_init(root)
    if "/" in slug:
        raise click.ClickException(f"'{slug}' is an external reference, not a managed doc. View it directly.")
    try:
        d = load_doc(root, slug)
    except FileNotFoundError:
        raise click.ClickException(f"Doc '{slug}' not found.")
    if as_json:
        data = d.to_dict()
        all_issues = list_issues(root, status=None)
        data["linked_issues"] = [i.id for i in all_issues if slug in i.docs]
        click.echo(json.dumps(data, indent=2))
        return
    click.echo(f"{d.slug}: {d.title}")
    click.echo(f"Created: {d.created_at}")
    click.echo(f"Updated: {d.updated_at}")
    all_issues = list_issues(root, status=None)
    linked = [i for i in all_issues if slug in i.docs]
    if linked:
        parts = [f"#{i.id} ({i.status})" for i in linked]
        click.echo(f"Linked issues: {', '.join(parts)}")
    if d.body:
        click.echo(f"\n{d.body}")


@doc.command(name="list")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def doc_list(as_json):
    """List all managed documents.

    \b
    Examples:
      yait doc list
      yait doc list --json
    """
    root = _root()
    _require_init(root)
    docs = list_docs(root)
    if as_json:
        all_issues = list_issues(root, status=None)
        data = []
        for d in docs:
            dd = d.to_dict()
            dd["linked_issues"] = [i.id for i in all_issues if d.slug in i.docs]
            data.append(dd)
        click.echo(json.dumps(data, indent=2))
        return
    if not docs:
        click.echo("No documents found.")
        return
    all_issues = list_issues(root, status=None)
    header = f"{'SLUG':<20}  {'TITLE':<24}  {'UPDATED':<20}  ISSUES"
    click.echo(click.style(header, bold=True))
    for d in docs:
        linked = [i for i in all_issues if d.slug in i.docs]
        issues_str = ", ".join(f"#{i.id}" for i in linked) if linked else "\u2014"
        updated = d.updated_at[:16] if d.updated_at else "\u2014"
        click.echo(f"{d.slug:<20}  {d.title:<24}  {updated:<20}  {issues_str}")


@doc.command(name="edit")
@click.argument("slug")
@click.option("--title", "-T", "new_title", default=None, help="New title")
@click.option("--body", "-b", "new_body", default=None, help="New body text")
def doc_edit(slug, new_title, new_body):
    """Edit a managed document.

    \b
    Examples:
      yait doc edit auth-prd
      yait doc edit auth-prd --title "New Title"
      yait doc edit auth-prd -b "New content"
    """
    root = _root()
    _require_init(root)
    try:
        d = load_doc(root, slug)
    except FileNotFoundError:
        raise click.ClickException(f"Doc '{slug}' not found.")
    if new_title is not None or new_body is not None:
        if new_title is not None:
            d.title = new_title
        if new_body is not None:
            d.body = new_body
    else:
        result = click.edit(d.body)
        if result is None:
            click.echo("Edit cancelled.")
            return
        d.body = result.strip()
    d.updated_at = _now()
    save_doc(root, d)
    click.echo(f"Updated doc '{slug}'")
    git_commit(root, f"yait: edit doc '{slug}'")


@doc.command(name="delete")
@click.argument("slug")
@click.option("--force", "-f", is_flag=True, default=False, help="Skip confirmation")
def doc_delete(slug, force):
    """Delete a managed document.

    \b
    Examples:
      yait doc delete auth-prd
      yait doc delete auth-prd -f
    """
    root = _root()
    _require_init(root)
    try:
        d = load_doc(root, slug)
    except FileNotFoundError:
        raise click.ClickException(f"Doc '{slug}' not found.")
    all_issues = list_issues(root, status=None)
    linked = [i for i in all_issues if slug in i.docs]
    if linked and not force:
        ids_str = ", ".join(f"#{i.id}" for i in linked)
        click.echo(f"Warning: {slug} is linked to {len(linked)} issues ({ids_str}).")
        click.echo("Delete will remove the document but NOT the references.")
        click.echo("Use 'yait doc unlink' to clean up first.")
        click.confirm("Are you sure?", abort=True)
    delete_doc(root, slug)
    click.echo(f"Deleted doc '{slug}'")
    git_commit(root, f"yait: delete doc '{slug}'")


@doc.command(name="link")
@click.argument("args", nargs=-1, required=True)
def doc_link(args):
    """Link a document to one or more issues.

    \b
    Last argument is the doc slug/path, preceding arguments are issue IDs.

    \b
    Examples:
      yait doc link 1 auth-prd
      yait doc link 1 docs/arch.md
      yait doc link 1 2 3 auth-prd
    """
    root = _root()
    _require_init(root)
    if len(args) < 2:
        raise click.ClickException("Usage: yait doc link <id> [id...] <doc>")
    doc_ref = args[-1]
    issue_ids = []
    for a in args[:-1]:
        try:
            issue_ids.append(int(a))
        except ValueError:
            raise click.ClickException(f"Invalid issue ID: {a!r}")
    linked_ids = []
    for iid in issue_ids:
        issue = _load_or_exit(root, iid)
        if doc_ref in issue.docs:
            click.echo(f"Issue #{iid} already linked to '{doc_ref}'.")
            continue
        issue.docs.append(doc_ref)
        issue.updated_at = _now()
        save_issue(root, issue)
        linked_ids.append(iid)
    if linked_ids:
        if len(linked_ids) == 1:
            click.echo(f"Linked doc '{doc_ref}' to issue #{linked_ids[0]}")
        else:
            ids_str = ", ".join(f"#{i}" for i in linked_ids)
            click.echo(f"Linked doc '{doc_ref}' to issues {ids_str}")
        git_commit(root, f"yait: link doc '{doc_ref}' to #{', #'.join(str(i) for i in linked_ids)}")


@doc.command(name="unlink")
@click.argument("id", type=int)
@click.argument("doc_ref")
def doc_unlink(id, doc_ref):
    """Unlink a document from an issue.

    \b
    Examples:
      yait doc unlink 1 auth-prd
    """
    root = _root()
    _require_init(root)
    issue = _load_or_exit(root, id)
    if doc_ref not in issue.docs:
        click.echo(f"Issue #{id} is not linked to '{doc_ref}'.")
        return
    issue.docs.remove(doc_ref)
    issue.updated_at = _now()
    save_issue(root, issue)
    click.echo(f"Unlinked doc '{doc_ref}' from issue #{id}")
    git_commit(root, f"yait: unlink doc '{doc_ref}' from #{id}")


# ── bulk ───────────────────────────────────────────────────

def _try_load(root: Path, issue_id: int) -> Issue | None:
    """Load an issue, returning None (with a warning) if not found."""
    try:
        return load_issue(root, issue_id)
    except (FileNotFoundError, ValueError):
        click.echo(f"Warning: issue #{issue_id} not found, skipping.", err=True)
        return None


def _bulk_summary(updated: int, failed: int, skipped: int = 0) -> None:
    parts = [f"Updated {updated} issues.", f"Failed: {failed}."]
    if skipped:
        parts.append(f"Skipped: {skipped}.")
    click.echo(" ".join(parts))


def _has_filters(**kwargs) -> bool:
    """Return True if any --filter-* option was provided."""
    return any(v is not None for v in kwargs.values())


def _resolve_bulk_issues(root: Path, ids: tuple[int, ...], **filters) -> list[Issue] | None:
    """Resolve issues from IDs or filters.

    Returns None on error (conflict or no match), printing appropriate message.
    """
    has_ids = len(ids) > 0
    has_filter = _has_filters(**filters)

    if has_ids and has_filter:
        click.echo("Error: Cannot use both issue IDs and --filter options.")
        return None
    if not has_ids and not has_filter:
        click.echo("Error: Provide issue IDs or --filter options.")
        return None

    if has_ids:
        # ID mode: return list with Nones for missing
        result = []
        for issue_id in ids:
            issue = _try_load(root, issue_id)
            result.append((issue_id, issue))
        return result

    # Filter mode
    status = filters.get("filter_status")
    issues = list_issues(
        root,
        status=status,
        type=filters.get("filter_type"),
        priority=filters.get("filter_priority"),
        label=filters.get("filter_label"),
        assignee=filters.get("filter_assignee"),
        milestone=filters.get("filter_milestone"),
    )
    if not issues:
        click.echo("No issues match the filter criteria.")
        return None
    return [(i.id, i) for i in issues]


def bulk_filter_options(f):
    """Decorator that adds --filter-* options to a bulk command."""
    f = click.option("--filter-status", default=None,
                     type=click.Choice(["open", "closed"]),
                     help="Filter by status")(f)
    f = click.option("--filter-type", default=None,
                     type=click.Choice(ISSUE_TYPES),
                     help="Filter by type")(f)
    f = click.option("--filter-priority", default=None,
                     type=click.Choice(PRIORITIES),
                     help="Filter by priority")(f)
    f = click.option("--filter-label", default=None,
                     help="Filter by label")(f)
    f = click.option("--filter-assignee", default=None,
                     help="Filter by assignee")(f)
    f = click.option("--filter-milestone", default=None,
                     help="Filter by milestone")(f)
    return f


@main.group()
def bulk():
    """Batch operations on multiple issues."""


# ── bulk label ──────────────────────────────────────────────

@bulk.group(name="label")
def bulk_label():
    """Bulk label operations."""


@bulk_label.command(name="add")
@click.argument("name")
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
def bulk_label_add(name, ids, filter_status, filter_type, filter_priority,
                   filter_label, filter_assignee, filter_milestone):
    """Add a label to multiple issues.

    \b
    Examples:
      yait bulk label add urgent 1 2 3 4 5
      yait bulk label add release-blocker --filter-priority p0 --filter-status open
    """
    root = _root()
    _require_init(root)
    pairs = _resolve_bulk_issues(root, ids,
        filter_status=filter_status, filter_type=filter_type,
        filter_priority=filter_priority, filter_label=filter_label,
        filter_assignee=filter_assignee, filter_milestone=filter_milestone)
    if pairs is None:
        return
    updated = 0
    failed = 0
    skipped = 0
    for issue_id, issue in pairs:
        if issue is None:
            failed += 1
            continue
        if name in issue.labels:
            click.echo(f"Issue #{issue_id} already has label '{name}', skipping.")
            skipped += 1
            continue
        issue.labels.append(name)
        issue.updated_at = _now()
        save_issue(root, issue)
        git_commit(root, f"yait: bulk label #{issue_id} +{name}")
        updated += 1
    _bulk_summary(updated, failed, skipped)


@bulk_label.command(name="remove")
@click.argument("name")
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
def bulk_label_remove(name, ids, filter_status, filter_type, filter_priority,
                      filter_label, filter_assignee, filter_milestone):
    """Remove a label from multiple issues.

    \b
    Examples:
      yait bulk label remove urgent 1 2 3
      yait bulk label remove urgent --filter-status open
    """
    root = _root()
    _require_init(root)
    pairs = _resolve_bulk_issues(root, ids,
        filter_status=filter_status, filter_type=filter_type,
        filter_priority=filter_priority, filter_label=filter_label,
        filter_assignee=filter_assignee, filter_milestone=filter_milestone)
    if pairs is None:
        return
    updated = 0
    failed = 0
    skipped = 0
    for issue_id, issue in pairs:
        if issue is None:
            failed += 1
            continue
        if name not in issue.labels:
            click.echo(f"Issue #{issue_id} does not have label '{name}', skipping.")
            skipped += 1
            continue
        issue.labels.remove(name)
        issue.updated_at = _now()
        save_issue(root, issue)
        git_commit(root, f"yait: bulk label #{issue_id} -{name}")
        updated += 1
    _bulk_summary(updated, failed, skipped)


# ── bulk assign / unassign ──────────────────────────────────

@bulk.command(name="assign")
@click.argument("name")
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
def bulk_assign(name, ids, filter_status, filter_type, filter_priority,
                filter_label, filter_assignee, filter_milestone):
    """Assign multiple issues to someone.

    \b
    Examples:
      yait bulk assign alice 1 2 3
      yait bulk assign alice --filter-milestone v1.0 --filter-status open
    """
    root = _root()
    _require_init(root)
    pairs = _resolve_bulk_issues(root, ids,
        filter_status=filter_status, filter_type=filter_type,
        filter_priority=filter_priority, filter_label=filter_label,
        filter_assignee=filter_assignee, filter_milestone=filter_milestone)
    if pairs is None:
        return
    updated = 0
    failed = 0
    for issue_id, issue in pairs:
        if issue is None:
            failed += 1
            continue
        issue.assignee = name
        issue.updated_at = _now()
        save_issue(root, issue)
        git_commit(root, f"yait: bulk assign #{issue_id} to {name}")
        updated += 1
    _bulk_summary(updated, failed)


@bulk.command(name="unassign")
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
def bulk_unassign(ids, filter_status, filter_type, filter_priority,
                  filter_label, filter_assignee, filter_milestone):
    """Remove assignee from multiple issues.

    \b
    Examples:
      yait bulk unassign 1 2 3
      yait bulk unassign --filter-status open --filter-assignee alice
    """
    root = _root()
    _require_init(root)
    pairs = _resolve_bulk_issues(root, ids,
        filter_status=filter_status, filter_type=filter_type,
        filter_priority=filter_priority, filter_label=filter_label,
        filter_assignee=filter_assignee, filter_milestone=filter_milestone)
    if pairs is None:
        return
    updated = 0
    failed = 0
    for issue_id, issue in pairs:
        if issue is None:
            failed += 1
            continue
        issue.assignee = None
        issue.updated_at = _now()
        save_issue(root, issue)
        git_commit(root, f"yait: bulk unassign #{issue_id}")
        updated += 1
    _bulk_summary(updated, failed)


# ── bulk priority ───────────────────────────────────────────

@bulk.command(name="priority")
@click.argument("value", type=click.Choice(PRIORITIES))
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
def bulk_priority(value, ids, filter_status, filter_type, filter_priority,
                  filter_label, filter_assignee, filter_milestone):
    """Set priority on multiple issues.

    \b
    Examples:
      yait bulk priority p0 1 2 3
      yait bulk priority p1 --filter-type bug --filter-status open
    """
    root = _root()
    _require_init(root)
    pairs = _resolve_bulk_issues(root, ids,
        filter_status=filter_status, filter_type=filter_type,
        filter_priority=filter_priority, filter_label=filter_label,
        filter_assignee=filter_assignee, filter_milestone=filter_milestone)
    if pairs is None:
        return
    updated = 0
    failed = 0
    for issue_id, issue in pairs:
        if issue is None:
            failed += 1
            continue
        issue.priority = value
        issue.updated_at = _now()
        save_issue(root, issue)
        git_commit(root, f"yait: bulk priority #{issue_id} -> {value}")
        updated += 1
    _bulk_summary(updated, failed)


# ── bulk milestone ──────────────────────────────────────────

@bulk.command(name="milestone")
@click.argument("value")
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
def bulk_milestone(value, ids, filter_status, filter_type, filter_priority,
                   filter_label, filter_assignee, filter_milestone):
    """Set milestone on multiple issues.

    \b
    Examples:
      yait bulk milestone v1.0 1 2 3
      yait bulk milestone v2.0 --filter-label deferred
    """
    root = _root()
    _require_init(root)
    pairs = _resolve_bulk_issues(root, ids,
        filter_status=filter_status, filter_type=filter_type,
        filter_priority=filter_priority, filter_label=filter_label,
        filter_assignee=filter_assignee, filter_milestone=filter_milestone)
    if pairs is None:
        return
    updated = 0
    failed = 0
    for issue_id, issue in pairs:
        if issue is None:
            failed += 1
            continue
        issue.milestone = value
        issue.updated_at = _now()
        save_issue(root, issue)
        git_commit(root, f"yait: bulk milestone #{issue_id} -> {value}")
        updated += 1
    _bulk_summary(updated, failed)


# ── bulk type ───────────────────────────────────────────────

@bulk.command(name="type")
@click.argument("value", type=click.Choice(ISSUE_TYPES))
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
def bulk_type(value, ids, filter_status, filter_type, filter_priority,
              filter_label, filter_assignee, filter_milestone):
    """Set type on multiple issues.

    \b
    Examples:
      yait bulk type bug 1 2 3
      yait bulk type enhancement --filter-label improvement
    """
    root = _root()
    _require_init(root)
    pairs = _resolve_bulk_issues(root, ids,
        filter_status=filter_status, filter_type=filter_type,
        filter_priority=filter_priority, filter_label=filter_label,
        filter_assignee=filter_assignee, filter_milestone=filter_milestone)
    if pairs is None:
        return
    updated = 0
    failed = 0
    for issue_id, issue in pairs:
        if issue is None:
            failed += 1
            continue
        issue.type = value
        issue.updated_at = _now()
        save_issue(root, issue)
        git_commit(root, f"yait: bulk type #{issue_id} -> {value}")
        updated += 1
    _bulk_summary(updated, failed)
