from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import click

from .. import __version__
from ..git_ops import git_commit
from ..lock import YaitLock
from ..models import ISSUE_TYPES, PRIORITIES
from ..store import (
    init_store, is_initialized, load_issue,
    get_defaults, get_workflow, validate_status,
    _read_config, _write_config,
)


# ── Public helpers used by submodules ─────────────────────────

_PROJECT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


def _yait_home() -> Path:
    return Path(os.environ.get("YAIT_HOME", "~/.yait")).expanduser()


def _validate_project_name(name: str) -> None:
    if not name or len(name) > 64:
        raise click.ClickException(
            "Project name must be 1-64 characters."
        )
    if not _PROJECT_NAME_RE.match(name):
        raise click.ClickException(
            f"Invalid project name: {name!r}. "
            "Must start with alphanumeric, contain only [a-zA-Z0-9_-]."
        )


def _project_create(name: str) -> Path:
    """Create a named project. Returns the project data dir."""
    _validate_project_name(name)
    home = _yait_home()
    project_dir = home / "projects" / name
    if project_dir.exists():
        raise click.ClickException(
            f"Project '{name}' already exists at {project_dir}"
        )
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    (home / "projects").mkdir(mode=0o700, exist_ok=True)
    project_dir.mkdir(parents=True)
    init_store(project_dir)
    (project_dir / ".gitignore").write_text("yait.lock\n")
    import subprocess
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "yait@local"], cwd=project_dir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "yait"], cwd=project_dir, capture_output=True)
    git_commit(project_dir, "yait: init project", ".")
    return project_dir


def _resolve(ctx) -> Path:
    """Resolve the yait data directory from --project, YAIT_PROJECT, or cwd."""
    if ctx.obj.get("data_dir") is not None:
        return ctx.obj["data_dir"]

    project = ctx.obj.get("project")
    yait_home = _yait_home()

    name = project or os.environ.get("YAIT_PROJECT")
    if name:
        p = yait_home / "projects" / name
        if not p.is_dir():
            raise click.ClickException(
                f"Project '{name}' not found.\n"
                f"  Create it:      yait project create {name}\n"
                f"  List projects:  yait project list\n"
                f"  Import local:   yait project import {name}"
            )
        ctx.obj["data_dir"] = p
        ctx.obj["is_project"] = True
        return p

    local = Path.cwd() / ".yait"
    if local.is_dir():
        ctx.obj["data_dir"] = local
        ctx.obj["is_project"] = False
        return local

    raise click.ClickException(
        "No yait project found.\n\n"
        "  Use one of:\n"
        "    yait -P <name> <command>     Use a named project\n"
        "    export YAIT_PROJECT=<name>   Set default project for this shell\n"
        "    yait init                    Create local .yait/ in current directory\n"
        "    yait project create <name>   Create a new named project\n\n"
        "  List existing projects: yait project list"
    )


def _commit(ctx, root: Path, message: str) -> None:
    """Git commit helper that handles local vs project mode staging."""
    if ctx.obj.get("is_project"):
        git_commit(root, message, ".")
    else:
        git_commit(root.parent, message, ".yait")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _require_init(root: Path) -> None:
    if not is_initialized(root):
        raise click.ClickException("Not a yait project. Run 'yait init' first.")


def _load_or_exit(root: Path, issue_id: int):
    from ..store import load_issue
    try:
        return load_issue(root, issue_id)
    except (FileNotFoundError, ValueError):
        raise click.ClickException(f"Issue #{issue_id} not found.")


def _read_body(body: str | None, body_file: str | None) -> str:
    """Resolve body text from --body and --body-file options."""
    import sys
    if body is not None and body_file is not None:
        raise click.ClickException("Cannot use both --body and --body-file.")
    if body_file is not None:
        return Path(body_file).read_text().rstrip("\n")
    if body == "-":
        return sys.stdin.read().rstrip("\n")
    return body or ""


def _read_message(message: str | None, message_file: str | None) -> str | None:
    """Resolve message text from --message and --message-file options."""
    import sys
    if message is not None and message_file is not None:
        raise click.ClickException("Cannot use both --message and --message-file.")
    if message_file is not None:
        return Path(message_file).read_text().rstrip("\n")
    if message == "-":
        return sys.stdin.read().rstrip("\n")
    return message


# ── CLI Group ────────────────────────────────────────────────

@click.group(epilog="""\b
Quick start:
  yait init
  yait new "Fix login bug" -t bug -l urgent
  yait list
  yait search "login"
  yait show 1
  yait close 1
""")
@click.version_option(version=__version__)
@click.option("--project", "-P", default=None, envvar="YAIT_PROJECT",
              help="Named project (stored in ~/.yait/projects/)")
@click.pass_context
def main(ctx, project):
    """yait — Yet Another Issue Tracker

    A lightweight, git-backed issue tracker that lives in your repo.
    Issues are stored as Markdown files and every change is auto-committed.
    """
    ctx.ensure_object(dict)
    ctx.obj["project"] = project


# ── Register all submodule commands ──────────────────────────

from . import (  # noqa: E402, F401
    issues,
    search,
    milestone,
    bulk,
    docs,
    project,
    config,
    io,
    links,
    labels,
    board,
    dashboard,
    template,
    update,
)

# Re-export symbols that tests import directly from yait.cli
from ._helpers import (  # noqa: E402, F401
    _detect_display_mode,
    _truncate_title,
    _format_date,
    _print_issue_table,
    _status_color,
    _type_color,
    _highlight_text,
    _format_labels,
)
from .search import _build_stats_data  # noqa: E402, F401
