from __future__ import annotations

import os
import re
from pathlib import Path

import click

from ..models import Issue
from ..store import get_display, get_workflow


def _status_color(status: str, root=None) -> str:
    if root:
        wf = get_workflow(root)
        return "red" if status in set(wf["closed_statuses"]) else "green"
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
    """Auto-detect display mode based on terminal width."""
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


def _format_labels(labels: list[str]) -> str:
    return ",".join(labels) if labels else "\u2014"


def _print_issue_table(
    issues: list[Issue],
    highlight: str | None = None,
    root: Path | None = None,
    mode: str | None = None,
) -> None:
    if not issues:
        click.echo('No issues found. Create one with: yait new "..."')
        return
    max_title_w = 50
    date_fmt = "short"
    if root is not None:
        try:
            display = get_display(root)
            max_title_w = display.get("max_title_width", 50)
            date_fmt = display.get("date_format", "short")
        except Exception:
            pass

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
