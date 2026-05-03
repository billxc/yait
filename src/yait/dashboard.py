"""Generate a multi-page HTML dashboard snapshot for a yait project.

Layout written into ``output_dir`` (default ``<root>/dashboard/``)::

    dashboard/
      .gitignore                ("*" — whole snapshot is excluded from git)
      index.html                (overview + tables linking to issue pages)
      assets/style.css          (shared stylesheet)
      issues/<id>.html          (one page per issue with rendered markdown body)
"""

from __future__ import annotations

import html
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .store import list_issues, list_milestones, get_workflow


def generate_dashboard(
    root: Path,
    output_dir: Path | None = None,
    project_name: str = "",
) -> Path:
    """Render dashboard snapshot under ``output_dir``. Returns path to ``index.html``."""
    if output_dir is None:
        output_dir = Path(root) / "dashboard"
    output_dir = Path(output_dir)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    (output_dir / "issues").mkdir()
    (output_dir / "assets").mkdir()

    (output_dir / ".gitignore").write_text("*\n", encoding="utf-8")
    (output_dir / "assets" / "style.css").write_text(_STYLESHEET, encoding="utf-8")

    all_issues = list_issues(root)
    milestones = list_milestones(root)
    workflow = get_workflow(root)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    issue_titles = {i.id: i.title for i in all_issues}
    issue_statuses = {i.id: i.status for i in all_issues}

    for issue in all_issues:
        page = _render_issue_page(
            issue,
            project_name=project_name,
            workflow=workflow,
            now_str=now_str,
            issue_titles=issue_titles,
            issue_statuses=issue_statuses,
        )
        (output_dir / "issues" / f"{issue.id}.html").write_text(page, encoding="utf-8")

    index_html = _render_index(
        all_issues=all_issues,
        milestones=milestones,
        project_name=project_name,
        now_str=now_str,
    )
    index_path = output_dir / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    return index_path


def _esc(text) -> str:
    return html.escape(str(text), quote=True)


def _safe_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", r"<\/")


def _issue_href(issue_id: int, *, from_index: bool) -> str:
    return f"issues/{issue_id}.html" if from_index else f"{issue_id}.html"


def _bar_section(label: str, counts: dict, color_map: dict) -> str:
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
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div>'
            f'<span class="bar-value">{count}</span>'
            f'</div>'
        )
    return f'<h3>{_esc(label)}</h3>' + "\n".join(rows)


def _badge(value: str, kind: str) -> str:
    return f'<span class="chip chip-{kind} chip-{kind}-{_esc(value)}">{_esc(value)}</span>'


def _label_chips(labels) -> str:
    if not labels:
        return ""
    return " ".join(f'<span class="chip chip-label">{_esc(l)}</span>' for l in labels)


_TYPE_COLORS = {
    "bug": "#ef4444",
    "feature": "#3b82f6",
    "enhancement": "#8b5cf6",
    "misc": "#6b7280",
}
_PRIORITY_COLORS = {
    "p0": "#ef4444",
    "p1": "#f59e0b",
    "p2": "#3b82f6",
    "p3": "#6b7280",
    "none": "#9ca3af",
}


def _page_head(title: str, css_href: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{css_href}">
</head>"""


def _render_index(
    *,
    all_issues,
    milestones,
    project_name: str,
    now_str: str,
) -> str:
    title_text = (
        f"YAIT Dashboard — {_esc(project_name)}" if project_name else "YAIT Dashboard"
    )

    total = len(all_issues)
    open_issues = [i for i in all_issues if i.status == "open"]
    closed_issues = [i for i in all_issues if i.status == "closed"]
    open_count = len(open_issues)
    closed_count = len(closed_issues)
    close_rate = round(closed_count / total * 100) if total else 0

    type_counts = Counter(i.type for i in all_issues)
    priority_counts = Counter(i.priority for i in all_issues)
    type_section = _bar_section("By Type", dict(type_counts), _TYPE_COLORS)
    priority_section = _bar_section("By Priority", dict(priority_counts), _PRIORITY_COLORS)

    open_milestones = [m for m in milestones if m.status == "open"]
    if open_milestones:
        rows = []
        for m in open_milestones:
            ms_issues = [i for i in all_issues if i.milestone == m.name]
            ms_total = len(ms_issues)
            ms_closed = sum(1 for i in ms_issues if i.status == "closed")
            pct = round(ms_closed / ms_total * 100) if ms_total else 0
            due = f' &middot; Due: {_esc(m.due_date)}' if m.due_date else ""

            li_items = ""
            for mi in sorted(ms_issues, key=lambda x: x.id):
                cls = "ms-issue-closed" if mi.status == "closed" else ""
                li_items += (
                    f'<li class="{cls}"><a href="{_issue_href(mi.id, from_index=True)}">'
                    f'#{mi.id} {_esc(mi.title)}</a></li>'
                )
            issue_list = (
                f'<ul class="ms-issue-list" style="display:none">{li_items}</ul>'
                if li_items else ""
            )
            toggle_attr = ' onclick="toggleAccordion(this)"' if li_items else ""
            toggle_cls = " accordion-toggle" if li_items else ""
            rows.append(
                f'<div class="ms-item">'
                f'<div class="ms-header{toggle_cls}"{toggle_attr}>'
                f'<span class="ms-name">{_esc(m.name)}</span>'
                f'<span class="ms-stats">{ms_closed}/{ms_total} closed ({pct}%){due}</span>'
                f'</div>'
                f'<div class="bar-track"><div class="bar-fill bar-fill-ms" style="width:{pct}%"></div></div>'
                f'{issue_list}'
                f'</div>'
            )
        ms_html = "\n".join(rows)
    else:
        ms_html = '<p class="muted">No open milestones</p>'

    types_set = sorted(set(i.type for i in open_issues))
    priorities_set = sorted(set(i.priority for i in open_issues))
    assignees_set = sorted(set(i.assignee for i in open_issues if i.assignee))

    def _options(values):
        return "".join(f'<option value="{_esc(v)}">{_esc(v)}</option>' for v in values)

    filter_bar = (
        '<div class="filter-bar">'
        '<input type="text" id="filter-search" placeholder="Search title, label, assignee..." oninput="applyFilters()">'
        '<select id="filter-type" onchange="applyFilters()"><option value="">All Types</option>'
        + _options(types_set) + '</select>'
        '<select id="filter-priority" onchange="applyFilters()"><option value="">All Priorities</option>'
        + _options(priorities_set) + '</select>'
        '<select id="filter-assignee" onchange="applyFilters()"><option value="">All Assignees</option>'
        + _options(assignees_set) + '</select>'
        '</div>'
    )

    open_sorted = sorted(open_issues, key=lambda i: i.id)
    if open_sorted:
        rows = []
        for i in open_sorted:
            href = _issue_href(i.id, from_index=True)
            rows.append(
                f'<tr data-type="{_esc(i.type)}" data-priority="{_esc(i.priority)}" data-assignee="{_esc(i.assignee or "")}">'
                f'<td class="col-id">#{i.id}</td>'
                f'<td><a class="issue-link" href="{href}">{_esc(i.title)}</a> {_label_chips(i.labels)}</td>'
                f'<td>{_badge(i.type, "type")}</td>'
                f'<td>{_badge(i.priority, "prio")}</td>'
                f'<td>{_esc(i.assignee or "—")}</td>'
                f'<td class="col-date">{_esc(i.created_at[:10] if i.created_at else "")}</td>'
                f'</tr>'
            )
        open_table = (
            filter_bar
            + '<div class="table-wrap"><table id="open-issues-table"><thead><tr>'
            '<th>ID</th><th>Title</th><th>Type</th><th>Priority</th><th>Assignee</th><th>Created</th>'
            '</tr></thead><tbody>'
            + "\n".join(rows)
            + '</tbody></table></div>'
        )
    else:
        open_table = '<p class="muted">No open issues</p>'

    recently_closed = sorted(
        closed_issues,
        key=lambda i: i.updated_at or i.created_at or "",
        reverse=True,
    )[:10]
    if recently_closed:
        rows = []
        for i in recently_closed:
            href = _issue_href(i.id, from_index=True)
            rows.append(
                f'<tr>'
                f'<td class="col-id">#{i.id}</td>'
                f'<td><a class="issue-link" href="{href}">{_esc(i.title)}</a></td>'
                f'<td>{_badge(i.type, "type")}</td>'
                f'<td class="col-date">{_esc((i.updated_at or i.created_at)[:10])}</td>'
                f'</tr>'
            )
        closed_table = (
            '<div class="table-wrap"><table><thead><tr>'
            '<th>ID</th><th>Title</th><th>Type</th><th>Closed</th>'
            '</tr></thead><tbody>'
            + "\n".join(rows)
            + '</tbody></table></div>'
        )
    else:
        closed_table = '<p class="muted">No closed issues</p>'

    head = _page_head(title_text, "assets/style.css")
    return f"""{head}
<body>
<div class="container">
<header>
<div>
<h1>{title_text}</h1>
<div class="timestamp">Generated: {_esc(now_str)} &middot; <span class="muted">snapshot — re-run <code>yait dashboard</code> to refresh</span></div>
</div>
</header>

<div class="cards">
<div class="card"><div class="label">Total</div><div class="value">{total}</div></div>
<div class="card accent"><div class="label">Open</div><div class="value">{open_count}</div></div>
<div class="card ok"><div class="label">Closed</div><div class="value">{closed_count}</div></div>
<div class="card warn"><div class="label">Close Rate</div><div class="value">{close_rate}%</div></div>
</div>

<div class="grid-2">
<section><h2>Breakdown</h2>{type_section}{priority_section}</section>
<section><h2>Milestone Progress</h2>{ms_html}</section>
</div>

<section><h2>Open Issues</h2>{open_table}</section>
<section><h2>Recently Closed</h2>{closed_table}</section>
</div>

<script>
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
  tbl.querySelectorAll('tbody tr').forEach(function(r){{
    var show=true;
    if(type&&r.getAttribute('data-type')!==type)show=false;
    if(priority&&r.getAttribute('data-priority')!==priority)show=false;
    if(assignee&&r.getAttribute('data-assignee')!==assignee)show=false;
    if(search&&r.textContent.toLowerCase().indexOf(search)===-1)show=false;
    r.style.display=show?'':'none';
  }});
}}
</script>
</body>
</html>"""


def _render_issue_page(
    issue,
    *,
    project_name: str,
    workflow: dict,
    now_str: str,
    issue_titles: dict,
    issue_statuses: dict,
) -> str:
    title_text = f"#{issue.id} · {_esc(issue.title)}"

    sorted_ids = sorted(issue_titles.keys())
    pos = sorted_ids.index(issue.id) if issue.id in sorted_ids else -1
    prev_id = sorted_ids[pos - 1] if pos > 0 else None
    next_id_ = sorted_ids[pos + 1] if 0 <= pos < len(sorted_ids) - 1 else None

    nav_prev = (
        f'<a class="nav-btn" href="{prev_id}.html" title="Previous issue">‹ #{prev_id}</a>'
        if prev_id else '<span class="nav-btn disabled">‹</span>'
    )
    nav_next = (
        f'<a class="nav-btn" href="{next_id_}.html" title="Next issue">#{next_id_} ›</a>'
        if next_id_ else '<span class="nav-btn disabled">›</span>'
    )

    badges = (
        f'<span class="chip chip-status chip-status-{_esc(issue.status)}">{_esc(issue.status)}</span>'
        + _badge(issue.type, "type")
        + _badge(issue.priority, "prio")
        + (_label_chips(issue.labels))
    )

    meta = (
        f'<div><b>Assignee:</b> {_esc(issue.assignee or "—")}</div>'
        f'<div><b>Milestone:</b> {_esc(issue.milestone or "—")}</div>'
        f'<div><b>Created:</b> {_esc(issue.created_at or "—")}</div>'
        f'<div><b>Updated:</b> {_esc(issue.updated_at or "—")}</div>'
    )

    if issue.links:
        link_items = []
        for l in issue.links:
            tgt = l.get("target")
            link_type = l.get("type", "")
            tgt_title = issue_titles.get(tgt, "")
            tgt_status = issue_statuses.get(tgt, "")
            tgt_label = f"#{tgt} {tgt_title}" if tgt_title else f"#{tgt}"
            cls = "ms-issue-closed" if tgt_status == "closed" else ""
            link_items.append(
                f'<li class="{cls}"><span class="link-type">{_esc(link_type)}</span> '
                f'<a href="{tgt}.html">{_esc(tgt_label)}</a></li>'
            )
        links_html = (
            '<section><h2>Links</h2><ul class="link-list">' + "".join(link_items) + "</ul></section>"
        )
    else:
        links_html = ""

    if issue.docs:
        docs_html = (
            '<section><h2>Docs</h2><ul class="link-list">'
            + "".join(f'<li>{_esc(d)}</li>' for d in issue.docs)
            + "</ul></section>"
        )
    else:
        docs_html = ""

    pfx = f"-P {project_name} " if project_name else ""
    statuses = workflow.get("statuses") or ["open", "closed"]
    cmds = [f"yait {pfx}show {issue.id}", f"yait {pfx}log {issue.id}"]
    cmds += [f"yait {pfx}status {issue.id} {s}" for s in statuses]
    cmds += [
        f'yait {pfx}edit {issue.id} --title ""',
        f"yait {pfx}assign {issue.id} ",
        f'yait {pfx}comment {issue.id} -m ""',
        f"yait {pfx}close {issue.id}",
        f"yait {pfx}reopen {issue.id}",
        f"yait {pfx}label add {issue.id} ",
    ]
    cmd_html = "".join(
        f'<div class="cmd" onclick="copyCmd(this)">{_esc(c)}</div>' for c in cmds
    )

    body_json = _safe_json(issue.body or "")
    head = _page_head(title_text, "../assets/style.css")
    return f"""{head}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css">
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dompurify@3.0.11/dist/purify.min.js"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>
<body class="issue-page">
<div class="container narrow">
<header class="issue-header">
<div class="breadcrumb"><a href="../index.html">← Dashboard</a></div>
<div class="nav-pair">{nav_prev}{nav_next}</div>
</header>

<h1 class="issue-title">{title_text}</h1>
<div class="badges">{badges}</div>
<div class="meta">{meta}</div>

<section><h2>Description</h2>
<div id="md-body" class="md-body"></div>
</section>

{links_html}
{docs_html}

<section>
<h2>Quick Commands</h2>
<div class="commands-grid">{cmd_html}</div>
</section>

<footer class="page-footer">Snapshot: {_esc(now_str)}</footer>
</div>

<script>
const BODY={body_json};
function copyCmd(el){{
  navigator.clipboard.writeText(el.textContent.trim());
  var orig=el.textContent;
  el.textContent='\\u2713 Copied!';
  el.classList.add('copied');
  setTimeout(function(){{el.textContent=orig;el.classList.remove('copied')}},1500);
}}
function renderBody(){{
  var el=document.getElementById('md-body');
  if(!BODY||!BODY.trim()){{el.classList.add('empty');el.textContent='No description';return}}
  if(window.marked&&window.DOMPurify){{
    if(window.hljs){{
      marked.setOptions({{gfm:true,breaks:false,highlight:function(c,l){{
        try{{return l&&hljs.getLanguage(l)?hljs.highlight(c,{{language:l}}).value:hljs.highlightAuto(c).value}}catch(e){{return c}}
      }}}});
    }}
    el.innerHTML=DOMPurify.sanitize(marked.parse(BODY),{{ADD_ATTR:['target']}});
    if(window.hljs)el.querySelectorAll('pre code').forEach(function(b){{try{{hljs.highlightElement(b)}}catch(e){{}}}});
  }}else{{
    var pre=document.createElement('pre');pre.textContent=BODY;el.appendChild(pre);
  }}
}}
renderBody();
document.addEventListener('keydown',function(e){{
  if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;
  if(e.key==='ArrowLeft'){{var p=document.querySelector('.nav-btn[href]:not(.disabled)');if(p&&p.textContent.indexOf('‹')===0)location.href=p.getAttribute('href')}}
  if(e.key==='ArrowRight'){{var ns=document.querySelectorAll('.nav-btn[href]:not(.disabled)');ns.forEach(function(n){{if(n.textContent.indexOf('›')!==-1)location.href=n.getAttribute('href')}})}}
  if(e.key==='Escape')location.href='../index.html';
}});
</script>
</body>
</html>"""


_STYLESHEET = """*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0b1220;--panel:#111a2e;--panel2:#16223b;--border:#26334d;--text:#e6edf7;--muted:#8a9ab5;--accent:#60a5fa;--ok:#22c55e;--warn:#f59e0b;--err:#ef4444}
html,body{height:100%}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;background:radial-gradient(1200px 600px at 10% -10%,#1b2547 0,transparent 60%),radial-gradient(900px 500px at 90% 0%,#1a1d3a 0,transparent 60%),var(--bg);color:var(--text);padding:1.5rem;line-height:1.55;-webkit-font-smoothing:antialiased}
.container{max-width:1180px;margin:0 auto}
.container.narrow{max-width:880px}
header{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:1.5rem;gap:1rem;flex-wrap:wrap}
header h1{font-size:1.6rem;font-weight:700;color:#fff;letter-spacing:-.01em}
header .timestamp{font-size:.8rem;color:var(--muted)}
header .timestamp code{font-family:ui-monospace,Menlo,Consolas,monospace;background:#0a1226;border:1px solid var(--border);border-radius:.3rem;padding:1px 6px;font-size:.78rem}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:1.25rem}
.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--border);border-radius:.75rem;padding:1rem 1.25rem}
.card .label{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-weight:600}
.card .value{font-size:2rem;font-weight:700;color:#fff;margin-top:.15rem;line-height:1.1}
.card.accent .value{color:var(--accent)}
.card.ok .value{color:var(--ok)}
.card.warn .value{color:var(--warn)}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1rem}
@media (max-width:860px){.grid-2{grid-template-columns:1fr}.cards{grid-template-columns:repeat(2,1fr)}}
section{background:var(--panel);border:1px solid var(--border);border-radius:.75rem;padding:1.25rem 1.5rem;margin-bottom:1rem}
h2{font-size:1rem;font-weight:600;color:#fff;margin-bottom:.75rem;display:flex;align-items:center;gap:.5rem}
h2::before{content:"";display:inline-block;width:3px;height:14px;background:var(--accent);border-radius:2px}
h3{font-size:.8rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin:.9rem 0 .4rem}
.bar-row{display:flex;align-items:center;gap:.75rem;margin-bottom:.35rem}
.bar-label{width:90px;font-size:.8rem;color:var(--muted);text-align:right}
.bar-track{flex:1;height:8px;background:#1f2a44;border-radius:999px;overflow:hidden}
.bar-fill{height:100%;border-radius:999px;transition:width .4s ease}
.bar-fill-ms{background:linear-gradient(90deg,var(--accent),var(--ok))}
.bar-value{width:32px;font-size:.8rem;color:var(--text);font-variant-numeric:tabular-nums;text-align:right}
.ms-item{margin-bottom:.9rem}
.ms-header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:.3rem;gap:.5rem}
.ms-header.accordion-toggle{cursor:pointer;user-select:none}
.ms-header.accordion-toggle:hover .ms-name{color:var(--accent)}
.ms-name{font-weight:600;color:#fff;font-size:.9rem;transition:color .15s}
.ms-stats{font-size:.75rem;color:var(--muted);font-variant-numeric:tabular-nums}
.ms-issue-list{list-style:none;padding:.5rem 0 0 .75rem;font-size:.85rem;border-left:2px solid var(--border);margin-left:.25rem;margin-top:.5rem}
.ms-issue-list li{padding:.18rem 0}
.ms-issue-list li a{color:var(--accent);text-decoration:none}
.ms-issue-list li a:hover{text-decoration:underline}
.ms-issue-list li.ms-issue-closed a{color:var(--muted);text-decoration:line-through}
.table-wrap{overflow-x:auto;border-radius:.5rem}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;padding:.55rem .75rem;border-bottom:1px solid var(--border);color:var(--muted);font-weight:600;text-transform:uppercase;font-size:.7rem;letter-spacing:.06em;background:#0e1830}
td{padding:.55rem .75rem;border-bottom:1px solid #1a2540;vertical-align:middle}
tbody tr{transition:background .15s}
tbody tr:hover td{background:#162243}
.col-id{font-variant-numeric:tabular-nums;color:var(--muted);width:64px;font-weight:600}
.col-date{color:var(--muted);font-size:.78rem;white-space:nowrap}
.muted{color:var(--muted);font-size:.85rem}
.issue-link{color:#cfe1ff;text-decoration:none;font-weight:500}
.issue-link:hover{color:var(--accent);text-decoration:underline}
.chip{display:inline-block;font-size:.68rem;padding:2px 8px;border-radius:999px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;line-height:1.4;border:1px solid transparent}
.chip-label{background:#1c2a4a;color:#bcd1ff;border-color:#2a3a60;text-transform:none;letter-spacing:0;font-weight:500;margin-left:.25rem}
.chip-status-open{background:rgba(34,197,94,.18);color:#86efac;border-color:rgba(34,197,94,.35)}
.chip-status-closed{background:rgba(107,114,128,.2);color:#cbd5e1;border-color:rgba(107,114,128,.35)}
.chip-type-bug{background:rgba(239,68,68,.15);color:#fca5a5;border-color:rgba(239,68,68,.3)}
.chip-type-feature{background:rgba(59,130,246,.15);color:#93c5fd;border-color:rgba(59,130,246,.3)}
.chip-type-enhancement{background:rgba(139,92,246,.15);color:#c4b5fd;border-color:rgba(139,92,246,.3)}
.chip-type-misc{background:rgba(107,114,128,.15);color:#cbd5e1;border-color:rgba(107,114,128,.3)}
.chip-prio-p0{background:rgba(239,68,68,.18);color:#fca5a5;border-color:rgba(239,68,68,.35)}
.chip-prio-p1{background:rgba(245,158,11,.18);color:#fcd34d;border-color:rgba(245,158,11,.35)}
.chip-prio-p2{background:rgba(59,130,246,.18);color:#93c5fd;border-color:rgba(59,130,246,.35)}
.chip-prio-p3{background:rgba(107,114,128,.18);color:#cbd5e1;border-color:rgba(107,114,128,.35)}
.chip-prio-none{background:#1a2540;color:var(--muted);border-color:var(--border)}
.filter-bar{display:flex;gap:.5rem;margin-bottom:.85rem;flex-wrap:wrap}
.filter-bar input,.filter-bar select{background:#0a1226;border:1px solid var(--border);color:var(--text);border-radius:.4rem;padding:.45rem .65rem;font-size:.85rem;outline:none;transition:border-color .15s}
.filter-bar input:focus,.filter-bar select:focus{border-color:var(--accent)}
.filter-bar input{flex:1;min-width:200px}
.filter-bar select{min-width:130px}
/* Issue page */
.issue-page .container{padding:0}
.issue-header{margin-bottom:1rem;align-items:center}
.breadcrumb a{color:var(--muted);text-decoration:none;font-size:.85rem}
.breadcrumb a:hover{color:var(--accent)}
.nav-pair{display:flex;gap:.4rem}
.nav-btn{display:inline-block;background:#0a1226;border:1px solid var(--border);color:var(--text);text-decoration:none;font-size:.85rem;padding:.35rem .7rem;border-radius:.4rem;transition:all .15s}
.nav-btn:hover{border-color:var(--accent);color:#fff}
.nav-btn.disabled{opacity:.35;cursor:not-allowed}
.issue-title{font-size:1.6rem;color:#fff;font-weight:700;margin-bottom:.6rem;letter-spacing:-.01em;line-height:1.25}
.badges{display:flex;flex-wrap:wrap;gap:.3rem;margin-bottom:1rem}
.meta{font-size:.85rem;color:var(--muted);display:grid;grid-template-columns:repeat(2,1fr);gap:.4rem .9rem;background:var(--panel);border:1px solid var(--border);border-radius:.6rem;padding:.85rem 1.1rem;margin-bottom:1rem}
.meta b{color:var(--text);font-weight:500}
.md-body{font-size:.95rem;line-height:1.65;color:var(--text)}
.md-body.empty{color:var(--muted);font-style:italic}
.md-body h1,.md-body h2,.md-body h3,.md-body h4{color:#fff;margin:1.2em 0 .5em;font-weight:600;line-height:1.25}
.md-body h1{font-size:1.5rem;border-bottom:1px solid var(--border);padding-bottom:.3rem}
.md-body h2{font-size:1.25rem;border-bottom:1px solid var(--border);padding-bottom:.25rem}
.md-body h2::before{content:none}
.md-body h3{font-size:1.08rem;color:#fff;text-transform:none;letter-spacing:0;margin:1.1em 0 .4em}
.md-body h4{font-size:.98rem}
.md-body p{margin:.6em 0}
.md-body ul,.md-body ol{margin:.5em 0 .5em 1.6em}
.md-body li{margin:.18em 0}
.md-body code{background:#162243;color:#f5d0fe;padding:.12em .4em;border-radius:.25em;font-size:.88em;font-family:ui-monospace,Menlo,Consolas,monospace}
.md-body pre{background:#06101f;border:1px solid var(--border);border-radius:.5rem;padding:.95rem 1.1rem;overflow-x:auto;margin:.8em 0}
.md-body pre code{background:none;color:inherit;padding:0;font-size:.85em}
.md-body blockquote{border-left:3px solid var(--accent);padding:.15em .9em;color:var(--muted);margin:.7em 0;background:#0d1730;border-radius:0 .3rem .3rem 0}
.md-body a{color:var(--accent);text-decoration:none}
.md-body a:hover{text-decoration:underline}
.md-body table{width:auto;border:1px solid var(--border);margin:.7em 0;font-size:.88rem}
.md-body th,.md-body td{padding:.4rem .7rem;border:1px solid var(--border)}
.md-body th{background:#142042;text-transform:none;letter-spacing:0;font-size:.88rem}
.md-body img{max-width:100%;border-radius:.4rem}
.md-body hr{border:none;border-top:1px solid var(--border);margin:1em 0}
.md-body input[type=checkbox]{margin-right:.4em}
.link-list{list-style:none;padding:0;font-size:.9rem}
.link-list li{padding:.25rem 0;border-bottom:1px dashed #1a2540}
.link-list li:last-child{border:none}
.link-list a{color:var(--accent);text-decoration:none}
.link-list a:hover{text-decoration:underline}
.link-list .ms-issue-closed a{color:var(--muted);text-decoration:line-through}
.link-type{display:inline-block;font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;background:#0a1226;border:1px solid var(--border);border-radius:.25rem;padding:1px 6px;margin-right:.5rem}
.commands-grid{display:grid;grid-template-columns:1fr 1fr;gap:.4rem}
.cmd{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.78rem;background:#0a1226;border:1px solid var(--border);border-radius:.35rem;padding:6px 10px;cursor:pointer;color:#cbd5e1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:all .15s}
.cmd:hover{border-color:var(--accent);color:#fff}
.cmd.copied{color:var(--ok);border-color:var(--ok)}
.page-footer{font-size:.75rem;color:var(--muted);text-align:center;margin-top:2rem;padding-top:1rem;border-top:1px solid var(--border)}
"""
