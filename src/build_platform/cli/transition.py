"""`/build-transition` — generic WP state escape hatch.

Moves a WP from any current state to any target state, writing an audit
entry, appending a history event, and refreshing the dashboard atomically.
No state-machine constraint — the caller owns the choice.
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

_STATE_CHOICES = [s.value for s in WPState]


def _err(msg: str, as_json: bool, code: int) -> None:
    click.echo(json.dumps({"error": msg}) if as_json else f"Error: {msg}", err=True)
    sys.exit(code)


@click.command("transition")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--wp", "wp_id", required=True, help="WP id to transition.")
@click.option(
    "--to",
    "target",
    required=True,
    type=click.Choice(_STATE_CHOICES),
    help="Target state.",
)
@click.option("--by", required=True, help="Persona id or user:NAME performing the transition.")
@click.option("--reason", required=True, help="One-line reason; recorded in history + audit.")
@click.option("--json", "as_json", is_flag=True)
def transition_cmd(root, wp_id, target, by, reason, as_json):
    """Move a WP to any target state (escape hatch — no state-machine guard)."""
    root_path = Path(root).resolve() if root else find_brains_build_root()
    wps = load_wp_state(root_path)

    if wp_id not in wps:
        _err(f"WP {wp_id} not found", as_json, 1)

    wp = wps[wp_id]
    target_state = WPState(target)

    if wp.state == target_state:
        _err(
            f"WP {wp_id} is already in state '{target_state.value}' — same-state transition refused.",
            as_json,
            1,
        )

    from_state = wp.state.value
    event = f"manual transition {from_state} -> {target_state.value} by {by}: {reason}"

    start = time.monotonic()
    update_wp_state(root_path, wp_id, target_state, by=by, event=event)

    write_audit(root_path, AuditEntry(
        wp_id=wp.id,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        persona=by,
        model="n/a-manual",
        tier=int(wp.tier.value),
        runtime_seconds=time.monotonic() - start,
        result=f"transition_{from_state}_to_{target_state.value}",
        inputs_read=[],
        outputs_written=[],
        notes=reason,
    ))

    render_dashboard(root_path)

    payload = {
        "ok": True,
        "wp_id": wp_id,
        "from_state": from_state,
        "new_state": target_state.value,
        "reason": reason,
    }
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(f"{wp_id}: {from_state} -> {target_state.value}. Reason: {reason}")
    sys.exit(0)


if __name__ == "__main__":
    transition_cmd()
