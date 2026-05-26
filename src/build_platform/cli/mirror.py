"""`/build-mirror` entry point group — init, push, status.

One-way push mirror of WPs and sprints to GitHub Issues + Milestones.
"""
import json
import sys
from pathlib import Path

import click

from build_platform.github_mirror import (
    MirrorError,
    load_mirror_map,
    push_all,
)
from build_platform.paths import find_brains_build_root
from build_platform.state import load_config, save_config


def _emit(payload: dict, *, as_json: bool, exit_code: int = 0) -> None:
    if as_json:
        click.echo(json.dumps(payload))
    elif "error" in payload:
        click.echo(f"Error: {payload['error']}", err=True)
    else:
        click.echo(payload.get("message", json.dumps(payload, indent=2)))
    sys.exit(exit_code)


@click.group("mirror")
def mirror_group():
    """One-way mirror of local state to GitHub Issues + Milestones."""


@mirror_group.command("init")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--owner", required=True, help="GitHub owner (user or org).")
@click.option("--repo", required=True, help="GitHub repo name (without owner).")
@click.option("--label-prefix", default="bbp:", show_default=True)
@click.option("--disable", is_flag=True, help="Mark github.enabled = False.")
@click.option("--json", "as_json", is_flag=True)
def init_cmd(root, owner, repo, label_prefix, disable, as_json):
    """Configure the mirror. Sets github.{owner, repo, enabled, label_prefix} in config.yml."""
    root_path = Path(root).resolve() if root else find_brains_build_root()
    config = load_config(root_path)
    config.github.enabled = not disable
    config.github.owner = owner
    config.github.repo = repo
    config.github.label_prefix = label_prefix
    save_config(root_path, config)
    _emit({
        "ok": True,
        "enabled": config.github.enabled,
        "owner": owner,
        "repo": repo,
        "label_prefix": label_prefix,
        "next": "Run `python -m build_platform.cli.mirror push` to seed labels and push WPs.",
    }, as_json=as_json)


@mirror_group.command("push")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--dry-run", "dry_run", is_flag=True,
              help="Preview what would be pushed without making any state-changing "
                   "gh calls. Read-only label/milestone probes still run.")
@click.option("--json", "as_json", is_flag=True)
def push_cmd(root, dry_run, as_json):
    """Reconcile every local WP + sprint to GitHub. Idempotent.

    Use --dry-run first if you're about to push to a public repo and want to
    see exactly which labels/milestones/issues would be created or edited.
    """
    root_path = Path(root).resolve() if root else find_brains_build_root()
    try:
        summary = push_all(root_path, dry_run=dry_run)
    except MirrorError as e:
        _emit({"error": str(e)}, as_json=as_json, exit_code=2)
    _emit(summary, as_json=as_json)


@mirror_group.command("status")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--json", "as_json", is_flag=True)
def status_cmd(root, as_json):
    """Show mirror config + map summary. Does not hit the network."""
    root_path = Path(root).resolve() if root else find_brains_build_root()
    config = load_config(root_path)
    mirror_map = load_mirror_map(root_path)
    payload = {
        "ok": True,
        "enabled": config.github.enabled,
        "owner": config.github.owner,
        "repo": config.github.repo,
        "label_prefix": config.github.label_prefix,
        "last_synced_at": config.github.last_synced_at,
        "wps_mirrored": len(mirror_map.wps),
        "sprints_mirrored": len(mirror_map.sprints),
        "labels_seeded": mirror_map.labels_seeded,
    }
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(f"Mirror enabled: {payload['enabled']}")
        if payload["enabled"]:
            click.echo(f"Repo: {payload['owner']}/{payload['repo']}")
            click.echo(f"WPs mirrored: {payload['wps_mirrored']}")
            click.echo(f"Sprints mirrored: {payload['sprints_mirrored']}")
            click.echo(f"Last sync: {payload['last_synced_at'] or 'never'}")


if __name__ == "__main__":
    mirror_group()
