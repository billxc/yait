"""Generate an HTML dashboard for a yait project."""

from __future__ import annotations

import html
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .store import list_issues, list_milestones


def generate_dashboard(root: Path, project_name: str = "") -> str:
    """
    Collect project data and generate a complete HTML dashboard string.

    Args:
        root: yait data directory path (.yait/ or project directory).
        project_name: Project name shown in the title. Empty string means local project.

    Returns:
        Complete HTML string that can be written directly to a file.
    """
    all_issues = list_issues(root)
    milestones = list_milestones(root)

    total = len(all_issues)
    open_issues = [i for i in all_issues if i.status == "open"]
    closed_issues = [i for i in all_issues if i.status == "closed"]
    open_count = len(open_issues)
    closed_count = len(closed_issues)
    close_rate = round(closed_count / total * 100) if total else 0

    # Breakdowns
    type_counts = Counter(i.type for i in all_issues)
    priority_counts = Counter(i.priority for i in all_issues)

    # Milestone progress
    open_milestones = [m for m in milestones if m.status == "open"]
    milestone_progress = []
    for m in open_milestones:
        ms_issues = [i for i in all_issues if i.milestone == m.name]
        ms_total = len(ms_issues)
        ms_closed = sum(1 for i in ms_issues if i.status == "closed")
        pct = round(ms_closed / ms_total * 100) if ms_total else 0
        milestone_progress.append({
            "name": m.name,
            "total": ms_total,
            "closed": ms_closed,
            "percent": pct,
            "due_date": m.due_date or "",
        })

    # Recently closed (last 10, sorted by updated_at desc)
    recently_closed = sorted(
        closed_issues,
        key=lambda i: i.updated_at or i.created_at or "",
        reverse=True,
    )[:10]

    # Sort open issues by id
    open_issues_sorted = sorted(open_issues, key=lambda i: i.id)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title = f"YAIT Dashboard — {_esc(project_name)}" if project_name else "YAIT Dashboard"

    return _render_html(
        title=title,
        now_str=now_str,
        total=total,
        open_count=open_count,
        closed_count=closed_count,
        close_rate=close_rate,
        type_counts=type_counts,
        priority_counts=priority_counts,
        milestone_progress=milestone_progress,
        open_issues=open_issues_sorted,
        recently_closed=recently_closed,
    )


def _esc(text: str) -> str:
    """Escape HTML entities."""
    return html.escape(str(text), quote=True)


def _bar_section(label: str, counts: dict[str, int], color_map: dict[str, str]) -> str:
    """Render a breakdown section with CSS bar chart."""
    if not counts:
        return f'<h3>{_esc(label)}</h3><p class="muted">No data</p>'
    max_val = max(counts.values()) if counts else 1
    rows = []
    for name, count in sorted(counts.items(), key=lambda x: -x[1]):
        pct = round(count / max_val * 100) if max_val else 0
        color = color_map.get(name, "#6b7280")
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{_esc(name)}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-fill" style="width:{pct}%;background:{color}"></div>'
            f'</div>'
            f'<span class="bar-value">{count}</span>'
            f'</div>'
        )
    return f'<h3>{_esc(label)}</h3>' + "\n".join(rows)


def _render_html(
    *,
    title: str,
    now_str: str,
    total: int,
    open_count: int,
    closed_count: int,
    close_rate: int,
    type_counts: Counter,
    priority_counts: Counter,
    milestone_progress: list[dict],
    open_issues: list,
    recently_closed: list,
) -> str:
    type_colors = {
        "bug": "#ef4444",
        "feature": "#3b82f6",
        "enhancement": "#8b5cf6",
        "misc": "#6b7280",
    }
    priority_colors = {
        "p0": "#ef4444",
        "p1": "#f59e0b",
        "p2": "#3b82f6",
        "p3": "#6b7280",
        "none": "#9ca3af",
    }

    type_section = _bar_section("By Type", dict(type_counts), type_colors)
    priority_section = _bar_section("By Priority", dict(priority_counts), priority_colors)

    # Milestone progress bars
    if milestone_progress:
        ms_rows = []
        for m in milestone_progress:
            due = f' &middot; Due: {_esc(m["due_date"])}' if m["due_date"] else ""
            ms_rows.append(
                f'<div class="ms-item">'
                f'<div class="ms-header">'
                f'<span class="ms-name">{_esc(m["name"])}</span>'
                f'<span class="ms-stats">{m["closed"]}/{m["total"]} closed ({m["percent"]}%){due}</span>'
                f'</div>'
                f'<div class="bar-track">'
                f'<div class="bar-fill bar-fill-ms" style="width:{m["percent"]}%"></div>'
                f'</div>'
                f'</div>'
            )
        ms_html = "\n".join(ms_rows)
    else:
        ms_html = '<p class="muted">No open milestones</p>'

    # Open issues table
    if open_issues:
        issue_rows = []
        for i in open_issues:
            issue_rows.append(
                f"<tr>"
                f"<td>#{i.id}</td>"
                f"<td>{_esc(i.title)}</td>"
                f"<td>{_esc(i.type)}</td>"
                f"<td>{_esc(i.priority)}</td>"
                f"<td>{_esc(i.assignee or '-')}</td>"
                f"<td>{_esc(i.created_at)}</td>"
                f"</tr>"
            )
        open_table = (
            '<table><thead><tr>'
            '<th>ID</th><th>Title</th><th>Type</th><th>Priority</th><th>Assignee</th><th>Created</th>'
            '</tr></thead><tbody>'
            + "\n".join(issue_rows)
            + '</tbody></table>'
        )
    else:
        open_table = '<p class="muted">No open issues</p>'

    # Recently closed table
    if recently_closed:
        closed_rows = []
        for i in recently_closed:
            closed_rows.append(
                f"<tr>"
                f"<td>#{i.id}</td>"
                f"<td>{_esc(i.title)}</td>"
                f"<td>{_esc(i.type)}</td>"
                f"<td>{_esc(i.updated_at or i.created_at)}</td>"
                f"</tr>"
            )
        closed_table = (
            '<table><thead><tr>'
            '<th>ID</th><th>Title</th><th>Type</th><th>Closed</th>'
            '</tr></thead><tbody>'
            + "\n".join(closed_rows)
            + '</tbody></table>'
        )
    else:
        closed_table = '<p class="muted">No closed issues</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0f172a;color:#e2e8f0;padding:2rem;line-height:1.6}}
.container{{max-width:960px;margin:0 auto}}
header{{margin-bottom:2rem}}
header h1{{font-size:1.5rem;font-weight:600;color:#f8fafc}}
header .timestamp{{font-size:.85rem;color:#94a3b8;margin-top:.25rem}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:2rem}}
.card{{background:#1e293b;border-radius:.5rem;padding:1.25rem;text-align:center}}
.card .value{{font-size:2rem;font-weight:700;color:#f8fafc}}
.card .label{{font-size:.8rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-top:.25rem}}
section{{background:#1e293b;border-radius:.5rem;padding:1.5rem;margin-bottom:1.5rem}}
h2{{font-size:1.15rem;font-weight:600;color:#f8fafc;margin-bottom:1rem}}
h3{{font-size:.95rem;font-weight:500;color:#cbd5e1;margin:1rem 0 .5rem}}
.bar-row{{display:flex;align-items:center;gap:.75rem;margin-bottom:.4rem}}
.bar-label{{width:90px;font-size:.85rem;color:#94a3b8;text-align:right}}
.bar-track{{flex:1;height:20px;background:#334155;border-radius:4px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:4px;transition:width .3s}}
.bar-fill-ms{{background:#22c55e}}
.bar-value{{width:36px;font-size:.85rem;color:#cbd5e1}}
.ms-item{{margin-bottom:1rem}}
.ms-header{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:.25rem}}
.ms-name{{font-weight:500;color:#f8fafc}}
.ms-stats{{font-size:.8rem;color:#94a3b8}}
table{{width:100%;border-collapse:collapse;font-size:.85rem}}
th{{text-align:left;padding:.5rem .75rem;border-bottom:1px solid #334155;color:#94a3b8;font-weight:500;text-transform:uppercase;font-size:.75rem;letter-spacing:.05em}}
td{{padding:.5rem .75rem;border-bottom:1px solid #1e293b}}
tr:hover td{{background:#1e293b}}
.muted{{color:#64748b;font-size:.85rem}}
</style>
</head>
<body>
<div class="container">
<header>
<h1>{title}</h1>
<div class="timestamp">Generated: {_esc(now_str)}</div>
</header>

<div class="cards">
<div class="card"><div class="value">{total}</div><div class="label">Total</div></div>
<div class="card"><div class="value">{open_count}</div><div class="label">Open</div></div>
<div class="card"><div class="value">{closed_count}</div><div class="label">Closed</div></div>
<div class="card"><div class="value">{close_rate}%</div><div class="label">Close Rate</div></div>
</div>

<section>
<h2>Breakdown</h2>
{type_section}
{priority_section}
</section>

<section>
<h2>Milestone Progress</h2>
{ms_html}
</section>

<section>
<h2>Open Issues</h2>
{open_table}
</section>

<section>
<h2>Recently Closed</h2>
{closed_table}
</section>

</div>
</body>
</html>"""
