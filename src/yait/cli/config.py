from __future__ import annotations

import click

from ..lock import YaitLock
from ..store import (
    get_defaults, get_display, get_workflow,
    set_config_value, reset_config_value,
    _read_config, _write_config,
    _DEFAULT_DEFAULTS, _DEFAULT_DISPLAY,
)
from . import main, _resolve, _require_init


@main.group(invoke_without_command=True)
@click.pass_context
def config(ctx):
    """View or modify yait configuration.

    \b
    Examples:
      yait config                         # show all config
      yait config set defaults.type bug   # set a value
      yait config reset defaults.type     # reset to default
    """
    if ctx.invoked_subcommand is not None:
        return
    root = _resolve(ctx)
    _require_init(root)
    defaults = get_defaults(root)
    display = get_display(root)
    workflow = get_workflow(root)
    click.echo(click.style("defaults:", bold=True))
    for k, v in sorted(defaults.items()):
        default_marker = ""
        if k in _DEFAULT_DEFAULTS and defaults[k] == _DEFAULT_DEFAULTS[k]:
            default_marker = " (default)"
        click.echo(f"  {k}: {_format_config_value(v)}{default_marker}")
    click.echo(click.style("display:", bold=True))
    for k, v in sorted(display.items()):
        default_marker = ""
        if k in _DEFAULT_DISPLAY and display[k] == _DEFAULT_DISPLAY[k]:
            default_marker = " (default)"
        click.echo(f"  {k}: {_format_config_value(v)}{default_marker}")
    click.echo(click.style("workflow:", bold=True))
    for k, v in sorted(workflow.items()):
        click.echo(f"  {k}: {_format_config_value(v)}")


def _format_config_value(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, list):
        return ", ".join(v) if v else "[]"
    return str(v)


@config.command(name="set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx, key, value):
    """Set a configuration value.

    \b
    Examples:
      yait config set defaults.type bug
      yait config set defaults.priority p2
      yait config set defaults.assignee alice
      yait config set defaults.labels urgent,frontend
      yait config set display.max_title_width 60
      yait config set display.date_format full
      yait config set workflow.statuses backlog,ready,in-progress,done,closed
      yait config set workflow.closed_statuses closed,done
    """
    root = _resolve(ctx)
    _require_init(root)
    with YaitLock(root, "config set"):
        if key.startswith("workflow."):
            field = key.split(".", 1)[1]
            if field not in ("statuses", "closed_statuses"):
                raise click.ClickException(f"Unknown config key: {key!r}")
            converted = [v.strip() for v in value.split(",") if v.strip()]
            cfg = _read_config(root)
            if "workflow" not in cfg:
                cfg["workflow"] = {}
            cfg["workflow"][field] = converted
            _write_config(root, cfg)
        else:
            try:
                set_config_value(root, key, value)
            except (KeyError, ValueError) as e:
                raise click.ClickException(str(e))
        click.echo(f"Set {key} = {value}")


@config.command(name="reset")
@click.argument("key")
@click.pass_context
def config_reset(ctx, key):
    """Reset a configuration value to its default.

    \b
    Examples:
      yait config reset defaults.type
      yait config reset display.max_title_width
    """
    root = _resolve(ctx)
    _require_init(root)
    with YaitLock(root, "config reset"):
        try:
            reset_config_value(root, key)
        except KeyError as e:
            raise click.ClickException(str(e))
        click.echo(f"Reset {key} to default")
