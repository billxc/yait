from __future__ import annotations

from pathlib import Path

import click

from . import main, _resolve, _require_init


@main.command()
@click.option("--output", "-o", default=None, help="Output HTML file path (default: dashboard.html in data dir)")
@click.option("--no-open", is_flag=True, help="Don't open browser after generating")
@click.pass_context
def dashboard(ctx, output, no_open):
    """Generate a local HTML dashboard."""
    import webbrowser

    from ..dashboard import generate_dashboard

    root = _resolve(ctx)
    _require_init(root)

    project_name = ctx.obj.get("project") or ""
    html = generate_dashboard(root, project_name=project_name)

    output_path = Path(output) if output else root / "dashboard.html"
    output_path.write_text(html, encoding="utf-8")

    if not no_open:
        webbrowser.open(str(output_path))

    click.echo(f"Dashboard generated: {output_path}")
