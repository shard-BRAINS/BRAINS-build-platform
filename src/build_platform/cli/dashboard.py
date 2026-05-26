"""`/build-dashboard` entry point — renders current dashboard."""
import json
from pathlib import Path

import click

from build_platform.paths import find_brains_build_root
from build_platform.render_dashboard import (
    render_dashboard,
    render_dashboard_all,
    render_dashboard_html,
)


@click.command("dashboard")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--format", "fmt", type=click.Choice(["md", "html", "both"]),
              default="both", show_default=True,
              help="Output format. 'both' writes both files; 'md' is canonical.")
@click.option("--json", "as_json", is_flag=True)
def dashboard_cmd(root, fmt, as_json):
    """Render the markdown and/or HTML PMO dashboard."""
    root_path = Path(root).resolve() if root else find_brains_build_root()
    paths: dict[str, Path] = {}
    if fmt in ("md", "both"):
        paths["md"] = render_dashboard(root_path)
    if fmt in ("html", "both"):
        paths["html"] = render_dashboard_html(root_path)

    payload = {
        "ok": True,
        "paths": {k: str(v) for k, v in paths.items()},
        "path": str(paths.get("md") or paths.get("html")),  # back-compat single path
    }
    if as_json:
        click.echo(json.dumps(payload))
    elif "md" in paths:
        click.echo(paths["md"].read_text(encoding="utf-8"))
    else:
        click.echo(f"HTML dashboard written to {paths['html']}")


if __name__ == "__main__":
    dashboard_cmd()
