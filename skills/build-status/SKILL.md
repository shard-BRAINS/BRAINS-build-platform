---
name: build-status
description: Read-only status query for the active build project. Project-level summary, a specific WP, or a specific persona.
---

# Build status

## Flow

For project summary:

```powershell
python -m build_platform.cli.status --root . --json
```

For a specific WP:

```powershell
python -m build_platform.cli.status --root . --wp WP-XXXX --json
```

For a specific persona's activity: grep the audit files.

```powershell
Get-ChildItem .brains-build\audit\*.md | Select-String -Pattern "Persona:.*<persona-id>"
```

## Output

Always quote concrete values from the CLI output. Don't paraphrase the JSON shape; show counts.

## When the question is bigger than the numbers

This verb is a state snapshot. If the user is asking for a *read* rather than a value — "are we on track", "what has this cost me", "why is this slipping", "write up where the project stands" — spawn `build-pmo-lead` on top of this output. PMO owns tracking, project documentation, and cost/burn rollup, and reports to the user rather than to the Dev Orchestrator.

Don't synthesise that yourself from the JSON. The judgement is the persona's job, and its independence from delivery is the reason its reporting is worth anything.
