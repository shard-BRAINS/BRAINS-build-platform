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
  "next": "Spawn build-backend-sme subagent with this brief"
}
```

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
