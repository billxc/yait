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
from .models import ISSUE_TYPES, PRIORITIES, Issue
from .store import init_store, is_initialized, list_issues, load_issue, next_id, save_issue, delete_issue


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
def list_cmd(status, type, priority, label, assignee, milestone, as_json, sort):
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
        fieldnames = ["id", "title", "status", "type", "priority", "labels", "assignee", "created_at", "updated_at", "body"]
        writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in data:
            row = dict(row)
            row["labels"] = ",".join(row["labels"]) if row["labels"] else ""
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
