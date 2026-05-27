---
name: build-loop
description: Auto-dispatch eligible `autonomy=auto` tier-1 work packages in sequence. Stops on first failure. The unattended-execution verb for work the user has pre-authorised.
---

# Auto-dispatch the queue

Run a sequence of tier-1 work packages that the user has explicitly marked `autonomy=auto`. Each WP is dispatched, the diff applied, and the project's test command run. The loop stops on the first failure — the offending WP is left in state `blocked` for human attention.

## When to use

- The user says "run the loop", "auto-dispatch the queue", "burn down the auto WPs", or similar.
- After `/build-package` has tagged one or more WPs with `--autonomy auto`.
- After `/build-scrum` and you want to clear the mechanical work before judgement work resumes.

Do NOT invoke without an explicit request from the user; the loop applies code changes and runs tests without per-step confirmation. The safety boundary is the `autonomy=auto` field, which is opt-in at package time.

## Eligibility (enforced by the CLI)

A WP is eligible only if ALL hold:

1. `state == defined`
2. `autonomy == auto`
3. `tier == 1` — judgement work (tier-2) is never auto-dispatched
4. Every `depends_on` WP is `state == done`

Sorted by WP id ascending; processed sequentially up to `--limit` (default 5).

## Run

Dry-run first to see what will fire:

```powershell
python -m build_platform.cli.loop --root . --dry-run --json
```

Then for real:

```powershell
python -m build_platform.cli.loop --root . --limit 5 --json
```

The CLI:
1. Dispatches each WP via the existing tier-1 path (Ollama → diff validation → `git apply --check`).
2. On a clean diff, immediately runs `dispatch_apply` (which `git apply`s, runs the project's test command, transitions state).
3. Stops on the first failure — the failing WP is left `blocked` with audit entry.
4. Refreshes the dashboard at the end.

## What you do

1. If the user did not pre-confirm, ask once: "About to auto-dispatch N WPs without further confirmation. Proceed?" If they say yes, run. If not, exit.
2. Run the CLI as above with `--json`.
3. Read the response. Surface:
   - WPs successfully dispatched + applied (final state: `in_review`).
   - The WP that stopped the loop, if any, and why.
   - The link to the dashboard.
4. If the loop stopped, do NOT auto-restart. The user decides whether to unblock the failing WP or accept the partial run.

## Don't

- Don't relax the eligibility rules client-side. The CLI is authoritative.
- Don't loop over tier-2 WPs even if the user asks — they require a Claude SME spawn and human verification.
- Don't continue past a failure. The whole point of the safety boundary is "stop on first surprise".
- Don't run without a clean git working tree — uncommitted changes will be tangled with the loop's applies. Surface a warning if `git status --porcelain` is non-empty.
