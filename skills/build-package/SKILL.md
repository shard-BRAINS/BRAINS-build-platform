---
name: build-package
description: Define one or more work packages for a deliverable. Spawns the Dev Orchestrator subagent to decompose; writes WPs via the CLI.
---

# Define work packages

## Flow

1. **Confirm target.** Which deliverable id are we breaking down?
2. **Spawn `build-dev-orchestrator`** with: project.yml, deliverables.yml, workstreams.yml, current work-packages.jsonl, target deliverable id.
3. **Dev Orch proposes WPs** — title, workstream, executor_persona, tier, spec, spec_files, acceptance, depends_on, consult. For each WP, Dev Orch also outputs the exact `python -m build_platform.cli.package` invocation.
4. **Confirm with user.** Show the proposed list; accept edits.
5. **Run each invocation:**

```powershell
python -m build_platform.cli.package `
  --root . `
  --title "<title>" `
  --workstream backend `
  --deliverable D-auth `
  --tier 1 `
  --executor build-backend-sme `
  --spec "<spec text>" `
  --file "src/auth/login.py" `
  --accept "tests pass" --accept "endpoint returns 200" `
  --json
```

6. **Refresh dashboard:**

```powershell
python -m build_platform.cli.dashboard --root . --json
```

## Tier-1 checklist (Dev Orch enforces)

A WP is tier-1 ONLY if:
1. Touches ≤ 3 files, total < 50KB
2. Single well-defined transformation
3. Acceptance is objectively checkable
4. No new design decisions

Anything failing one criterion is tier-2.

## Editing an existing WP

If a user wants to change a WP that's already in the log (rename, re-tier, add deps, swap executor), use the `package_edit` CLI rather than re-creating:

```powershell
python -m build_platform.cli.package_edit --root . --wp WP-0001 --title "Renamed" --json
python -m build_platform.cli.package_edit --root . --wp WP-0001 --tier 1 --add-file src/y.py --remove-file src/x.py --json
python -m build_platform.cli.package_edit --root . --wp WP-0001 --add-dep WP-0002 --json
```

The edit verb refuses orphan deps, enforces the tier-1 ≤3-files cap, appends a history event, and writes an audit entry. State (`defined`, `dispatched`, etc.) cannot be edited here — use `dispatch`, `dispatch_apply`, or `dispatch_reject` for state transitions.

## Don't

- Don't append to work-packages.jsonl directly. The CLI handles schema validation, id assignment, and tier-1 checks.
- Don't try to edit `state` via `package_edit` — state has its own transition verbs.
