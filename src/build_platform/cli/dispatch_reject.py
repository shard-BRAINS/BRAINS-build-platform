"""`/build-dispatch reject` — Dev Orchestrator rejects a dispatched diff.

Atomically transitions WP -> blocked (or back to defined for re-tiering),
writes an audit entry with the reason, refreshes the dashboard. Closes
Finding #10 from the 2026-05-26 dogfood report: state transitions that
happen outside cli/dispatch.py previously skipped audit-writing.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import click

from build_platform.audit import AuditEntry, write_audit
from build_platform.paths import find_brains_build_root
from build_platform.render_dashboard import render_dashboard
from build_platform.schemas import WPState
from build_platform.state import load_wp_state, update_wp_state


def _err(msg: str, as_json: bool, code: int) -> None:
    click.echo(json.dumps({"error": msg}) if as_json else f"Error: {msg}", err=True)
    sys.exit(code)


@click.command("reject")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--wp", "wp_id", required=True, help="WP id to reject.")
@click.option("--reason", required=True,
              help="One-line reason for rejection. Recorded in history + audit.")
@click.option("--retier", is_flag=True,
              help="Transition back to 'defined' instead of 'blocked'. Use when "
                   "the tier-1 work was sound but the WP should be re-tagged tier-2 "
                   "via /build-package.")
@click.option("--json", "as_json", is_flag=True)
def reject_cmd(root, wp_id, reason, retier, as_json):
    """Reject a dispatched WP. Transitions to blocked (or defined with --retier)."""
    root_path = Path(root).resolve() if root else find_brains_build_root()
    wps = load_wp_state(root_path)
    if wp_id not in wps:
        _err(f"WP {wp_id} not found", as_json, 1)
    wp = wps[wp_id]
    if wp.state != WPState.DISPATCHED:
        _err(f"WP {wp_id} is in state {wp.state.value}, expected 'dispatched'",
             as_json, 1)

    target = WPState.DEFINED if retier else WPState.BLOCKED
    event = (f"rejected by Dev Orchestrator (retier): {reason}" if retier
             else f"rejected by Dev Orchestrator: {reason}")

    start = time.monotonic()
    update_wp_state(root_path, wp_id, target,
                    by="build-dev-orchestrator", event=event)

    write_audit(root_path, AuditEntry(
        wp_id=wp.id,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        persona="build-dev-orchestrator",
        model="n/a-deterministic",
        tier=int(wp.tier.value),
        runtime_seconds=time.monotonic() - start,
        result="rejected_retier" if retier else "rejected",
        inputs_read=[],
        outputs_written=[],
        notes=reason,
    ))

    render_dashboard(root_path)

    payload = {
        "ok": True, "wp_id": wp_id,
        "new_state": target.value,
        "reason": reason,
        "next": ("Re-package the WP via /build-package (likely tier 2)."
                 if retier
                 else "WP is blocked. Resolve via /build-decision or new WP."),
    }
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(f"{wp_id} -> {target.value}. Reason: {reason}")
    sys.exit(0)


if __name__ == "__main__":
    reject_cmd()
