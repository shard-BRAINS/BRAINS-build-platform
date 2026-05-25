# BRAINS Build Platform

Agentic end-to-end software delivery — Claude skills + subagents + local Python tooling.

See [docs/superpowers/specs/2026-05-25-brains-build-platform-design.md](docs/superpowers/specs/2026-05-25-brains-build-platform-design.md) for the design.

## Install (Windows)

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
