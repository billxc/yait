from __future__ import annotations

import json
import os

import click

from ..store import list_issues, get_workflow
from . import main, _resolve, _require_init


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def board(ctx, as_json):
    """Show kanban board view.

    \b
    Displays issues grouped by workflow status columns.

    \b
    Examples:
      yait board
      yait board --json
    """
    from ..board import render_board

    root = _resolve(ctx)
    _require_init(root)
    wf = get_workflow(root)
    issues = list_issues(root, status=None)
    if as_json:
        grouped = {}
        for s in wf["statuses"]:
            grouped[s] = [
                i.to_dict() for i in issues if i.status == s
            ]
        click.echo(json.dumps(grouped, indent=2))
    else:
        try:
            width = os.get_terminal_size().columns
        except (ValueError, OSError):
            width = 80
        click.echo(render_board(issues, wf, width))
