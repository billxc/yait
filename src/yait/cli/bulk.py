from __future__ import annotations

import click

from ..lock import YaitLock
from ..models import ISSUE_TYPES, PRIORITIES
from ..store import list_issues, load_issue, save_issue, resolve_status_filter, validate_status
from . import main, _resolve, _require_init, _commit, _now


def _try_load(root, issue_id: int):
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
    return any(v is not None for v in kwargs.values())


def _resolve_bulk_issues(root, ids, **filters):
    has_ids = len(ids) > 0
    has_filter = _has_filters(**filters)

    if has_ids and has_filter:
        click.echo("Error: Cannot use both issue IDs and --filter options.")
        return None
    if not has_ids and not has_filter:
        click.echo("Error: Provide issue IDs or --filter options.")
        return None

    if has_ids:
        result = []
        for issue_id in ids:
            issue = _try_load(root, issue_id)
            result.append((issue_id, issue))
        return result

    filter_status = filters.get("filter_status")
    status_list = None
    if filter_status:
        try:
            status_list = resolve_status_filter(root, filter_status)
        except ValueError as e:
            click.echo(f"Error: {e}")
            return None
    issues = list_issues(
        root,
        status_list=status_list,
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


@bulk.command(name="status")
@click.argument("new_status")
@click.argument("ids", nargs=-1, type=int)
@bulk_filter_options
@click.pass_context
def bulk_status(ctx, new_status, ids, filter_status, filter_type, filter_priority,
                filter_label, filter_assignee, filter_milestone):
    """Set status on multiple issues.

    \b
    Examples:
      yait bulk status done 1 2 3
      yait bulk status in-progress --filter-type bug --filter-status open
    """
    root = _resolve(ctx)
    _require_init(root)
    try:
        validate_status(root, new_status)
    except ValueError as e:
        raise click.ClickException(str(e))
    pairs = _resolve_bulk_issues(root, ids,
        filter_status=filter_status, filter_type=filter_type,
        filter_priority=filter_priority, filter_label=filter_label,
        filter_assignee=filter_assignee, filter_milestone=filter_milestone)
    if pairs is None:
        return
    updated = 0
    failed = 0
    with YaitLock(root, "bulk status"):
        for issue_id, issue in pairs:
            if issue is None:
                failed += 1
                continue
            issue.status = new_status
            issue.updated_at = _now()
            save_issue(root, issue)
            _commit(ctx, root, f"yait: bulk status #{issue_id} -> {new_status}")
            updated += 1
    _bulk_summary(updated, failed)
