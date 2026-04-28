from __future__ import annotations

import json

import click

from ..lock import YaitLock
from ..models import MILESTONE_STATUSES, Milestone
from ..store import (
    list_issues, save_milestone, load_milestone, list_milestones,
    update_milestone, delete_milestone,
)
from . import main, _resolve, _require_init, _commit, _now
from ._helpers import _status_color, _type_color


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
