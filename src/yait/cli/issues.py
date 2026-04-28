from __future__ import annotations

import json
from pathlib import Path

import click
from ..lock import YaitLock
from ..models import ISSUE_TYPES, PRIORITIES, Issue
from ..store import (
    init_store, is_initialized, list_issues, load_issue, next_id, save_issue, delete_issue,
    get_defaults, get_workflow, resolve_status_filter, validate_status,
    load_template,
)
from . import main, _resolve, _require_init, _commit, _now, _load_or_exit, _read_body, _read_message, _yait_home, _project_create
from ._helpers import _print_issue_table, _status_color, _type_color


# ── init ─────────────────────────────────────────────────────

@main.command()
@click.pass_context
def init(ctx):
    """Initialize yait in current directory (or create named project with -P)."""
    from ..git_ops import git_commit as _git_commit
    project = ctx.obj.get("project")
    if project:
        project_dir = _yait_home() / "projects" / project
        if project_dir.exists() and is_initialized(project_dir):
            click.echo(f"Project '{project}' already initialized.")
            return
        _project_create(project)
        click.echo(f"Created project '{project}' at {project_dir}/")
        return
    data_dir = Path.cwd() / ".yait"
    if is_initialized(data_dir):
        click.echo("yait already initialized.")
        return
    init_store(data_dir)
    click.echo("Initialized yait in .yait/")
    _git_commit(Path.cwd(), "yait: init")


# ── new ──────────────────────────────────────────────────────

@main.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("title", required=False, default=None)
@click.option("--title", "-T", "title_opt", default=None, help="Issue title")
@click.option("--type", "-t", "type", default=None, type=click.Choice(ISSUE_TYPES), help="Issue type (default: misc)")
@click.option("--priority", "-p", default=None, type=click.Choice(PRIORITIES), help="Priority (default: none)")
@click.option("--label", "-l", multiple=True, help="Add label (repeatable)")
@click.option("--assign", "-a", default=None, help="Assignee")
@click.option("--body", "-b", default=None, help="Issue body text (use '-' for stdin)")
@click.option("--body-file", default=None, help="Read body from file")
@click.option("--milestone", "-m", default=None, help="Milestone (e.g. v1.0)")
@click.option("--template", "template_name", default=None, help="Create from template")
@click.pass_context
def new(ctx, title, title_opt, type, priority, label, assign, body, body_file, milestone, template_name):
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
      yait new "Login crash" --template bug
    """
    resolved = title or title_opt
    if not resolved or not resolved.strip():
        raise click.ClickException("Title cannot be empty or whitespace only")
    root = _resolve(ctx)
    _require_init(root)

    with YaitLock(root, "new"):
        cfg_defaults = get_defaults(root)

        tmpl_type = cfg_defaults["type"]
        tmpl_priority = cfg_defaults["priority"]
        tmpl_labels: list[str] = list(cfg_defaults["labels"])
        tmpl_body = ""
        tmpl_assignee = cfg_defaults["assignee"]
        if template_name:
            try:
                tmpl = load_template(root, template_name)
            except FileNotFoundError as e:
                raise click.ClickException(str(e))
            tmpl_type = tmpl.type
            tmpl_priority = tmpl.priority
            tmpl_labels = list(tmpl.labels)
            tmpl_body = tmpl.body

        final_type = type if type is not None else tmpl_type
        final_priority = priority if priority is not None else tmpl_priority
        final_labels = list(label) if label else tmpl_labels
        final_assignee = assign if assign is not None else tmpl_assignee

        resolved_body = _read_body(body, body_file)
        if not resolved_body and tmpl_body:
            resolved_body = tmpl_body

        now = _now()
        nid = next_id(root)
        issue = Issue(
            id=nid,
            title=resolved,
            status="open",
            type=final_type,
            priority=final_priority,
            labels=final_labels,
            assignee=final_assignee,
            milestone=milestone,
            created_at=now,
            updated_at=now,
            body=resolved_body,
        )
        save_issue(root, issue)
        click.echo(f"Created issue #{nid}: {resolved}")
        _commit(ctx, root, f"yait: create issue #{nid} \u2014 {resolved}")


# ── list ─────────────────────────────────────────────────────

@main.command(name="list")
@click.option(
    "--status", default="open",
    help="Filter by status (open, closed, all, or specific status)",
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
@click.option("--compact", is_flag=True, default=False, help="Compact output (ID + Status + Title)")
@click.option("--wide", is_flag=True, default=False, help="Wide output (all fields including dates)")
@click.pass_context
def list_cmd(ctx, status, type, priority, label, assignee, milestone, as_json, sort, has_doc, no_doc, doc_filter, compact, wide):
    """List issues (default: open only).

    \b
    Examples:
      yait list
      yait list --status all
      yait list --type bug --label urgent
      yait list --milestone v1.0
      yait list --assignee alice --sort updated --json
    """
    root = _resolve(ctx)
    _require_init(root)
    try:
        status_filter = resolve_status_filter(root, status)
    except ValueError as e:
        raise click.ClickException(str(e))
    issues = list_issues(root, status_list=status_filter, type=type, label=label, assignee=assignee, priority=priority, milestone=milestone)
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
    if compact and wide:
        raise click.ClickException("Cannot use both --compact and --wide.")
    display_mode = "compact" if compact else ("wide" if wide else None)
    _print_issue_table(issues, root=root, mode=display_mode)


# ── show ─────────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int)
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
def show(ctx, id, as_json):
    """Show issue details.

    \b
    Examples:
      yait show 1
      yait show 1 --json
    """
    from ..store import load_doc
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)
    if as_json:
        data = issue.to_dict()
        enriched_links = []
        for link in issue.links:
            entry = dict(link)
            try:
                t = load_issue(root, link["target"])
                entry["target_status"] = t.status
                entry["target_title"] = t.title
            except (FileNotFoundError, ValueError):
                entry["target_status"] = "deleted"
                entry["target_title"] = ""
            enriched_links.append(entry)
        data["links"] = enriched_links
        click.echo(json.dumps(data, indent=2))
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
                if ctx.obj.get("is_project"):
                    click.echo(f"  - {doc_ref} (external ref, not available in project mode)")
                else:
                    doc_file = root.parent / doc_ref
                    if doc_file.exists():
                        click.echo(f"  - {doc_ref}")
                    else:
                        click.echo(f"  - {doc_ref} (file not found)")
    if issue.links:
        click.echo("Links:")
        for link in issue.links:
            lt = link["type"]
            tid = link["target"]
            try:
                t = load_issue(root, tid)
                t_status = click.style(t.status, fg=_status_color(t.status))
                click.echo(f"  {lt} #{tid} ({t_status}): {t.title}")
            except (FileNotFoundError, ValueError):
                click.echo(f"  {lt} #{tid} (deleted)")
    click.echo(f"Created: {issue.created_at}")
    click.echo(f"Updated: {issue.updated_at}")
    click.echo(f"Comments: {comment_count}")
    if issue.body:
        click.echo(f"\n{issue.body}")


# ── status ────────────────────────────────────────────────────

@main.command(name="status")
@click.argument("id", type=int)
@click.argument("new_status", required=False, default=None)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def status_cmd(ctx, id, new_status, as_json):
    """View or change issue status.

    \b
    Examples:
      yait status 1              # show current status
      yait status 1 in-progress  # change status
      yait status 1 --json       # JSON output
    """
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)

    if new_status is None:
        if as_json:
            click.echo(json.dumps({"id": id, "status": issue.status}))
        else:
            click.echo(f"Issue #{id}: {click.style(issue.status, fg=_status_color(issue.status, root))}")
        return

    try:
        validate_status(root, new_status)
    except ValueError as e:
        raise click.ClickException(str(e))

    with YaitLock(root, "status"):
        issue.status = new_status
        issue.updated_at = _now()
        save_issue(root, issue)
        click.echo(f"Issue #{id} status \u2192 {new_status}")
        _commit(ctx, root, f"yait: status #{id} -> {new_status}")


# ── close ────────────────────────────────────────────────────

@main.command()
@click.argument("ids", nargs=-1, type=int, required=True)
@click.pass_context
def close(ctx, ids):
    """Close one or more issues."""
    root = _resolve(ctx)
    _require_init(root)
    wf = get_workflow(root)
    closed_status = wf["closed_statuses"][0]
    closed_set = set(wf["closed_statuses"])
    with YaitLock(root, "close"):
        for id in ids:
            issue = _load_or_exit(root, id)
            if issue.status in closed_set:
                click.echo(f"Issue #{id} is already closed.")
                continue
            issue.status = closed_status
            issue.updated_at = _now()
            save_issue(root, issue)
            click.echo(f"Closed issue #{id}: {issue.title}")
            _commit(ctx, root, f"yait: close issue #{id}")


# ── delete ──────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int)
@click.option("--force", "-f", is_flag=True, default=False, help="Skip confirmation prompt")
@click.pass_context
def delete(ctx, id, force):
    """Delete an issue permanently.

    \b
    Examples:
      yait delete 1
      yait delete 1 -f   # skip confirmation
    """
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)
    if not force:
        click.confirm(f"Are you sure you want to delete issue #{id}?", abort=True)
    with YaitLock(root, "delete"):
        delete_issue(root, id)
        click.echo(f"Deleted issue #{id}: {issue.title}")
        _commit(ctx, root, f"yait: delete issue #{id}")


# ── reopen ───────────────────────────────────────────────────

@main.command()
@click.argument("ids", nargs=-1, type=int, required=True)
@click.pass_context
def reopen(ctx, ids):
    """Reopen one or more closed issues."""
    root = _resolve(ctx)
    _require_init(root)
    wf = get_workflow(root)
    closed_set = set(wf["closed_statuses"])
    open_statuses = [s for s in wf["statuses"] if s not in closed_set]
    open_status = open_statuses[0]
    with YaitLock(root, "reopen"):
        for id in ids:
            issue = _load_or_exit(root, id)
            if issue.status not in closed_set:
                click.echo(f"Issue #{id} is already open.")
                continue
            issue.status = open_status
            issue.updated_at = _now()
            save_issue(root, issue)
            click.echo(f"Reopened issue #{id}: {issue.title}")
            _commit(ctx, root, f"yait: reopen issue #{id}")


# ── comment ──────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int)
@click.option("--message", "-m", default=None, help="Comment text (use '-' for stdin)")
@click.option("--message-file", default=None, help="Read comment from file")
@click.pass_context
def comment(ctx, id, message, message_file):
    """Add a comment to an issue."""
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)
    message = _read_message(message, message_file)
    if message is None:
        message = click.edit()
        if not message or not message.strip():
            click.echo("Aborted: empty comment.")
            return
        message = message.strip()
    with YaitLock(root, "comment"):
        now = _now()
        separator = "\n\n---\n" if issue.body else ""
        issue.body += f"{separator}**Comment** ({now}):\n{message}"
        issue.updated_at = now
        save_issue(root, issue)
        click.echo(f"Added comment to issue #{id}")
        _commit(ctx, root, f"yait: comment on issue #{id}")


# ── edit ─────────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int)
@click.option("--title", "-T", "new_title", default=None, help="New title")
@click.option("--type", "-t", "new_type", default=None, type=click.Choice(ISSUE_TYPES), help="New type")
@click.option("--priority", "-p", "new_priority", default=None, type=click.Choice(PRIORITIES), help="New priority")
@click.option("--status", "-s", "new_status", default=None, help="New status")
@click.option("--assign", "-a", "new_assign", default=None, help="New assignee")
@click.option("--body", "-b", "new_body", default=None, help="New body (use '-' for stdin)")
@click.option("--body-file", "new_body_file", default=None, help="Read new body from file")
@click.option("--milestone", "-m", "new_milestone", default=None, help="New milestone")
@click.pass_context
def edit(ctx, id, new_title, new_type, new_priority, new_status, new_assign, new_body, new_body_file, new_milestone):
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
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)
    if new_body is not None or new_body_file is not None:
        resolved_body = _read_body(new_body, new_body_file)
        new_body = resolved_body
    if any(v is not None for v in (new_title, new_type, new_priority, new_status, new_assign, new_body, new_milestone)):
        with YaitLock(root, "edit"):
            if new_title is not None:
                issue.title = new_title
            if new_type is not None:
                issue.type = new_type
            if new_priority is not None:
                issue.priority = new_priority
            if new_status is not None:
                try:
                    validate_status(root, new_status)
                except ValueError as e:
                    raise click.ClickException(str(e))
                issue.status = new_status
            if new_assign is not None:
                issue.assignee = new_assign or None
            if new_body is not None:
                issue.body = new_body
            if new_milestone is not None:
                issue.milestone = new_milestone or None
            issue.updated_at = _now()
            save_issue(root, issue)
            click.echo(f"Updated issue #{id}: {issue.title}")
            _commit(ctx, root, f"yait: edit #{id}")
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
        with YaitLock(root, "edit"):
            issue.updated_at = _now()
            save_issue(root, issue)
            click.echo(f"Updated issue #{id}: {issue.title}")
            _commit(ctx, root, f"yait: edit #{id}")


# ── assign / unassign ──────────────────────────────────────

@main.command()
@click.argument("id", type=int)
@click.argument("name")
@click.pass_context
def assign(ctx, id, name):
    """Assign an issue to someone."""
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)
    with YaitLock(root, "assign"):
        issue.assignee = name
        issue.updated_at = _now()
        save_issue(root, issue)
        click.echo(f"Assigned issue #{id} to {name}")
        _commit(ctx, root, f"yait: assign #{id} to {name}")


@main.command()
@click.argument("id", type=int)
@click.pass_context
def unassign(ctx, id):
    """Remove assignee from an issue."""
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)
    with YaitLock(root, "unassign"):
        issue.assignee = None
        issue.updated_at = _now()
        save_issue(root, issue)
        click.echo(f"Unassigned issue #{id}")
        _commit(ctx, root, f"yait: unassign #{id}")
