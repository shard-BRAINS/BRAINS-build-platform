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

## `python -m build_platform.cli.dashboard`

Render the markdown PMO dashboard. Pure derivation from state files — no LLM call.

```powershell
python -m build_platform.cli.dashboard --root . --json
```

**Output:** `{"ok": true, "path": "<path to dashboards/current.md>"}`

**Without `--json`:** prints the rendered dashboard markdown to stdout.

**Sections rendered:** Plan position · Live (right now) · Health · Deliverables · Workstreams · Persona activity · Daily completed work · Open blockers · Recent decisions · Up next.

The dashboard is refreshed automatically by `dispatch` and `scrum`. Run this explicitly any time you want a fresh view.

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
