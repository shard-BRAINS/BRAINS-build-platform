# Contributing to BRAINS Build Platform

Thanks for your interest. This is a BRAINS Incubator project: agentic end-to-end software delivery built under the BRAINS umbrella. Contributions are welcome from coders, designers, researchers, writers, and lived-experience experts.

Before you start a substantial change, please open an issue or comment on an existing one so we can align — small PRs land fastest when the design is agreed first.

## Code of Conduct

This repo is governed by the [BRAINS Incubator org-level Code of Conduct](https://github.com/shard-BRAINS/.github/blob/main/CODE_OF_CONDUCT.md). Async-first, identity-first language by default, adjustments by default — the long version is at the org page.

## What's a good first contribution

- **Documentation** — the [CLI reference](docs/cli-reference.md), skill READMEs under `skills/*/SKILL.md`, or examples for new use cases.
- **Tests** — the [`tests/`](tests/) folder is exhaustive on happy paths; edge-case coverage is always welcome.
- **Small fixes** — typo fixes, error-message improvements, log clarity. Tier-1 work in our own vocabulary.
- **A new SME persona** — add a definition in `agents/` and register it in `skills/build-platform/SKILL.md`. See `agents/build-frontend-sme.md` for the template.

Bigger changes (new CLI verbs, schema changes, new sub-platforms) should start with an issue.

## Getting set up

```powershell
# Windows
git clone https://github.com/shard-BRAINS/brains-build-platform.git
cd brains-build-platform
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
.\install.ps1
ollama pull qwen2.5-coder:7b
ollama pull llama3.2:3b
```

```bash
# macOS / Linux (untested — community contributions welcome)
git clone https://github.com/shard-BRAINS/brains-build-platform.git
cd brains-build-platform
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# install.ps1 is Windows-only; on Unix, manually copy skills/ + agents/ to ~/.claude/
```

## The change loop

1. **Branch.** Off `main`. Name it `feat/short-description` or `fix/short-description`.
2. **Test first.** TDD where it fits — red, green, refactor. New behavior needs a test that would have failed before. See [`tests/`](tests/) for patterns.
3. **Lint clean.** `ruff check src tests` must pass.
4. **All tests green.** `pytest` must pass before you push. CI runs Python 3.11, 3.12, 3.13 on Ubuntu.
5. **Commit messages.** [Conventional Commits](https://www.conventionalcommits.org/) — `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`. Reference issues when relevant.
6. **PR.** Open against `main`. Keep the description short: what changed and why. Link the issue if there is one.

## What lives where

- [`src/build_platform/`](src/build_platform/) — Python package. Schemas, state I/O, CLIs, dispatcher, dashboard renderer, mirror, triage.
- [`skills/`](skills/) — Claude skill files. One subdirectory per verb (`build-init`, `build-package`, ...). SKILL.md is the only file that matters; it's read by Claude Code when the skill matches.
- [`agents/`](agents/) — Subagent definitions, one markdown file per persona. Frontmatter declares `tools` and `model`.
- [`tests/`](tests/) — pytest. Mirrors the package structure; one file per module.
- [`docs/`](docs/) — long-form docs. Design specs under `docs/superpowers/specs/`, implementation plans under `docs/superpowers/plans/`, dogfood reports under `docs/dogfood/`.

## Conventions worth knowing

**State is on disk, not in heads.** Every CLI verb writes its outputs to `.brains-build/` (per-project state). Audit entries are append-only. The dashboard is a pure render of state — never the source of truth. Don't add behavior that depends on in-memory state surviving across invocations.

**Skills stay thin.** SKILL.md files orchestrate (prose telling Claude what to do); Python scripts under the package do the deterministic work; subagents handle judgment. If you find yourself writing logic in SKILL.md, that logic belongs in the package.

**Tier-1 vs tier-2.** Tier-1 = mechanical work routed to Ollama. Tier-2 = judgment work routed to Claude SME subagents. The four-criterion tier-1 checklist lives in `build_platform/triage.py` — use `python -m build_platform.cli.triage` to check a WP's tier before committing.

**Conservative validation.** Prefer to refuse with a clear error over silent fallback. Examples: orphan deps rejected at WP-creation time, tier-1 file-count enforced, diff structure required to start with `--- a/`.

**Brand-compliant output.** When generating user-facing content (dashboards, READMEs, anything stylistic), follow the BRAINS brand standards: Gold Deep `#D99518` on white (not `#FCC14D`), no italic body text, no justified text, identity-first language. The `brains-brand` skill enforces this for BRAINS-facing output.

## What NOT to do

- Don't bypass `--no-verify` on hooks unless explicitly instructed.
- Don't commit secrets. The repo is public.
- Don't add features without an issue or design discussion for changes touching schemas, the dispatcher state machine, or the audit trail.
- Don't add dependencies casually — the `requires-python = ">=3.11"` constraint and the no-GPL preference matter.

## Reporting bugs

Open an issue with:
- What you ran (exact command).
- What you expected.
- What happened (exit code, output, audit entry if any).
- Versions: `python --version`, `pip show build-platform`, `ollama --version` if applicable.

For tier-1 dispatch failures, include the contents of `.brains-build/runs/<wp-id>/raw-attempt-N.txt` — that's the raw model output before validation.

## License

By contributing, you agree your contributions are licensed under [Apache License 2.0](LICENSE), matching the project license.
