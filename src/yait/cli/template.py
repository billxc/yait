from __future__ import annotations

import click
import yaml

from ..lock import YaitLock
from ..models import Template
from ..store import save_template, load_template, list_templates, delete_template
from . import main, _resolve, _require_init, _commit


@main.group()
def template():
    """Manage issue templates."""


@template.command(name="create")
@click.argument("name")
@click.pass_context
def template_create(ctx, name):
    """Create or edit an issue template.

    \b
    Opens $EDITOR to define template frontmatter and body.

    \b
    Examples:
      yait template create bug
      yait template create feature
    """
    root = _resolve(ctx)
    _require_init(root)
    try:
        existing = load_template(root, name)
        fm = {
            "name": existing.name,
            "type": existing.type,
            "priority": existing.priority,
            "labels": existing.labels,
        }
        initial = "---\n" + yaml.dump(fm, default_flow_style=False).rstrip("\n") + "\n---\n"
        if existing.body:
            initial += "\n" + existing.body + "\n"
    except FileNotFoundError:
        fm = {
            "name": name,
            "type": "misc",
            "priority": "none",
            "labels": [],
        }
        initial = "---\n" + yaml.dump(fm, default_flow_style=False).rstrip("\n") + "\n---\n"
        initial += "\n"

    result = click.edit(initial)
    if result is None:
        click.echo("Aborted: editor returned empty.")
        return

    text = result.strip()
    if not text.startswith("---"):
        raise click.ClickException("Invalid template: missing YAML frontmatter (---).")

    try:
        end_idx = text.index("---", 3)
    except ValueError:
        raise click.ClickException("Invalid template: missing closing --- delimiter.")
    fm_text = text[3:end_idx].strip()
    body = text[end_idx + 3:].strip()
    fm = yaml.safe_load(fm_text) or {}

    tmpl = Template(
        name=fm.get("name", name),
        type=fm.get("type", "misc"),
        priority=fm.get("priority", "none"),
        labels=fm.get("labels") or [],
        body=body,
    )
    with YaitLock(root, "template create"):
        save_template(root, tmpl)
        click.echo(f"Saved template '{tmpl.name}'")
        _commit(ctx, root, f"yait: save template '{tmpl.name}'")


@template.command(name="list")
@click.pass_context
def template_list(ctx):
    """List available templates.

    \b
    Examples:
      yait template list
    """
    root = _resolve(ctx)
    _require_init(root)
    templates = list_templates(root)
    if not templates:
        click.echo("No templates found.")
        return
    header = f"{'NAME':<16}  {'TYPE':<12}  {'PRIORITY':<8}  LABELS"
    click.echo(click.style(header, bold=True))
    for t in templates:
        labels = ",".join(t.labels) if t.labels else "\u2014"
        click.echo(f"{t.name:<16}  {t.type:<12}  {t.priority:<8}  {labels}")


@template.command(name="delete")
@click.argument("name")
@click.pass_context
def template_delete(ctx, name):
    """Delete a template.

    \b
    Examples:
      yait template delete bug
    """
    root = _resolve(ctx)
    _require_init(root)
    with YaitLock(root, "template delete"):
        try:
            delete_template(root, name)
        except FileNotFoundError as e:
            raise click.ClickException(str(e))
        click.echo(f"Deleted template '{name}'")
        _commit(ctx, root, f"yait: delete template '{name}'")
