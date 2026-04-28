from __future__ import annotations

import json
import re
from collections import Counter

import click

from ..models import ISSUE_TYPES, PRIORITIES
from ..store import list_issues, list_docs, get_workflow, resolve_status_filter
from . import main, _resolve, _require_init
from ._helpers import _print_issue_table, _status_color


# ── search ───────────────────────────────────────────────────

@main.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("query", required=False, default=None)
@click.option(
    "--status", default="open",
    help="Filter by status (open, closed, all, or specific status)",
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
    try:
        status_filter = resolve_status_filter(root, status)
    except ValueError as e:
        raise click.ClickException(str(e))
    issues = list_issues(root, status_list=status_filter, type=type, label=label,
                         priority=priority, assignee=assignee, milestone=milestone)

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


def _open_closed(issues, closed_set=None) -> tuple[int, int]:
    if closed_set is None:
        closed_set = {"closed"}
    c = sum(1 for i in issues if i.status in closed_set)
    o = len(issues) - c
    return o, c


def _build_stats_data(all_issues, root=None) -> dict:
    """Build the full stats data structure."""
    total = len(all_issues)
    if root:
        wf = get_workflow(root)
        closed_set = set(wf["closed_statuses"])
    else:
        closed_set = {"closed"}
    closed_count = sum(1 for i in all_issues if i.status in closed_set)
    open_count = total - closed_count

    type_counts = Counter(i.type for i in all_issues)
    priority_counts = Counter(i.priority for i in all_issues)
    status_counts = Counter(i.status for i in all_issues)

    label_counts: Counter[str] = Counter()
    for i in all_issues:
        for lbl in i.labels:
            label_counts[lbl] += 1

    milestone_groups = _group_by_field(all_issues, "milestone")
    milestone_data = {}
    for name, issues in sorted(milestone_groups.items(), key=lambda x: (x[0] == "(none)", x[0])):
        o, c = _open_closed(issues, closed_set)
        pct = round(c / (o + c) * 100) if (o + c) else 0
        milestone_data[name] = {"open": o, "closed": c, "percent": pct}

    assignee_groups = _group_by_field(all_issues, "assignee")
    assignee_data = {}
    for name, issues in sorted(assignee_groups.items(), key=lambda x: (x[0] == "(none)", x[0])):
        o, c = _open_closed(issues, closed_set)
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
        "by_status": dict(status_counts.most_common()),
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
@click.option("--by", "dimension", type=click.Choice(["type", "priority", "label", "milestone", "assignee", "status"]),
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

    data = _build_stats_data(all_issues, root=root)

    if as_json:
        if dimension:
            key = f"by_{dimension}"
            click.echo(json.dumps({key: data[key]}, indent=2))
        else:
            click.echo(json.dumps(data, indent=2))
        return

    if dimension:
        key = f"by_{dimension}"
        if dimension in ("type", "priority", "label", "status"):
            vals = data[key]
            val_str = ", ".join(f"{k}={v}" for k, v in vals.items())
            click.echo(f"By {dimension}: {val_str}")
        elif dimension == "milestone":
            _print_dimension("milestone", data[key], show_percent=True)
        elif dimension == "assignee":
            _print_dimension("assignee", data[key])
        return

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
