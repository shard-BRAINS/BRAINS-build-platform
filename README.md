<!-- markdownlint-disable MD041 (brand banner starts with a centered HTML block) -->
<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/shard-BRAINS/.github/main/profile/brand-mark-dark-bg.png">
  <img alt="BRAINS" src="https://raw.githubusercontent.com/shard-BRAINS/.github/main/profile/brand-mark-light-bg.png" width="220">
</picture>

# BRAINS Build Platform

<!-- markdownlint-disable-next-line MD001 (intentional tagline subtitle) -->
### Agentic end-to-end software delivery, built under the BRAINS umbrella

<br />

[![BRAINS Certified Gold](https://img.shields.io/badge/BRAINS%20Certified-Gold-D99518?style=for-the-badge&labelColor=0A0A0A)](https://github.com/shard-BRAINS/BRAINS-template-repo)
[![Status](https://img.shields.io/badge/status-v0.1.0%20MVP-D99518?style=for-the-badge&labelColor=0A0A0A)](https://github.com/shard-BRAINS/BRAINS-build-platform/releases/tag/v0.1.0)
[![Tests](https://img.shields.io/badge/tests-270%2F270%20passing-2A8B91?style=for-the-badge&labelColor=0A0A0A)](#run-the-tests)
[![Python](https://img.shields.io/badge/python-3.11%2B-D99518?style=for-the-badge&logo=python&logoColor=FFFFFF&labelColor=0A0A0A)](#install)
[![Licence](https://img.shields.io/badge/licence-Apache%202.0-0A0A0A?style=for-the-badge&labelColor=D99518)](LICENSE)
[![Discord](https://img.shields.io/badge/Discord-Community-5865F2?style=for-the-badge&logo=discord&logoColor=FFFFFF&labelColor=0A0A0A)](https://discord.gg/BEmTXXscBr)
[![Bluesky](https://img.shields.io/badge/Bluesky-%40brainscertified.com-D99518?style=for-the-badge&logo=bluesky&logoColor=FFFFFF&labelColor=0A0A0A)](https://bsky.app/profile/brainscertified.com)
[![Incubator](https://img.shields.io/badge/BRAINS-Incubator-4DA8FF?style=for-the-badge&labelColor=0A0A0A)](https://github.com/shard-BRAINS)

<br />

<a href="https://github.com/shard-BRAINS/BRAINS-template-repo" title="Meets the BRAINS standard floor — click for the standard"><img src="https://raw.githubusercontent.com/shard-BRAINS/BRAINS-template-repo/main/assets/badges/brains-certified-gold.svg" alt="BRAINS Certified — Gold Standard" height="86"></a>

<br />

[Install ↓](#install) · [How it works ↓](#how-it-works) · [The team ↓](#the-team) · [Quickstart ↓](#quickstart)

</div>

---

## What this is

The Build Platform turns any software project into a team of AI personas. A **PMO Lead** drives delivery. A **Dev Orchestrator** breaks deliverables into work packages. Six executor SMEs — Frontend, Backend, Code Review, QA, Security, and DevOps — write, review, and test the code. Mechanical work goes to a local Ollama model. Work that needs judgement goes to Claude subagents.

State lives in a `.brains-build/` folder inside your project. The dashboard at `.brains-build/dashboards/current.md` is the one source of truth. Open it and you know where the build stands.

> **State on disk, not in heads.** Every status, decision, and dispatch is saved as a file. Every dispatch writes an audit entry. The PMO Lead rebuilds the picture from evidence, not memory.

---

## Architecture

```mermaid
flowchart TD
    U["<b>You</b><br/><span style='font-size:11px'>/build-init · /build-package · /build-dispatch · /build-scrum · /build-status</span>"]:::user

    subgraph SKILLS["Claude Skills (~/.claude/skills/)"]
      direction LR
      MS["<b>build-platform</b><br/>master router"]:::skill
      VS["<b>13 verb skills</b><br/>init · package · dispatch · loop · scrum · schedule-scrum<br/>status · decision · dashboard · persona · portfolio · mirror · timeline"]:::skill
    end

    subgraph AGENTS["Subagents (~/.claude/agents/build/)"]
      direction LR
      LEAD["<b>Leadership</b><br/>PMO Lead<br/>Dev Orchestrator<br/>Product Owner<br/><span style='font-size:11px'>Opus</span>"]:::lead
      SME["<b>Executor SMEs</b><br/>Frontend · Backend · Code Review<br/>QA · Security · DevOps<br/><span style='font-size:11px'>Sonnet</span>"]:::sme
    end

    subgraph PKG["build_platform Python package"]
      direction LR
      STATE["<b>State I/O</b><br/>schemas · audit · git"]:::pkg
      DISP["<b>Dispatcher</b><br/>tier-1 · tier-2"]:::pkg
      DASH["<b>Dashboard</b><br/>renderer"]:::pkg
    end

    OLLAMA["<b>Ollama</b><br/>qwen2.5-coder · llama3.2<br/><span style='font-size:11px'>tier-1 mechanical</span>"]:::ollama
    FS[".brains-build/<br/><span style='font-size:11px'>project · deliverables · work-packages<br/>audit · decisions · sprints · dashboards</span>"]:::state

    U --> SKILLS
    SKILLS --> PKG
    SKILLS --> AGENTS
    PKG --> OLLAMA
    PKG --> FS
    AGENTS --> FS

    classDef user fill:#0A0A0A,stroke:#D99518,stroke-width:2px,color:#FFFFFF
    classDef skill fill:#D99518,stroke:#0A0A0A,stroke-width:2px,color:#0A0A0A
    classDef lead fill:#FFFFFF,stroke:#D99518,stroke-width:2px,color:#0A0A0A
    classDef sme fill:#FFFFFF,stroke:#4DA8FF,stroke-width:2px,color:#0A0A0A
    classDef pkg fill:#F5F5F5,stroke:#0A0A0A,stroke-width:1px,color:#0A0A0A
    classDef ollama fill:#4DA8FF,stroke:#0A0A0A,stroke-width:2px,color:#0A0A0A
    classDef state fill:#2A8B91,stroke:#0A0A0A,stroke-width:2px,color:#FFFFFF
```

Three tiers, one rule per tier:

- **Skills** route the work. SKILL.md files stay thin. They tell Claude what to do, not how.
- **Subagents** judge. Each persona has a fixed role, a tool allowlist, and an output contract.
- **Python** stores the state. It handles fixed state, schema checks, audit, and dashboard rendering.

---

## The team

Nine personas, all spawned as Claude subagents from `~/.claude/agents/build/`.

| Persona | Tier | Owns |
|---|---|---|
| ![PMO](https://img.shields.io/badge/-PMO%20Lead-D99518?style=flat-square&labelColor=0A0A0A) | Opus | Backlog state, sprint cadence, blocker escalation, dashboard refresh, scrum recap |
| ![Dev Orch](https://img.shields.io/badge/-Dev%20Orchestrator-D99518?style=flat-square&labelColor=0A0A0A) | Opus | Deliverables → work packages, tier-1/tier-2 tagging, technical coherence, executor sign-off |
| ![Product](https://img.shields.io/badge/-Product%20Owner-D99518?style=flat-square&labelColor=0A0A0A) | Opus | Project context, deliverable definitions, acceptance criteria, scope guard |
| ![Frontend](https://img.shields.io/badge/-Frontend%20SME-4DA8FF?style=flat-square&labelColor=0A0A0A) | Sonnet | UI components, styles, frontend tests, accessibility |
| ![Backend](https://img.shields.io/badge/-Backend%20SME-4DA8FF?style=flat-square&labelColor=0A0A0A) | Sonnet | Services, APIs, data layer, backend tests |
| ![Code Review](https://img.shields.io/badge/-Code%20Review%20SME-4DA8FF?style=flat-square&labelColor=0A0A0A) | Sonnet | Read-only review: architectural fit, style, codebase consistency before QA |
| ![QA](https://img.shields.io/badge/-QA%20SME-4DA8FF?style=flat-square&labelColor=0A0A0A) | Sonnet | Acceptance verification, integration/E2E tests, regression matrices, bug repro |
| ![Security](https://img.shields.io/badge/-Security%20SME-2A8B91?style=flat-square&labelColor=0A0A0A) | Sonnet | Read-only audit: secret scan, dep audit, OWASP review, threat surface |
| ![DevOps](https://img.shields.io/badge/-DevOps%20SME-4DA8FF?style=flat-square&labelColor=0A0A0A) | Sonnet | CI/CD config, build scripts, deploy manifests, environment management |

---

## How it works

### Tier-1 — mechanical work, Ollama

A work package is tier-1 only if **all four** hold:

1. Touches ≤ 3 files, total < 50 KB
2. Single well-defined transformation (rename, format, scaffold, dep-bump, doc edit, mechanical refactor)
3. Acceptance is objectively checkable (lint passes, test passes, file matches pattern)
4. No new design decisions required

`/build-dispatch` sends it to Ollama (`qwen2.5-coder:7b`). It checks the returned diff and asks the Dev Orchestrator to review before apply. Two failed checks block the WP, and the next scrum surfaces it.

### Tier-2 — judgement work, Claude SMEs

Everything else. `/build-dispatch` writes a brief to `.brains-build/runs/<wp-id>/tier2-brief.md`, then spawns the named executor SME subagent. The SME reads the brief, edits code, runs tests, and returns a result block. The **Code Review SME** then makes a read-only pass for fit and style. QA verifies acceptance. Security runs in parallel on sensitive WPs, such as auth, data, and dependencies.

### The code-review gate

After tier-2 work — and on tier-1 in `review-on-complete` or `auto` mode — the Code-Review SME returns a verdict. `dispatch_apply` records it in the audit entry. The loop then respects it:

| Verdict | What happens | Exit code |
|---|---|---|
| `approve` | Apply continues normally; verdict + findings stored in the audit entry | `0` |
| `request-changes` | `dispatch_apply` skips the apply step and hands off to `dispatch_request_changes`: findings are written to `runs/<wp>/code-review.md`, the proposed diff is reset, the WP returns to `defined` for re-dispatch | `6` |
| `reject` | The apply step is skipped, the working tree is untouched, the WP is transitioned to `blocked`, and `/build-loop` will refuse to re-queue it until a later `approve` overrides the reject | `5` |

The verdict travels through the audit trail. The file `.brains-build/audit/<wp-id>-<ts>.md` is for humans. An append-only `.brains-build/audit/index.jsonl` feeds the loop's reject-gate and the dashboard's cost panel. The latest timestamp wins. A later `approve` then overrides an earlier `reject` with no manual file edits.

### Re-tiering on the way out of blocked

If a tier-1 dispatch fails twice, Ollama has used up its retries. `/build-dispatch reject --retier` then moves the WP back to `defined` instead of leaving it `blocked`. You can re-package it as tier-2 with `/build-package`. The audit records the re-tier as a chosen decision, not a stuck state.

### The weekly scrum

`/build-scrum` works out the diff since the last scrum and writes a recap stub. Then it spawns the **PMO Lead** to fill in Progress, Blockers, Velocity, Re-prioritization, and Next-up. Anything that needs your input shows as a `[USER ACTION]` block at the top of the recap.

---

## Autonomy modes — how much the platform decides on its own

Every work package carries an `autonomy` field. It tells the platform how much oversight you want. **You set it at packaging time, and the default is the safest mode.** Choose it per WP. A project can mix modes freely.

| Mode | What happens | What the platform can do without you | When to use |
|---|---|---|---|
| `manual` *(default)* | Every step pauses for your confirmation. Diffs need approval; QA verdicts need approval; state transitions need approval. | Read state. Propose. Show. Nothing applied without you. | Unfamiliar codebase. Judgement-heavy work. First time using the platform on a project. |
| `review-on-complete` | Executor runs to completion; the Code-Review SME runs automatically; then you review + approve before the next WP. | Read state. Edit code. Run tests. Run code-review. Stop at the gate and wait for you. | You trust the executor on this kind of work but still want a human signoff before merge. |
| `auto` *(tier-1 only)* | The `/build-loop` verb auto-dispatches the WP unattended. Diff is validated, applied, tests are run, Code-Review SME is invoked. Any failure → WP blocked, loop stops. | Read state. Edit code. Apply diffs. Run tests. Transition state. Refresh dashboard. **No code is pushed to a remote** unless the GitHub mirror is separately enabled. | Mechanical work you've explicitly pre-authorised: rename sweeps, doc edits, formatter runs, dependency bumps below your watermark. |

**Hard constraints (enforced by the CLI, not advisory):**

1. `auto` requires `tier == 1`. Judgement work (`tier-2`) cannot be auto-dispatched. It always spawns a Claude SME and waits for your review.
2. `auto` requires every `depends_on` WP to be `done`. Unmet deps make the WP ineligible for the loop.
3. The loop **stops on the first failure**. It does not retry, route around, or "fix" the failing WP. The WP is left `blocked` for you.
4. Code-Review SME runs on every `review-on-complete` and `auto` WP. You cannot opt out per WP — opt out by choosing `manual`.
5. The autonomy field controls **local** action only. Remote actions, such as a push to GitHub or an open PR, live behind the separate `/build-mirror` verb and the `github.enabled` config flag. They never fire from autonomy alone.

### Access implications — what you're authorising the agent to do

| Mode | Local file edits | Run shell tests | Git apply | Git push | Open PRs | Read secrets |
|---|---|---|---|---|---|---|
| `manual` | with your approval | with your approval | with your approval | no | no | no |
| `review-on-complete` | yes | yes | yes | no | no | no |
| `auto` | yes | yes | yes | no | no | no |

Out of the box, the platform never pushes to a remote, opens a PR, posts to GitHub, sends email, or reads secrets. Those powers turn on only when you enable the optional `/build-mirror` integration with a named owner and repo. Even then, the mirror is one-way write, for issues and milestones. It does not run code for you.

### Cost visibility

Every dispatch writes its tokens-in, tokens-out, and dollar cost into `.brains-build/audit/index.jsonl`. The dashboard's **Cost burn** panel sums this up per persona and for the lifetime total. You can cap a session with `--limit` on `/build-loop`, or by mixing autonomy modes. For example, run 3 mechanical WPs as `auto` and the architectural one as `manual`.

---

## Install

```powershell
git clone https://github.com/shard-BRAINS/BRAINS-build-platform.git c:\BRAINS_Build_Platform
cd c:\BRAINS_Build_Platform
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
.\install.ps1
ollama pull qwen2.5-coder:7b
ollama pull llama3.2:3b
```

On Linux or macOS, run the steps by hand: create the venv, `pip install -e ".[dev]"`, copy `skills/*` to `~/.claude/skills/` and `agents/*.md` to `~/.claude/agents/build/`, then pull the Ollama models.

The installer copies the 14 skills to `~/.claude/skills/` and the 9 subagent definitions to `~/.claude/agents/build/`. Then it editable-installs the Python package.

---

## Quickstart

```powershell
mkdir c:\path\to\new-project
cd c:\path\to\new-project
# In Claude Code:
/build-init
```

`/build-init` is an interactive wizard. Once you have a project context, the loop is:

| Step | Verb | What happens |
|---|---|---|
| 1 | `/build-package` | Dev Orchestrator decomposes a deliverable into work packages, tagged tier-1 or tier-2 and assigned an autonomy mode (`manual` default, `review-on-complete`, or `auto`) |
| 2 | `/build-dispatch` | Tier-1 runs through Ollama; tier-2 spawns the named SME subagent. Code-Review SME runs on tier-2 before QA. |
| 3 | `/build-loop` *(optional)* | Burns down the `autonomy=auto` tier-1 queue unattended; stops on first failure |
| 4 | `/build-scrum` | PMO Lead writes the weekly recap, refreshes the dashboard, surfaces blockers |
| 5 | `/build-dashboard` | Render the current view at `.brains-build/dashboards/current.md` — includes autonomy column, pending-decisions inbox, cost burn |

Log decisions through `/build-decision`. Make read-only queries through `/build-status`. For a weekly rhythm, `/build-schedule-scrum` registers a remote routine through the `schedule` skill. It pushes a reminder when scrum is due.

---

## What's in the repo

```text
BRAINS-build-platform/
├── src/build_platform/          # Python package
│   ├── schemas.py · state.py    # Pydantic models + read/write/validate
│   ├── audit.py · git_utils.py  # Audit trail + read-only git helpers
│   ├── ollama_client.py         # HTTP client + preflight + chat
│   ├── digest.py                # Token-saving pre-digest helper
│   ├── dispatcher.py            # Tier-1 (Ollama) + tier-2 (brief) paths
│   ├── render_dashboard.py      # Deterministic markdown renderer
│   ├── cli/                     # CLI verbs (init, package, package_edit, dispatch,
│   │                            #   dispatch_apply, dispatch_reject,
│   │                            #   dispatch_request_changes, loop, scrum,
│   │                            #   schedule_scrum, status, decision, dashboard,
│   │                            #   persona, portfolio, mirror, timeline, triage)
│   └── templates/               # Jinja templates for prompts, dashboards, audits
├── skills/build-*/SKILL.md      # 14 Claude skills (1 router + 13 verbs)
├── agents/build-*.md            # 9 subagent definitions
├── tests/                       # pytest suite (270 tests, 100% pass)
├── docs/superpowers/            # design spec + implementation plan
├── install.ps1                  # Installer (Windows / PowerShell)
└── pyproject.toml
```

Per-project state lives in `.brains-build/` inside the project you're building, **not** inside this repo.

---

## Run the tests

```powershell
.venv\Scripts\python -m pytest
```

```text
270 passed in ~11 seconds
```

This includes an end-to-end smoke test. It runs `/build-init` → 3 WPs (1 tier-1, 2 tier-2) → 3 dispatches → scrum → dashboard render, with Ollama mocked (see `tests/test_end_to_end.py`). A second test covers the code-review gate. It walks dispatch → approve, request-changes, and reject across the audit trail and loop filter (see `tests/test_code_review_gate_integration.py`).

---

## Where this fits in BRAINS

This is a **BRAINS Incubator** project. It is internal tooling, reusable across any project the Incubator runs. We use it to drive other Incubator builds. It is also open to community contributors who want the same delivery model for their own work.

| | |
|---|---|
| ![Incubator](https://img.shields.io/badge/BRAINS-Incubator-4DA8FF?style=flat-square&labelColor=0A0A0A) | New projects, partnerships, prototypes — see the [BRAINS org page](https://github.com/shard-BRAINS) |
| ![Resume](https://img.shields.io/badge/-brains--resume-D99518?style=flat-square&labelColor=0A0A0A) | The first live Incubator project — [ND-aware résumé toolkit](https://github.com/shard-BRAINS/BRAINS-resume-skill) |
| ![Discord](https://img.shields.io/badge/-Discord-5865F2?style=flat-square&logo=discord&logoColor=FFFFFF&labelColor=0A0A0A) | Join the BRAINS Community — [discord.gg/BEmTXXscBr](https://discord.gg/BEmTXXscBr) |

| ![Bluesky](https://img.shields.io/badge/-Bluesky-D99518?style=flat-square&logo=bluesky&logoColor=FFFFFF&labelColor=0A0A0A) | Follow updates — [@brainscertified.com on Bluesky](https://bsky.app/profile/brainscertified.com) |
Want to use the platform on your own project, or contribute? See the Incubator application process on the [org page](https://github.com/shard-BRAINS#apply-to-join-the-incubator). Or jump into [the Discord](https://discord.gg/BEmTXXscBr) to talk first. Or follow updates on [Bluesky](https://bsky.app/profile/brainscertified.com).

---

## Design & plan

The design and implementation are public.

- [CLI reference](docs/cli-reference.md) — every verb, every option, every output shape
- [Design spec (2026-05-25)](docs/superpowers/specs/2026-05-25-brains-build-platform-design.md) — architecture, state model, persona contracts, MVP cut
- [Implementation plan (2026-05-25)](docs/superpowers/plans/2026-05-25-brains-build-platform.md) — 16 TDD tasks, full code, acceptance criteria

---

## Licence

Apache License 2.0 — see [LICENSE](LICENSE).

You may use, change, and share this software in commercial and non-commercial settings, under the licence terms. The Apache 2.0 licence also gives an explicit patent grant from contributors.

---

<div align="center">

<br />

**Built by neurodivergent minds, for neurodivergent people.**

<br />

[![Made by](https://img.shields.io/badge/built%20by-neurodivergent%20minds-0A0A0A?style=for-the-badge&labelColor=D99518)](https://brainscertified.com)

</div>
