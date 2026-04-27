from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import csv
import io
import shutil
import sys

import click
import yaml

from . import __version__
from .git_ops import git_commit, git_log, is_git_repo
from .lock import YaitLock
from .models import ISSUE_TYPES, PRIORITIES, MILESTONE_STATUSES, LINK_TYPES, LINK_REVERSE, Issue, Milestone, Template, Doc, _SLUG_RE
from .store import (
    init_store, is_initialized, list_issues, load_issue, next_id, save_issue, delete_issue,
    save_milestone, load_milestone, list_milestones, update_milestone, delete_milestone,
    save_template, load_template, list_templates, delete_template,
    save_doc, load_doc, list_docs, delete_doc, _docs_dir,
    add_link, remove_link,
    get_defaults, get_display, get_config_value, set_config_value, reset_config_value,
    _DEFAULT_DEFAULTS, _DEFAULT_DISPLAY,
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


def _resolve(ctx) -> Path:
    """Resolve the yait data directory from --project, YAIT_PROJECT, or cwd.

    Returns the Path to the data directory (containing config.yaml, issues/, etc).
    Also stores is_project in ctx.obj for git staging decisions.
    """
    if ctx.obj.get("data_dir") is not None:
        return ctx.obj["data_dir"]

    project = ctx.obj.get("project")
    yait_home = Path(os.environ.get("YAIT_HOME", "~/.yait")).expanduser()

    name = project or os.environ.get("YAIT_PROJECT")
    if name:
        p = yait_home / "projects" / name
        if not p.is_dir():
            raise click.ClickException(
                f"Project '{name}' not found.\n"
                f"  Create it:      yait project create {name}\n"
                f"  List projects:  yait project list\n"
                f"  Import local:   yait project import {name}"
            )
        ctx.obj["data_dir"] = p
        ctx.obj["is_project"] = True
        return p

    local = Path.cwd() / ".yait"
    if local.is_dir():
        ctx.obj["data_dir"] = local
        ctx.obj["is_project"] = False
        return local

    raise click.ClickException(
        "No yait project found.\n\n"
        "  Use one of:\n"
        "    yait -P <name> <command>     Use a named project\n"
        "    export YAIT_PROJECT=<name>   Set default project for this shell\n"
        "    yait init                    Create local .yait/ in current directory\n"
        "    yait project create <name>   Create a new named project\n\n"
        "  List existing projects: yait project list"
    )


def _commit(ctx, root: Path, message: str) -> None:
    """Git commit helper that handles local vs project mode staging."""
    if ctx.obj.get("is_project"):
        git_commit(root, message, ".")
    else:
        git_commit(root.parent, message, ".yait")


_PROJECT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


def _validate_project_name(name: str) -> None:
    if not name or len(name) > 64:
        raise click.ClickException(
            "Project name must be 1-64 characters."
        )
    if not _PROJECT_NAME_RE.match(name):
        raise click.ClickException(
            f"Invalid project name: {name!r}. "
            "Must start with alphanumeric, contain only [a-zA-Z0-9_-]."
        )


def _yait_home() -> Path:
    return Path(os.environ.get("YAIT_HOME", "~/.yait")).expanduser()


def _project_create(name: str) -> Path:
    """Create a named project. Returns the project data dir."""
    _validate_project_name(name)
    home = _yait_home()
    project_dir = home / "projects" / name
    if project_dir.exists():
        raise click.ClickException(
            f"Project '{name}' already exists at {project_dir}"
        )
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    (home / "projects").mkdir(mode=0o700, exist_ok=True)
    project_dir.mkdir(parents=True)
    init_store(project_dir)
    (project_dir / ".gitignore").write_text("yait.lock\n")
    # Initialize git repo in project dir
    import subprocess
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "yait@local"], cwd=project_dir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "yait"], cwd=project_dir, capture_output=True)
    git_commit(project_dir, "yait: init project", ".")
    return project_dir


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


def _detect_display_mode() -> str:
    """Auto-detect display mode based on terminal width.

    Returns 'compact' (<80), 'normal' (80-120), or 'wide' (>120).
    Falls back to 'normal' when terminal size cannot be detected (e.g. pipe).
    """
    try:
        cols = os.get_terminal_size().columns
    except (OSError, ValueError):
        return "normal"
    if cols < 80:
        return "compact"
    elif cols > 120:
        return "wide"
    return "normal"


def _truncate_title(title: str, max_width: int) -> str:
    """Truncate title to max_width, appending '...' if needed."""
    if len(title) <= max_width:
        return title
    return title[:max_width - 3] + "..."


def _format_date(dt_str: str, fmt: str = "short") -> str:
    """Format an ISO datetime string for display."""
    if not dt_str:
        return "\u2014"
    if fmt == "short":
        return dt_str[:10]
    return dt_str[:19]


def _print_issue_table(
    issues: list[Issue],
    highlight: str | None = None,
    root: Path | None = None,
    mode: str | None = None,
) -> None:
    if not issues:
        click.echo('No issues found. Create one with: yait new "..."')
        return
    # Read display settings
    max_title_w = 50
    date_fmt = "short"
    if root is not None:
        try:
            display = get_display(root)
            max_title_w = display.get("max_title_width", 50)
            date_fmt = display.get("date_format", "short")
        except Exception:
            pass

    # Determine display mode
    if mode is None:
        mode = _detect_display_mode()

    id_w = max(len(f"#{i.id}") for i in issues)
    st_w = max(len(i.status) for i in issues)
    ti_w = min(max(len(i.title) for i in issues), max_title_w)

    if mode == "compact":
        header = f"{'#':<{id_w}}  {'STATUS':<{st_w}}  TITLE"
        click.echo(click.style(header, bold=True))
        for i in issues:
            status_str = click.style(f"{i.status:<{st_w}}", fg=_status_color(i.status))
            display_title = _truncate_title(i.title, max_title_w)
            title = _highlight_text(display_title, highlight) if highlight else display_title
            click.echo(f"{'#' + str(i.id):<{id_w}}  {status_str}  {title}")

    elif mode == "wide":
        ty_w = max(len(i.type) for i in issues)
        pr_w = max((len(i.priority) for i in issues), default=4)
        ms_w = max((len(i.milestone or "\u2014") for i in issues), default=4)
        as_w = max((len(i.assignee or "\u2014") for i in issues), default=8)
        date_w = 10 if date_fmt == "short" else 19
        header = (
            f"{'#':<{id_w}}  {'STATUS':<{st_w}}  {'TYPE':<{ty_w}}  "
            f"{'PRIORITY':<{pr_w}}  {'TITLE':<{ti_w}}  {'LABELS':<12}  "
            f"{'MILESTONE':<{ms_w}}  {'ASSIGNEE':<{as_w}}  "
            f"{'CREATED':<{date_w}}  UPDATED"
        )
        click.echo(click.style(header, bold=True))
        for i in issues:
            status_str = click.style(f"{i.status:<{st_w}}", fg=_status_color(i.status))
            type_str = click.style(f"{i.type:<{ty_w}}", fg=_type_color(i.type))
            display_title = _truncate_title(i.title, max_title_w)
            title = _highlight_text(display_title, highlight) if highlight else display_title
            pad = ti_w - len(display_title)
            title_padded = title + " " * max(pad, 0)
            labels = ",".join(i.labels) if i.labels else "\u2014"
            assignee = i.assignee or "\u2014"
            priority = i.priority or "none"
            ms = i.milestone or "\u2014"
            created = _format_date(i.created_at, date_fmt)
            updated = _format_date(i.updated_at, date_fmt)
            click.echo(
                f"{'#' + str(i.id):<{id_w}}  {status_str}  {type_str}  "
                f"{priority:<{pr_w}}  {title_padded}  {labels:<12}  "
                f"{ms:<{ms_w}}  {assignee:<{as_w}}  "
                f"{created:<{date_w}}  {updated}"
            )

    else:  # normal
        ty_w = max(len(i.type) for i in issues)
        header = f"{'#':<{id_w}}  {'STATUS':<{st_w}}  {'TYPE':<{ty_w}}  {'TITLE':<{ti_w}}  {'LABELS':<12}  ASSIGNEE"
        click.echo(click.style(header, bold=True))
        for i in issues:
            labels = ",".join(i.labels) if i.labels else "\u2014"
            assignee = i.assignee or "\u2014"
            status_str = click.style(f"{i.status:<{st_w}}", fg=_status_color(i.status))
            type_str = click.style(f"{i.type:<{ty_w}}", fg=_type_color(i.type))
            display_title = _truncate_title(i.title, max_title_w)
            title = _highlight_text(display_title, highlight) if highlight else display_title
            pad = ti_w - len(display_title)
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
@click.option("--project", "-P", default=None, envvar="YAIT_PROJECT",
              help="Named project (stored in ~/.yait/projects/)")
@click.pass_context
def main(ctx, project):
    """yait — Yet Another Issue Tracker

    A lightweight, git-backed issue tracker that lives in your repo.
    Issues are stored as Markdown files and every change is auto-committed.
    """
    ctx.ensure_object(dict)
    ctx.obj["project"] = project


# ── init ─────────────────────────────────────────────────────

@main.command()
@click.pass_context
def init(ctx):
    """Initialize yait in current directory (or create named project with -P)."""
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
    # init creates .yait/ so we cannot lock before it exists.
    init_store(data_dir)
    click.echo("Initialized yait in .yait/")
    git_commit(Path.cwd(), "yait: init")


# ── config ──────────────────────────────────────────────────

@main.group(invoke_without_command=True)
@click.pass_context
def config(ctx):
    """View or modify yait configuration.

    \b
    Examples:
      yait config                         # show all config
      yait config set defaults.type bug   # set a value
      yait config reset defaults.type     # reset to default
    """
    if ctx.invoked_subcommand is not None:
        return
    root = _resolve(ctx)
    _require_init(root)
    defaults = get_defaults(root)
    display = get_display(root)
    click.echo(click.style("defaults:", bold=True))
    for k, v in sorted(defaults.items()):
        default_marker = ""
        if k in _DEFAULT_DEFAULTS and defaults[k] == _DEFAULT_DEFAULTS[k]:
            default_marker = " (default)"
        click.echo(f"  {k}: {_format_config_value(v)}{default_marker}")
    click.echo(click.style("display:", bold=True))
    for k, v in sorted(display.items()):
        default_marker = ""
        if k in _DEFAULT_DISPLAY and display[k] == _DEFAULT_DISPLAY[k]:
            default_marker = " (default)"
        click.echo(f"  {k}: {_format_config_value(v)}{default_marker}")


def _format_config_value(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, list):
        return ", ".join(v) if v else "[]"
    return str(v)


@config.command(name="set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx, key, value):
    """Set a configuration value.

    \b
    Examples:
      yait config set defaults.type bug
      yait config set defaults.priority p2
      yait config set defaults.assignee alice
      yait config set defaults.labels urgent,frontend
      yait config set display.max_title_width 60
      yait config set display.date_format full
    """
    root = _resolve(ctx)
    _require_init(root)
    with YaitLock(root, "config set"):
        try:
            set_config_value(root, key, value)
        except (KeyError, ValueError) as e:
            raise click.ClickException(str(e))
        click.echo(f"Set {key} = {value}")


@config.command(name="reset")
@click.argument("key")
@click.pass_context
def config_reset(ctx, key):
    """Reset a configuration value to its default.

    \b
    Examples:
      yait config reset defaults.type
      yait config reset display.max_title_width
    """
    root = _resolve(ctx)
    _require_init(root)
    with YaitLock(root, "config reset"):
        try:
            reset_config_value(root, key)
        except KeyError as e:
            raise click.ClickException(str(e))
        click.echo(f"Reset {key} to default")


# ── new ──────────────────────────────────────────────────────

@main.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("title", required=False, default=None)
@click.option("--title", "title_opt", default=None, help="Issue title")
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
        # Load config defaults as the base fallback
        cfg_defaults = get_defaults(root)

        # Load template defaults if specified
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

        # CLI args override template/config values
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
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)
    if as_json:
        data = issue.to_dict()
        # Enrich links with target info
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


# ── close ────────────────────────────────────────────────────

@main.command()
@click.argument("ids", nargs=-1, type=int, required=True)
@click.pass_context
def close(ctx, ids):
    """Close one or more issues."""
    root = _resolve(ctx)
    _require_init(root)
    with YaitLock(root, "close"):
        for id in ids:
            issue = _load_or_exit(root, id)
            if issue.status == "closed":
                click.echo(f"Issue #{id} is already closed.")
                continue
            issue.status = "closed"
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
    with YaitLock(root, "reopen"):
        for id in ids:
            issue = _load_or_exit(root, id)
            if issue.status == "open":
                click.echo(f"Issue #{id} is already open.")
                continue
            issue.status = "open"
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
@click.option("--assign", "-a", "new_assign", default=None, help="New assignee")
@click.option("--body", "-b", "new_body", default=None, help="New body (use '-' for stdin)")
@click.option("--body-file", "new_body_file", default=None, help="Read new body from file")
@click.option("--milestone", "-m", "new_milestone", default=None, help="New milestone")
@click.pass_context
def edit(ctx, id, new_title, new_type, new_priority, new_assign, new_body, new_body_file, new_milestone):
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
    if any(v is not None for v in (new_title, new_type, new_priority, new_assign, new_body, new_milestone)):
        with YaitLock(root, "edit"):
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


# ── label ────────────────────────────────────────────────────

@main.group()
def label():
    """Manage issue labels."""


@label.command(name="add")
@click.argument("id", type=int)
@click.argument("name")
@click.pass_context
def label_add(ctx, id, name):
    """Add a label to an issue."""
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)
    if name in issue.labels:
        click.echo(f"Issue #{id} already has label '{name}'.")
        return
    with YaitLock(root, "label add"):
        issue.labels.append(name)
        issue.updated_at = _now()
        save_issue(root, issue)
        click.echo(f"Added label '{name}' to issue #{id}")
        _commit(ctx, root, f"yait: label #{id} +{name}")


@label.command(name="remove")
@click.argument("id", type=int)
@click.argument("name")
@click.pass_context
def label_remove(ctx, id, name):
    """Remove a label from an issue."""
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)
    if name not in issue.labels:
        click.echo(f"Issue #{id} does not have label '{name}'.")
        return
    with YaitLock(root, "label remove"):
        issue.labels.remove(name)
        issue.updated_at = _now()
        save_issue(root, issue)
        click.echo(f"Removed label '{name}' from issue #{id}")
        _commit(ctx, root, f"yait: label #{id} -{name}")


# ── milestone ───────────────────────────────────────────────

@main.group()
def milestone():
    """Manage milestones."""


@milestone.command(name="create")
@click.argument("name")
@click.option("--description", "-d", default="", help="Milestone description")
@click.option("--due", default=None, help="Due date (YYYY-MM-DD)")
@click.pass_context
def milestone_create(ctx, name, description, due):
    """Create a new milestone.

    \b
    Examples:
      yait milestone create v1.0
      yait milestone create v1.0 --description "First release" --due 2026-06-01
    """
    root = _resolve(ctx)
    _require_init(root)
    m = Milestone(
        name=name,
        description=description,
        due_date=due or "",
        created_at=_now(),
    )
    with YaitLock(root, "milestone create"):
        try:
            save_milestone(root, m)
        except ValueError as e:
            raise click.ClickException(str(e))
        click.echo(f"Created milestone '{name}'")
        _commit(ctx, root, f"yait: create milestone '{name}'")


@milestone.command(name="list")
@click.option("--status", default=None, type=click.Choice(list(MILESTONE_STATUSES)), help="Filter by status")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
def milestone_list(ctx, status, as_json):
    """List milestones.

    \b
    Examples:
      yait milestone list
      yait milestone list --status open
      yait milestone list --json
    """
    root = _resolve(ctx)
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
@click.pass_context
def milestone_show(ctx, name, as_json):
    """Show milestone details.

    \b
    Examples:
      yait milestone show v1.0
      yait milestone show v1.0 --json
    """
    root = _resolve(ctx)
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
@click.pass_context
def milestone_close(ctx, name):
    """Close a milestone.

    \b
    Examples:
      yait milestone close v1.0
    """
    root = _resolve(ctx)
    _require_init(root)
    try:
        m = load_milestone(root, name)
    except KeyError:
        raise click.ClickException(f"Milestone '{name}' not found.")
    if m.status == "closed":
        click.echo(f"Milestone '{name}' is already closed.")
        return
    with YaitLock(root, "milestone close"):
        m.status = "closed"
        update_milestone(root, m)
        click.echo(f"Closed milestone '{name}'")
        _commit(ctx, root, f"yait: close milestone '{name}'")


@milestone.command(name="reopen")
@click.argument("name")
@click.pass_context
def milestone_reopen(ctx, name):
    """Reopen a closed milestone.

    \b
    Examples:
      yait milestone reopen v1.0
    """
    root = _resolve(ctx)
    _require_init(root)
    try:
        m = load_milestone(root, name)
    except KeyError:
        raise click.ClickException(f"Milestone '{name}' not found.")
    if m.status == "open":
        click.echo(f"Milestone '{name}' is already open.")
        return
    with YaitLock(root, "milestone reopen"):
        m.status = "open"
        update_milestone(root, m)
        click.echo(f"Reopened milestone '{name}'")
        _commit(ctx, root, f"yait: reopen milestone '{name}'")


@milestone.command(name="edit")
@click.argument("name")
@click.option("--description", "-d", default=None, help="New description")
@click.option("--due", default=None, help="New due date (YYYY-MM-DD)")
@click.pass_context
def milestone_edit(ctx, name, description, due):
    """Edit a milestone.

    \b
    Examples:
      yait milestone edit v1.0 --description "Updated"
      yait milestone edit v1.0 --due 2026-07-01
    """
    root = _resolve(ctx)
    _require_init(root)
    try:
        m = load_milestone(root, name)
    except KeyError:
        raise click.ClickException(f"Milestone '{name}' not found.")
    if description is None and due is None:
        raise click.ClickException("Nothing to edit. Use --description or --due.")
    with YaitLock(root, "milestone edit"):
        if description is not None:
            m.description = description
        if due is not None:
            m.due_date = due
        try:
            update_milestone(root, m)
        except ValueError as e:
            raise click.ClickException(str(e))
        click.echo(f"Updated milestone '{name}'")
        _commit(ctx, root, f"yait: edit milestone '{name}'")


@milestone.command(name="delete")
@click.argument("name")
@click.option("--force", "-f", is_flag=True, default=False, help="Force delete and clear issue references")
@click.pass_context
def milestone_delete(ctx, name, force):
    """Delete a milestone.

    \b
    Fails if issues reference it unless --force is used.
    With --force, clears the milestone field from all referencing issues.

    \b
    Examples:
      yait milestone delete v1.0
      yait milestone delete v1.0 --force
    """
    root = _resolve(ctx)
    _require_init(root)
    with YaitLock(root, "milestone delete"):
        try:
            delete_milestone(root, name, force=force)
        except KeyError:
            raise click.ClickException(f"Milestone '{name}' not found.")
        except ValueError as e:
            raise click.ClickException(str(e).replace("force=True", "--force"))
        click.echo(f"Deleted milestone '{name}'")
        _commit(ctx, root, f"yait: delete milestone '{name}'")


# ── template ───────────────────────────────────────────────

@main.group()
def template():
    """Manage issue templates."""


@template.command(name="create")
@click.argument("name")
@click.pass_context
def template_create(ctx, name):
    """Create or edit an issue template.

    \b
    Opens $EDITOR to define template frontmatter and body.

    \b
    Examples:
      yait template create bug
      yait template create feature
    """
    root = _resolve(ctx)
    _require_init(root)
    try:
        existing = load_template(root, name)
        fm = {
            "name": existing.name,
            "type": existing.type,
            "priority": existing.priority,
            "labels": existing.labels,
        }
        initial = "---\n" + yaml.dump(fm, default_flow_style=False).rstrip("\n") + "\n---\n"
        if existing.body:
            initial += "\n" + existing.body + "\n"
    except FileNotFoundError:
        fm = {
            "name": name,
            "type": "misc",
            "priority": "none",
            "labels": [],
        }
        initial = "---\n" + yaml.dump(fm, default_flow_style=False).rstrip("\n") + "\n---\n"
        initial += "\n"

    result = click.edit(initial)
    if result is None:
        click.echo("Aborted: editor returned empty.")
        return

    text = result.strip()
    if not text.startswith("---"):
        raise click.ClickException("Invalid template: missing YAML frontmatter (---).")

    try:
        end_idx = text.index("---", 3)
    except ValueError:
        raise click.ClickException("Invalid template: missing closing --- delimiter.")
    fm_text = text[3:end_idx].strip()
    body = text[end_idx + 3:].strip()
    fm = yaml.safe_load(fm_text) or {}

    tmpl = Template(
        name=fm.get("name", name),
        type=fm.get("type", "misc"),
        priority=fm.get("priority", "none"),
        labels=fm.get("labels") or [],
        body=body,
    )
    with YaitLock(root, "template create"):
        save_template(root, tmpl)
        click.echo(f"Saved template '{tmpl.name}'")
        _commit(ctx, root, f"yait: save template '{tmpl.name}'")


@template.command(name="list")
@click.pass_context
def template_list(ctx):
    """List available templates.

    \b
    Examples:
      yait template list
    """
    root = _resolve(ctx)
    _require_init(root)
    templates = list_templates(root)
    if not templates:
        click.echo("No templates found.")
        return
    header = f"{'NAME':<16}  {'TYPE':<12}  {'PRIORITY':<8}  LABELS"
    click.echo(click.style(header, bold=True))
    for t in templates:
        labels = ",".join(t.labels) if t.labels else "\u2014"
        click.echo(f"{t.name:<16}  {t.type:<12}  {t.priority:<8}  {labels}")


@template.command(name="delete")
@click.argument("name")
@click.pass_context
def template_delete(ctx, name):
    """Delete a template.

    \b
    Examples:
      yait template delete bug
    """
    root = _resolve(ctx)
    _require_init(root)
    with YaitLock(root, "template delete"):
        try:
            delete_template(root, name)
        except FileNotFoundError as e:
            raise click.ClickException(str(e))
        click.echo(f"Deleted template '{name}'")
        _commit(ctx, root, f"yait: delete template '{name}'")


# ── search ───────────────────────────────────────────────────

@main.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("query", required=False, default=None)
@click.option(
    "--status", default="open",
    type=click.Choice(["open", "closed", "all"]),
    help="Filter by status (default: open)",
)
@click.option("--type", default=None, type=click.Choice(ISSUE_TYPES), help="Filter by type")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.option("--label", default=None, help="Filter by label")
@click.option("--priority", default=None, type=click.Choice(PRIORITIES), help="Filter by priority")
@click.option("--assignee", default=None, help="Filter by assignee")
@click.option("--milestone", default=None, help="Filter by milestone")
@click.option("--regex", "use_regex", is_flag=True, default=False, help="Treat query as regex pattern")
@click.option("--title-only", is_flag=True, default=False, help="Search only in issue titles")
@click.option("--count", is_flag=True, default=False, help="Show match count only")
@click.option("--compact", is_flag=True, default=False, help="Compact output (ID + Status + Title)")
@click.option("--wide", is_flag=True, default=False, help="Wide output (all fields including dates)")
@click.pass_context
def search(ctx, query, status, type, as_json, label, priority, assignee, milestone,
           use_regex, title_only, count, compact, wide):
    """Full-text search across issue titles and bodies.

    \b
    Examples:
      yait search "login"
      yait search "crash" --status all
      yait search "api" --type bug --json
      yait search "login" --label auth --priority p0 --assignee alice
      yait search --regex "crash|oom|kill" --status all
      yait search "login" --title-only
      yait search "bug" --count
    """
    root = _resolve(ctx)
    _require_init(root)
    st = None if status == "all" else status
    issues = list_issues(root, status=st, type=type, label=label,
                         priority=priority, assignee=assignee, milestone=milestone)

    # Build doc title cache for search matching
    doc_titles = {}
    for d in list_docs(root):
        doc_titles[d.slug] = d.title.lower()

    def _matches_doc_titles(issue, q_lower):
        for doc_ref in getattr(issue, "docs", []):
            if "/" not in doc_ref and doc_ref in doc_titles and q_lower in doc_titles[doc_ref]:
                return True
        return False

    if query is None:
        matches = issues
    elif use_regex:
        try:
            pat = re.compile(query, re.IGNORECASE)
        except re.error as e:
            raise click.ClickException(f"Invalid regex: {e}")
        if title_only:
            matches = [i for i in issues if pat.search(i.title)]
        else:
            matches = [i for i in issues if pat.search(i.title) or pat.search(i.body)]
    else:
        q = query.lower()
        if title_only:
            matches = [i for i in issues if q in i.title.lower()]
        else:
            matches = [
                i for i in issues
                if q in i.title.lower() or q in i.body.lower() or _matches_doc_titles(i, q)
            ]

    if count:
        label_str = f' "{query}"' if query else ""
        click.echo(f"{len(matches)} issues match{label_str}")
        return
    if as_json:
        click.echo(json.dumps([i.to_dict() for i in matches], indent=2))
        return
    if not matches:
        click.echo("No matching issues.")
        return
    if compact and wide:
        raise click.ClickException("Cannot use both --compact and --wide.")
    display_mode = "compact" if compact else ("wide" if wide else None)
    _print_issue_table(matches, highlight=query, root=root, mode=display_mode)


# ── stats ───────────────────────────────────────────────────


def _group_by_field(issues, field: str) -> dict[str, list]:
    """Group issues by a field value. None values become '(none)'."""
    groups: dict[str, list] = {}
    for i in issues:
        val = getattr(i, field) or "(none)"
        groups.setdefault(val, []).append(i)
    return groups


def _open_closed(issues) -> tuple[int, int]:
    o = sum(1 for i in issues if i.status == "open")
    c = sum(1 for i in issues if i.status == "closed")
    return o, c


def _build_stats_data(all_issues) -> dict:
    """Build the full stats data structure."""
    total = len(all_issues)
    open_count = sum(1 for i in all_issues if i.status == "open")
    closed_count = total - open_count

    type_counts = Counter(i.type for i in all_issues)
    priority_counts = Counter(i.priority for i in all_issues)

    label_counts: Counter[str] = Counter()
    for i in all_issues:
        for lbl in i.labels:
            label_counts[lbl] += 1

    milestone_groups = _group_by_field(all_issues, "milestone")
    milestone_data = {}
    for name, issues in sorted(milestone_groups.items(), key=lambda x: (x[0] == "(none)", x[0])):
        o, c = _open_closed(issues)
        pct = round(c / (o + c) * 100) if (o + c) else 0
        milestone_data[name] = {"open": o, "closed": c, "percent": pct}

    assignee_groups = _group_by_field(all_issues, "assignee")
    assignee_data = {}
    for name, issues in sorted(assignee_groups.items(), key=lambda x: (x[0] == "(none)", x[0])):
        o, c = _open_closed(issues)
        assignee_data[name] = {"open": o, "closed": c}

    return {
        "total": total,
        "open": open_count,
        "closed": closed_count,
        "by_type": dict(type_counts.most_common()),
        "by_priority": dict(priority_counts.most_common()),
        "by_label": dict(label_counts.most_common()),
        "by_milestone": milestone_data,
        "by_assignee": assignee_data,
    }


def _print_dimension(title: str, data: dict, show_percent: bool = False):
    """Print a single dimension breakdown."""
    click.echo(f"By {title}:")
    for name, info in data.items():
        if isinstance(info, dict):
            line = f"  {name:<12}{info['open']} open / {info['closed']} closed"
            if show_percent:
                line += f"  ({info['percent']}%)"
            click.echo(line)


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--by", "dimension", type=click.Choice(["type", "priority", "label", "milestone", "assignee"]),
              help="Show breakdown for a single dimension")
@click.pass_context
def stats(ctx, as_json, dimension):
    """Show issue statistics."""
    root = _resolve(ctx)
    _require_init(root)
    all_issues = list_issues(root, status=None)
    total = len(all_issues)
    if total == 0:
        if as_json:
            click.echo(json.dumps({"total": 0, "open": 0, "closed": 0}))
        else:
            click.echo("No issues.")
        return

    data = _build_stats_data(all_issues)

    if as_json:
        if dimension:
            key = f"by_{dimension}"
            click.echo(json.dumps({key: data[key]}, indent=2))
        else:
            click.echo(json.dumps(data, indent=2))
        return

    if dimension:
        key = f"by_{dimension}"
        if dimension in ("type", "priority", "label"):
            vals = data[key]
            val_str = ", ".join(f"{k}={v}" for k, v in vals.items())
            click.echo(f"By {dimension}: {val_str}")
        elif dimension == "milestone":
            _print_dimension("milestone", data[key], show_percent=True)
        elif dimension == "assignee":
            _print_dimension("assignee", data[key])
        return

    # Full output
    click.echo(f"Issues: {data['total']} total ({data['open']} open, {data['closed']} closed)")
    click.echo()

    type_str = ", ".join(f"{k}={v}" for k, v in data["by_type"].items())
    click.echo(f"By type:     {type_str}")

    priority_str = ", ".join(f"{k}={v}" for k, v in data["by_priority"].items())
    click.echo(f"By priority: {priority_str}")

    if data["by_label"]:
        label_str = ", ".join(f"{k}={v}" for k, v in data["by_label"].items())
        click.echo(f"By label:    {label_str}")

    _print_dimension("milestone", data["by_milestone"], show_percent=True)
    _print_dimension("assignee", data["by_assignee"])


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


# ── log ─────────────────────────────────────────────────────

@main.command()
@click.argument("id", type=int, required=False, default=None)
@click.option("--limit", "-n", default=10, help="Max entries")
@click.pass_context
def log(ctx, id, limit):
    """Show issue change history from git log."""
    root = _resolve(ctx)
    _require_init(root)
    is_project = ctx.obj.get("is_project", False)
    if is_project:
        git_root = root
        if id is not None:
            sid = str(id)
            if not sid.isdigit():
                raise click.BadParameter(f"Invalid issue ID: {id!r}")
            path = f"issues/{sid}.md"
        else:
            path = "."
    else:
        git_root = root.parent
        if id is not None:
            sid = str(id)
            if not sid.isdigit():
                raise click.BadParameter(f"Invalid issue ID: {id!r}")
            path = f".yait/issues/{sid}.md"
        else:
            path = ".yait/"
    output = git_log(git_root, path, limit)
    if output:
        click.echo(output)
    else:
        click.echo("No history found.")


# ── export ──────────────────────────────────────────────────

@main.command(name="export")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "csv"]), help="Output format (default: json)")
@click.option("-o", "--output", "outfile", default=None, help="Output file path (default: stdout)")
@click.pass_context
def export_cmd(ctx, fmt, outfile):
    """Export all issues.

    \b
    Examples:
      yait export
      yait export --format csv
      yait export -o issues.json
      yait export --format csv -o issues.csv
    """
    root = _resolve(ctx)
    _require_init(root)
    issues = list_issues(root, status=None)
    issues.sort(key=lambda i: i.id)
    data = [i.to_dict() for i in issues]

    if fmt == "json":
        text = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        buf = io.StringIO()
        fieldnames = ["id", "title", "status", "type", "priority", "labels", "assignee", "milestone", "created_at", "updated_at", "body", "docs", "links"]
        writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in data:
            row = dict(row)
            row["labels"] = ",".join(row["labels"]) if row["labels"] else ""
            row["docs"] = ",".join(row["docs"]) if row["docs"] else ""
            row["links"] = json.dumps(row["links"]) if row["links"] else ""
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
@click.pass_context
def import_cmd(ctx, file):
    """Import issues from a JSON file.

    \b
    Examples:
      yait import issues.json
    """
    root = _resolve(ctx)
    _require_init(root)
    data = json.loads(Path(file).read_text())
    if not isinstance(data, list):
        raise click.ClickException("Expected a JSON array of issues.")

    with YaitLock(root, "import"):
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
            _commit(ctx, root, f"yait: import {imported} issues")

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
@click.pass_context
def doc_create(ctx, slug, title, body, body_file):
    """Create a managed document.

    \b
    Examples:
      yait doc create auth-prd --title "Auth PRD"
      yait doc create auth-prd --title "Auth PRD" -b "## Overview"
      yait doc create auth-prd --title "Auth PRD" --body-file draft.md
    """
    root = _resolve(ctx)
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
    with YaitLock(root, "doc create"):
        now = _now()
        d = Doc(slug=slug, title=title, created_at=now, updated_at=now, body=resolved_body)
        save_doc(root, d)
        click.echo(f"Created doc '{slug}': {title}")
        _commit(ctx, root, f"yait: create doc '{slug}'")


@doc.command(name="show")
@click.argument("slug")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
def doc_show(ctx, slug, as_json):
    """Show a managed document.

    \b
    Examples:
      yait doc show auth-prd
      yait doc show auth-prd --json
    """
    root = _resolve(ctx)
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
@click.pass_context
def doc_list(ctx, as_json):
    """List all managed documents.

    \b
    Examples:
      yait doc list
      yait doc list --json
    """
    root = _resolve(ctx)
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
@click.pass_context
def doc_edit(ctx, slug, new_title, new_body):
    """Edit a managed document.

    \b
    Examples:
      yait doc edit auth-prd
      yait doc edit auth-prd --title "New Title"
      yait doc edit auth-prd -b "New content"
    """
    root = _resolve(ctx)
    _require_init(root)
    try:
        d = load_doc(root, slug)
    except FileNotFoundError:
        raise click.ClickException(f"Doc '{slug}' not found.")
    if new_title is not None or new_body is not None:
        with YaitLock(root, "doc edit"):
            if new_title is not None:
                d.title = new_title
            if new_body is not None:
                d.body = new_body
            d.updated_at = _now()
            save_doc(root, d)
            click.echo(f"Updated doc '{slug}'")
            _commit(ctx, root, f"yait: edit doc '{slug}'")
    else:
        result = click.edit(d.body)
        if result is None:
            click.echo("Edit cancelled.")
            return
        d.body = result.strip()
        with YaitLock(root, "doc edit"):
            d.updated_at = _now()
            save_doc(root, d)
            click.echo(f"Updated doc '{slug}'")
            _commit(ctx, root, f"yait: edit doc '{slug}'")


@doc.command(name="delete")
@click.argument("slug")
@click.option("--force", "-f", is_flag=True, default=False, help="Skip confirmation")
@click.pass_context
def doc_delete(ctx, slug, force):
    """Delete a managed document.

    \b
    Examples:
      yait doc delete auth-prd
      yait doc delete auth-prd -f
    """
    root = _resolve(ctx)
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
    with YaitLock(root, "doc delete"):
        delete_doc(root, slug)
        click.echo(f"Deleted doc '{slug}'")
        _commit(ctx, root, f"yait: delete doc '{slug}'")


@doc.command(name="link")
@click.argument("args", nargs=-1, required=True)
@click.pass_context
def doc_link(ctx, args):
    """Link a document to one or more issues.

    \b
    Last argument is the doc slug/path, preceding arguments are issue IDs.

    \b
    Examples:
      yait doc link 1 auth-prd
      yait doc link 1 docs/arch.md
      yait doc link 1 2 3 auth-prd
    """
    root = _resolve(ctx)
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
    with YaitLock(root, "doc link"):
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
            _commit(ctx, root, f"yait: link doc '{doc_ref}' to #{', #'.join(str(i) for i in linked_ids)}")


@doc.command(name="unlink")
@click.argument("id", type=int)
@click.argument("doc_ref")
@click.pass_context
def doc_unlink(ctx, id, doc_ref):
    """Unlink a document from an issue.

    \b
    Examples:
      yait doc unlink 1 auth-prd
    """
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)
    if doc_ref not in issue.docs:
        click.echo(f"Issue #{id} is not linked to '{doc_ref}'.")
        return
    with YaitLock(root, "doc unlink"):
        issue.docs.remove(doc_ref)
        issue.updated_at = _now()
        save_issue(root, issue)
        click.echo(f"Unlinked doc '{doc_ref}' from issue #{id}")
        _commit(ctx, root, f"yait: unlink doc '{doc_ref}' from #{id}")


# ── link / unlink ──────────────────────────────────────────

# Valid user-facing link types (excludes reverse-only types)
_USER_LINK_TYPES = ("blocks", "depends-on", "relates-to")


@main.command(name="link")
@click.argument("source_id", type=int)
@click.argument("link_type", type=click.Choice(_USER_LINK_TYPES))
@click.argument("target_id", type=int)
@click.pass_context
def link_cmd(ctx, source_id, link_type, target_id):
    """Add a link between two issues.

    \b
    Examples:
      yait link 3 blocks 5          # issue #3 blocks issue #5
      yait link 3 relates-to 7      # issue #3 relates to #7
      yait link 3 depends-on 1      # issue #3 depends on #1
    """
    root = _resolve(ctx)
    _require_init(root)
    with YaitLock(root, "link"):
        try:
            add_link(root, source_id, link_type, target_id)
        except FileNotFoundError as e:
            raise click.ClickException(str(e))
        except ValueError as e:
            raise click.ClickException(str(e))
        click.echo(f"Linked #{source_id} {link_type} #{target_id}")
        _commit(ctx, root, f"yait: link #{source_id} {link_type} #{target_id}")


@main.command(name="unlink")
@click.argument("source_id", type=int)
@click.argument("target_id", type=int)
@click.pass_context
def unlink_cmd(ctx, source_id, target_id):
    """Remove all links between two issues.

    \b
    Examples:
      yait unlink 3 5
    """
    root = _resolve(ctx)
    _require_init(root)
    # Check both issues exist
    source = _load_or_exit(root, source_id)
    target = _load_or_exit(root, target_id)
    had_link = any(l.get("target") == target_id for l in source.links)
    if not had_link:
        click.echo(f"No link between #{source_id} and #{target_id}.")
        return
    with YaitLock(root, "unlink"):
        remove_link(root, source_id, target_id)
        click.echo(f"Unlinked #{source_id} and #{target_id}")
        _commit(ctx, root, f"yait: unlink #{source_id} and #{target_id}")


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
@click.pass_context
def bulk_label_add(ctx, name, ids, filter_status, filter_type, filter_priority,
                   filter_label, filter_assignee, filter_milestone):
    """Add a label to multiple issues.

    \b
    Examples:
      yait bulk label add urgent 1 2 3 4 5
      yait bulk label add release-blocker --filter-priority p0 --filter-status open
    """
    root = _resolve(ctx)
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
    with YaitLock(root, "bulk label add"):
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
            _commit(ctx, root, f"yait: bulk label #{issue_id} +{name}")
            updated += 1
    _bulk_summary(updated, failed, skipped)


@bulk_label.command(name="remove")
@click.argument("name")
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
@click.pass_context
def bulk_label_remove(ctx, name, ids, filter_status, filter_type, filter_priority,
                      filter_label, filter_assignee, filter_milestone):
    """Remove a label from multiple issues.

    \b
    Examples:
      yait bulk label remove urgent 1 2 3
      yait bulk label remove urgent --filter-status open
    """
    root = _resolve(ctx)
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
    with YaitLock(root, "bulk label remove"):
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
            _commit(ctx, root, f"yait: bulk label #{issue_id} -{name}")
            updated += 1
    _bulk_summary(updated, failed, skipped)


# ── bulk assign / unassign ──────────────────────────────────

@bulk.command(name="assign")
@click.argument("name")
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
@click.pass_context
def bulk_assign(ctx, name, ids, filter_status, filter_type, filter_priority,
                filter_label, filter_assignee, filter_milestone):
    """Assign multiple issues to someone.

    \b
    Examples:
      yait bulk assign alice 1 2 3
      yait bulk assign alice --filter-milestone v1.0 --filter-status open
    """
    root = _resolve(ctx)
    _require_init(root)
    pairs = _resolve_bulk_issues(root, ids,
        filter_status=filter_status, filter_type=filter_type,
        filter_priority=filter_priority, filter_label=filter_label,
        filter_assignee=filter_assignee, filter_milestone=filter_milestone)
    if pairs is None:
        return
    updated = 0
    failed = 0
    with YaitLock(root, "bulk assign"):
        for issue_id, issue in pairs:
            if issue is None:
                failed += 1
                continue
            issue.assignee = name
            issue.updated_at = _now()
            save_issue(root, issue)
            _commit(ctx, root, f"yait: bulk assign #{issue_id} to {name}")
            updated += 1
    _bulk_summary(updated, failed)


@bulk.command(name="unassign")
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
@click.pass_context
def bulk_unassign(ctx, ids, filter_status, filter_type, filter_priority,
                  filter_label, filter_assignee, filter_milestone):
    """Remove assignee from multiple issues.

    \b
    Examples:
      yait bulk unassign 1 2 3
      yait bulk unassign --filter-status open --filter-assignee alice
    """
    root = _resolve(ctx)
    _require_init(root)
    pairs = _resolve_bulk_issues(root, ids,
        filter_status=filter_status, filter_type=filter_type,
        filter_priority=filter_priority, filter_label=filter_label,
        filter_assignee=filter_assignee, filter_milestone=filter_milestone)
    if pairs is None:
        return
    updated = 0
    failed = 0
    with YaitLock(root, "bulk unassign"):
        for issue_id, issue in pairs:
            if issue is None:
                failed += 1
                continue
            issue.assignee = None
            issue.updated_at = _now()
            save_issue(root, issue)
            _commit(ctx, root, f"yait: bulk unassign #{issue_id}")
            updated += 1
    _bulk_summary(updated, failed)


# ── bulk priority ───────────────────────────────────────────

@bulk.command(name="priority")
@click.argument("value", type=click.Choice(PRIORITIES))
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
@click.pass_context
def bulk_priority(ctx, value, ids, filter_status, filter_type, filter_priority,
                  filter_label, filter_assignee, filter_milestone):
    """Set priority on multiple issues.

    \b
    Examples:
      yait bulk priority p0 1 2 3
      yait bulk priority p1 --filter-type bug --filter-status open
    """
    root = _resolve(ctx)
    _require_init(root)
    pairs = _resolve_bulk_issues(root, ids,
        filter_status=filter_status, filter_type=filter_type,
        filter_priority=filter_priority, filter_label=filter_label,
        filter_assignee=filter_assignee, filter_milestone=filter_milestone)
    if pairs is None:
        return
    updated = 0
    failed = 0
    with YaitLock(root, "bulk priority"):
        for issue_id, issue in pairs:
            if issue is None:
                failed += 1
                continue
            issue.priority = value
            issue.updated_at = _now()
            save_issue(root, issue)
            _commit(ctx, root, f"yait: bulk priority #{issue_id} -> {value}")
            updated += 1
    _bulk_summary(updated, failed)


# ── bulk milestone ──────────────────────────────────────────

@bulk.command(name="milestone")
@click.argument("value")
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
@click.pass_context
def bulk_milestone(ctx, value, ids, filter_status, filter_type, filter_priority,
                   filter_label, filter_assignee, filter_milestone):
    """Set milestone on multiple issues.

    \b
    Examples:
      yait bulk milestone v1.0 1 2 3
      yait bulk milestone v2.0 --filter-label deferred
    """
    root = _resolve(ctx)
    _require_init(root)
    pairs = _resolve_bulk_issues(root, ids,
        filter_status=filter_status, filter_type=filter_type,
        filter_priority=filter_priority, filter_label=filter_label,
        filter_assignee=filter_assignee, filter_milestone=filter_milestone)
    if pairs is None:
        return
    updated = 0
    failed = 0
    with YaitLock(root, "bulk milestone"):
        for issue_id, issue in pairs:
            if issue is None:
                failed += 1
                continue
            issue.milestone = value
            issue.updated_at = _now()
            save_issue(root, issue)
            _commit(ctx, root, f"yait: bulk milestone #{issue_id} -> {value}")
            updated += 1
    _bulk_summary(updated, failed)


# ── bulk type ───────────────────────────────────────────────

@bulk.command(name="type")
@click.argument("value", type=click.Choice(ISSUE_TYPES))
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
@click.pass_context
def bulk_type(ctx, value, ids, filter_status, filter_type, filter_priority,
              filter_label, filter_assignee, filter_milestone):
    """Set type on multiple issues.

    \b
    Examples:
      yait bulk type bug 1 2 3
      yait bulk type enhancement --filter-label improvement
    """
    root = _resolve(ctx)
    _require_init(root)
    pairs = _resolve_bulk_issues(root, ids,
        filter_status=filter_status, filter_type=filter_type,
        filter_priority=filter_priority, filter_label=filter_label,
        filter_assignee=filter_assignee, filter_milestone=filter_milestone)
    if pairs is None:
        return
    updated = 0
    failed = 0
    with YaitLock(root, "bulk type"):
        for issue_id, issue in pairs:
            if issue is None:
                failed += 1
                continue
            issue.type = value
            issue.updated_at = _now()
            save_issue(root, issue)
            _commit(ctx, root, f"yait: bulk type #{issue_id} -> {value}")
            updated += 1
    _bulk_summary(updated, failed)


# ── project ──────────────────────────────────────────────────

@main.group()
def project():
    """Manage named projects."""


@project.command(name="create")
@click.argument("name")
def project_create(name):
    """Create a new named project.

    \b
    Examples:
      yait project create myapp
    """
    project_dir = _project_create(name)
    click.echo(f"Created project '{name}' at {project_dir}/")


@project.command(name="list")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def project_list(as_json):
    """List all named projects.

    \b
    Examples:
      yait project list
      yait project list --json
    """
    home = _yait_home()
    projects_dir = home / "projects"
    if not projects_dir.exists():
        if as_json:
            click.echo("[]")
        else:
            click.echo("No projects found. Create one with: yait project create <name>")
        return

    entries = []
    for p in sorted(projects_dir.iterdir()):
        if not p.is_dir() or not is_initialized(p):
            continue
        all_issues = list_issues(p, status=None)
        open_c = sum(1 for i in all_issues if i.status == "open")
        closed_c = sum(1 for i in all_issues if i.status == "closed")
        # Get last updated time from most recent issue
        updated = ""
        if all_issues:
            updated = max(i.updated_at for i in all_issues)[:10]
        entries.append({
            "name": p.name,
            "open": open_c,
            "closed": closed_c,
            "updated": updated,
        })

    if as_json:
        click.echo(json.dumps(entries, indent=2))
        return

    if not entries:
        click.echo("No projects found. Create one with: yait project create <name>")
        return

    header = f"{'NAME':<20}  {'OPEN':>4}  {'CLOSED':>6}  UPDATED"
    click.echo(click.style(header, bold=True))
    for e in entries:
        click.echo(f"{e['name']:<20}  {e['open']:>4}  {e['closed']:>6}  {e['updated'] or '—'}")


@project.command(name="delete")
@click.argument("name")
@click.option("--force", "-f", is_flag=True, default=False, help="Skip confirmation")
def project_delete(name, force):
    """Delete a named project.

    \b
    Examples:
      yait project delete myapp
      yait project delete myapp -f
    """
    home = _yait_home()
    project_dir = home / "projects" / name
    if not project_dir.exists():
        raise click.ClickException(f"Project '{name}' not found.")
    if not force:
        click.confirm(f"Delete project '{name}' and all its data?", abort=True)
    shutil.rmtree(project_dir)
    click.echo(f"Deleted project '{name}'")


@project.command(name="rename")
@click.argument("old")
@click.argument("new")
def project_rename(old, new):
    """Rename a project.

    \b
    Examples:
      yait project rename old-name new-name
    """
    _validate_project_name(new)
    home = _yait_home()
    old_dir = home / "projects" / old
    new_dir = home / "projects" / new
    if not old_dir.exists():
        raise click.ClickException(f"Project '{old}' not found.")
    if new_dir.exists():
        raise click.ClickException(f"Project '{new}' already exists.")
    old_dir.rename(new_dir)
    click.echo(f"Renamed project '{old}' -> '{new}'.")
    click.echo(f"Note: Update any scripts or YAIT_PROJECT env vars that reference '{old}'.")


@project.command(name="import")
@click.argument("name")
@click.option("--path", "src_path", default=None,
              help="Path to directory containing .yait/ (default: cwd)")
@click.option("--move", is_flag=True, default=False,
              help="Remove local .yait/ after import")
def project_import(name, src_path, move):
    """Import a local .yait/ directory as a named project.

    \b
    Examples:
      yait project import myapp
      yait project import myapp --path /other/repo
      yait project import myapp --move
    """
    _validate_project_name(name)
    home = _yait_home()
    project_dir = home / "projects" / name
    if project_dir.exists():
        raise click.ClickException(f"Project '{name}' already exists.")

    src = Path(src_path) if src_path else Path.cwd()
    local_yait = src / ".yait"
    if not local_yait.is_dir():
        raise click.ClickException(
            f"No .yait/ directory found in {src}. Nothing to import."
        )

    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    (home / "projects").mkdir(mode=0o700, exist_ok=True)

    # Copy contents of .yait/ into project dir (flat layout)
    shutil.copytree(local_yait, project_dir)

    # Remove lock file if copied
    lock_file = project_dir / "yait.lock"
    if lock_file.exists():
        lock_file.unlink()

    # Write .gitignore
    (project_dir / ".gitignore").write_text("yait.lock\n")

    # Initialize git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "yait@local"], cwd=project_dir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "yait"], cwd=project_dir, capture_output=True)
    git_commit(project_dir, "yait: import project", ".")

    if move:
        shutil.rmtree(local_yait)
        click.echo(f"Moved .yait/ -> {project_dir}/")
    else:
        click.echo(f"Copied .yait/ -> {project_dir}/")

    click.echo(
        "Note: git history for issues is not migrated. "
        "History remains in the original repo's git log."
    )


@project.command(name="path")
@click.argument("name")
@click.option("--check", is_flag=True, default=False,
              help="Exit non-zero if project doesn't exist")
def project_path(name, check):
    """Print the data directory path for a project.

    \b
    Examples:
      yait project path myapp
      yait project path myapp --check
    """
    home = _yait_home()
    project_dir = home / "projects" / name
    if check and not project_dir.exists():
        raise SystemExit(1)
    click.echo(str(project_dir))
