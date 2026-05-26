---
name: build-mirror
description: One-way push mirror of the active project's WPs and sprints to GitHub Issues + Milestones. Use when the user wants work packages visible in GitHub (so dev teams can see/comment on them), or asks "sync to GitHub", "push to GitHub", "mirror this build". Three subcommands: init, push, status.
---

# Mirror local state to GitHub

The mirror is **one-way** (local → GitHub). Local files stay canonical for writes. GitHub becomes a readable surface for stakeholders without Claude Code. Two-way sync (PR merges close WPs, issue comments → decisions) is planned for v2.6.

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
```

Idempotent. On first run:
1. Ensures all platform labels exist on the remote (one-time seed).
2. For each `sprints/sprint-NN.md`, ensures a matching milestone exists.
3. For each WP, creates an issue (or edits the existing one if mapped).
4. Closes the issue if `state=done`; reopens if `state=blocked`.

The wp_id → issue_number and sprint_id → milestone_number maps are persisted at `.brains-build/github-mirror.json`. Second push only edits issues whose state changed.

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
