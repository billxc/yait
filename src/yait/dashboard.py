"""Generate an interactive HTML dashboard for a yait project."""

from __future__ import annotations

import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .store import list_issues, list_milestones, get_workflow


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
    workflow = get_workflow(root)

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
            "issues": [{"id": i.id, "title": i.title, "status": i.status} for i in ms_issues],
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

    # Serialize all issues to JSON for client-side modal
    issues_json = _safe_json([_issue_to_dict(i) for i in all_issues])
    project_json = _safe_json(project_name)
    workflow_json = _safe_json(workflow)

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
        issues_json=issues_json,
        project_json=project_json,
        workflow_json=workflow_json,
    )


def _esc(text: str) -> str:
    """Escape HTML entities."""
    return html.escape(str(text), quote=True)


def _safe_json(obj) -> str:
    """Serialize to JSON, escaping </script> for safe embedding in HTML."""
    return json.dumps(obj, ensure_ascii=False).replace("</", r"<\/")


def _issue_to_dict(issue) -> dict:
    return {
        "id": issue.id,
        "title": issue.title,
        "status": issue.status,
        "type": issue.type,
        "priority": issue.priority,
        "labels": issue.labels,
        "assignee": issue.assignee,
        "milestone": issue.milestone,
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
        "body": issue.body,
        "docs": issue.docs,
        "links": issue.links,
    }


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
    issues_json: str,
    project_json: str,
    workflow_json: str,
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

    # Milestone progress bars with accordion
    if milestone_progress:
        ms_rows = []
        for m in milestone_progress:
            due = f' &middot; Due: {_esc(m["due_date"])}' if m["due_date"] else ""
            issue_list_items = ""
            for mi in m["issues"]:
                status_cls = "ms-issue-closed" if mi["status"] == "closed" else ""
                issue_list_items += (
                    f'<li class="{status_cls}">'
                    f'<a href="#" onclick="showIssue({mi["id"]});return false">#{mi["id"]} {_esc(mi["title"])}</a>'
                    f'</li>'
                )
            issue_list = f'<ul class="ms-issue-list" style="display:none">{issue_list_items}</ul>' if issue_list_items else ""
            toggle = ' onclick="toggleAccordion(this)"' if issue_list_items else ""
            toggle_cls = " accordion-toggle" if issue_list_items else ""
            ms_rows.append(
                f'<div class="ms-item">'
                f'<div class="ms-header{toggle_cls}"{toggle}>'
                f'<span class="ms-name">{_esc(m["name"])}</span>'
                f'<span class="ms-stats">{m["closed"]}/{m["total"]} closed ({m["percent"]}%){due}</span>'
                f'</div>'
                f'<div class="bar-track">'
                f'<div class="bar-fill bar-fill-ms" style="width:{m["percent"]}%"></div>'
                f'</div>'
                f'{issue_list}'
                f'</div>'
            )
        ms_html = "\n".join(ms_rows)
    else:
        ms_html = '<p class="muted">No open milestones</p>'

    # Collect unique values for filter dropdowns
    types_set = sorted(set(i.type for i in open_issues))
    priorities_set = sorted(set(i.priority for i in open_issues))
    assignees_set = sorted(set(i.assignee for i in open_issues if i.assignee))

    def _options(values):
        return "".join(f'<option value="{_esc(v)}">{_esc(v)}</option>' for v in values)

    filter_bar = (
        '<div class="filter-bar">'
        '<input type="text" id="filter-search" placeholder="Search issues..." oninput="applyFilters()">'
        '<select id="filter-type" onchange="applyFilters()"><option value="">All Types</option>'
        + _options(types_set) +
        '</select>'
        '<select id="filter-priority" onchange="applyFilters()"><option value="">All Priorities</option>'
        + _options(priorities_set) +
        '</select>'
        '<select id="filter-assignee" onchange="applyFilters()"><option value="">All Assignees</option>'
        + _options(assignees_set) +
        '</select>'
        '</div>'
    )

    # Open issues table with data attributes and copy column
    if open_issues:
        issue_rows = []
        for i in open_issues:
            issue_rows.append(
                f'<tr data-type="{_esc(i.type)}" data-priority="{_esc(i.priority)}" data-assignee="{_esc(i.assignee or "")}">'
                f'<td>#{i.id}</td>'
                f'<td><a href="#" class="issue-link" onclick="showIssue({i.id});return false">{_esc(i.title)}</a></td>'
                f'<td>{_esc(i.type)}</td>'
                f'<td>{_esc(i.priority)}</td>'
                f'<td>{_esc(i.assignee or "-")}</td>'
                f'<td>{_esc(i.created_at)}</td>'
                f'<td><span class="copy-icon" onclick="copyCmd(this)" title="Copy yait show command">yait show {i.id}</span></td>'
                f'</tr>'
            )
        open_table = (
            filter_bar
            + '<table id="open-issues-table"><thead><tr>'
            '<th>ID</th><th>Title</th><th>Type</th><th>Priority</th><th>Assignee</th><th>Created</th><th></th>'
            '</tr></thead><tbody>'
            + "\n".join(issue_rows)
            + '</tbody></table>'
        )
    else:
        open_table = '<p class="muted">No open issues</p>'

    # Recently closed table with copy column
    if recently_closed:
        closed_rows = []
        for i in recently_closed:
            closed_rows.append(
                f'<tr data-type="{_esc(i.type)}" data-priority="{_esc(i.priority)}" data-assignee="{_esc(i.assignee or "")}">'
                f'<td>#{i.id}</td>'
                f'<td><a href="#" class="issue-link" onclick="showIssue({i.id});return false">{_esc(i.title)}</a></td>'
                f'<td>{_esc(i.type)}</td>'
                f'<td>{_esc(i.updated_at or i.created_at)}</td>'
                f'<td><span class="copy-icon" onclick="copyCmd(this)" title="Copy yait show command">yait show {i.id}</span></td>'
                f'</tr>'
            )
        closed_table = (
            '<table><thead><tr>'
            '<th>ID</th><th>Title</th><th>Type</th><th>Closed</th><th></th>'
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
.ms-header.accordion-toggle{{cursor:pointer}}
.ms-header.accordion-toggle:hover .ms-name{{text-decoration:underline}}
.ms-name{{font-weight:500;color:#f8fafc}}
.ms-stats{{font-size:.8rem;color:#94a3b8}}
.ms-issue-list{{list-style:none;padding:.5rem 0 0 1rem;font-size:.85rem}}
.ms-issue-list li{{padding:.2rem 0}}
.ms-issue-list li a{{color:#93c5fd;text-decoration:none}}
.ms-issue-list li a:hover{{text-decoration:underline}}
.ms-issue-list li.ms-issue-closed a{{color:#6b7280;text-decoration:line-through}}
table{{width:100%;border-collapse:collapse;font-size:.85rem}}
th{{text-align:left;padding:.5rem .75rem;border-bottom:1px solid #334155;color:#94a3b8;font-weight:500;text-transform:uppercase;font-size:.75rem;letter-spacing:.05em}}
td{{padding:.5rem .75rem;border-bottom:1px solid #1e293b}}
tr:hover td{{background:#1e293b}}
.muted{{color:#64748b;font-size:.85rem}}
.issue-link{{color:#93c5fd;text-decoration:none}}
.issue-link:hover{{text-decoration:underline}}
.copy-icon{{cursor:pointer;font-family:monospace;font-size:.75rem;color:#64748b;background:#0f172a;border:1px solid #334155;border-radius:3px;padding:2px 6px}}
.copy-icon:hover{{color:#e2e8f0;border-color:#94a3b8}}
.copy-icon.copied{{color:#22c55e;border-color:#22c55e}}
.filter-bar{{display:flex;gap:.5rem;margin-bottom:1rem;flex-wrap:wrap}}
.filter-bar input,.filter-bar select{{background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px;padding:.4rem .6rem;font-size:.85rem}}
.filter-bar input{{flex:1;min-width:150px}}
.filter-bar select{{min-width:120px}}
.modal-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:1000;justify-content:center;align-items:flex-start;padding:3rem 1rem;overflow-y:auto}}
.modal-overlay.active{{display:flex}}
.modal{{background:#1e293b;border-radius:.5rem;max-width:700px;width:100%;padding:1.5rem;position:relative}}
.modal-close{{position:absolute;top:.75rem;right:1rem;background:none;border:none;color:#94a3b8;font-size:1.5rem;cursor:pointer}}
.modal-close:hover{{color:#f8fafc}}
.modal h3{{font-size:1.15rem;color:#f8fafc;margin-bottom:.75rem;padding-right:2rem}}
.modal .badge{{display:inline-block;font-size:.7rem;padding:2px 8px;border-radius:3px;margin-right:.25rem;font-weight:500;text-transform:uppercase}}
.badge-status{{background:#334155;color:#e2e8f0}}
.badge-type{{background:#1e3a5f;color:#93c5fd}}
.badge-priority{{background:#3b1f1f;color:#fca5a5}}
.modal .meta{{font-size:.8rem;color:#94a3b8;margin:.75rem 0;line-height:1.8}}
.modal .meta span{{margin-right:1rem}}
.modal .body-content{{background:#0f172a;border:1px solid #334155;border-radius:4px;padding:1rem;font-size:.85rem;white-space:pre-wrap;margin:.75rem 0;max-height:200px;overflow-y:auto}}
.modal .links-list,.modal .docs-list{{font-size:.85rem;margin:.5rem 0}}
.modal .links-list a{{color:#93c5fd;cursor:pointer;text-decoration:none}}
.modal .links-list a:hover{{text-decoration:underline}}
.commands-section{{margin-top:1rem;border-top:1px solid #334155;padding-top:.75rem}}
.commands-section h4{{font-size:.85rem;color:#94a3b8;margin-bottom:.5rem}}
.commands-grid{{display:grid;grid-template-columns:1fr 1fr;gap:.35rem}}
.cmd{{font-family:monospace;font-size:.8rem;background:#0f172a;border:1px solid #334155;border-radius:3px;padding:4px 8px;cursor:pointer;color:#cbd5e1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.cmd:hover{{border-color:#94a3b8;color:#f8fafc}}
.cmd.copied{{color:#22c55e;border-color:#22c55e}}
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

<div class="modal-overlay" id="modal-overlay" onclick="if(event.target===this)closeModal()">
<div class="modal" id="modal">
<button class="modal-close" onclick="closeModal()">&times;</button>
<div id="modal-content"></div>
</div>
</div>

<script>
const ISSUES={issues_json};
const PROJECT_NAME={project_json};
const WORKFLOW={workflow_json};
const issueMap={{}};
ISSUES.forEach(function(i){{issueMap[i.id]=i}});
const issueIds=ISSUES.map(function(i){{return i.id}});
let currentIssueIdx=-1;

function esc(s){{
  var d=document.createElement('div');d.textContent=s||'';return d.innerHTML;
}}

function copyCmd(el){{
  navigator.clipboard.writeText(el.textContent.trim());
  var orig=el.textContent;
  el.textContent='\\u2713 Copied!';
  el.classList.add('copied');
  setTimeout(function(){{el.textContent=orig;el.classList.remove('copied')}},1500);
}}

function pfx(){{return PROJECT_NAME?'-P '+PROJECT_NAME+' ':''}}

function buildCommands(id){{
  var p=pfx();
  var cmds=['yait '+p+'show '+id,'yait '+p+'log '+id];
  var statuses=WORKFLOW.statuses||['open','closed'];
  statuses.forEach(function(s){{cmds.push('yait '+p+'status '+id+' '+s)}});
  cmds.push('yait '+p+'edit '+id+' --title ""');
  cmds.push('yait '+p+'assign '+id+' ');
  cmds.push('yait '+p+'comment '+id+' -m ""');
  cmds.push('yait '+p+'close '+id);
  cmds.push('yait '+p+'reopen '+id);
  cmds.push('yait '+p+'label add '+id+' ');
  return cmds;
}}

function showIssue(id){{
  var i=issueMap[id];if(!i)return;
  currentIssueIdx=issueIds.indexOf(id);
  var h='<h3>'+esc(i.title)+'</h3>';
  h+='<div><span class="badge badge-status">'+esc(i.status)+'</span>';
  h+='<span class="badge badge-type">'+esc(i.type)+'</span>';
  h+='<span class="badge badge-priority">'+esc(i.priority)+'</span></div>';
  h+='<div class="meta">';
  h+='<span>Assignee: '+(esc(i.assignee)||'-')+'</span>';
  h+='<span>Milestone: '+(esc(i.milestone)||'-')+'</span><br>';
  if(i.labels&&i.labels.length)h+='<span>Labels: '+i.labels.map(esc).join(', ')+'</span><br>';
  h+='<span>Created: '+esc(i.created_at)+'</span>';
  h+='<span>Updated: '+esc(i.updated_at)+'</span>';
  h+='</div>';
  if(i.body)h+='<div class="body-content">'+esc(i.body)+'</div>';
  if(i.links&&i.links.length){{
    h+='<div class="links-list"><strong>Links:</strong> ';
    i.links.forEach(function(l){{h+='<a onclick="showIssue('+l.target+');return false">'+esc(l.type)+' #'+l.target+'</a> '}});
    h+='</div>';
  }}
  if(i.docs&&i.docs.length){{
    h+='<div class="docs-list"><strong>Docs:</strong> '+i.docs.map(esc).join(', ')+'</div>';
  }}
  var cmds=buildCommands(id);
  h+='<div class="commands-section"><h4>Quick Commands</h4><div class="commands-grid">';
  cmds.forEach(function(c){{h+='<div class="cmd" onclick="copyCmd(this)">'+esc(c)+'</div>'}});
  h+='</div></div>';
  document.getElementById('modal-content').innerHTML=h;
  document.getElementById('modal-overlay').classList.add('active');
}}

function closeModal(){{
  document.getElementById('modal-overlay').classList.remove('active');
  currentIssueIdx=-1;
}}

function toggleAccordion(el){{
  var list=el.parentElement.querySelector('.ms-issue-list');
  if(list)list.style.display=list.style.display==='none'?'block':'none';
}}

function applyFilters(){{
  var search=(document.getElementById('filter-search').value||'').toLowerCase();
  var type=document.getElementById('filter-type').value;
  var priority=document.getElementById('filter-priority').value;
  var assignee=document.getElementById('filter-assignee').value;
  var tbl=document.getElementById('open-issues-table');
  if(!tbl)return;
  var rows=tbl.querySelectorAll('tbody tr');
  rows.forEach(function(r){{
    var show=true;
    if(type&&r.getAttribute('data-type')!==type)show=false;
    if(priority&&r.getAttribute('data-priority')!==priority)show=false;
    if(assignee&&r.getAttribute('data-assignee')!==assignee)show=false;
    if(search&&r.textContent.toLowerCase().indexOf(search)===-1)show=false;
    r.style.display=show?'':'none';
  }});
}}

document.addEventListener('keydown',function(e){{
  var overlay=document.getElementById('modal-overlay');
  if(!overlay.classList.contains('active'))return;
  if(e.key==='Escape')closeModal();
  if(e.key==='ArrowLeft'&&currentIssueIdx>0)showIssue(issueIds[currentIssueIdx-1]);
  if(e.key==='ArrowRight'&&currentIssueIdx<issueIds.length-1)showIssue(issueIds[currentIssueIdx+1]);
}});
</script>
</body>
</html>"""
