# BRAINS Build Platform — v1 Design Spec

**Date:** 2026-05-25
**Author:** Matthew Gell (with Claude)
**Status:** Draft — awaiting user review before plan
**Working directory:** `c:\BRAINS_Build_Platform`

---

## 1. Overview

The BRAINS Build Platform is an agentic end-to-end software delivery system, packaged as a family of Claude skills with supporting subagent definitions and Python tooling. It coordinates a fixed team of AI personas (PMO Lead, Dev Orchestrator, Product/Spec Owner, plus five executor SMEs) to define, dispatch, execute, review, and track work packages against a project's deliverables.

The platform is **project-agnostic**: BRAINS is the developer of the skill, but the skill itself contains no BRAINS-specific business content. It can drive any software project — startup MVP, internal POC, business idea prototype, or full product build.

It is **deliverable-driven**, not time-driven. Sprints are bounded by deliverable progress, not calendar weeks (though weekly scrum cadence is the default rhythm).

The platform is **orchestrator-class**: agents directly read, write, and modify code in the project repository via Claude Code tools. Humans review and approve.

A **markdown PMO dashboard** is the single source of truth for the user. Opening `dashboards/current.md` should answer the question "where is the build?" without needing to ask the platform.

---

## 2. Scope

### In scope (v1 MVP)

- Family of `build-*` Claude skills with a master router
- 8 subagent personas (3 leadership + 5 executor SMEs)
- Local-file state model (`.brains-build/` directory) as canonical source of truth
- Ollama-backed tier-1 executor (mechanical work) + Claude-backed tier-2 executor (judgment work)
- Explicit tier tagging by Dev Orchestrator (no auto-triage in v1)
- Manual `/build-scrum` weekly ritual with full agenda
- Markdown PMO dashboard, refreshed automatically on state changes
- Decision log with rationale and alternatives
- Per-dispatch audit trail
- Single active project per platform install

### Out of scope (deferred to v2)

- GitHub mirror sync (issues, PRs, milestones)
- HTML / web-rendered dashboard
- Auto tier-1/tier-2 triage heuristics
- Cron-scheduled autonomous scrum
- Cross-project portfolio view
- User-defined custom personas via UI (v1 = edit files by hand)
- Pluggable executor backends beyond Claude + Ollama
- Cross-platform parity testing (v1 is Windows-first)

### Integration touch points (in scope as adapters, not core features)

- `crisp` — all verb skills respect crisp mode if active
- `superpowers:brainstorming` — may be invoked by `/build-init` for deliverable definition
- `superpowers:writing-plans` — may be invoked by Dev Orchestrator when a tier-2 WP is large enough to need its own plan
- `brains-brand` — referenced only when a build project is itself a BRAINS-facing surface; the platform itself is brand-neutral

---

## 3. Architecture

### 3.1 Three-tier shape

```
┌─────────────────────────────────────────────────────────────┐
│  Skill verbs (build-init, build-dispatch, build-scrum, …)   │
│  Thin SKILL.md files — orchestration prose only             │
└─────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
┌──────────────────────────┐   ┌────────────────────────────┐
│  Python scripts          │   │  Claude subagents          │
│  (deterministic logic)   │   │  (judgment / writing code) │
│                          │   │                            │
│  - state I/O             │   │  - 8 personas              │
│  - schema validation     │   │  - dispatched per WP       │
│  - Ollama HTTP client    │   │  - bounded tool allowlists │
│  - dashboard renderer    │   │  - audit-emitting          │
│  - audit writer          │   │                            │
└──────────────────────────┘   └────────────────────────────┘
```

**Why three tiers:** scripts give deterministic state and predictable token cost; subagents give expert judgment where it matters; skills stay thin so SKILL.md loads cheaply.

### 3.2 Skill family

Mirrors the existing `brains-*` family pattern.

| Skill | Purpose | Primary triggers |
|---|---|---|
| `build-platform` | Master router + system overview. Always loadable. | "build platform", any unrouted `/build-*` request |
| `build-init` | One-time project setup wizard | "init build", `/build-init` |
| `build-package` | Define work packages (Dev Orch persona) | "new work package", "break down deliverable X" |
| `build-dispatch` | Execute a WP via tier-1 (Ollama) or tier-2 (Claude) | "dispatch WP-XXX", "run next" |
| `build-scrum` | Weekly ritual: progress, blockers, velocity, re-prioritization, next-up | `/build-scrum`, "weekly standup" |
| `build-status` | Read-only query of project / workstream / persona / WP | "status of X", "where are we" |
| `build-decision` | Log a decision with rationale, owner, alternatives | "log decision", "we decided X" |
| `build-dashboard` | Render markdown PMO dashboard (idempotent) | `/build-dashboard`, "show dashboard" |

**Token discipline:**
- Master `build-platform` SKILL.md ≤ 150 lines
- Each verb SKILL.md ≤ 200 lines
- Heavy logic lives in `scripts/` directories, not SKILL.md

**Installation root:** `C:\Users\matth\.claude\skills\build-*` (user-level, available across machines via the same skill-distribution mechanism as `brains-*`).

### 3.3 Subagent layer

All 8 personas live as standalone subagent definitions under `C:\Users\matth\.claude\agents\build\<persona>.md`.

**Leadership tier** — `claude-opus-4-7`, dispatched as orchestrators:

| Persona | Owns | Tools |
|---|---|---|
| `build-pmo-lead` | Backlog state, sprint cadence, blocker escalation, dashboard refresh, scrum recap | Read, Write, Edit, Grep, Glob, Bash (read-only git), TodoWrite |
| `build-dev-orchestrator` | Translating deliverables → WPs, tier tagging, technical coherence, executor output sign-off | Read, Write, Edit, Grep, Glob, Bash, Agent |
| `build-product-owner` | Project context doc, deliverable definitions, acceptance criteria, scope guard | Read, Write, Edit, Grep, Glob |

**Executor tier** — `claude-sonnet-4-6`, dispatched per WP:

| Persona | Owns | Tools |
|---|---|---|
| `build-frontend-sme` | UI components, styles, frontend tests, accessibility | Read, Write, Edit, Grep, Glob, Bash |
| `build-backend-sme` | Services, APIs, data layer, backend tests | Read, Write, Edit, Grep, Glob, Bash |
| `build-qa-sme` | Test plans, integration/E2E tests, regression matrices, bug repro | Read, Write, Edit, Grep, Glob, Bash |
| `build-security-sme` | Threat modeling, secret scanning, OWASP review, dependency audit | Read, Grep, Glob, Bash (read-only audit tools) |
| `build-devops-sme` | CI/CD config, build scripts, deploy manifests, env management | Read, Write, Edit, Grep, Glob, Bash |

**Shared persona contract** — every subagent's frontmatter and system prompt includes:

- **Mission** — one-sentence statement of role
- **Inputs expected** — WP format reference + project context path
- **Outputs required** — result block: files changed, decisions logged, blockers, handoff notes
- **Rules of engagement** — must read project context first; must log decisions to `decisions.md`; must update WP state via the audit writer; must not invent dependencies
- **Token discipline** — read only scoped files; summarize findings, don't quote whole files; prefer `digest.py` helper for large inputs
- **Escalation triggers** — explicit "when to block vs push through" rules

### 3.4 RACI (encoded, not maintained separately)

- **Responsible** — persona named in WP's `dispatched` event
- **Accountable** — workstream owner persona who signs off (Dev Orch for code; QA for tests; Security for sensitive WPs)
- **Consulted** — personas named in WP's `consult` field (spawned read-only during dispatch)
- **Informed** — PMO Lead always; user via dashboard

RACI emerges from the audit trail + persona definitions. No separate RACI matrix file needs maintaining.

---

## 4. State model

All state lives under `.brains-build/` in the project root. Files are canonical; nothing in the platform's behavior depends on conversation memory.

### 4.1 Directory layout

```
.brains-build/
├── project.yml                  # Project context: name, mission, stack, constraints
├── deliverables.yml             # Top-level deliverables + acceptance criteria
├── workstreams.yml              # Workstream definitions + persona owners
├── work-packages.jsonl          # Append-only log of all WPs (one JSON per line)
├── wp-state.json                # Derived current state per WP
├── decisions.md                 # Decision log (append-only)
├── sprints/
│   └── sprint-NN.md             # One file per sprint
├── audit/
│   └── <wp-id>-<timestamp>.md   # One per dispatch
├── dashboards/
│   └── current.md               # Latest rendered dashboard
├── runs/
│   └── <wp-id>/                 # Per-WP working dir
│       ├── raw-response.txt     # Raw Ollama or subagent output
│       ├── proposed.diff        # Parsed diff (tier-1 path)
│       ├── review.md            # Dev Orch / QA / Security review notes
│       └── digests/             # Pre-digested large inputs (see §6.4)
└── config.yml                   # Platform config (Ollama URL, models, paths)
```

### 4.2 Schemas

**`project.yml`:**
```yaml
name: string
mission: string                  # one sentence
stack: [string]
constraints: [string]
ground_truth: local              # v1 always 'local'; 'github' reserved for v2
created: ISO-8601
```

**`deliverables.yml`:**
```yaml
deliverables:
  - id: D-auth
    title: Authentication MVP
    why: One-sentence motivation
    acceptance:
      - testable criterion 1
      - testable criterion 2
    sequence: 1                  # order in plan
    state: not_started | in_progress | acceptance_review | done
```

**`workstreams.yml`:**
```yaml
workstreams:
  - id: backend
    owner_persona: build-backend-sme
    review_persona: build-dev-orchestrator
    description: One-line scope
```

**`work-packages.jsonl`** (one JSON per line, append-only):
```json
{
  "id": "WP-0042",
  "title": "Add login endpoint",
  "workstream": "backend",
  "deliverable_id": "D-auth",
  "tier": 1,
  "executor_persona": "build-backend-sme",
  "spec": "string description",
  "spec_files": ["src/auth/login.py"],
  "acceptance": ["criterion 1", "criterion 2"],
  "depends_on": ["WP-0040"],
  "consult": ["build-security-sme"],
  "state": "defined",
  "created_by": "build-dev-orchestrator",
  "created_at": "ISO-8601",
  "history": [{"at": "ISO-8601", "by": "persona-id", "event": "string"}]
}
```

**State machine** (enforced by `build-dispatch` script, not by personas):

```
defined ──► dispatched ──► in_review ──► done
                       └─► blocked  (requires PMO or user to unblock)
```

**`config.yml`:**
```yaml
ollama:
  url: http://localhost:11434
  timeout_seconds: 300
  models:
    tier1_default: qwen2.5-coder:7b
    summarizer: llama3.2:3b
    fallback: qwen2.5-coder:7b
  preflight:
    require_running: true
    auto_pull_missing: false
project:
  test_command: "pytest"
  lint_command: "ruff check"
```

### 4.3 Audit entry format

Every dispatch writes `.brains-build/audit/<wp-id>-<ISO-timestamp>.md`:

```markdown
# WP-XXXX dispatch · ISO timestamp

**Persona:** persona-id · **Model:** model-id · **Tier:** 1|2
**Runtime:** Xm Ys · **Result:** done|blocked|requested_changes

## Inputs read
- file paths with size or digest reference

## Outputs written
- file paths modified/created

## Decisions logged
- decision id references

## Tests run
- command + result summary

## Notes
- free-form persona notes (kept short)
```

---

## 5. Core flows

### 5.1 `/build-init` — project setup

1. Refuse if `.brains-build/` already exists; suggest `/build-status` instead.
2. Interactive prompts for: project name, one-sentence mission, stack (multi-select common + free text), constraints, top 3–5 deliverables.
3. Spawn `build-product-owner` subagent with raw inputs → produces structured `project.yml`, `deliverables.yml` (with acceptance criteria), draft `workstreams.yml`.
4. Show drafts to user; accept edits; write to disk.
5. Initialize empty `work-packages.jsonl`, seed `decisions.md` ("Project initialized"), write `config.yml` with defaults.
6. Print next-step guidance, including `ollama pull` commands for required local models.

### 5.2 `/build-package` — define work packages

1. Script loads `deliverables.yml`, `workstreams.yml`, existing `work-packages.jsonl`.
2. Spawn `build-dev-orchestrator` subagent with target deliverable + existing WPs as context.
3. Dev Orchestrator proposes 1–N new WPs with all required fields including tier and `spec_files`.
4. **Tier-1 checklist** (Dev Orch must verify all true):
   - Touches ≤ 3 files, total < 50KB
   - Single well-defined transformation (rename, format, scaffold from template, dependency bump, doc edit, mechanical refactor)
   - Acceptance criteria objectively checkable (lint, test, file pattern match)
   - No new design decisions required
5. User reviews proposed WPs, accepts/edits.
6. Script validates schema + tier-1 checklist where applicable; appends to `work-packages.jsonl`; writes audit entry.

### 5.3 `/build-dispatch` — execute a WP

1. Script loads WP from `wp-state.json`. Validates `state=defined` and all `depends_on` are `done`.
2. **Tier-1 path (Ollama):**
   - Load `spec_files` content (cap 50KB total; if exceeded, refuse and instruct Dev Orch to split or re-tier).
   - Render `templates/tier1_executor.j2` prompt: mission, 3-line project context summary, WP block, hard constraints ("output unified diff only; touch only listed files").
   - POST to Ollama `/api/chat`; stream response to `runs/<wp-id>/raw-response.txt`; parse diff to `runs/<wp-id>/proposed.diff`.
   - Validate diff is well-formed and touches only allowed files. One retry with stricter prompt on failure. Second failure → mark WP `blocked` with reason; script exits with clear error so user can ask Dev Orch to re-package the WP.
   - Spawn `build-dev-orchestrator` subagent for review. Verdicts: **approve** (apply diff, run tests, hand to QA) / **request changes** (write `review.md`, re-dispatch with feedback, max 2 cycles) / **reject** (re-tag tier=2, re-dispatch via Claude path).
3. **Tier-2 path (Claude):**
   - Spawn WP's `executor_persona` subagent with WP spec + project context + relevant files.
   - Subagent reads, writes code via Edit/Write, runs project test command, produces result block.
4. State transitions to `in_review`. Script spawns `build-qa-sme` subagent to verify acceptance criteria. QA writes verdict.
5. **Security review** runs in parallel for tier-2 WPs flagged sensitive (auth, data, deps). Spawns `build-security-sme` read-only.
6. QA pass → `done`. QA fail → `blocked` with findings; surfaces in next scrum.
7. Every step appends to WP `history` and writes audit entry.

### 5.4 `/build-scrum` — weekly ritual

1. Script computes since-last-scrum diff: WPs created / dispatched / completed / blocked since last sprint file's timestamp; git commits since same timestamp (if git available).
2. Spawn `build-pmo-lead` subagent with that diff + current `wp-state.json` + open blockers.
3. PMO Lead runs five passes (one structured prompt, not separate spawns):
   - **Progress** — completed WPs per workstream, vs. expected.
   - **Blockers** — open blockers and what / who's needed to clear them; user escalations explicitly flagged.
   - **Velocity** — WPs done this sprint vs. trailing average; flag if trending down.
   - **Re-prioritization** — proposed re-ranking of `defined` WPs.
   - **Next up** — WPs ready to dispatch this coming sprint.
4. Script writes recap to `sprints/sprint-NN.md`; refreshes `dashboards/current.md`; prints one-screen summary with `[USER ACTION]` blocks at top.

### 5.5 Cross-flow contracts

- No flow modifies state without writing an audit entry.
- No subagent reads files outside its scoped allowlist + named WP inputs.
- Read-only flows (`/build-status`, `/build-dashboard`) are fully idempotent.
- `/build-dispatch` and `/build-scrum` refresh the dashboard as a side-effect so the dashboard is never stale.

---

## 6. Ollama integration & tiering

### 6.1 Adapter boundary

A single Python module `build-platform/scripts/ollama_client.py` is the only code that talks to Ollama. Subagents never call Ollama directly. This keeps the boundary clean and lets v2 swap in alternative local-LLM runtimes by replacing the adapter.

### 6.2 Runtime config

In `.brains-build/config.yml` (default values shown):

```yaml
ollama:
  url: http://localhost:11434
  timeout_seconds: 300
  models:
    tier1_default: qwen2.5-coder:7b
    summarizer: llama3.2:3b
    fallback: qwen2.5-coder:7b
  preflight:
    require_running: true
    auto_pull_missing: false
```

### 6.3 Recommended models (Windows workstation)

- **`qwen2.5-coder:7b`** — tier-1 executor; best small open coding model in early 2026; ~5 GB.
- **`llama3.2:3b`** — summarizer for large input digesting; ~2 GB.

Init prints exact `ollama pull` commands. Preflight refuses dispatch with a clear error if models are missing or Ollama is unreachable.

### 6.4 Pre-digest helper

`scripts/digest.py` is a generic helper any persona can invoke via Bash:

- Input: file paths or raw text, target token budget (default 1500).
- Calls Ollama with the `summarizer` model + a "preserve facts, drop prose" prompt.
- Writes the digest to `runs/<wp-id>/digests/<source-name>.md`.

Personas read the digest, not the original, when the original exceeds budget. This is the primary token-saving lever in the platform.

### 6.5 Failure modes

| Failure | Handling |
|---|---|
| Ollama unreachable | Preflight blocks dispatch; suggests `ollama serve` |
| Model not pulled | Preflight blocks; prints exact `ollama pull` command |
| Tier-1 diff validation fails twice | WP → `blocked`, surfaced in scrum |
| Dev Orch rejects tier-1 output | WP re-tagged tier=2, re-dispatched via Claude path |
| Tests fail after applied diff | QA marks `blocked`, audit captures full transcript |

---

## 7. Dashboard — source of truth

`dashboards/current.md` is the user's primary instrument. Opening this file answers "where is the build?" without needing to ask the platform. It is refreshed automatically by `/build-dispatch` and `/build-scrum`, and on demand by `/build-dashboard`. Pure derivation from state files; no hidden state.

### 7.1 Sections (in order)

1. **Header** — project name, generated-at timestamp, sprint, day-of-sprint.
2. **Plan position** — deliverable sequence with progress bar, current focus, next milestone, recommended next action.
3. **Live (right now)** — dispatches currently running (read from `runs/` directory state).
4. **Health** — counts: active WPs, blocked, done this sprint, velocity (3-sprint trailing avg), open user-action blockers.
5. **Deliverables** — table: id, title, acceptance met (X/Y), WPs done/total, state.
6. **Workstreams (this sprint)** — table: workstream, owner persona, done, in review, blocked, next up.
7. **Persona activity (last 7 days)** — table: persona, dispatches, avg runtime, tier-1 share.
8. **Daily completed work (last 7 days)** — list capped at 7 days; older lives in `sprints/`.
9. **Open blockers** — bulleted, each with suggested resolution.
10. **Recent decisions (last 7 days)** — bulleted, each linking to decision entry.
11. **Up next (this sprint, in priority order)** — numbered list with tier and brief unlock note.

### 7.2 Render rules

- One Python script (`scripts/render_dashboard.py`) — deterministic, no LLM call.
- Empty sections render as a single `_None_` line; no empty tables.
- Persona-activity stats come from `audit/` entries.
- "What I'd do next" recommendation derived from blocker-unlock count + deliverable progress (heuristic in renderer).

---

## 8. Decision log

`.brains-build/decisions.md` is append-only markdown. Schema enforced by `/build-decision`:

```markdown
## ISO-date — Decision title
**Owner:** persona-id or `user:<name>`
**Decision:** what was decided (one sentence)
**Why:** rationale
**Alternatives considered:** option A (rejected: reason), option B (rejected: reason)
**Related WPs:** WP-XXXX, WP-YYYY
**Audit:** link to audit file
```

`/build-decision` invokes `build-product-owner` subagent if the user input is freeform; otherwise script-only. Owner must be a known persona id or `user:<name>`.

---

## 9. Acceptance criteria for v1

Proof MVP works:

1. `/build-init` on a new empty directory produces a valid `.brains-build/` tree.
2. Define 3 work packages (1 tier-1, 2 tier-2) and dispatch all three; tier-1 hits Ollama, tier-2s hit Claude subagents.
3. `/build-scrum` produces a recap file and refreshed dashboard reflecting actual state.
4. `dashboards/current.md` shows Plan position, Live, Health, Blockers, Up next — enough to answer "where are we" without invoking the platform.
5. Any WP's full lifecycle can be reconstructed from `.brains-build/audit/` files alone.
6. Tier-1 dispatch failure paths (Ollama down, model missing, malformed diff, Dev Orch rejects) all produce clear errors and correct state transitions without manual intervention.
7. All 8 skills (1 master router + 7 verbs) pass a smoke test: load SKILL.md, invoke each verb's primary command on a seeded project, expect no errors.

---

## 10. v2 backlog (deferred, listed for design alignment)

- GitHub mirror sync — issues, PRs, milestones; `ground_truth: github` mode.
- HTML / web-rendered dashboard.
- Auto tier-1/tier-2 triage from historical tier-2 → tier-1 reclassifications.
- Cron-scheduled scrum via existing `schedule` skill.
- Cross-project portfolio view.
- User-defined custom personas via a registration command.
- Pluggable executor backends (LM Studio, llama.cpp direct, OpenRouter, etc.) — adapter pattern already in place.
- Cross-platform parity (macOS / Linux paths).

---

## 11. Plan-stage notes

### Phasing recommendation

This spec is one design but likely too large for a single linear implementation plan. Recommend the plan-writing stage split into three phases, each independently runnable:

- **Phase A — Foundation.** Skill family scaffolding, state model schemas + validators, `/build-init` end-to-end, `/build-status` and `/build-dashboard` (read-only). Acceptance: `/build-init` produces a valid `.brains-build/` tree on an empty dir.
- **Phase B — Execution.** Subagent definitions, `/build-package`, `/build-dispatch` with both tier-1 (Ollama) and tier-2 (Claude) paths, audit writer. Acceptance: dispatch 3 WPs (1 tier-1, 2 tier-2) successfully.
- **Phase C — Coordination.** `/build-scrum`, `/build-decision`, dashboard refresh side-effects, all five PMO passes. Acceptance: scrum produces recap + refreshed dashboard reflecting actual state.

### Open items to confirm at plan time

None blocking. Items to confirm:

- Which Ollama model to default to if `qwen2.5-coder:7b` proves slow on Matthew's hardware (fallback candidate: `qwen2.5-coder:1.5b` for speed, `deepseek-coder-v2:16b` for quality).
- Whether to seed the skill installation under `C:\Users\matth\.claude\skills\` directly or stage it under `c:\BRAINS_Build_Platform\` and symlink/install at end.
- Test strategy: unit tests for Python scripts (pytest), smoke tests for skills (manual seed-and-run), no test harness for subagent output quality (judged by Dev Orch/QA personas at runtime).
