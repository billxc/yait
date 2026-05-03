from __future__ import annotations

from pathlib import Path

import click

from . import main, _resolve, _require_init


@main.command()
@click.option(
    "--output", "-o", default=None,
    help="Output directory (default: <data-dir>/dashboard/)",
)
@click.option("--no-open", is_flag=True, help="Don't open browser after generating")
@click.pass_context
def dashboard(ctx, output, no_open):
    """Generate a multi-page HTML dashboard snapshot."""
    import webbrowser

    from ..dashboard import generate_dashboard

    root = _resolve(ctx)
    _require_init(root)

    project_name = ctx.obj.get("project") or ""
    output_dir = Path(output) if output else root / "dashboard"

    index_path = generate_dashboard(root, output_dir=output_dir, project_name=project_name)

    if not no_open:
        webbrowser.open(index_path.as_uri())

    click.echo(f"Dashboard generated: {index_path}")
