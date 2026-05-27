"""`/build-package edit` — edit fields of an existing WP (Finding #7).

Pre-fix workaround was hand-editing work-packages.jsonl; this exposes the
mutations as a first-class CLI with schema validation, orphan-dep checks,
history-event appending, and audit writing.

Excluded from editing: id, created_by, created_at, state, history. State
has its own transition paths (`/build-dispatch`, `dispatch_apply`,
`dispatch_reject`); history is append-only.
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
from build_platform.schemas import Autonomy, WPTier
from build_platform.state import (
    load_work_packages,
    load_wp_state,
    update_work_package_fields,
)


def _err(msg: str, as_json: bool, code: int) -> None:
    click.echo(json.dumps({"error": msg}) if as_json else f"Error: {msg}", err=True)
    sys.exit(code)


def _set_list(current: list[str], add: tuple[str, ...], remove: tuple[str, ...]) -> list[str]:
    """Apply add/remove to a list, preserving order; dedups; preserves originals
    not touched by add/remove."""
    out = [x for x in current if x not in remove]
    for x in add:
        if x not in out:
            out.append(x)
    return out


@click.command("edit")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--wp", "wp_id", required=True, help="WP id to edit.")
# Scalar fields
@click.option("--title", default=None)
@click.option("--workstream", default=None)
@click.option("--deliverable", "deliverable_id", default=None,
              help="New deliverable_id.")
@click.option("--tier", type=click.Choice(["1", "2"]), default=None)
@click.option("--executor", "executor_persona", default=None)
@click.option("--spec", default=None)
# List fields — add/remove pairs (repeatable)
@click.option("--add-file", "add_files", multiple=True)
@click.option("--remove-file", "remove_files", multiple=True)
@click.option("--add-accept", "add_acceptance", multiple=True)
@click.option("--remove-accept", "remove_acceptance", multiple=True)
@click.option("--add-dep", "add_deps", multiple=True)
@click.option("--remove-dep", "remove_deps", multiple=True)
@click.option("--add-consult", "add_consult_personas", multiple=True)
@click.option("--remove-consult", "remove_consult_personas", multiple=True)
@click.option("--autonomy", type=click.Choice(["manual", "review-on-complete", "auto"]),
              default=None, help="Change the autonomy level.")
@click.option("--by", default="user", help="Who's making the edit. Recorded in history.")
@click.option("--json", "as_json", is_flag=True)
def edit_cmd(root, wp_id, title, workstream, deliverable_id, tier,
             executor_persona, spec,
             add_files, remove_files,
             add_acceptance, remove_acceptance,
             add_deps, remove_deps,
             add_consult_personas, remove_consult_personas,
             autonomy, by, as_json):
    """Edit fields on an existing WP. Mutates the JSONL line; appends a history event."""
    root_path = Path(root).resolve() if root else find_brains_build_root()
    wps_state = load_wp_state(root_path)
    if wp_id not in wps_state:
        _err(f"WP {wp_id} not found", as_json, 1)
    wp = wps_state[wp_id]

    updates: dict = {}
    diffs: list[str] = []  # human-readable changes for the history event

    if title is not None and title != wp.title:
        updates["title"] = title
        diffs.append(f"title: {wp.title!r} -> {title!r}")
    if workstream is not None and workstream != wp.workstream:
        updates["workstream"] = workstream
        diffs.append(f"workstream: {wp.workstream!r} -> {workstream!r}")
    if deliverable_id is not None and deliverable_id != wp.deliverable_id:
        updates["deliverable_id"] = deliverable_id
        diffs.append(f"deliverable_id: {wp.deliverable_id!r} -> {deliverable_id!r}")
    if tier is not None:
        new_tier = WPTier(int(tier))
        if new_tier != wp.tier:
            updates["tier"] = new_tier
            diffs.append(f"tier: {wp.tier.value} -> {new_tier.value}")
    if executor_persona is not None and executor_persona != wp.executor_persona:
        updates["executor_persona"] = executor_persona
        diffs.append(f"executor_persona: {wp.executor_persona!r} -> {executor_persona!r}")
    if spec is not None and spec != wp.spec:
        updates["spec"] = spec
        diffs.append("spec: updated")

    if add_files or remove_files:
        new_files = _set_list(wp.spec_files, add_files, remove_files)
        if new_files != wp.spec_files:
            updates["spec_files"] = new_files
            diffs.append(f"spec_files: {wp.spec_files} -> {new_files}")
    if add_acceptance or remove_acceptance:
        new_accept = _set_list(wp.acceptance, add_acceptance, remove_acceptance)
        if new_accept != wp.acceptance:
            updates["acceptance"] = new_accept
            diffs.append(f"acceptance: {wp.acceptance} -> {new_accept}")
    if add_deps or remove_deps:
        # Validate add_deps against existing WPs (Finding #1 logic, applied to edit).
        existing_ids = {w.id for w in load_work_packages(root_path)}
        orphans = [d for d in add_deps if d not in existing_ids and d != wp_id]
        if orphans:
            _err(f"Unknown WP IDs in --add-dep: {orphans}", as_json, 2)
        new_deps = _set_list(wp.depends_on, add_deps, remove_deps)
        if new_deps != wp.depends_on:
            updates["depends_on"] = new_deps
            diffs.append(f"depends_on: {wp.depends_on} -> {new_deps}")
    if add_consult_personas or remove_consult_personas:
        new_consult = _set_list(wp.consult, add_consult_personas, remove_consult_personas)
        if new_consult != wp.consult:
            updates["consult"] = new_consult
            diffs.append(f"consult: {wp.consult} -> {new_consult}")

    if autonomy is not None:
        new_autonomy = Autonomy(autonomy)
        if new_autonomy != wp.autonomy:
            updates["autonomy"] = new_autonomy
            diffs.append(f"autonomy: {wp.autonomy.value} -> {new_autonomy.value}")

    # Validate tier-1 constraint AFTER all updates merged into current view.
    final_tier = updates.get("tier", wp.tier)
    final_files = updates.get("spec_files", wp.spec_files)
    if final_tier == WPTier.ONE and len(final_files) > 3:
        _err(f"Tier-1 WP must touch <= 3 files; final count would be {len(final_files)}",
             as_json, 2)

    if not updates:
        _err(f"No editable changes provided for {wp_id}.", as_json, 1)

    start = time.monotonic()
    event = "edit: " + "; ".join(diffs)
    updated = update_work_package_fields(root_path, wp_id, updates, by=by, event=event)

    # Audit entry so the edit is reconstructable from audit/ alone (Finding #10).
    write_audit(root_path, AuditEntry(
        wp_id=wp_id,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        persona=by, model="n/a-deterministic",
        tier=int(updated.tier.value),
        runtime_seconds=time.monotonic() - start,
        result="edited",
        inputs_read=[], outputs_written=[],
        notes=event,
    ))

    render_dashboard(root_path)

    payload = {
        "ok": True, "wp_id": wp_id,
        "changes": diffs,
        "next": "Run /build-dispatch when ready (if WP is still in 'defined' state).",
    }
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(f"Edited {wp_id}: {'; '.join(diffs)}")
    sys.exit(0)


if __name__ == "__main__":
    edit_cmd()
