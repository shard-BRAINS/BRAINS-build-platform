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

3. The CLI returns one of two shapes:

### Tier-1 (Ollama) response
```json
{ "ok": true, "wp_id": "WP-X", "tier": 1, "diff": "<path>", "next": "review and apply" }
```

What you do:
- Read the diff at the returned path.
- Spawn `build-dev-orchestrator` to review the diff against the WP spec.
- Verdict cases:
  - **approve** → apply the diff with `git apply <path>` (or manual Edit/Write equivalent), run tests, spawn `build-qa-sme` to verify acceptance, then update state.
  - **request changes** → write feedback to `.brains-build/runs/<wp-id>/review.md` and re-run the dispatch CLI (it picks up the feedback on next attempt).
  - **reject** → re-tag the WP as tier-2 via a new `/build-package` invocation; mark the current WP as blocked.

### Tier-2 (Claude subagent) response
```json
{ "ok": true, "wp_id": "WP-X", "tier": 2, "brief": "<path>", "next": "Spawn <persona> subagent with this brief" }
```

What you do:
- Read the brief.
- Spawn the named executor persona subagent (e.g., `build-backend-sme`) with the brief path as its primary input.
- When the subagent returns its Result block, spawn `build-qa-sme` to verify acceptance.
- If WP is flagged sensitive (auth, data, deps), spawn `build-security-sme` in parallel with QA.
- If QA verdict = pass and Security ≠ block: mark WP `done` (update state via CLI invocation under the hood); write audit entry; refresh dashboard.
- If QA fails: mark WP `blocked` with QA findings; refresh dashboard.

## Always at end

```powershell
python -m build_platform.cli.dashboard --root . --json
```

## Don't

- Don't apply diffs without Dev Orch review.
- Don't mark `done` without QA verdict.
- Don't skip Security on sensitive WPs.
