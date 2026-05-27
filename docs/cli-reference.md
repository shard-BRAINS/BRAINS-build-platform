# CLI Reference

Every `build-*` skill is a thin orchestration layer that calls one of these CLI entry points. Skills are user-facing prose; CLIs are deterministic.

All CLIs accept `--root <path>` (defaults to `.brains-build/` discovered upward from cwd) and `--json` (machine-readable output). All emit non-zero exit codes on error and a `{"error": "..."}` JSON payload when `--json` is set.

---

## `python -m build_platform.cli.init`

Initialize a new build project. Refuses if `.brains-build/` already exists.

```powershell
python -m build_platform.cli.init `
  --root . `
  --name "<name>" `
  --mission "<one sentence>" `
  --stack "<stack-element>" --stack "<another>" `
  --constraint "<absolute constraint>" `
  --deliverable "D-id:Title:Why:Acceptance1;Acceptance2" `
  --json
```

**Options:**

| Option | Required | Repeatable | Description |
|---|---|---|---|
| `--root` | no | — | Project root (default: current dir) |
| `--name` | yes | — | Project name |
| `--mission` | yes | — | One-sentence mission |
| `--stack` | yes | yes | Stack element (e.g., `python`, `fastapi`) |
| `--constraint` | no | yes | Absolute constraint (e.g., `no GPL`) |
| `--deliverable` | yes | yes | Format: `id:title:why:accept1;accept2` |
| `--json` | no | — | Emit JSON output |

**Output (success):** `{"ok": true, "message": "...", "root": "..."}`

**Writes:** `.brains-build/project.yml`, `deliverables.yml`, `workstreams.yml` (5 default workstreams), `config.yml`, empty `work-packages.jsonl`, seeded `decisions.md`.

**Exit codes:** `0` success · `1` already initialized · `2` invalid deliverable format.

---

## `python -m build_platform.cli.package`

Add a work package. Heavy decomposition is the Dev Orchestrator subagent's job; this CLI validates the shape and writes.

```powershell
python -m build_platform.cli.package `
  --root . `
  --title "<imperative title>" `
  --workstream backend `
  --deliverable D-auth `
  --tier 1 `
  --executor build-backend-sme `
  --spec "<concrete spec>" `
  --file "src/auth/login.py" --file "src/auth/types.py" `
  --accept "tests pass" --accept "returns 200" `
  --depends-on WP-0010 `
  --consult build-security-sme `
  --json
```

**Options:**

| Option | Required | Repeatable | Description |
|---|---|---|---|
| `--title` | yes | — | Imperative title |
| `--workstream` | yes | — | Workstream id |
| `--deliverable` | yes | — | Deliverable id |
| `--tier` | yes | — | `1` or `2` |
| `--executor` | yes | — | Persona id (e.g., `build-backend-sme`) |
| `--spec` | yes | — | Spec text |
| `--file` | no | yes | File in scope (tier-1: ≤ 3 files) |
| `--accept` | yes | yes | Acceptance criterion |
| `--depends-on` | no | yes | WP id this depends on |
| `--consult` | no | yes | Persona id to consult during dispatch |
| `--created-by` | no | — | Defaults to `build-dev-orchestrator` |

**Output (success):** `{"ok": true, "wp_id": "WP-NNNN"}`

**Exit codes:** `0` success · `2` tier-1 violation (> 3 files).

---

## `python -m build_platform.cli.package_edit`

Edit fields on an existing WP. Closes Finding #7 — pre-fix workaround was hand-editing `work-packages.jsonl`. Appends a history event and writes an audit entry.

```powershell
python -m build_platform.cli.package_edit --root . --wp WP-0001 --title "New title" --json
python -m build_platform.cli.package_edit --root . --wp WP-0001 --tier 1 --add-file src/extra.py --json
python -m build_platform.cli.package_edit --root . --wp WP-0001 --add-dep WP-0002 --remove-dep WP-0099 --json
```

**Editable fields:** `title`, `workstream`, `deliverable_id` (`--deliverable`), `tier`, `executor_persona` (`--executor`), `spec`.

**Editable lists** (use add/remove pairs, repeatable):
- `spec_files` — `--add-file PATH` / `--remove-file PATH`
- `acceptance` — `--add-accept TEXT` / `--remove-accept TEXT`
- `depends_on` — `--add-dep WP-X` / `--remove-dep WP-X`
- `consult` — `--add-consult PERSONA` / `--remove-consult PERSONA`

**NOT editable:** `id`, `created_by`, `created_at`, `state`, `history`. State has its own transition paths (`dispatch`, `dispatch_apply`, `dispatch_reject`).

**Validation:**
- `--add-dep` rejects WP IDs that don't exist (same as `package` CLI).
- If the WP would end up tier-1 with > 3 files after the edit, the edit is refused.

**Output:**
```json
{
  "ok": true,
  "wp_id": "WP-0001",
  "changes": ["title: 'Original' -> 'Renamed'"],
  "next": "Run /build-dispatch when ready (if WP is still in 'defined' state)."
}
```

**Exit codes:** `0` success · `1` WP not found / no changes provided · `2` validation failure (orphan dep, tier-1 file overflow).

---

## `python -m build_platform.cli.dispatch`

Execute a work package. Routes to Ollama (tier-1) or emits a Claude subagent brief (tier-2).

```powershell
python -m build_platform.cli.dispatch --root . --wp WP-0042 --json
```

**Options:**

| Option | Required | Description |
|---|---|---|
| `--wp` | yes | WP id to dispatch |

**Preconditions:** WP must be in state `defined`. All `depends_on` WPs must be in state `done`. For tier-1, Ollama must be reachable AND `tier1_default` + `summarizer` models must be pulled.

**Output — tier-1:**
```json
{
  "ok": true,
  "wp_id": "WP-0042",
  "tier": 1,
  "diff": "<path to runs/WP-0042/proposed.diff>",
  "next": "review and apply"
}
```

**Output — tier-2:**
```json
{
  "ok": true,
  "wp_id": "WP-0042",
  "tier": 2,
  "brief": "<path to runs/WP-0042/tier2-brief.md>",
  "warnings": [],
  "next": "Spawn build-backend-sme subagent with this brief"
}
```

`warnings` is populated when the persona's subagent file is missing at `~/.claude/agents/build/<persona>.md`. Run `install.ps1` from the build-platform repo to install all persona definitions. Brief generation still succeeds either way (you can read the brief and spawn the persona manually).

**Side effects:** Updates WP state to `dispatched`. Appends a history event. Writes an audit entry at `audit/<wp-id>-<ts>.md`. Refreshes the dashboard.

**Tier-1 failure modes:**
- Scope > 50KB → `DispatchError` raised before Ollama call. WP state unchanged.
- Diff validation fails twice → WP transitioned to `blocked`. Exit 3.
- Ollama unreachable → Exit 2 with `ollama pull` / `ollama serve` guidance.

**Tier-1 retry behavior** (configured via `.brains-build/config.yml`):
- `max_retries: 3` for transient network errors (ConnectError, timeouts). Default 3.
- `retry_backoff_base_seconds: 1.0` — actual backoff is `base * 2**attempt` (1s, 2s, 4s).
- HTTP status errors (e.g., 4xx, 5xx) are NOT retried — they need user attention.

**Exit codes:** `0` success · `1` WP not found / wrong state / unmet deps · `2` Ollama preflight failed · `3` dispatch failed.

---

## `python -m build_platform.cli.dispatch_apply`

Apply an approved tier-1 diff atomically: `git apply --check`, apply, optionally run the project's test command, transition the WP to `in_review`, write an audit entry, refresh the dashboard. Closes the tier-1 review loop without manual `git apply` invocations.

```powershell
python -m build_platform.cli.dispatch_apply --root . --wp WP-0001 --json
python -m build_platform.cli.dispatch_apply --root . --wp WP-0001 --no-test --json
python -m build_platform.cli.dispatch_apply --root . --wp WP-0001 --test-timeout 600 --json
```

**Preconditions:** WP must be in state `dispatched`. `runs/<wp-id>/proposed.diff` must exist (created by `cli.dispatch`).

**Options:**

| Option | Default | Description |
|---|---|---|
| `--wp` | required | WP id whose diff to apply |
| `--no-test` | — | Skip running the project's test command after apply |
| `--test-timeout` | 300 | Seconds before test command is killed |

**Exit codes:** `0` apply + tests succeeded (or tests skipped); WP → `in_review` · `1` WP not found / wrong state / no diff · `3` `git apply --check` failed (WP → `blocked`) · `4` tests failed after apply (WP → `blocked`).

**Output (success):**
```json
{
  "ok": true,
  "wp_id": "WP-0001",
  "tests": "passed",
  "applied_from": ".brains-build/runs/WP-0001/proposed.diff",
  "next": "QA SME verifies acceptance criteria."
}
```

**Behavior on failure:**
- `git apply --check` fails → WP transitioned to `blocked` with the check stderr in the history event. Audit entry result=`check_failed`. Source tree untouched.
- `git apply` itself fails (rare after a passing --check) → WP transitioned to `blocked`. Audit result=`apply_failed`.
- Test command fails or times out → WP transitioned to `blocked` (diff stays applied). Audit result=`tests_failed` / `tests_timeout`.

---

## `python -m build_platform.cli.dispatch_reject`

Dev Orchestrator rejects a dispatched WP. Atomically transitions state, writes an audit entry, refreshes the dashboard. Closes Finding #10 from the 2026-05-26 dogfood — state transitions outside `cli.dispatch` previously skipped audit-writing.

```powershell
python -m build_platform.cli.dispatch_reject `
  --root . --wp WP-0001 `
  --reason "out-of-scope changes; tier-1 prompt was too permissive" `
  --json
```

**Options:**

| Option | Default | Description |
|---|---|---|
| `--wp` | required | WP id to reject |
| `--reason` | required | One-line reason. Recorded in WP history + audit notes |
| `--retier` | — | Transition to `defined` instead of `blocked`. Use when the WP needs re-packaging as tier-2 |

**Preconditions:** WP must be in state `dispatched`.

**Output:**
```json
{
  "ok": true, "wp_id": "WP-0001",
  "new_state": "blocked",
  "reason": "out-of-scope changes ...",
  "next": "WP is blocked. Resolve via /build-decision or new WP."
}
```

**Exit codes:** `0` success · `1` WP not found / wrong state.

---

## `python -m build_platform.cli.scrum`

Assemble the weekly scrum brief and recap stub. The PMO Lead subagent fills in the qualitative sections.

```powershell
python -m build_platform.cli.scrum --root . --json
```

**Output:**
```json
{
  "ok": true,
  "sprint_number": 3,
  "recap_stub": "<path to sprints/sprint-03.md>",
  "next": "Spawn build-pmo-lead subagent to fill in the recap stub."
}
```

**What the CLI writes** (raw diff embedded in the stub):
- WPs created / dispatched / done / blocked since last scrum
- Git commits since the same timestamp (if the project is a git repo)
- Five empty sections for the PMO Lead to fill: Progress · Blockers · Velocity · Re-prioritization · Next up

**Side effects:** Refreshes the dashboard.

---

## `python -m build_platform.cli.schedule_scrum`

Generate the routine spec for a weekly scrum reminder, and persist the schedule intent in `config.yml`. **Does not** create the remote routine itself — that's the `schedule` skill's job. Output includes the cron expression and routine prompt to pass through.

```powershell
python -m build_platform.cli.schedule_scrum `
  --root . `
  --day mon --hour 9 --minute 0 `
  --timezone UTC `
  --json
```

**Options:**

| Option | Required | Default | Description |
|---|---|---|---|
| `--day` | no | `mon` | One of `mon, tue, wed, thu, fri, sat, sun` |
| `--hour` | no | `9` | 0-23 |
| `--minute` | no | `0` | 0-59 |
| `--timezone` | no | `UTC` | IANA tz id (informational) |
| `--routine-id` | no | — | Record the id returned by `/schedule` after creation |
| `--disable` | no | — | Mark `scrum_schedule.enabled = False` in config (does not delete the remote routine) |

**Output:**
```json
{
  "ok": true,
  "project": "Demo",
  "project_root": "C:\\path\\to\\project",
  "enabled": true,
  "cron": "0 9 * * 1",
  "timezone": "UTC",
  "routine_id": null,
  "routine_prompt": "You are the BRAINS Build Platform scrum reminder...",
  "next": "Pass cron + routine_prompt to /schedule to create the routine. Then re-run with --routine-id <id> to record it."
}
```

**Why the routine only sends a reminder:** remote routines created by `/schedule` run in Claude's cloud and cannot read the local `.brains-build/`. So the routine sends a `PushNotification` reminding the user to run `/build-scrum` themselves. True autonomous remote scrum requires the v2 GitHub mirror.

**Side effects:** Writes `scrum_schedule.{enabled, cron, timezone, routine_id}` to `.brains-build/config.yml`.

**Exit codes:** `0` success · `2` invalid day/hour/minute.

---

## `python -m build_platform.cli.status`

Read-only query of project or specific WP.

```powershell
python -m build_platform.cli.status --root . --json
python -m build_platform.cli.status --root . --wp WP-0042 --json
```

**Output (project summary):**
```json
{
  "project": "Demo",
  "total_wps": 12,
  "by_state": {"defined": 3, "dispatched": 2, "done": 7}
}
```

**Output (single WP):** Full WorkPackage as JSON (matches `schemas.WorkPackage`).

---

## `python -m build_platform.cli.decision`

Append a decision entry to `decisions.md`.

```powershell
python -m build_platform.cli.decision --root . `
  --title "Use Argon2 for password hashing" `
  --owner build-security-sme `
  --decision "Argon2id with t=3, m=64MB, p=4" `
  --why "OWASP 2024 recommendation; prior bcrypt instances flagged" `
  --alternative "bcrypt:weaker, legacy" `
  --alternative "scrypt:less library support" `
  --related-wp WP-0041 `
  --audit-link "audit/WP-0041-20260525T1402.md" `
  --json
```

**Options:**

| Option | Required | Repeatable | Description |
|---|---|---|---|
| `--title` | yes | — | One-line decision title |
| `--owner` | yes | — | Persona id or `user:<name>` |
| `--decision` | yes | — | One-sentence decision |
| `--why` | yes | — | Rationale |
| `--alternative` | no | yes | Format: `name:why rejected` |
| `--related-wp` | no | yes | WP id |
| `--audit-link` | no | — | Path to related audit entry |

**Output:** `{"ok": true, "decision_date": "2026-05-25", "title": "..."}`

---

## `python -m build_platform.cli.mirror`

One-way push mirror of WPs + sprints to GitHub Issues + Milestones. Uses your existing `gh` CLI auth. Click group with three subcommands: `init`, `push`, `status`.

### `mirror init`

```powershell
python -m build_platform.cli.mirror init `
  --root . --owner shard-BRAINS --repo my-project --json
```

**Options:** `--owner` (required), `--repo` (required), `--label-prefix` (default `bbp:`), `--disable` (turn the mirror off without losing config).

Writes `github.{enabled, owner, repo, label_prefix}` to `.brains-build/config.yml`.

### `mirror push`

```powershell
python -m build_platform.cli.mirror push --root . --json
python -m build_platform.cli.mirror push --root . --dry-run --json
```

**Options:** `--dry-run` (preview without making state-changing gh calls; read-only probes still run).

Reconciles everything. On first run, seeds platform labels (state-*, tier-1/2, workstream-*, deliverable-*, persona-*) and creates a milestone per sprint file. For each WP, creates an issue or edits the mapped one. Closes on `state=done`, reopens on `state=blocked`. Persists wp_id → issue_number map at `.brains-build/github-mirror.json`. Idempotent.

**Dry-run output** (--dry-run):
```json
{
  "ok": true, "dry_run": true, "repo": "shard-BRAINS/demo",
  "labels": {"to_create": ["bbp:state-defined", ...], "already_present": [], "total_target": 14},
  "sprints": [],
  "wps": [{"wp_id": "WP-0001", "issue": null, "action": "create", "state": "defined", "post_action": null}],
  "counts": {"wps_to_create": 1, "wps_to_edit": 0, "wps_to_close": 0, "wps_to_reopen": 0, "labels_to_create": 14, "sprints_to_create": 0}
}
```

**Output:**
```json
{
  "ok": true,
  "repo": "shard-BRAINS/my-project",
  "wps_pushed": 7,
  "sprints_milestoned": 2,
  "issues": [{"wp_id": "WP-0001", "issue": 100}, ...],
  "last_synced_at": "2026-05-26T..."
}
```

**Exit codes:** `0` success · `2` mirror disabled or `gh` failure.

### `mirror status`

```powershell
python -m build_platform.cli.mirror status --root . --json
```

Reads local config + mirror map only — does not hit the network. Returns `{enabled, owner, repo, label_prefix, last_synced_at, wps_mirrored, sprints_mirrored, labels_seeded}`.

### Mapping reference

| Local | GitHub |
|---|---|
| `WorkPackage` | Issue |
| `sprints/sprint-NN.md` | Milestone |
| `Deliverable` / `Workstream` / `Executor persona` / `Tier` / `WPState` | Labels (prefixed) |
| `decisions.md` / `audit/` / `dashboards/` | Not mirrored |

The mirror is **one-way**. Manual edits on GitHub won't flow back to local — that's v2.6.

---

## `python -m build_platform.cli.portfolio`

Cross-project portfolio. Click group with subcommands `register`, `unregister`, `list`, `view`. Registry lives at `~/.brains-build-portfolio.yml`.

### `portfolio register <path>`

Add a project to the registry. Validates that the path contains `.brains-build/project.yml`. Idempotent.

```powershell
python -m build_platform.cli.portfolio register c:\path\to\project --json
```

**Exit codes:** `0` success · `2` not a build project.

### `portfolio unregister <path>`

Remove a path from the registry. Does not delete the project itself.

**Exit codes:** `0` success · `1` not registered.

### `portfolio list`

```powershell
python -m build_platform.cli.portfolio list --json
```

Returns `{ok, count, projects, registry}`. No project state is loaded.

### `portfolio view`

```powershell
python -m build_platform.cli.portfolio view --format both --json
```

**Options:**

| Option | Default | Description |
|---|---|---|
| `--format` | `md` | One of `md`, `html`, `both` |
| `--out` | — | Write rendered view to this path (overrides default location) |

**Default destinations:**
- `md` → stdout
- `html` → `~/brains-build-portfolio.html`
- `both` → `~/brains-build-portfolio.{md,html}`

**Output (--json):**
```json
{
  "ok": true,
  "count": 3,
  "written": {"md": "~/brains-build-portfolio.md", "html": "~/brains-build-portfolio.html"},
  "rows": [
    {
      "path": "c:/path/to/alpha",
      "name": "Alpha",
      "mission": "Build alpha",
      "deliverables_done": 1, "deliverables_total": 3, "progress_pct": 33,
      "wps_active": 4, "wps_blocked": 0, "wps_done": 7,
      "last_activity": "2026-05-26T08:42:11+00:00",
      "dashboard": "c:/path/to/alpha/.brains-build/dashboards/current.md"
    }
  ]
}
```

Projects whose `.brains-build/` is missing render as `{"path": "...", "error": "not a build project"}` — view never crashes on stale registry entries.

---

## `python -m build_platform.cli.persona`

Click group with three subcommands: `register`, `list`, `install`. Manages custom personas beyond the default 8.

### `persona register`

```powershell
python -m build_platform.cli.persona register `
  --root . `
  --id build-data-sme `
  --tier executor `
  --description "Data engineering SME for pipelines and warehousing" `
  --mission "Execute tier-2 data work packages per the WP brief." `
  --json
```

**Options:**

| Option | Required | Default | Description |
|---|---|---|---|
| `--id` | yes | — | Must match `^build-[a-z][a-z0-9-]+[a-z0-9]$` |
| `--tier` | no | `executor` | One of `leadership`, `executor`, `read-only` |
| `--description` | yes | — | One-line description (for Claude skill matching) |
| `--mission` | yes | — | One-paragraph mission |
| `--when-invoked` | no | sensible default | Free-form "when invoked" prose |
| `--model` | no | tier default | Override model id |
| `--tools` | no | tier default | Comma-separated tool list |
| `--step` | no | — | Repeatable; append to "What to do" |
| `--rule` | no | — | Repeatable; append to "Rules of engagement" |
| `--force` | no | — | Overwrite if persona already exists |

**Tier defaults:**

| Tier | Model | Tools |
|---|---|---|
| `leadership` | `claude-opus-4-7` | Read, Write, Edit, Grep, Glob, Bash, TodoWrite, Agent |
| `executor` | `claude-sonnet-4-6` | Read, Write, Edit, Grep, Glob, Bash |
| `read-only` | `claude-sonnet-4-6` | Read, Grep, Glob, Bash |

**Output:**
```json
{
  "ok": true,
  "id": "build-data-sme",
  "tier": "executor",
  "path": ".brains-build/personas/build-data-sme.md",
  "installed_globally": false,
  "next": "Run `python -m build_platform.cli.persona install build-data-sme` to make it available across projects."
}
```

**Exit codes:** `0` success · `2` invalid id · `3` already exists (use `--force`).

### `persona list`

```powershell
python -m build_platform.cli.persona list --root . --json
```

Lists project-local + globally-installed personas. Local overrides global on id collision.

**Output:**
```json
{
  "ok": true,
  "count": 9,
  "personas": [
    {"id": "build-data-sme", "scope": "local", "path": ".brains-build/personas/build-data-sme.md"},
    {"id": "build-backend-sme", "scope": "global", "path": "~/.claude/agents/build/build-backend-sme.md"}
  ]
}
```

### `persona install`

```powershell
python -m build_platform.cli.persona install build-data-sme --root . --json
```

Copies `.brains-build/personas/<id>.md` to `~/.claude/agents/build/<id>.md`. Re-run with `--force` to overwrite global.

**Exit codes:** `0` success · `1` no local persona with that id · `3` global already exists (use `--force`).

---

## `python -m build_platform.cli.dashboard`

Render the PMO dashboard. Pure derivation from state files — no LLM call. Emits markdown and/or HTML.

```powershell
python -m build_platform.cli.dashboard --root . --json
python -m build_platform.cli.dashboard --root . --format html --json
python -m build_platform.cli.dashboard --root . --format md
```

**Options:**

| Option | Default | Description |
|---|---|---|
| `--format` | `both` | One of `md`, `html`, `both` |
| `--json` | — | Emit JSON instead of streaming the markdown to stdout |

**Output (--json):** `{"ok": true, "paths": {"md": "...", "html": "..."}, "path": "..."}` (the `path` field is the markdown path for back-compat with earlier callers).

**Without `--json`:** prints the rendered dashboard markdown to stdout if md was written; otherwise prints the HTML path.

**Sections rendered:** Plan position · Live (right now) · Health · Deliverables · Workstreams · Persona activity · Daily completed work · Open blockers · Recent decisions · Up next.

**HTML brand styling:**
- Gold Deep `#D99518` on white (accessible 4.6:1 contrast); Gold `#FCC14D` only as decorative token, never as body text.
- No italic body text, no justified text. Left-aligned, ragged-right.
- Atkinson Hyperlegible / Inter font stack with system fallbacks.
- Auto light/dark mode via `prefers-color-scheme`.
- No external assets — single self-contained HTML file.

The dashboard is refreshed automatically by `dispatch` and `scrum` (markdown only). Run this explicitly any time you want a fresh view in either format.

---

## Common patterns

**Project setup:**
```powershell
python -m build_platform.cli.init --root . --name X --mission "..." --stack python --deliverable "D-a:Title:Why:accept"
ollama pull qwen2.5-coder:7b
ollama pull llama3.2:3b
```

**Add and dispatch a tier-1 WP:**
```powershell
python -m build_platform.cli.package --root . --title "..." --workstream backend `
  --deliverable D-a --tier 1 --executor build-backend-sme `
  --spec "..." --file src/foo.py --accept "tests pass" --json
# Outputs WP-0001
python -m build_platform.cli.dispatch --root . --wp WP-0001 --json
```

**Weekly cadence:**
```powershell
python -m build_platform.cli.scrum --root . --json
# In Claude Code: spawn build-pmo-lead subagent against the recap stub
python -m build_platform.cli.dashboard --root . --json
```

---

## State files touched by each verb

| Verb | Reads | Writes |
|---|---|---|
| `init` | — | `project.yml`, `deliverables.yml`, `workstreams.yml`, `config.yml`, `work-packages.jsonl`, `decisions.md` |
| `package` | `work-packages.jsonl` | `work-packages.jsonl` (append) |
| `dispatch` | all state | `work-packages.jsonl` (rewrite), `audit/<wp>-<ts>.md`, `runs/<wp>/...`, `dashboards/current.md` |
| `scrum` | all state, `git log` | `sprints/sprint-NN.md`, `dashboards/current.md` |
| `status` | `work-packages.jsonl`, `project.yml` | — |
| `decision` | — | `decisions.md` (append) |
| `dashboard` | all state | `dashboards/current.md` |
