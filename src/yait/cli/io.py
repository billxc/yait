from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import click

from ..git_ops import git_log
from ..lock import YaitLock
from ..models import Issue
from ..store import list_issues, save_issue
from . import main, _resolve, _require_init, _commit


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
                docs=item.get("docs") or [],
                links=item.get("links") or [],
            )
            save_issue(root, issue)
            imported += 1

        if imported > 0:
            from ..store import ensure_next_id_above
            all_issues = list_issues(root, status=None)
            max_id = max(i.id for i in all_issues)
            ensure_next_id_above(root, max_id + 1)
            _commit(ctx, root, f"yait: import {imported} issues")

        click.echo(f"Imported {imported} issues, skipped {skipped}.")


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
