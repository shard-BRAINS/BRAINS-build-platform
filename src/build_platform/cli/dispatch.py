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
            diff_path, metrics = dispatch_tier1(root_path, wp, client)
        except DispatchError as e:
            update_wp_state(root_path, wp_id, WPState.BLOCKED,
                            by="build-dev-orchestrator", event=f"tier-1 dispatch failed: {e}")
            render_dashboard(root_path)
            suggested = getattr(e, "suggested_action", None)
            _err_dispatch(str(e), as_json, 3, suggested_action=suggested)
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
            tokens_in=metrics.get("tokens_in", 0),
            tokens_out=metrics.get("tokens_out", 0),
            cost_usd=metrics.get("cost_usd", 0.0),
        ))
        result_payload = {"ok": True, "wp_id": wp.id, "tier": 1,
                          "diff": str(diff_path), "warnings": [],
                          "next": "review and apply"}
    else:
        brief_path = prepare_tier2_brief(root_path, wp)

        # Finding #9: tier-2 dispatch requires the persona's subagent
        # definition to be installed at ~/.claude/agents/build/<persona>.md
        # for Claude Code to spawn it. Don't refuse — emit a warning so
        # the caller knows to run install.ps1 (or the user can read the
        # brief and spawn manually elsewhere).
        warnings = []
        persona_path = Path.home() / ".claude" / "agents" / "build" / f"{wp.executor_persona}.md"
        if not persona_path.exists():
            warnings.append(
                f"Persona subagent file missing at {persona_path}. "
                f"Claude Code cannot spawn {wp.executor_persona} until this exists. "
                f"Run `.\\install.ps1` from the build-platform repo to install."
            )

        update_wp_state(root_path, wp_id, WPState.DISPATCHED,
                        by="build-dev-orchestrator",
                        event=f"tier-2 brief at {brief_path.relative_to(root_path)}")
        # tier-2 audit token fields are intentionally 0: the Claude subagent
        # runs out-of-band and the dispatcher cannot observe its token usage.
        # If/when the Claude Agent SDK exposes per-spawn token counts, plumb
        # them through the subagent result block and into this AuditEntry.
        write_audit(root_path, AuditEntry(
            wp_id=wp.id, timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            persona=wp.executor_persona, model="claude-sonnet-5",
            tier=2, runtime_seconds=time.monotonic() - start, result="brief_emitted",
            inputs_read=wp.spec_files,
            outputs_written=[str(brief_path.relative_to(root_path))],
            notes="Awaiting subagent execution in Claude session." +
                  (f" WARNING: {warnings[0]}" if warnings else ""),
        ))
        result_payload = {"ok": True, "wp_id": wp.id, "tier": 2,
                          "brief": str(brief_path),
                          "warnings": warnings,
                          "next": f"Spawn {wp.executor_persona} subagent with this brief"}

    render_dashboard(root_path)
    click.echo(json.dumps(result_payload) if as_json else _human(result_payload))


def _err(msg: str, as_json: bool, code: int):
    click.echo(json.dumps({"error": msg}) if as_json else f"Error: {msg}", err=True)
    sys.exit(code)


def _err_dispatch(msg: str, as_json: bool, code: int, *, suggested_action: str | None = None):
    """Like _err but optionally embeds suggested_action in the error payload."""
    if as_json:
        payload: dict = {"error": msg}
        if suggested_action:
            payload["suggested_action"] = suggested_action
        click.echo(json.dumps(payload), err=True)
    else:
        lines = [f"Error: {msg}"]
        if suggested_action == "retier-to-2":
            lines.append(
                "Suggested next step: re-tier this WP to tier-2 with "
                "`python -m build_platform.cli.dispatch_reject --wp <id> "
                "--reason '...' --retier`"
            )
        click.echo("\n".join(lines), err=True)
    sys.exit(code)


def _human(payload: dict) -> str:
    warnings = payload.get("warnings") or []
    warn_lines = "".join(f"\n  WARNING: {w}" for w in warnings)
    if payload["tier"] == 1:
        return (f"{payload['wp_id']} dispatched (tier-1). Diff: {payload['diff']}\n"
                f"Next: review and apply.{warn_lines}")
    return (f"{payload['wp_id']} dispatched (tier-2). Brief: {payload['brief']}\n"
            f"Next: {payload['next']}{warn_lines}")


if __name__ == "__main__":
    dispatch_cmd()
