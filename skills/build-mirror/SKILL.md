---
name: build-mirror
description: 'One-way push mirror of the active project''s WPs and sprints to GitHub Issues + Milestones. Use when the user wants work packages visible in GitHub (so dev teams can see/comment on them), or asks "sync to GitHub", "push to GitHub", "mirror this build". Three subcommands: init, push, status.'
---

# Mirror local state to GitHub

The mirror is **mostly one-way** (local → GitHub) with a **read-back pull verb** added in v2.6. Local files remain canonical for writes; the pull verb reconciles a small set of remote signals (issue close/reopen, `bbp:decision` comments) back into local state. Anything else on GitHub is ignored.

## Mapping

| Local concept | GitHub concept |
|---|---|
| WorkPackage | Issue (title `[WP-NNNN] <title>`, body = spec + acceptance + history) |
| Sprint (`sprints/sprint-NN.md`) | Milestone |
| Deliverable | Label `bbp:deliverable-<id>` |
| Workstream | Label `bbp:workstream-<id>` |
| Executor persona | Label `bbp:persona-<id>` |
| Tier | Label `bbp:tier-1` / `bbp:tier-2` |
| WPState | Label `bbp:state-<state>` (also closes issue on `done`, reopens on `blocked`) |
| decisions.md / audit/ / dashboards/ | **Not mirrored** (local-only) |

The `bbp:` prefix namespaces everything platform-managed. You can change it via `--label-prefix`.

## Subcommands

### `init` — configure the mirror

```powershell
python -m build_platform.cli.mirror init `
  --root . `
  --owner shard-BRAINS `
  --repo my-project `
  --label-prefix bbp: `
  --json
```

Writes `github.{enabled, owner, repo, label_prefix}` to `.brains-build/config.yml`. Run `--disable` to turn the mirror off without deleting config.

**Auth:** uses your existing `gh` CLI auth — no token management. If `gh` isn't installed or you're not logged in, `push` will fail with a clear message.

### `push` — reconcile everything

```powershell
python -m build_platform.cli.mirror push --root . --json
python -m build_platform.cli.mirror push --root . --dry-run --json   # preview only
```

`--dry-run` makes NO state-changing gh calls (no label create, no issue create/edit/close/reopen, no milestone create). Read-only probes still run so the plan can show which labels/milestones already exist vs. need creating. Use this before any first push to a public repo — the output enumerates exactly what would land.

Idempotent. On first run:

1. Ensures all platform labels exist on the remote (one-time seed).
2. For each `sprints/sprint-NN.md`, ensures a matching milestone exists.
3. For each WP, creates an issue (or edits the existing one if mapped).
4. Closes the issue if `state=done`; reopens if `state=blocked`.

The wp_id → issue_number and sprint_id → milestone_number maps are persisted at `.brains-build/github-mirror.json`. Second push only edits issues whose state changed.

### `pull` — reconcile remote signals back to local (v2.6)

```powershell
python -m build_platform.cli.mirror pull --root . --json
```

For each WP currently mapped to an issue:

1. **State sync.** Fetches remote issue state via `gh issue view --json state,closedAt,author`. Applies these rules:
   - Remote `closed` + local in (`defined`, `dispatched`, `in_review`) → local transitions to `done`, history event `by=github:<actor>`.
   - Remote `closed` + local already `done` → no-op.
   - Remote `closed` + local `blocked` → **preserved** (manual review). Surfaced in the `transitions` list with a `skipped` field.
   - Remote `open` + local `done` → local transitions to `blocked` (someone reopened the issue; needs review).
   - All other combinations: no-op.

2. **Decision ingestion.** Fetches comments via the REST API (gh issue view doesn't return comment ids). Any comment whose **first line is `bbp:decision`** is parsed and appended to `decisions.md`. Idempotent via `mirror_map.seen_comments[issue_number_str]` — second pull with the same comments is a no-op.

Expected `bbp:decision` comment format:

```text
bbp:decision
title: <one-line decision title>
owner: <persona id or user:name>
decision: <one sentence>
why: <rationale>
alternatives: name1:why rejected; name2:why rejected   (optional)
related-wp: WP-XXXX, WP-YYYY                            (optional)
```

Required fields: `title` and `decision`. Missing either → the comment is ignored.

**Output:**

```json
{
  "ok": true,
  "repo": "shard-BRAINS/demo",
  "remote_states": [{"wp_id": "WP-0001", "issue": 100, "remote_state": "closed", "author": "alice"}, ...],
  "transitions": [{"wp_id": "WP-0001", "from": "defined", "to": "done"}, ...],
  "ingested_decisions": [{"comment_id": 9001, "title": "...", "from_wp": "WP-0002", "from_issue": 101}]
}
```

**When to pull:**

- After a teammate closes a mirrored issue on GitHub (signals the WP is done).
- After a teammate posts a `bbp:decision` comment that should land in `decisions.md`.
- Periodically as part of a cadence (could be wired up via `/build-schedule-scrum`-style routine in a future verb).

**Pull does NOT:** create / edit / close / reopen issues, modify labels, push anything. Read-only on GitHub by design.

### `status` — inspect mirror state

```powershell
python -m build_platform.cli.mirror status --root . --json
```

Reads local config + mirror map only. Does NOT hit the network.

## When to push

- After `/build-package` adds new WPs (so they appear as issues).
- After `/build-dispatch` updates state.
- After `/build-scrum` writes a new sprint recap (creates a milestone).
- Manually any time the user wants the remote in sync.

This is **not** auto-triggered by the other verbs — transient `gh` failures would cascade. Run it explicitly.

## Don't

- Don't edit issues manually on GitHub expecting them to flow back to local — this is one-way. v2.6 will add two-way.
- Don't change `bbp:` labels by hand; the next push will overwrite them.
- Don't push from a project that hasn't been `init`'d — `push` refuses cleanly.
