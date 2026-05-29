"""`/build-dispatch apply` (v2.5+) — apply an approved tier-1 diff atomically.

Replaces the manual `git apply runs/<wp-id>/proposed.diff` step that
build-dispatch's SKILL.md previously told the user to run. Does:

  1. Verify WP exists and is in state=dispatched.
  2. Verify proposed.diff exists at runs/<wp-id>/proposed.diff.
  3. `git apply --check` — if fails, transition WP to blocked.
  4. `git apply` — apply for real.
  5. Optionally run the project's test command.
  6. Transition WP to in_review (or blocked on test failure).
  7. Write the audit entry. Refresh the dashboard.

Closes Finding #8 from the 2026-05-26 dogfood report.
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import click

from build_platform.audit import AuditEntry, write_audit
from build_platform.paths import find_brains_build_root, state_dir
from build_platform.render_dashboard import render_dashboard
from build_platform.schemas import Autonomy, WPState
from build_platform.state import load_config, load_wp_state, update_wp_state


def _err(msg: str, as_json: bool, code: int) -> None:
    click.echo(json.dumps({"error": msg}) if as_json else f"Error: {msg}", err=True)
    sys.exit(code)


def _emit_ok(payload: dict, as_json: bool, human: str, *, exit_code: int = 0) -> None:
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(human)
    sys.exit(exit_code)


@click.command("apply")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--wp", "wp_id", required=True, help="WP id whose diff to apply.")
@click.option("--no-test", is_flag=True,
              help="Skip running the project test command after apply.")
@click.option("--test-timeout", type=int, default=300, show_default=True,
              help="Seconds before the test command is killed.")
@click.option("--json", "as_json", is_flag=True)
@click.option(
    "--code-review-verdict",
    type=click.Choice(["approve", "request-changes", "reject"]),
    default=None,
    help="Code-review verdict: approve, request-changes, or reject.",
)
@click.option(
    "--code-review-findings-file",
    type=click.Path(exists=False),
    default=None,
    help="Path to a text file with one finding per line.",
)
def apply_cmd(root, wp_id, no_test, test_timeout, as_json,
              code_review_verdict, code_review_findings_file):
    """Apply the approved tier-1 diff for WP-XXXX. Atomic: check, apply, test, transition."""
    root_path = Path(root).resolve() if root else find_brains_build_root()
    config = load_config(root_path)
    wps = load_wp_state(root_path)
    if wp_id not in wps:
        _err(f"WP {wp_id} not found", as_json, 1)
    wp = wps[wp_id]
    if wp.state != WPState.DISPATCHED:
        _err(f"WP {wp_id} is in state {wp.state.value}, expected 'dispatched'",
             as_json, 1)

    # Autonomy gate (WP-0016): auto / review-on-complete WPs require a verdict.
    if (
        wp.autonomy in {Autonomy.REVIEW_ON_COMPLETE, Autonomy.AUTO}
        and code_review_verdict is None
    ):
        _err(
            f"WP {wp_id} has autonomy={wp.autonomy.value} which requires "
            f"--code-review-verdict. Run code review then re-invoke apply "
            f"with --code-review-verdict approve|request-changes|reject.",
            as_json,
            7,
        )

    diff_path = state_dir(root_path) / "runs" / wp_id / "proposed.diff"
    if not diff_path.exists():
        _err(f"No proposed diff at {diff_path}. Run /build-dispatch first.",
             as_json, 1)

    # Load findings from file (if provided)
    findings: list[str] = []
    if code_review_findings_file:
        findings = [
            line for line in
            Path(code_review_findings_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    start = time.monotonic()

    # --- Code-review gate: reject ---
    if code_review_verdict == "reject":
        reason = findings[0] if findings else "no reason"
        update_wp_state(root_path, wp_id, WPState.BLOCKED,
                        by="build-dev-orchestrator",
                        event=f"code-review reject: {reason}")
        _write_audit(root_path, wp, time.monotonic() - start,
                     "rejected_by_code_review", diff_path,
                     code_review_verdict=code_review_verdict,
                     code_review_findings=findings,
                     notes=reason)
        render_dashboard(root_path)
        _err(f"Code-review rejected WP {wp_id}: {reason}", as_json, 5)

    # --- Code-review gate: request-changes ---
    if code_review_verdict == "request-changes":
        if code_review_findings_file is None:
            _err("--code-review-findings-file is required when --code-review-verdict=request-changes",
                 as_json, 1)
        from build_platform.cli import dispatch_request_changes  # noqa: PLC0415
        try:
            payload = dispatch_request_changes.request_changes(
                root_path, wp_id, Path(code_review_findings_file)
            )
        except (ValueError, FileNotFoundError) as exc:
            _err(str(exc), as_json, 1)
        human = (
            f"{wp_id} returned to defined; {payload['findings_count']} finding(s) recorded."
            " Re-dispatch when fixes are in."
        )
        _emit_ok(payload, as_json, human, exit_code=6)

    # 1. Dry-run check
    check = subprocess.run(
        ["git", "apply", "--check", str(diff_path)],
        cwd=root_path, capture_output=True, text=True,
    )
    if check.returncode != 0:
        update_wp_state(root_path, wp_id, WPState.BLOCKED,
                        by="build-dev-orchestrator",
                        event=f"git apply --check failed: {check.stderr.strip()}")
        _write_audit(root_path, wp, time.monotonic() - start, "check_failed",
                     diff_path, notes=check.stderr.strip())
        render_dashboard(root_path)
        _err(f"git apply --check failed:\n{check.stderr.strip()}", as_json, 3)

    # 2. Apply for real
    apply = subprocess.run(
        ["git", "apply", str(diff_path)],
        cwd=root_path, capture_output=True, text=True,
    )
    if apply.returncode != 0:
        update_wp_state(root_path, wp_id, WPState.BLOCKED,
                        by="build-dev-orchestrator",
                        event=f"git apply failed unexpectedly: {apply.stderr.strip()}")
        _write_audit(root_path, wp, time.monotonic() - start, "apply_failed",
                     diff_path, notes=apply.stderr.strip())
        render_dashboard(root_path)
        _err(f"git apply failed unexpectedly:\n{apply.stderr.strip()}", as_json, 3)

    # 3. Optionally run the project's test command
    test_status = "skipped"
    test_output = ""
    if not no_test and config.project.test_command:
        try:
            test = subprocess.run(
                config.project.test_command.split(),
                cwd=root_path, capture_output=True, text=True,
                timeout=test_timeout,
            )
            test_output = (test.stdout + test.stderr)[-2000:]
            test_status = "passed" if test.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            test_status = "timeout"
            test_output = f"Test command timed out after {test_timeout}s"

        if test_status != "passed":
            update_wp_state(root_path, wp_id, WPState.BLOCKED,
                            by="build-qa-sme",
                            event=f"tests {test_status} after apply (see audit)")
            _write_audit(root_path, wp, time.monotonic() - start,
                         f"tests_{test_status}", diff_path,
                         tests_run=[(config.project.test_command, test_status)],
                         notes=test_output)
            render_dashboard(root_path)
            _err(f"Tests {test_status}:\n{test_output}", as_json, 4)

    # 4. Success path — transition to in_review
    update_wp_state(root_path, wp_id, WPState.IN_REVIEW,
                    by="build-dev-orchestrator",
                    event=f"diff applied; tests {test_status}; awaiting QA verification")
    _write_audit(root_path, wp, time.monotonic() - start, "applied", diff_path,
                 tests_run=([(config.project.test_command, test_status)]
                            if test_status != "skipped" else []),
                 code_review_verdict=code_review_verdict,
                 code_review_findings=findings,
                 notes="Tier-1 diff applied. Awaiting QA acceptance verification.")

    render_dashboard(root_path)

    payload = {
        "ok": True, "wp_id": wp_id, "tests": test_status,
        "applied_from": str(diff_path),
        "next": "QA SME verifies acceptance criteria.",
    }
    _emit_ok(payload, as_json,
             f"{wp_id} diff applied. Tests: {test_status}. State -> in_review. "
             f"Next: QA SME verifies acceptance.")


def _write_audit(
    project_root: Path,
    wp,
    runtime: float,
    result: str,
    diff_path: Path,
    *,
    tests_run=None,
    notes: str = "",
    code_review_verdict: str | None = None,
    code_review_findings: list[str] | None = None,
) -> None:
    write_audit(project_root, AuditEntry(
        wp_id=wp.id,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        persona="build-dev-orchestrator",
        model="n/a-deterministic",
        tier=int(wp.tier.value),
        runtime_seconds=runtime,
        result=result,
        inputs_read=[str(diff_path.relative_to(project_root))],
        outputs_written=[],  # could parse diff to enumerate; deferred
        tests_run=tests_run or [],
        notes=notes,
        code_review_verdict=code_review_verdict,
        code_review_findings=code_review_findings or [],
    ))


if __name__ == "__main__":
    apply_cmd()
