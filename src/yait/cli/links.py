from __future__ import annotations

import click

from ..lock import YaitLock
from ..store import add_link, remove_link, load_issue
from . import main, _resolve, _require_init, _commit, _load_or_exit


_USER_LINK_TYPES = ("blocks", "depends-on", "relates-to")


@main.command(name="link")
@click.argument("source_id", type=int)
@click.argument("link_type", type=click.Choice(_USER_LINK_TYPES))
@click.argument("target_id", type=int)
@click.pass_context
def link_cmd(ctx, source_id, link_type, target_id):
    """Add a link between two issues.

    \b
    Examples:
      yait link 3 blocks 5          # issue #3 blocks issue #5
      yait link 3 relates-to 7      # issue #3 relates to #7
      yait link 3 depends-on 1      # issue #3 depends on #1
    """
    root = _resolve(ctx)
    _require_init(root)
    with YaitLock(root, "link"):
        try:
            add_link(root, source_id, link_type, target_id)
        except FileNotFoundError as e:
            raise click.ClickException(str(e))
        except ValueError as e:
            raise click.ClickException(str(e))
        click.echo(f"Linked #{source_id} {link_type} #{target_id}")
        _commit(ctx, root, f"yait: link #{source_id} {link_type} #{target_id}")


@main.command(name="unlink")
@click.argument("source_id", type=int)
@click.argument("target_id", type=int)
@click.pass_context
def unlink_cmd(ctx, source_id, target_id):
    """Remove all links between two issues.

    \b
    Examples:
      yait unlink 3 5
    """
    root = _resolve(ctx)
    _require_init(root)
    source = _load_or_exit(root, source_id)
    target = _load_or_exit(root, target_id)
    had_link = any(l.get("target") == target_id for l in source.links)
    if not had_link:
        click.echo(f"No link between #{source_id} and #{target_id}.")
        return
    with YaitLock(root, "unlink"):
        remove_link(root, source_id, target_id)
        click.echo(f"Unlinked #{source_id} and #{target_id}")
        _commit(ctx, root, f"yait: unlink #{source_id} and #{target_id}")
