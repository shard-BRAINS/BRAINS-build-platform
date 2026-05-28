"""`/build-dispatch request-changes` — Code-Review SME requests changes on a dispatched diff.

Writes findings to code-review.md, deletes proposed.diff, transitions the WP
back to defined so it can be re-dispatched after fixes, and writes an audit entry.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import click

from build_platform.audit import AuditEntry, write_audit
from build_platform.paths import find_brains_build_root, state_dir
from build_platform.render_dashboard import render_dashboard
from build_platform.schemas import WPState
from build_platform.state import load_wp_state, update_wp_state


def _err(msg: str, as_json: bool, code: int) -> None:
    click.echo(json.dumps({"error": msg}) if as_json else f"Error: {msg}", err=True)
    sys.exit(code)


def request_changes(project_root: Path, wp_id: str, findings_file: Path) -> dict:
    """Request changes on a dispatched WP.

    Returns the same payload shape as the click command's --json output.
    """
    wps = load_wp_state(project_root)
    if wp_id not in wps:
        raise ValueError(f"WP {wp_id} not found")
    wp = wps[wp_id]
    if wp.state not in {WPState.DISPATCHED, WPState.IN_REVIEW}:
        raise ValueError(
            f"WP {wp_id} is in state {wp.state.value}, "
            "expected 'dispatched' or 'in_review'"
        )
    if not findings_file.exists():
        raise FileNotFoundError(f"Findings file not found: {findings_file}")

    raw = findings_file.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    first_line = lines[0] if lines else "no reason given"

    # Write code-review.md (verbatim)
    run_dir = state_dir(project_root) / "runs" / wp_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "code-review.md").write_text(raw, encoding="utf-8")

    # Delete proposed.diff if present
    (run_dir / "proposed.diff").unlink(missing_ok=True)

    start = time.monotonic()
    event = f"code-review request-changes: {first_line}"
    update_wp_state(project_root, wp_id, WPState.DEFINED,
                    by="build-code-review-sme", event=event)

    write_audit(project_root, AuditEntry(
        wp_id=wp.id,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        persona="build-code-review-sme",
        model="n/a-deterministic",
        tier=int(wp.tier.value),
        runtime_seconds=time.monotonic() - start,
        result="requested_changes",
        inputs_read=[str(findings_file)],
        outputs_written=[str(run_dir / "code-review.md")],
        code_review_verdict="request-changes",
        code_review_findings=lines,
        notes="Diff reset; WP returned to defined for re-dispatch.",
    ))

    render_dashboard(project_root)

    return {
        "ok": True,
        "wp_id": wp_id,
        "new_state": WPState.DEFINED.value,
        "findings_count": len(lines),
        "next": "Re-dispatch via /build-dispatch when fixes are in.",
    }


@click.command("request-changes")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--wp", "wp_id", required=True, help="WP id to request changes on.")
@click.option("--findings-file", "findings_file", required=True,
              type=click.Path(dir_okay=False),
              help="Path to text file with one finding per line.")
@click.option("--json", "as_json", is_flag=True)
def request_changes_cmd(root, wp_id, findings_file, as_json):
    """Request changes on a dispatched WP. Resets diff and returns WP to defined."""
    root_path = Path(root).resolve() if root else find_brains_build_root()
    findings_path = Path(findings_file).resolve()

    if not findings_path.exists():
        _err(f"Findings file not found: {findings_path}", as_json, 1)

    wps = load_wp_state(root_path)
    if wp_id not in wps:
        _err(f"WP {wp_id} not found", as_json, 1)
    wp = wps[wp_id]
    if wp.state not in {WPState.DISPATCHED, WPState.IN_REVIEW}:
        _err(
            f"WP {wp_id} is in state {wp.state.value}, "
            "expected 'dispatched' or 'in_review'",
            as_json, 1,
        )

    try:
        payload = request_changes(root_path, wp_id, findings_path)
    except (ValueError, FileNotFoundError) as exc:
        _err(str(exc), as_json, 1)

    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(
            f"{wp_id} -> defined. {payload['findings_count']} finding(s) recorded."
        )
    sys.exit(0)


if __name__ == "__main__":
    request_changes_cmd()
