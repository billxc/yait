from __future__ import annotations

import json
import shutil
from pathlib import Path

import click

from ..git_ops import git_commit
from ..store import is_initialized, list_issues, get_workflow
from . import main, _yait_home, _validate_project_name, _project_create


@main.group()
def project():
    """Manage named projects."""


@project.command(name="create")
@click.argument("name")
def project_create(name):
    """Create a new named project.

    \b
    Examples:
      yait project create myapp
    """
    project_dir = _project_create(name)
    click.echo(f"Created project '{name}' at {project_dir}/")


@project.command(name="list")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def project_list(as_json):
    """List all named projects.

    \b
    Examples:
      yait project list
      yait project list --json
    """
    home = _yait_home()
    projects_dir = home / "projects"
    if not projects_dir.exists():
        if as_json:
            click.echo("[]")
        else:
            click.echo("No projects found. Create one with: yait project create <name>")
        return

    entries = []
    for p in sorted(projects_dir.iterdir()):
        if not p.is_dir() or not is_initialized(p):
            continue
        all_issues = list_issues(p, status=None)
        wf = get_workflow(p)
        closed_set = set(wf["closed_statuses"])
        closed_c = sum(1 for i in all_issues if i.status in closed_set)
        open_c = len(all_issues) - closed_c
        updated = ""
        if all_issues:
            updated = max(i.updated_at for i in all_issues)[:10]
        entries.append({
            "name": p.name,
            "open": open_c,
            "closed": closed_c,
            "updated": updated,
        })

    if as_json:
        click.echo(json.dumps(entries, indent=2))
        return

    if not entries:
        click.echo("No projects found. Create one with: yait project create <name>")
        return

    header = f"{'NAME':<20}  {'OPEN':>4}  {'CLOSED':>6}  UPDATED"
    click.echo(click.style(header, bold=True))
    for e in entries:
        click.echo(f"{e['name']:<20}  {e['open']:>4}  {e['closed']:>6}  {e['updated'] or '\u2014'}")


@project.command(name="delete")
@click.argument("name")
@click.option("--force", "-f", is_flag=True, default=False, help="Skip confirmation")
def project_delete(name, force):
    """Delete a named project.

    \b
    Examples:
      yait project delete myapp
      yait project delete myapp -f
    """
    home = _yait_home()
    project_dir = home / "projects" / name
    if not project_dir.exists():
        raise click.ClickException(f"Project '{name}' not found.")
    if not force:
        click.confirm(f"Delete project '{name}' and all its data?", abort=True)
    shutil.rmtree(project_dir)
    click.echo(f"Deleted project '{name}'")


@project.command(name="rename")
@click.argument("old")
@click.argument("new")
def project_rename(old, new):
    """Rename a project.

    \b
    Examples:
      yait project rename old-name new-name
    """
    _validate_project_name(new)
    home = _yait_home()
    old_dir = home / "projects" / old
    new_dir = home / "projects" / new
    if not old_dir.exists():
        raise click.ClickException(f"Project '{old}' not found.")
    if new_dir.exists():
        raise click.ClickException(f"Project '{new}' already exists.")
    old_dir.rename(new_dir)
    click.echo(f"Renamed project '{old}' -> '{new}'.")
    click.echo(f"Note: Update any scripts or YAIT_PROJECT env vars that reference '{old}'.")


@project.command(name="import")
@click.argument("name")
@click.option("--path", "src_path", default=None,
              help="Path to directory containing .yait/ (default: cwd)")
@click.option("--move", is_flag=True, default=False,
              help="Remove local .yait/ after import")
def project_import(name, src_path, move):
    """Import a local .yait/ directory as a named project.

    \b
    Examples:
      yait project import myapp
      yait project import myapp --path /other/repo
      yait project import myapp --move
    """
    _validate_project_name(name)
    home = _yait_home()
    project_dir = home / "projects" / name
    if project_dir.exists():
        raise click.ClickException(f"Project '{name}' already exists.")

    src = Path(src_path) if src_path else Path.cwd()
    local_yait = src / ".yait"
    if not local_yait.is_dir():
        raise click.ClickException(
            f"No .yait/ directory found in {src}. Nothing to import."
        )

    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    (home / "projects").mkdir(mode=0o700, exist_ok=True)

    shutil.copytree(local_yait, project_dir)

    lock_file = project_dir / "yait.lock"
    if lock_file.exists():
        lock_file.unlink()

    (project_dir / ".gitignore").write_text("yait.lock\n")

    import subprocess
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "yait@local"], cwd=project_dir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "yait"], cwd=project_dir, capture_output=True)
    git_commit(project_dir, "yait: import project", ".")

    if move:
        shutil.rmtree(local_yait)
        click.echo(f"Moved .yait/ -> {project_dir}/")
    else:
        click.echo(f"Copied .yait/ -> {project_dir}/")

    click.echo(
        "Note: git history for issues is not migrated. "
        "History remains in the original repo's git log."
    )


@project.command(name="path")
@click.argument("name")
@click.option("--check", is_flag=True, default=False,
              help="Exit non-zero if project doesn't exist")
def project_path(name, check):
    """Print the data directory path for a project.

    \b
    Examples:
      yait project path myapp
      yait project path myapp --check
    """
    home = _yait_home()
    project_dir = home / "projects" / name
    if check and not project_dir.exists():
        raise SystemExit(1)
    click.echo(str(project_dir))
