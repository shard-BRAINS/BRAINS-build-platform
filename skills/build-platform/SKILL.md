---
name: build-platform
description: Master entry point for the BRAINS Build Platform. Use when the user starts or continues a build project — defining deliverables, dispatching work packages, running scrums, or asking where a build stands. Routes to specialized build-* skills.
---

# BRAINS Build Platform — system overview

I drive software delivery via a fixed team of AI personas (3 leadership + 5 executor SMEs), local-file state under `.brains-build/`, and Ollama for cheap tier-1 mechanical work. Use this skill when the user mentions any build / project / dispatch / scrum / deliverable / work-package action.

## The 8 verbs

Always check whether one of these matches the user's intent first.

| Skill | Use when |
|---|---|
| `build-init` | New build project; "init build", "start a build" |
| `build-package` | "Add work package", "break down deliverable X" |
| `build-dispatch` | "Dispatch WP-X", "run next" |
| `build-scrum` | Weekly ritual; "run scrum", "weekly standup" |
| `build-status` | "Status of X", "where are we" |
| `build-decision` | "Log decision", "we decided X" |
| `build-dashboard` | "Show dashboard" |

## State of record

All project state lives in `.brains-build/` in the project root. Files are canonical; conversation memory is not. Always read state files before reasoning about project status.

## Persona dispatch

The 8 personas are subagent definitions in `~/.claude/agents/build/`. Spawn them via the `Agent` tool when a verb's flow calls for it:
- Leadership tier (`build-pmo-lead`, `build-dev-orchestrator`, `build-product-owner`) — `claude-opus-4-7`.
- Executor tier (`build-frontend-sme`, `build-backend-sme`, `build-qa-sme`, `build-security-sme`, `build-devops-sme`) — `claude-sonnet-4-6`.

## Tiering

- **Tier 1** — mechanical work. Routed to Ollama (`qwen2.5-coder:7b`) by `/build-dispatch`. Dev Orchestrator reviews the diff.
- **Tier 2** — judgment work. Routed to the executor persona subagent. The dispatch CLI emits a brief file (`.brains-build/runs/<wp-id>/tier2-brief.md`); you read it, then spawn the named subagent.

Dev Orchestrator tags every WP with its tier at creation time using a strict checklist. See `~/.claude/agents/build/build-dev-orchestrator.md`.

## Token discipline

- Read only the files relevant to the current verb.
- Use `python -m build_platform.cli.status --json` for structured project state, not freeform file reads.
- Large file inputs to subagents should be pre-digested via `build_platform.digest`.
- One persona per spawn; do not load context from prior spawns into new ones.

## Working directory

The active build project's root is wherever `.brains-build/` is found by walking up from the user's current working directory.

## Operating principles

1. **State on disk, not in heads.** Every status, every decision, every dispatch is in a file.
2. **Audit everything.** Every dispatch writes `.brains-build/audit/<wp-id>-<ts>.md`. PMO Lead reconstructs from these, not from memory.
3. **Dashboard is the answer.** `dashboards/current.md` is the user's primary view. Refresh it on every state change.
4. **Deliverables drive timeline, not the calendar.** Sprints end when their committed WPs are done.
