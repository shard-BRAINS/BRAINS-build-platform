"""`/build-loop` — autonomous dispatch loop for tier-1 AUTO WPs.

Finds all eligible WPs (state=DEFINED, autonomy=AUTO, tier=ONE, deps DONE),
dispatches them via tier-1, applies the diff, then refreshes the dashboard.
"""
import json
import sys
from pathlib import Path

import click
from click.testing import CliRunner

from build_platform.audit import load_audit_index
from build_platform.paths import find_brains_build_root
from build_platform.render_dashboard import render_dashboard
from build_platform.schemas import Autonomy, WPState, WPTier
from build_platform.state import load_wp_state

from build_platform.cli.dispatch import dispatch_cmd
from build_platform.cli.dispatch_apply import apply_cmd


def _wps_blocked_by_code_review(audit_rows: list[dict]) -> set[str]:
    """Return WP ids whose MOST RECENT audit row has code_review_verdict='reject'.

    Latest-by-timestamp wins; earlier rejects that have been overridden by later
    approves don't count.
    """
    latest: dict[str, dict] = {}
    for row in audit_rows:
        wp_id = row.get("wp_id")
        ts = row.get("timestamp", "")
        if wp_id is None:
            continue
        if wp_id not in latest or ts > latest[wp_id].get("timestamp", ""):
            latest[wp_id] = row
    return {
        wp_id
        for wp_id, row in latest.items()
        if row.get("code_review_verdict") == "reject"
    }


def _eligible_wps(project_root: Path, verbose: bool = False) -> list:
    """Return DEFINED + AUTO + tier-1 WPs whose deps are all DONE, sorted by id."""
    wps = load_wp_state(project_root)
    blocked = _wps_blocked_by_code_review(load_audit_index(project_root))
    out = []
    for wp in sorted(wps.values(), key=lambda w: w.id):
        if wp.state != WPState.DEFINED:
            continue
        if wp.autonomy != Autonomy.AUTO:
            continue
        if wp.tier != WPTier.ONE:
            continue
        if wp.id in blocked:
            if verbose:
                click.echo(f"skipping {wp.id}: code-review reject on record", err=True)
            continue
        unmet = [d for d in wp.depends_on if wps.get(d) is None or wps[d].state != WPState.DONE]
        if unmet:
            continue
        out.append(wp)
    return out


@click.command("loop")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--limit", type=int, default=5, show_default=True,
              help="Maximum number of WPs to dispatch in one loop run.")
@click.option("--dry-run", is_flag=True, help="Print the planned queue and exit without dispatching.")
@click.option("--no-test", is_flag=True,
              help="Skip post-apply tests. Off by default — tests are the safety net for auto mode.")
@click.option("--test-timeout", type=int, default=300, show_default=True,
              help="Seconds before each apply's test command is killed.")
@click.option("--json", "as_json", is_flag=True)
def loop_cmd(root, limit, dry_run, no_test, test_timeout, as_json):
    """Auto-dispatch eligible tier-1 WPs with autonomy=auto."""
    root_path = Path(root).resolve() if root else find_brains_build_root()

    verbose = not dry_run and not as_json
    queue = _eligible_wps(root_path, verbose=verbose)[:limit]

    if dry_run:
        payload = {
            "dry_run": True,
            "queue": [{"id": wp.id, "title": wp.title} for wp in queue],
        }
        click.echo(json.dumps(payload) if as_json else _fmt_queue(queue))
        sys.exit(0)

    runner = CliRunner()
    dispatched: list[str] = []
    stopped_at: str | None = None
    reason: str = "completed"

    for wp in queue:
        # Step 1: dispatch (tier-1 Ollama)
        r = runner.invoke(dispatch_cmd, ["--root", str(root_path), "--wp", wp.id, "--json"])
        if r.exit_code != 0:
            stopped_at = wp.id
            reason = f"dispatch failed (exit {r.exit_code}): {r.output.strip()}"
            break

        # Step 2: apply diff (tests on by default — safety net for auto mode)
        apply_args = [
            "--root", str(root_path), "--wp", wp.id,
            "--test-timeout", str(test_timeout), "--json",
        ]
        if no_test:
            apply_args.append("--no-test")
        r = runner.invoke(apply_cmd, apply_args)
        if r.exit_code != 0:
            stopped_at = wp.id
            reason = f"apply failed (exit {r.exit_code}): {r.output.strip()}"
            break

        dispatched.append(wp.id)

    render_dashboard(root_path)

    payload = {
        "dispatched": dispatched,
        "stopped_at": stopped_at,
        "reason": reason,
    }
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(f"Dispatched: {dispatched or 'none'}")
        if stopped_at:
            click.echo(f"Stopped at {stopped_at}: {reason}", err=True)

    if stopped_at:
        sys.exit(1)


def _fmt_queue(queue) -> str:
    if not queue:
        return "Queue is empty — no eligible AUTO tier-1 WPs."
    lines = ["Planned queue:"]
    for i, wp in enumerate(queue, 1):
        lines.append(f"  {i}. {wp.id} — {wp.title}")
    return "\n".join(lines)


if __name__ == "__main__":
    loop_cmd()
