---
name: build-dashboard
description: Render the markdown PMO dashboard from current state. Idempotent — pure derivation from .brains-build/ files. Run any time the user asks where the build stands.
---

# Refresh / view dashboard

## Flow

```powershell
python -m build_platform.cli.dashboard --root . --json
```

The CLI writes `.brains-build/dashboards/current.md` and prints its path. Quote the dashboard's "Plan position" and "What I'd do next" sections to the user, and offer to open `dashboards/current.md` for the full view.

## Don't

- Don't write directly to `current.md`. The renderer is deterministic; manual edits get overwritten on next refresh.
