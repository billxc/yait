from __future__ import annotations

import click

from ..lock import YaitLock
from ..store import save_issue
from . import main, _resolve, _require_init, _commit, _now, _load_or_exit


@main.group()
def label():
    """Manage issue labels."""


@label.command(name="add")
@click.argument("id", type=int)
@click.argument("name")
@click.pass_context
def label_add(ctx, id, name):
    """Add a label to an issue."""
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)
    if name in issue.labels:
        click.echo(f"Issue #{id} already has label '{name}'.")
        return
    with YaitLock(root, "label add"):
        issue.labels.append(name)
        issue.updated_at = _now()
        save_issue(root, issue)
        click.echo(f"Added label '{name}' to issue #{id}")
        _commit(ctx, root, f"yait: label #{id} +{name}")


@label.command(name="remove")
@click.argument("id", type=int)
@click.argument("name")
@click.pass_context
def label_remove(ctx, id, name):
    """Remove a label from an issue."""
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)
    if name not in issue.labels:
        click.echo(f"Issue #{id} does not have label '{name}'.")
        return
    with YaitLock(root, "label remove"):
        issue.labels.remove(name)
        issue.updated_at = _now()
        save_issue(root, issue)
        click.echo(f"Removed label '{name}' from issue #{id}")
        _commit(ctx, root, f"yait: label #{id} -{name}")
