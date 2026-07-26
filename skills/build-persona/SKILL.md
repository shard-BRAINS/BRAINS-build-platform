---
name: build-persona
description: Register, list, or install custom personas for a BRAINS Build Platform project. Use when the user wants to add a new SME beyond the default 10 (e.g. "build-data-sme", "build-ml-sme", "build-design-sme"), list available personas, or promote a project-local persona to global.
---

# Manage custom personas

Custom personas live as subagent definition files at `.brains-build/personas/<id>.md` (project-local). The `install` subcommand copies them to `~/.claude/agents/build/` to make them available across projects.

## Register a new persona

```powershell
python -m build_platform.cli.persona register `
  --root . `
  --id build-data-sme `
  --tier executor `
  --description "Data engineering SME for pipelines, schemas, and data tests" `
  --mission "Execute tier-2 data work packages — implement pipelines, schemas, and data tests per the WP brief." `
  --json
```

**Options:**

- `--id` — must start with `build-` and use lowercase + hyphens (e.g. `build-data-sme`).
- `--tier` — `leadership` (Opus, broad tools), `executor` (Sonnet, write tools), or `read-only` (Sonnet, no write).
- `--description` — one-liner Claude uses for skill-matching.
- `--mission` — one-paragraph mission statement.
- `--model` / `--tools` — override tier defaults if needed.
- `--step` / `--rule` — repeatable, override default "What to do" / "Rules" lists.
- `--force` — overwrite an existing persona.

**Defaults by tier:**

| Tier | Model | Tools |
|---|---|---|
| `leadership` | `claude-opus-4-8` | Read, Write, Edit, Grep, Glob, Bash, TodoWrite, Agent |
| `executor` | `claude-sonnet-5` | Read, Write, Edit, Grep, Glob, Bash |
| `read-only` | `claude-sonnet-5` | Read, Grep, Glob, Bash |

## List available personas

```powershell
python -m build_platform.cli.persona list --root . --json
```

Lists project-local personas (under `.brains-build/personas/`) and globally-installed ones (under `~/.claude/agents/build/`). Local entries override global ones with the same id.

## Install a project-local persona globally

```powershell
python -m build_platform.cli.persona install build-data-sme --root . --json
```

Copies `.brains-build/personas/build-data-sme.md` to `~/.claude/agents/build/build-data-sme.md`. After this, Claude Code can spawn the persona in any project. Re-run with `--force` to overwrite an existing global version.

## Flow when the user asks to add a persona

1. Confirm the id, tier, and one-line description.
2. Spawn `build-business-analyst` if the mission/scope isn't clear yet — they're the one who shapes role definitions.
3. Run the `register` CLI with the gathered inputs.
4. Show the user the generated file. Offer to install globally if it's reusable across projects.
5. If the persona is meant to receive tier-2 WPs, no further setup is needed — `/build-package --executor <id>` will work.

## When NOT to create a custom persona

- If an existing persona's mission can cover the work — don't duplicate.
- If the work is mechanical (rename, format, dep bump) — that's a tier-1 dispatch, not a new persona.
- If it's a one-off — write a tier-2 brief directly, don't create a permanent role.

## Don't

- Don't edit `.brains-build/personas/*.md` by hand. Always go through the CLI so structure stays consistent.
- Don't use ids that collide with the 10 default personas (`build-pmo-lead`, `build-dev-orchestrator`, `build-business-analyst`, `build-frontend-sme`, `build-backend-sme`, `build-qa-sme`, `build-security-sme`, `build-devops-sme`, `build-code-review-sme`, `build-debug-sme`).
- Don't install a project-specific persona globally if its mission only makes sense in that project context.
