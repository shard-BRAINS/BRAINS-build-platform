---
name: build-scrum
description: Run the weekly scrum ritual. Generates the since-last-scrum diff, spawns the PMO Lead to produce the recap, and refreshes the dashboard.
---

# Run the scrum

## Flow

1. **Run the CLI:**

```powershell
python -m build_platform.cli.scrum --root . --json
```

This writes a recap stub at `.brains-build/sprints/sprint-NN.md` with the raw diff embedded and six sections to fill in.

1. **Spawn `build-pmo-lead`** with:
   - Path to the recap stub
   - Path to `.brains-build/` for direct reads (project.yml, deliverables, work-packages, audit/)

PMO Lead fills in: Progress, Blockers, Velocity, Cost, Re-prioritization, Next up — and surfaces any `[USER ACTION]` blocks at the top.

Cost comes from rolling up `cost_usd`, `tokens_in`, and `tokens_out` in `.brains-build/audit/index.jsonl` for this sprint's window, reported against WPs completed. Cost alone is noise. A tier-1 line with real dollars on it is a finding — tier-1 runs through local Ollama and should be ~$0.

1. **PMO Lead refreshes the dashboard:**

```powershell
python -m build_platform.cli.dashboard --root . --json
```

1. **Print a one-screen summary** of the recap to the user — pull from the recap file. Lead with `[USER ACTION]` blocks if any.

## Don't

- Don't write the recap manually. Always spawn `build-pmo-lead`.
- Don't trust executor self-reports — PMO Lead must read `audit/` files for evidence.
