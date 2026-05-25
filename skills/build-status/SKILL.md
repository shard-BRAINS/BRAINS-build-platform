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
