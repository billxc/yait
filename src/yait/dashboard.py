"""Generate a multi-page HTML dashboard snapshot for a yait project.

Visual: GitHub-style minimal — white background, system sans-serif,
blue accent. Markdown is rendered server-side (no CDN, no runtime JS
for content). Pages are fully self-contained: no network requests.
"""

from __future__ import annotations

import html
import json
import re
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


def _short_date(s: str) -> str:
    return s[:10] if s else ""


_PRIORITY_RANK = {"p0": 0, "p1": 1, "p2": 2, "p3": 3, "none": 4}


# ---------------------------------------------------------------- markdown

def render_markdown(text: str) -> str:
    """Render a useful subset of GFM to safe HTML, server-side.

    Supports: ATX headings, fenced code blocks (```lang), blockquotes,
    unordered/ordered lists, horizontal rules, paragraphs, hard breaks,
    inline code, bold, italic, and ``[text](url)`` links. All output is
    HTML-escaped before inline transforms run, so user content cannot
    inject tags.
    """
    if not text:
        return ""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m = re.match(r"^```\s*([\w+-]*)\s*$", line)
        if m:
            lang = m.group(1)
            i += 1
            buf: list[str] = []
            while i < n and not re.match(r"^```\s*$", lines[i]):
                buf.append(lines[i])
                i += 1
            if i < n:
                i += 1  # closing fence
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(
                f'<pre><code{cls}>{html.escape("\n".join(buf))}</code></pre>'
            )
            continue
        m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if re.match(r"^\s{0,3}([-*_])\s*\1\s*\1[\s\-*_]*$", line):
            out.append("<hr>")
            i += 1
            continue
        if line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").lstrip())
                i += 1
            out.append(f"<blockquote>{render_markdown(chr(10).join(buf))}</blockquote>")
            continue
        if re.match(r"^[-*+]\s+", line):
            items = []
            while i < n and re.match(r"^[-*+]\s+", lines[i]):
                items.append(_inline(re.sub(r"^[-*+]\s+", "", lines[i])))
                i += 1
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
            continue
        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i]):
                items.append(_inline(re.sub(r"^\d+\.\s+", "", lines[i])))
                i += 1
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in items) + "</ol>")
            continue
        if not line.strip():
            i += 1
            continue
        buf = []
        while i < n and lines[i].strip() and not _is_block_start(lines[i]):
            buf.append(lines[i])
            i += 1
        out.append(f"<p>{_inline(chr(10).join(buf))}</p>")
    return "\n".join(out)


def _is_block_start(line: str) -> bool:
    return bool(
        re.match(r"^```", line)
        or re.match(r"^#{1,6}\s+", line)
        or re.match(r"^\s{0,3}([-*_])\s*\1\s*\1[\s\-*_]*$", line)
        or line.startswith(">")
        or re.match(r"^[-*+]\s+", line)
        or re.match(r"^\d+\.\s+", line)
    )


def _inline(text: str) -> str:
    text = html.escape(text)
    placeholders: list[str] = []

    def stash(html_str: str) -> str:
        placeholders.append(html_str)
        return f"\x00{len(placeholders) - 1}\x00"

    text = re.sub(r"`([^`]+)`", lambda m: stash(f"<code>{m.group(1)}</code>"), text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: stash(f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>'),
        text,
    )
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![*\w])\*([^*\s][^*]*?)\*(?![*\w])", r"<em>\1</em>", text)
    text = re.sub(r"(?<![_\w])_([^_\s][^_]*?)_(?![_\w])", r"<em>\1</em>", text)
    text = text.replace("  \n", "<br>\n")
    text = re.sub(r"\x00(\d+)\x00", lambda m: placeholders[int(m.group(1))], text)
    return text


# ---------------------------------------------------------------- helpers

def _ascii_bar(pct: int, width: int = 16) -> str:
    pct = max(0, min(100, pct))
    filled = round(pct * width / 100)
    return "█" * filled + "░" * (width - filled)


def _page_head(title: str, css_href: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{css_href}">
</head>"""


# ---------------------------------------------------------------- index

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

    stats_html = (
        '<dl class="stats">'
        f'<div class="stat"><dt>Total</dt><dd>{total}</dd></div>'
        f'<div class="stat"><dt>Open</dt><dd>{open_count}</dd></div>'
        f'<div class="stat"><dt>Closed</dt><dd>{closed_count}</dd></div>'
        f'<div class="stat"><dt>Close rate</dt><dd>{close_rate}%</dd></div>'
        '</dl>'
    )

    def _count_block(label: str, counts: Counter) -> str:
        if not counts:
            return f'<div class="block"><h3>{_esc(label)}</h3><p class="muted">No data</p></div>'
        max_v = max(counts.values())
        rows = []
        for name, n in sorted(counts.items(), key=lambda x: -x[1]):
            pct = round(n / max_v * 100) if max_v else 0
            rows.append(
                f'<div class="count-row">'
                f'<span class="count-name">{_esc(name)}</span>'
                f'<span class="count-bar"><span class="count-bar-fill" style="width:{pct}%"></span></span>'
                f'<span class="count-num">{n}</span>'
                f'</div>'
            )
        return f'<div class="block"><h3>{_esc(label)}</h3>' + "".join(rows) + "</div>"

    breakdown_html = (
        '<div class="two-col">'
        + _count_block("By Type", type_counts)
        + _count_block("By Priority", priority_counts)
        + '</div>'
    )

    open_milestones = [m for m in milestones if m.status == "open"]
    if open_milestones:
        rows = []
        for m in open_milestones:
            ms_issues = [i for i in all_issues if i.milestone == m.name]
            ms_total = len(ms_issues)
            ms_closed = sum(1 for i in ms_issues if i.status == "closed")
            pct = round(ms_closed / ms_total * 100) if ms_total else 0
            due = f' · due {_esc(m.due_date)}' if m.due_date else ""
            child_items = ""
            for mi in sorted(ms_issues, key=lambda x: x.id):
                cls = " done" if mi.status == "closed" else ""
                child_items += (
                    f'<li class="ms-li{cls}">'
                    f'<a href="issues/{mi.id}.html">'
                    f'<span class="num">#{mi.id}</span> {_esc(mi.title)}</a></li>'
                )
            rows.append(
                f'<details class="ms-details"><summary>'
                f'<span class="ms-name">{_esc(m.name)}</span>'
                f'<span class="ms-progress"><span class="ms-progress-fill" style="width:{pct}%"></span></span>'
                f'<span class="ms-stats">{ms_closed}/{ms_total} closed ({pct}%){due}</span>'
                f'</summary>'
                f'<ul class="ms-children">{child_items or "<li class=\"muted\">no issues</li>"}</ul>'
                f'</details>'
            )
        ms_html = "".join(rows)
    else:
        ms_html = '<p class="muted">No open milestones</p>'

    types_set = sorted(set(i.type for i in open_issues))
    priorities_set = sorted(
        set(i.priority for i in open_issues), key=lambda p: _PRIORITY_RANK.get(p, 99)
    )
    assignees_set = sorted(set(i.assignee for i in open_issues if i.assignee))

    def _opts(values):
        return "".join(f'<option value="{_esc(v)}">{_esc(v)}</option>' for v in values)

    filter_bar = (
        '<div class="filter-bar">'
        '<input type="text" id="filter-search" placeholder="Filter issues" oninput="applyFilters()">'
        '<select id="filter-type" onchange="applyFilters()"><option value="">All types</option>'
        + _opts(types_set) + '</select>'
        '<select id="filter-priority" onchange="applyFilters()"><option value="">All priorities</option>'
        + _opts(priorities_set) + '</select>'
        '<select id="filter-assignee" onchange="applyFilters()"><option value="">All assignees</option>'
        + _opts(assignees_set) + '</select>'
        '</div>'
    )

    if open_issues:
        groups: dict[str, list] = {}
        for i in open_issues:
            groups.setdefault(i.priority, []).append(i)
        group_keys = sorted(groups.keys(), key=lambda p: _PRIORITY_RANK.get(p, 99))
        sections = []
        for pkey in group_keys:
            issues_g = sorted(groups[pkey], key=lambda x: x.id)
            issue_rows = []
            for i in issues_g:
                labels = (
                    " ".join(f'<span class="tag">{_esc(l)}</span>' for l in i.labels)
                    if i.labels else ""
                )
                issue_rows.append(
                    f'<li data-type="{_esc(i.type)}" data-priority="{_esc(i.priority)}" data-assignee="{_esc(i.assignee or "")}">'
                    f'<a class="row" href="issues/{i.id}.html">'
                    f'<span class="status-dot status-open"></span>'
                    f'<span class="num">#{i.id}</span>'
                    f'<span class="title">{_esc(i.title)} {labels}</span>'
                    f'<span class="meta-cell type">{_esc(i.type)}</span>'
                    f'<span class="meta-cell who">{_esc(i.assignee or "—")}</span>'
                    f'<span class="meta-cell when">{_esc(_short_date(i.created_at))}</span>'
                    f'</a></li>'
                )
            label = pkey.upper() if pkey != "none" else "No priority"
            sections.append(
                f'<div class="prio-group" data-prio-group="{_esc(pkey)}">'
                f'<h4 class="prio-label prio-{_esc(pkey)}">{label} <span class="muted">· {len(issues_g)}</span></h4>'
                f'<ul class="issue-list">' + "".join(issue_rows) + '</ul>'
                f'</div>'
            )
        open_html = (
            filter_bar
            + '<div id="open-issues" class="open-issues">' + "".join(sections) + '</div>'
        )
    else:
        open_html = '<p class="muted">No open issues</p>'

    recently_closed = sorted(
        closed_issues,
        key=lambda i: i.updated_at or i.created_at or "",
        reverse=True,
    )[:10]
    if recently_closed:
        rows = []
        for i in recently_closed:
            rows.append(
                f'<li><a class="row" href="issues/{i.id}.html">'
                f'<span class="status-dot status-closed"></span>'
                f'<span class="num">#{i.id}</span>'
                f'<span class="title">{_esc(i.title)}</span>'
                f'<span class="meta-cell type">{_esc(i.type)}</span>'
                f'<span class="meta-cell when">{_esc(_short_date(i.updated_at or i.created_at))}</span>'
                f'</a></li>'
            )
        closed_html = '<ul class="issue-list closed-list">' + "".join(rows) + '</ul>'
    else:
        closed_html = '<p class="muted">No closed issues</p>'

    head = _page_head(title_text, "assets/style.css")
    return f"""{head}
<body class="index-page">
<div class="page">

<header class="masthead">
<h1 class="brand">{title_text}</h1>
<div class="byline">{_esc(now_str)} · snapshot · re-run <code>yait dashboard</code> to refresh</div>
</header>

<section class="overview">{stats_html}</section>

<section><h2>Composition</h2>{breakdown_html}</section>

<section><h2>Milestone progress</h2><div class="milestones">{ms_html}</div></section>

<section><h2>Open issues <span class="muted">· {open_count}</span></h2>{open_html}</section>

<section><h2>Recently closed</h2>{closed_html}</section>

<footer class="colophon">Generated {_esc(now_str)}</footer>

</div>

<script>
function applyFilters(){{
  var s=(document.getElementById('filter-search').value||'').toLowerCase();
  var t=document.getElementById('filter-type').value;
  var p=document.getElementById('filter-priority').value;
  var a=document.getElementById('filter-assignee').value;
  var root=document.getElementById('open-issues');
  if(!root)return;
  root.querySelectorAll('li[data-type]').forEach(function(li){{
    var ok=true;
    if(t&&li.getAttribute('data-type')!==t)ok=false;
    if(p&&li.getAttribute('data-priority')!==p)ok=false;
    if(a&&li.getAttribute('data-assignee')!==a)ok=false;
    if(s&&li.textContent.toLowerCase().indexOf(s)===-1)ok=false;
    li.style.display=ok?'':'none';
  }});
  root.querySelectorAll('.prio-group').forEach(function(g){{
    var visible=g.querySelectorAll('li[data-type]:not([style*="display: none"])').length;
    g.style.display=visible?'':'none';
  }});
}}
</script>
</body>
</html>"""


# ---------------------------------------------------------------- issue page

def _render_issue_page(
    issue,
    *,
    project_name: str,
    workflow: dict,
    now_str: str,
    issue_titles: dict,
    issue_statuses: dict,
) -> str:
    title_text = f"#{issue.id} — {_esc(issue.title)}"
    project_label = _esc(project_name) if project_name else "local"

    sorted_ids = sorted(issue_titles.keys())
    pos = sorted_ids.index(issue.id) if issue.id in sorted_ids else -1
    prev_id = sorted_ids[pos - 1] if pos > 0 else None
    next_id_ = sorted_ids[pos + 1] if 0 <= pos < len(sorted_ids) - 1 else None

    nav_prev = (
        f'<a class="nav-btn" href="{prev_id}.html">← #{prev_id}</a>'
        if prev_id else '<span class="nav-btn disabled">← prev</span>'
    )
    nav_next = (
        f'<a class="nav-btn" href="{next_id_}.html">#{next_id_} →</a>'
        if next_id_ else '<span class="nav-btn disabled">next →</span>'
    )

    state_cls = f"state-{_esc(issue.status)}"
    state_label = issue.status.capitalize()

    labels_html = (
        " ".join(f'<span class="tag">{_esc(l)}</span>' for l in issue.labels)
        if issue.labels else '<span class="muted">—</span>'
    )

    meta_rows = [
        ("Assignee", _esc(issue.assignee or "—")),
        ("Milestone", _esc(issue.milestone or "—")),
        ("Type", _esc(issue.type)),
        ("Priority", _esc(issue.priority).upper() if issue.priority != "none" else "—"),
        ("Labels", labels_html),
        ("Created", _esc(issue.created_at or "—")),
        ("Updated", _esc(issue.updated_at or "—")),
    ]
    meta_html = "".join(
        f'<div class="m-row"><dt>{k}</dt><dd>{v}</dd></div>' for k, v in meta_rows
    )

    body_rendered = render_markdown(issue.body) if issue.body and issue.body.strip() else ""

    if issue.links:
        link_items = []
        for l in issue.links:
            tgt = l.get("target")
            ltype = l.get("type", "")
            ttitle = issue_titles.get(tgt, "")
            tstatus = issue_statuses.get(tgt, "")
            cls = " done" if tstatus == "closed" else ""
            label = f"#{tgt} {ttitle}" if ttitle else f"#{tgt}"
            link_items.append(
                f'<li class="link-li{cls}">'
                f'<span class="link-type">{_esc(ltype)}</span>'
                f'<a href="{tgt}.html">{_esc(label)}</a></li>'
            )
        links_html = (
            '<section class="aside-block"><h3>Linked issues</h3>'
            '<ul class="link-list">' + "".join(link_items) + '</ul></section>'
        )
    else:
        links_html = ""

    if issue.docs:
        docs_html = (
            '<section class="aside-block"><h3>Docs</h3>'
            '<ul class="link-list">'
            + "".join(f'<li>{_esc(d)}</li>' for d in issue.docs)
            + '</ul></section>'
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
        f'<li><code class="cmd" onclick="copyCmd(this)">{_esc(c)}</code></li>'
        for c in cmds
    )

    body_block = (
        f'<div id="md-body" class="md-body">{body_rendered}</div>'
        if body_rendered
        else '<div id="md-body" class="md-body empty">No description.</div>'
    )

    head = _page_head(title_text, "../assets/style.css")
    return f"""{head}
<body class="issue-page">
<div class="page">

<header class="topbar">
<a class="crumb" href="../index.html">← Dashboard</a>
<span class="sep">/</span>
<span class="proj">{project_label}</span>
<span class="sep">/</span>
<span class="here">issue {issue.id}</span>
<span class="spacer"></span>
<nav class="topnav">{nav_prev}{nav_next}</nav>
</header>

<article class="issue">

<header class="issue-head">
<h1 class="issue-title">{_esc(issue.title)} <span class="issue-num">#{issue.id}</span></h1>
<div class="issue-sub">
<span class="state-badge {state_cls}">{state_label}</span>
<span class="muted">opened {_esc(_short_date(issue.created_at))}{(" · updated " + _esc(_short_date(issue.updated_at))) if issue.updated_at and issue.updated_at != issue.created_at else ""}</span>
</div>
</header>

<dl class="meta-grid">{meta_html}</dl>

<section class="body-section">
<h3 class="section-label">Description</h3>
{body_block}
</section>

{links_html}
{docs_html}

<section class="aside-block">
<h3>Quick commands <span class="muted">· click to copy</span></h3>
<ul class="cmd-list">{cmd_html}</ul>
</section>

</article>

<footer class="colophon">Snapshot {_esc(now_str)} · <a href="../index.html">back to dashboard</a></footer>

</div>

<script>
function copyCmd(el){{
  navigator.clipboard.writeText(el.textContent.trim());
  var orig=el.textContent;
  el.textContent='✓ copied';
  el.classList.add('copied');
  setTimeout(function(){{el.textContent=orig;el.classList.remove('copied')}},1400);
}}
document.addEventListener('keydown',function(e){{
  if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;
  var nav=document.querySelectorAll('.topnav .nav-btn');
  if(e.key==='ArrowLeft'){{nav.forEach(function(n){{if(n.tagName==='A'&&n.textContent.indexOf('←')!==-1)location.href=n.getAttribute('href')}})}}
  if(e.key==='ArrowRight'){{nav.forEach(function(n){{if(n.tagName==='A'&&n.textContent.indexOf('→')!==-1)location.href=n.getAttribute('href')}})}}
  if(e.key==='Escape')location.href='../index.html';
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------- stylesheet

_STYLESHEET = """*{box-sizing:border-box}
:root{
  --bg:#ffffff;
  --bg-subtle:#f6f8fa;
  --bg-muted:#eaeef2;
  --border:#d1d9e0;
  --border-muted:#d1d9e0b3;
  --fg:#1f2328;
  --fg-muted:#59636e;
  --accent:#0969da;
  --accent-bg:#ddf4ff;
  --open:#1a7f37;
  --open-bg:#dafbe1;
  --closed:#8250df;
  --closed-bg:#fbefff;
  --danger:#cf222e;
  --warn:#9a6700;
  --radius:6px;
  --radius-sm:4px;
}
html,body{margin:0;padding:0;background:var(--bg);color:var(--fg)}
body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif,"Apple Color Emoji","Segoe UI Emoji";
  font-size:17px;line-height:1.55;-webkit-font-smoothing:antialiased;
  padding:0;
}
.page{max-width:1280px;margin:0 auto;padding:28px 40px 80px}
.issue-page .page{max-width:1100px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
code,kbd,.mono{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;font-size:.85em}
.muted{color:var(--fg-muted)}
h1,h2,h3,h4{margin:0;font-weight:600;line-height:1.25}

/* ======== Index ======== */
.masthead{padding:8px 0 16px;border-bottom:1px solid var(--border);margin-bottom:20px}
.masthead .brand{font-size:28px;font-weight:600;color:var(--fg);letter-spacing:-.01em}
.masthead .byline{margin-top:6px;font-size:12px;color:var(--fg-muted)}
.masthead .byline code{background:var(--bg-subtle);border:1px solid var(--border);border-radius:var(--radius-sm);padding:1px 5px;color:var(--fg)}

section{margin:24px 0}
section h2{font-size:18px;font-weight:600;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid var(--border-muted)}

/* Stats */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:0;padding:0}
.stats .stat{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px}
.stats dt{font-size:12px;color:var(--fg-muted);font-weight:500;margin:0}
.stats dd{font-size:28px;font-weight:600;color:var(--fg);margin:2px 0 0;line-height:1.2}
@media (max-width:680px){.stats{grid-template-columns:repeat(2,1fr)}}

/* Composition */
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:24px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:16px}
@media (max-width:680px){.two-col{grid-template-columns:1fr;gap:16px}}
.block h3{font-size:12px;font-weight:600;color:var(--fg-muted);text-transform:uppercase;letter-spacing:.04em;margin:0 0 8px}
.count-row{display:grid;grid-template-columns:90px 1fr 32px;gap:10px;align-items:center;padding:3px 0;font-size:13px}
.count-name{color:var(--fg)}
.count-bar{height:8px;background:var(--bg-muted);border-radius:999px;overflow:hidden;position:relative}
.count-bar-fill{display:block;height:100%;background:var(--accent);border-radius:999px}
.count-num{text-align:right;color:var(--fg-muted);font-variant-numeric:tabular-nums;font-size:12px}

/* Milestones */
.milestones{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:4px 12px}
.ms-details{padding:10px 0;border-bottom:1px solid var(--border-muted)}
.ms-details:last-child{border-bottom:none}
.ms-details summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:auto 1fr 200px auto;gap:12px;align-items:center;padding:2px 0}
.ms-details summary::-webkit-details-marker{display:none}
.ms-details summary::before{content:"▸";display:inline-block;width:10px;color:var(--fg-muted);font-size:10px;transition:transform .1s}
.ms-details[open] summary::before{content:"▾"}
.ms-name{font-weight:600;color:var(--fg)}
.ms-progress{height:8px;background:var(--bg-muted);border-radius:999px;overflow:hidden;position:relative}
.ms-progress-fill{display:block;height:100%;background:var(--open);border-radius:999px}
.ms-stats{font-size:12px;color:var(--fg-muted);text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
@media (max-width:680px){.ms-details summary{grid-template-columns:auto 1fr;row-gap:4px}.ms-progress,.ms-stats{grid-column:2}}
.ms-children{list-style:none;margin:8px 0 0;padding:0 0 0 18px;border-left:2px solid var(--bg-muted)}
.ms-children li{padding:3px 0;font-size:13px}
.ms-children a{color:var(--fg);text-decoration:none}
.ms-children a:hover{color:var(--accent);text-decoration:underline}
.ms-children .num{color:var(--fg-muted);margin-right:4px;font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;font-size:.85em}
.ms-children li.done a{text-decoration:line-through;color:var(--fg-muted)}

/* Filter bar */
.filter-bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.filter-bar input,.filter-bar select{
  font:inherit;font-size:13px;color:var(--fg);background:var(--bg);
  border:1px solid var(--border);border-radius:var(--radius);
  padding:5px 10px;outline:none;transition:border-color .1s,box-shadow .1s;
}
.filter-bar input:focus,.filter-bar select:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-bg)}
.filter-bar input{flex:1;min-width:200px}
.filter-bar select{min-width:130px;cursor:pointer}

/* Open issue groups */
.open-issues{display:flex;flex-direction:column;gap:18px}
.prio-group h4.prio-label{font-size:12px;font-weight:600;color:var(--fg-muted);text-transform:uppercase;letter-spacing:.05em;margin:0 0 6px;padding:0 4px}
.prio-label.prio-p0{color:var(--danger)}
.prio-label.prio-p1{color:var(--warn)}
.prio-label.prio-p2{color:var(--accent)}
.prio-label.prio-p3,.prio-label.prio-none{color:var(--fg-muted)}

.issue-list{list-style:none;margin:0;padding:0;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius)}
.issue-list li{border-bottom:1px solid var(--border-muted)}
.issue-list li:last-child{border-bottom:none}
.row{
  display:grid;grid-template-columns:14px 56px 1fr 110px 110px 100px;
  gap:12px;align-items:center;padding:8px 14px;color:var(--fg);text-decoration:none;
}
.row:hover{background:var(--bg-subtle);text-decoration:none}
.status-dot{display:inline-block;width:10px;height:10px;border-radius:50%}
.status-dot.status-open{background:var(--open)}
.status-dot.status-closed{background:var(--closed)}
.row .num{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;color:var(--fg-muted);font-size:12px;font-variant-numeric:tabular-nums}
.row .title{font-size:14px;font-weight:500}
.row .meta-cell{font-size:12px;color:var(--fg-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tag{
  display:inline-block;background:var(--bg-subtle);color:var(--fg);
  border:1px solid var(--border);border-radius:999px;
  padding:0 8px;font-size:11px;font-weight:500;line-height:18px;margin-left:4px;
}
.closed-list .row{grid-template-columns:14px 56px 1fr 110px 100px}
@media (max-width:680px){
  .row{grid-template-columns:14px 1fr;row-gap:2px}
  .row .num{display:none}
  .row .meta-cell{grid-column:2;display:inline}
  .row .meta-cell.when{display:none}
}

/* Footer */
.colophon{margin-top:32px;padding-top:14px;border-top:1px solid var(--border-muted);font-size:12px;color:var(--fg-muted);text-align:center}

/* ======== Issue page ======== */
.topbar{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--fg-muted);padding:4px 0 14px;border-bottom:1px solid var(--border);margin-bottom:18px;flex-wrap:wrap}
.topbar .crumb{color:var(--accent);text-decoration:none;font-weight:500}
.topbar .crumb:hover{text-decoration:underline}
.topbar .sep{color:var(--border)}
.topbar .proj{color:var(--fg)}
.topbar .here{color:var(--fg-muted)}
.topbar .spacer{flex:1}
.topnav{display:flex;gap:6px}
.nav-btn{
  font-size:12px;padding:4px 10px;border:1px solid var(--border);
  border-radius:var(--radius);text-decoration:none;color:var(--fg);background:var(--bg);
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
}
.nav-btn:hover{background:var(--bg-subtle);text-decoration:none;border-color:var(--fg-muted)}
.nav-btn.disabled{opacity:.4;cursor:not-allowed;background:var(--bg-subtle)}

.issue-head{margin-bottom:18px}
.issue-title{font-size:28px;font-weight:600;color:var(--fg);line-height:1.3}
.issue-title .issue-num{color:var(--fg-muted);font-weight:400}
.issue-sub{margin-top:8px;display:flex;align-items:center;gap:10px;font-size:13px;flex-wrap:wrap}
.state-badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:500;padding:3px 10px;border-radius:999px;border:1px solid transparent}
.state-badge::before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;background:currentColor}
.state-badge.state-open{background:var(--open-bg);color:var(--open);border-color:transparent}
.state-badge.state-closed{background:var(--closed-bg);color:var(--closed)}

.meta-grid{
  display:grid;grid-template-columns:repeat(2,1fr);gap:0;margin:0 0 20px;
  background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;
}
.m-row{display:flex;gap:12px;padding:8px 14px;font-size:13px;border-bottom:1px solid var(--border-muted)}
.m-row:nth-last-child(-n+2){border-bottom:none}
.m-row dt{flex:0 0 96px;color:var(--fg-muted);font-weight:500}
.m-row dd{flex:1;color:var(--fg);margin:0}
@media (max-width:680px){.meta-grid{grid-template-columns:1fr}.m-row:nth-last-child(-n+2){border-bottom:1px solid var(--border-muted)}.m-row:last-child{border-bottom:none}}

.section-label{font-size:12px;font-weight:600;color:var(--fg-muted);text-transform:uppercase;letter-spacing:.05em;margin:24px 0 10px}

.body-section{margin-bottom:18px}
.md-body{
  font-size:16px;line-height:1.65;color:var(--fg);
  background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);
  padding:18px 22px;
}
.md-body.empty{color:var(--fg-muted);font-style:italic;background:var(--bg-subtle)}
.md-body > *:first-child{margin-top:0}
.md-body > *:last-child{margin-bottom:0}
.md-body h1,.md-body h2,.md-body h3,.md-body h4{font-weight:600;color:var(--fg);margin:24px 0 12px;line-height:1.25}
.md-body h1{font-size:1.7em;border-bottom:1px solid var(--border-muted);padding-bottom:.3em}
.md-body h2{font-size:1.4em;border-bottom:1px solid var(--border-muted);padding-bottom:.25em}
.md-body h3{font-size:1.2em}
.md-body h4{font-size:1em}
.md-body p{margin:0 0 14px}
.md-body ul,.md-body ol{margin:0 0 14px;padding-left:24px}
.md-body li{margin:4px 0}
.md-body blockquote{margin:0 0 14px;padding:0 14px;border-left:3px solid var(--border);color:var(--fg-muted)}
.md-body code{
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:85%;background:var(--bg-muted);padding:.2em .4em;border-radius:var(--radius-sm);
}
.md-body pre{
  background:var(--bg-subtle);border:1px solid var(--border);
  border-radius:var(--radius);padding:12px 14px;overflow-x:auto;margin:0 0 14px;
}
.md-body pre code{background:none;padding:0;font-size:85%}
.md-body a{color:var(--accent)}
.md-body a:hover{text-decoration:underline}
.md-body table{border-collapse:collapse;margin:0 0 14px;display:block;overflow-x:auto}
.md-body th,.md-body td{border:1px solid var(--border);padding:6px 12px;font-size:13px}
.md-body th{background:var(--bg-subtle);font-weight:600;text-align:left}
.md-body img{max-width:100%}
.md-body hr{border:none;border-top:1px solid var(--border);margin:18px 0}

.aside-block{margin:24px 0}
.aside-block h3{font-size:12px;font-weight:600;color:var(--fg-muted);text-transform:uppercase;letter-spacing:.05em;margin:0 0 8px}
.link-list{list-style:none;margin:0;padding:0;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
.link-list li{padding:8px 14px;font-size:13px;border-bottom:1px solid var(--border-muted);display:flex;align-items:center;gap:10px}
.link-list li:last-child{border-bottom:none}
.link-list a{color:var(--accent);text-decoration:none}
.link-list a:hover{text-decoration:underline}
.link-list .link-type{display:inline-block;min-width:84px;color:var(--fg-muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em;font-weight:600}
.link-list .done a{text-decoration:line-through;color:var(--fg-muted)}

.cmd-list{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:6px}
@media (max-width:680px){.cmd-list{grid-template-columns:1fr}}
.cmd{
  display:block;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;
  background:var(--bg-subtle);border:1px solid var(--border);border-radius:var(--radius);
  padding:6px 10px;cursor:pointer;color:var(--fg);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:background .1s;
}
.cmd::before{content:"$ ";color:var(--fg-muted)}
.cmd:hover{background:var(--bg-muted);border-color:var(--fg-muted)}
.cmd.copied{background:var(--open-bg);border-color:var(--open);color:var(--open)}
.cmd.copied::before{color:var(--open)}
"""
