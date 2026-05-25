"""`/build-dashboard` entry point — renders current dashboard."""
import json
from pathlib import Path

import click

from build_platform.paths import find_brains_build_root
from build_platform.render_dashboard import render_dashboard


@click.command("dashboard")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--json", "as_json", is_flag=True)
def dashboard_cmd(root, as_json):
    """Render the markdown PMO dashboard."""
    root_path = Path(root).resolve() if root else find_brains_build_root()
    out = render_dashboard(root_path)
    payload = {"ok": True, "path": str(out)}
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    dashboard_cmd()
