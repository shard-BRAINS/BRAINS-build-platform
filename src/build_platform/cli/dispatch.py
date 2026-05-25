"""`/build-dispatch` entry point — execute a WP via tier-1 (Ollama) or tier-2 (Claude brief)."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import click

from build_platform.audit import AuditEntry, write_audit
from build_platform.dispatcher import (
    DispatchError,
    dispatch_tier1,
    prepare_tier2_brief,
)
from build_platform.ollama_client import OllamaClient, OllamaError
from build_platform.paths import find_brains_build_root
from build_platform.render_dashboard import render_dashboard
from build_platform.schemas import WPState, WPTier
from build_platform.state import load_config, load_wp_state, update_wp_state


@click.command("dispatch")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--wp", "wp_id", required=True, help="WP id to dispatch.")
@click.option("--json", "as_json", is_flag=True)
def dispatch_cmd(root, wp_id, as_json):
    root_path = Path(root).resolve() if root else find_brains_build_root()
    config = load_config(root_path)
    wps = load_wp_state(root_path)
    if wp_id not in wps:
        _err(f"WP {wp_id} not found", as_json, 1)
    wp = wps[wp_id]
    if wp.state != WPState.DEFINED:
        _err(f"WP {wp_id} is in state {wp.state.value}, expected 'defined'", as_json, 1)
    unmet = [dep for dep in wp.depends_on if wps.get(dep) is None or wps[dep].state != WPState.DONE]
    if unmet:
        _err(f"WP {wp_id} blocked by unmet deps: {unmet}", as_json, 1)

    start = time.monotonic()
    if wp.tier == WPTier.ONE:
        client = OllamaClient(config.ollama)
        try:
            client.preflight(required_models=[
                config.ollama.models.tier1_default,
                config.ollama.models.summarizer,
            ])
        except OllamaError as e:
            _err(str(e), as_json, 2)
        try:
            diff_path = dispatch_tier1(root_path, wp, client)
        except DispatchError as e:
            update_wp_state(root_path, wp_id, WPState.BLOCKED,
                            by="build-dev-orchestrator", event=f"tier-1 dispatch failed: {e}")
            render_dashboard(root_path)
            _err(str(e), as_json, 3)
        update_wp_state(root_path, wp_id, WPState.DISPATCHED,
                        by="build-dev-orchestrator",
                        event=f"tier-1 diff at {diff_path.relative_to(root_path)}")
        write_audit(root_path, AuditEntry(
            wp_id=wp.id, timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            persona=wp.executor_persona, model=config.ollama.models.tier1_default,
            tier=1, runtime_seconds=time.monotonic() - start, result="dispatched",
            inputs_read=wp.spec_files,
            outputs_written=[str(diff_path.relative_to(root_path))],
            notes="Diff awaiting Dev Orchestrator review.",
        ))
        result_payload = {"ok": True, "wp_id": wp.id, "tier": 1,
                          "diff": str(diff_path), "next": "review and apply"}
    else:
        brief_path = prepare_tier2_brief(root_path, wp)
        update_wp_state(root_path, wp_id, WPState.DISPATCHED,
                        by="build-dev-orchestrator",
                        event=f"tier-2 brief at {brief_path.relative_to(root_path)}")
        write_audit(root_path, AuditEntry(
            wp_id=wp.id, timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            persona=wp.executor_persona, model="claude-sonnet-4-6",
            tier=2, runtime_seconds=time.monotonic() - start, result="brief_emitted",
            inputs_read=wp.spec_files,
            outputs_written=[str(brief_path.relative_to(root_path))],
            notes="Awaiting subagent execution in Claude session.",
        ))
        result_payload = {"ok": True, "wp_id": wp.id, "tier": 2,
                          "brief": str(brief_path),
                          "next": f"Spawn {wp.executor_persona} subagent with this brief"}

    render_dashboard(root_path)
    click.echo(json.dumps(result_payload) if as_json else _human(result_payload))


def _err(msg: str, as_json: bool, code: int):
    click.echo(json.dumps({"error": msg}) if as_json else f"Error: {msg}", err=True)
    sys.exit(code)


def _human(payload: dict) -> str:
    if payload["tier"] == 1:
        return f"{payload['wp_id']} dispatched (tier-1). Diff: {payload['diff']}\nNext: review and apply."
    return (f"{payload['wp_id']} dispatched (tier-2). Brief: {payload['brief']}\n"
            f"Next: {payload['next']}")


if __name__ == "__main__":
    dispatch_cmd()
