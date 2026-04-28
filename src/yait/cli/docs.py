from __future__ import annotations

import json

import click

from ..lock import YaitLock
from ..models import _SLUG_RE
from ..store import (
    list_issues, save_issue, save_doc, load_doc, list_docs, delete_doc, _docs_dir,
)
from . import main, _resolve, _require_init, _commit, _now, _load_or_exit, _read_body


@main.group()
def doc():
    """Manage documents linked to issues."""


@doc.command(name="create")
@click.argument("slug")
@click.option("--title", "-T", required=True, help="Document title")
@click.option("--body", "-b", default=None, help="Document body text")
@click.option("--body-file", default=None, help="Read body from file")
@click.pass_context
def doc_create(ctx, slug, title, body, body_file):
    """Create a managed document.

    \b
    Examples:
      yait doc create auth-prd --title "Auth PRD"
      yait doc create auth-prd --title "Auth PRD" -b "## Overview"
      yait doc create auth-prd --title "Auth PRD" --body-file draft.md
    """
    from ..models import Doc
    root = _resolve(ctx)
    _require_init(root)
    if "/" in slug:
        raise click.ClickException("Doc slug cannot contain '/'. Use a simple name like 'auth-prd'.")
    if not _SLUG_RE.match(slug):
        raise click.ClickException(f"Invalid slug: {slug!r}. Use letters, digits, hyphens, underscores.")
    if (_docs_dir(root) / f"{slug}.md").exists():
        raise click.ClickException(f"Doc '{slug}' already exists.")
    resolved_body = _read_body(body, body_file)
    if body is None and body_file is None:
        resolved_body = click.edit("") or ""
        resolved_body = resolved_body.strip()
    with YaitLock(root, "doc create"):
        now = _now()
        d = Doc(slug=slug, title=title, created_at=now, updated_at=now, body=resolved_body)
        save_doc(root, d)
        click.echo(f"Created doc '{slug}': {title}")
        _commit(ctx, root, f"yait: create doc '{slug}'")


@doc.command(name="show")
@click.argument("slug")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
def doc_show(ctx, slug, as_json):
    """Show a managed document.

    \b
    Examples:
      yait doc show auth-prd
      yait doc show auth-prd --json
    """
    root = _resolve(ctx)
    _require_init(root)
    if "/" in slug:
        raise click.ClickException(f"'{slug}' is an external reference, not a managed doc. View it directly.")
    try:
        d = load_doc(root, slug)
    except FileNotFoundError:
        raise click.ClickException(f"Doc '{slug}' not found.")
    if as_json:
        data = d.to_dict()
        all_issues = list_issues(root, status=None)
        data["linked_issues"] = [i.id for i in all_issues if slug in i.docs]
        click.echo(json.dumps(data, indent=2))
        return
    click.echo(f"{d.slug}: {d.title}")
    click.echo(f"Created: {d.created_at}")
    click.echo(f"Updated: {d.updated_at}")
    all_issues = list_issues(root, status=None)
    linked = [i for i in all_issues if slug in i.docs]
    if linked:
        parts = [f"#{i.id} ({i.status})" for i in linked]
        click.echo(f"Linked issues: {', '.join(parts)}")
    if d.body:
        click.echo(f"\n{d.body}")


@doc.command(name="list")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
def doc_list(ctx, as_json):
    """List all managed documents.

    \b
    Examples:
      yait doc list
      yait doc list --json
    """
    root = _resolve(ctx)
    _require_init(root)
    docs = list_docs(root)
    if as_json:
        all_issues = list_issues(root, status=None)
        data = []
        for d in docs:
            dd = d.to_dict()
            dd["linked_issues"] = [i.id for i in all_issues if d.slug in i.docs]
            data.append(dd)
        click.echo(json.dumps(data, indent=2))
        return
    if not docs:
        click.echo("No documents found.")
        return
    all_issues = list_issues(root, status=None)
    header = f"{'SLUG':<20}  {'TITLE':<24}  {'UPDATED':<20}  ISSUES"
    click.echo(click.style(header, bold=True))
    for d in docs:
        linked = [i for i in all_issues if d.slug in i.docs]
        issues_str = ", ".join(f"#{i.id}" for i in linked) if linked else "\u2014"
        updated = d.updated_at[:16] if d.updated_at else "\u2014"
        click.echo(f"{d.slug:<20}  {d.title:<24}  {updated:<20}  {issues_str}")


@doc.command(name="edit")
@click.argument("slug")
@click.option("--title", "-T", "new_title", default=None, help="New title")
@click.option("--body", "-b", "new_body", default=None, help="New body text")
@click.pass_context
def doc_edit(ctx, slug, new_title, new_body):
    """Edit a managed document.

    \b
    Examples:
      yait doc edit auth-prd
      yait doc edit auth-prd --title "New Title"
      yait doc edit auth-prd -b "New content"
    """
    root = _resolve(ctx)
    _require_init(root)
    try:
        d = load_doc(root, slug)
    except FileNotFoundError:
        raise click.ClickException(f"Doc '{slug}' not found.")
    if new_title is not None or new_body is not None:
        with YaitLock(root, "doc edit"):
            if new_title is not None:
                d.title = new_title
            if new_body is not None:
                d.body = new_body
            d.updated_at = _now()
            save_doc(root, d)
            click.echo(f"Updated doc '{slug}'")
            _commit(ctx, root, f"yait: edit doc '{slug}'")
    else:
        result = click.edit(d.body)
        if result is None:
            click.echo("Edit cancelled.")
            return
        d.body = result.strip()
        with YaitLock(root, "doc edit"):
            d.updated_at = _now()
            save_doc(root, d)
            click.echo(f"Updated doc '{slug}'")
            _commit(ctx, root, f"yait: edit doc '{slug}'")


@doc.command(name="delete")
@click.argument("slug")
@click.option("--force", "-f", is_flag=True, default=False, help="Skip confirmation")
@click.pass_context
def doc_delete(ctx, slug, force):
    """Delete a managed document.

    \b
    Examples:
      yait doc delete auth-prd
      yait doc delete auth-prd -f
    """
    root = _resolve(ctx)
    _require_init(root)
    try:
        d = load_doc(root, slug)
    except FileNotFoundError:
        raise click.ClickException(f"Doc '{slug}' not found.")
    all_issues = list_issues(root, status=None)
    linked = [i for i in all_issues if slug in i.docs]
    if linked and not force:
        ids_str = ", ".join(f"#{i.id}" for i in linked)
        click.echo(f"Warning: {slug} is linked to {len(linked)} issues ({ids_str}).")
        click.echo("Delete will remove the document but NOT the references.")
        click.echo("Use 'yait doc unlink' to clean up first.")
        click.confirm("Are you sure?", abort=True)
    with YaitLock(root, "doc delete"):
        delete_doc(root, slug)
        click.echo(f"Deleted doc '{slug}'")
        _commit(ctx, root, f"yait: delete doc '{slug}'")


@doc.command(name="link")
@click.argument("args", nargs=-1, required=True)
@click.pass_context
def doc_link(ctx, args):
    """Link a document to one or more issues.

    \b
    Last argument is the doc slug/path, preceding arguments are issue IDs.

    \b
    Examples:
      yait doc link 1 auth-prd
      yait doc link 1 docs/arch.md
      yait doc link 1 2 3 auth-prd
    """
    root = _resolve(ctx)
    _require_init(root)
    if len(args) < 2:
        raise click.ClickException("Usage: yait doc link <id> [id...] <doc>")
    doc_ref = args[-1]
    issue_ids = []
    for a in args[:-1]:
        try:
            issue_ids.append(int(a))
        except ValueError:
            raise click.ClickException(f"Invalid issue ID: {a!r}")
    linked_ids = []
    with YaitLock(root, "doc link"):
        for iid in issue_ids:
            issue = _load_or_exit(root, iid)
            if doc_ref in issue.docs:
                click.echo(f"Issue #{iid} already linked to '{doc_ref}'.")
                continue
            issue.docs.append(doc_ref)
            issue.updated_at = _now()
            save_issue(root, issue)
            linked_ids.append(iid)
        if linked_ids:
            if len(linked_ids) == 1:
                click.echo(f"Linked doc '{doc_ref}' to issue #{linked_ids[0]}")
            else:
                ids_str = ", ".join(f"#{i}" for i in linked_ids)
                click.echo(f"Linked doc '{doc_ref}' to issues {ids_str}")
            _commit(ctx, root, f"yait: link doc '{doc_ref}' to #{', #'.join(str(i) for i in linked_ids)}")


@doc.command(name="unlink")
@click.argument("id", type=int)
@click.argument("doc_ref")
@click.pass_context
def doc_unlink(ctx, id, doc_ref):
    """Unlink a document from an issue.

    \b
    Examples:
      yait doc unlink 1 auth-prd
    """
    root = _resolve(ctx)
    _require_init(root)
    issue = _load_or_exit(root, id)
    if doc_ref not in issue.docs:
        click.echo(f"Issue #{id} is not linked to '{doc_ref}'.")
        return
    with YaitLock(root, "doc unlink"):
        issue.docs.remove(doc_ref)
        issue.updated_at = _now()
        save_issue(root, issue)
        click.echo(f"Unlinked doc '{doc_ref}' from issue #{id}")
        _commit(ctx, root, f"yait: unlink doc '{doc_ref}' from #{id}")
