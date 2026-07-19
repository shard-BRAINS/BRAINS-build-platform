"""`/build-portfolio` entry point group — register, unregister, list, view.

Manages a cross-project portfolio at ~/.brains-build-portfolio.yml and renders
an aggregated view across all registered projects.
"""
import json
import sys
from datetime import datetime, timezone
from importlib.resources import files as pkg_files
from pathlib import Path

import click
from jinja2 import Template, select_autoescape

from build_platform.paths import STATE_DIR_NAME
from build_platform.portfolio import (
    is_brains_project,
    load_portfolio,
    registry_path,
    save_portfolio,
    scan_portfolio,
)


def _load_template(name: str) -> Template:
    src = pkg_files("build_platform.templates").joinpath(name).read_text(encoding="utf-8")
    return Template(src, autoescape=select_autoescape(), keep_trailing_newline=True)


def _resolve(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _emit(payload: dict, *, as_json: bool, exit_code: int = 0) -> None:
    if as_json:
        click.echo(json.dumps(payload))
    elif "error" in payload:
        click.echo(f"Error: {payload['error']}", err=True)
    else:
        click.echo(payload.get("message", json.dumps(payload, indent=2)))
    sys.exit(exit_code)


@click.group("portfolio")
def portfolio_group():
    """Manage the cross-project portfolio registry."""


@portfolio_group.command("register")
@click.argument("path", type=click.Path())
@click.option("--home", type=click.Path(file_okay=False), default=None,
              help="Override $HOME (mainly for testing).")
@click.option("--json", "as_json", is_flag=True)
def register_cmd(path, home, as_json):
    """Add a project path to the portfolio registry."""
    home_path = Path(home) if home else None
    target = _resolve(path)
    if not is_brains_project(target):
        _emit({"error": f"{target} is not a BRAINS Build Platform project "
                        f"(missing {STATE_DIR_NAME}/project.yml)"},
              as_json=as_json, exit_code=2)
    portfolio = load_portfolio(home_path)
    target_str = str(target)
    if target_str in portfolio.projects:
        _emit({"ok": True, "id": target_str, "already_registered": True},
              as_json=as_json)
    portfolio.projects.append(target_str)
    save_portfolio(portfolio, home_path)
    _emit({"ok": True, "id": target_str, "count": len(portfolio.projects),
           "registry": str(registry_path(home_path))}, as_json=as_json)


@portfolio_group.command("unregister")
@click.argument("path", type=click.Path())
@click.option("--home", type=click.Path(file_okay=False), default=None)
@click.option("--json", "as_json", is_flag=True)
def unregister_cmd(path, home, as_json):
    """Remove a project path from the portfolio registry."""
    home_path = Path(home) if home else None
    target = str(_resolve(path))
    portfolio = load_portfolio(home_path)
    if target not in portfolio.projects:
        _emit({"error": f"Not registered: {target}"}, as_json=as_json, exit_code=1)
    portfolio.projects.remove(target)
    save_portfolio(portfolio, home_path)
    _emit({"ok": True, "removed": target, "count": len(portfolio.projects)},
          as_json=as_json)


@portfolio_group.command("list")
@click.option("--home", type=click.Path(file_okay=False), default=None)
@click.option("--json", "as_json", is_flag=True)
def list_cmd(home, as_json):
    """List registered project paths (no scan, just the registry)."""
    home_path = Path(home) if home else None
    portfolio = load_portfolio(home_path)
    payload = {"ok": True, "count": len(portfolio.projects),
               "projects": portfolio.projects,
               "registry": str(registry_path(home_path))}
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(f"{len(portfolio.projects)} projects in {registry_path(home_path)}:")
        for p in portfolio.projects:
            click.echo(f"  {p}")


@portfolio_group.command("view")
@click.option("--home", type=click.Path(file_okay=False), default=None)
@click.option("--format", "fmt", type=click.Choice(["md", "html", "both"]),
              default="md", show_default=True)
@click.option("--out", type=click.Path(file_okay=True), default=None,
              help="Write the rendered view to this path. If omitted, stdout "
                   "(md) or the registry directory (html/both).")
@click.option("--json", "as_json", is_flag=True)
def view_cmd(home, fmt, out, as_json):
    """Render an aggregated view across all registered projects."""
    home_path = Path(home) if home else None
    portfolio = load_portfolio(home_path)
    rows = scan_portfolio(portfolio)
    ctx = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(rows),
        "rows": rows,
    }

    written: dict[str, str] = {}
    base_dir = (home_path or Path.home())

    if fmt in ("md", "both"):
        rendered_md = _load_template("portfolio.md.j2").render(**ctx)
        if out and fmt == "md":
            Path(out).write_text(rendered_md, encoding="utf-8")
            written["md"] = str(Path(out))
        elif fmt == "both":
            md_path = base_dir / "brains-build-portfolio.md"
            md_path.write_text(rendered_md, encoding="utf-8")
            written["md"] = str(md_path)
        else:
            written["md"] = "<stdout>"
            if not as_json:
                click.echo(rendered_md)

    if fmt in ("html", "both"):
        rendered_html = _load_template("portfolio.html.j2").render(**ctx)
        html_path = Path(out) if (out and fmt == "html") else (base_dir / "brains-build-portfolio.html")
        html_path.write_text(rendered_html, encoding="utf-8")
        written["html"] = str(html_path)

    payload = {"ok": True, "count": len(rows), "written": written, "rows": rows}
    if as_json:
        click.echo(json.dumps(payload))
    elif fmt != "md":
        for f, p in written.items():
            click.echo(f"{f}: {p}")


if __name__ == "__main__":
    portfolio_group()
