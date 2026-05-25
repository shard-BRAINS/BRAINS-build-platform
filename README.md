# BRAINS Build Platform

Agentic end-to-end software delivery for any project. Claude skills + 8 persona subagents + Ollama tier-1 executor + local-file state.

**Status:** v0.1.0 — MVP.

## Concepts

- **Project context** lives in `.brains-build/` inside any project directory.
- **Work packages** decompose deliverables; each is tier-1 (Ollama mechanical) or tier-2 (Claude SME).
- **Personas** are subagent definitions: PMO Lead, Dev Orchestrator, Product Owner, Frontend SME, Backend SME, QA SME, Security SME, DevOps SME.
- **Dashboard** at `.brains-build/dashboards/current.md` is the user-facing source of truth.

See [docs/superpowers/specs/2026-05-25-brains-build-platform-design.md](docs/superpowers/specs/2026-05-25-brains-build-platform-design.md) for the full design.

## Install

```powershell
cd c:\BRAINS_Build_Platform
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
.\install.ps1
ollama pull qwen2.5-coder:7b
ollama pull llama3.2:3b
```

## Quickstart

```powershell
mkdir c:\path\to\new-project
cd c:\path\to\new-project
# In Claude Code: /build-init
```

Then `/build-package`, `/build-dispatch`, `/build-scrum`, `/build-dashboard`.

## Layout

- `src/build_platform/` — Python package (state I/O, schemas, Ollama client, dispatcher, dashboard renderer, CLIs)
- `skills/build-*/SKILL.md` — Claude skill files (installed to `~/.claude/skills/`)
- `agents/build-*.md` — Subagent definitions (installed to `~/.claude/agents/build/`)
- `tests/` — pytest suite (49 tests)

## Run tests

```powershell
.venv\Scripts\python -m pytest
```
