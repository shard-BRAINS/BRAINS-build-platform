---
name: build-dispatch
description: Execute a work package. Tier-1 routes through Ollama and Dev Orchestrator review; tier-2 emits a brief and spawns the assigned executor SME subagent.
---

# Dispatch a work package

## Flow

1. **Identify the WP.** If the user said "dispatch next", run `python -m build_platform.cli.status --json` and pick the first `defined` WP whose `depends_on` are all `done`.
2. **Run the dispatch CLI:**

```powershell
python -m build_platform.cli.dispatch --root . --wp WP-XXXX --json
```

1. The CLI returns one of two shapes:

### Tier-1 (Ollama) response

```json
{ "ok": true, "wp_id": "WP-X", "tier": 1, "diff": "<path>", "next": "review and apply" }
```

What you do:

- Read the diff at the returned path.
- Spawn `build-dev-orchestrator` to review the diff against the WP spec.
- Verdict cases:
  - **approve** → run the apply CLI to atomically `git apply --check`, apply, run the project's test command, transition the WP to `in_review`, write the audit entry, and refresh the dashboard:

    ```powershell
    python -m build_platform.cli.dispatch_apply --root . --wp WP-XXXX --json
    ```

    Then spawn `build-qa-sme` to verify acceptance criteria.
  - **request changes** → write feedback to `.brains-build/runs/<wp-id>/review.md` and re-run the dispatch CLI (it picks up the feedback on next attempt).
  - **reject** → run the reject CLI to atomically transition + audit:

    ```powershell
    python -m build_platform.cli.dispatch_reject --root . --wp WP-XXXX --reason "..." --json
    # Or, if the WP should be re-packaged as tier-2:
    python -m build_platform.cli.dispatch_reject --root . --wp WP-XXXX --reason "..." --retier --json
    ```

### Tier-2 (Claude subagent) response

```json
{ "ok": true, "wp_id": "WP-X", "tier": 2, "brief": "<path>", "next": "Spawn <persona> subagent with this brief" }
```

What you do:

- Read the brief.
- Spawn the named executor persona subagent (e.g., `build-backend-sme`) with the brief path as its primary input.
- When the subagent returns its Result block:
  1. Spawn `build-code-review-sme` (read-only) to verify architectural fit, style, and codebase consistency. Verdicts: **approve** → continue; **request-changes** → return to executor with the findings; **reject** → mark WP `blocked` with the rejection notes.
  2. On code-review approve, spawn `build-qa-sme` to verify acceptance criteria.
  3. If WP is flagged sensitive (auth, data, deps), spawn `build-security-sme` in parallel with QA.
- If code-review approved, QA verdict = pass, and Security ≠ block: mark WP `done` (update state via CLI invocation); write audit entry; refresh dashboard.
- If QA fails: mark WP `blocked` with QA findings; refresh dashboard.

### Escalating to the Debug SME

A second failure on the same WP is evidence that the problem is not the one being solved. This is enforced, not left to judgement: every WP carries a `failures` count, and at 2 the dispatch CLI **refuses** with exit code 7 rather than spending a third identical attempt.

```json
{ "error": "WP-0007 has failed 2 times under build-backend-sme. Hand it to build-debug-sme ..." }
```

What increments the count: tier-1 dispatch errors, code-review reject, code-review request-changes, failed `git apply`, failed tests, and any `transition --failure`. What doesn't: `dispatch_reject --retier` (a packaging correction, not a failed attempt) and ordinary state moves.

When you hit exit 7:

```powershell
python -m build_platform.cli.package_edit --root . --wp WP-XXXX --executor build-debug-sme --json
python -m build_platform.cli.dispatch --root . --wp WP-XXXX --json
```

Then spawn `build-debug-sme` with the brief and both failure records. It returns a Diagnosis block, not a retry.

Two related cases the counter cannot see on its own:

- **QA fails a WP** → record it with `transition --to blocked --by build-qa-sme --failure` so the attempt actually counts. Without `--failure` the WP is blocked but the escalation never fires.
- **The acceptance criterion is "bug X no longer reproduces"** → it should already carry `build-debug-sme` as its executor from `/build-package`. Re-assign with `package_edit` if not.

`--force` bypasses the gate. Use it only when the failures were environmental (Ollama down, a dirty tree) rather than a genuine failure to solve the problem.

The Debug SME may report the cause as unproven. That is a valid outcome — mark the WP `blocked` with the diagnosis and surface it to the user. A speculative fix that makes the symptom vanish is worse than a blocked WP.

### Autonomy modes (`autonomy` field on each WP)

- `manual` (default) — every step pauses for user confirmation. Safest. Use for unfamiliar work or judgement-heavy tasks.
- `review-on-complete` — executor runs to completion; user reviews + approves before the next WP. Code-review SME is always run.
- `auto` (tier-1 only) — fully unattended via `/build-loop`. Code-review SME is run; failures stop the loop and block the WP. Only tier-1 WPs can be `auto` — judgement work always needs a human pass.

## Always at end

```powershell
python -m build_platform.cli.dashboard --root . --json
```

## Don't

- Don't apply diffs without Dev Orch review.
- Don't mark `done` without QA verdict.
- Don't skip Security on sensitive WPs.
- Don't `--force` past exit 7 to get moving. Two failures is the Debug SME's trigger, not a reason to try harder.
- Don't block a WP on a QA failure without `--failure` — an uncounted failure is one the platform cannot escalate.
