---
name: build-dashboard
description: Render the markdown PMO dashboard from current state. Idempotent — pure derivation from .brains-build/ files. Run any time the user asks where the build stands.
---

# Refresh / view dashboard

## Flow

```powershell
python -m build_platform.cli.dashboard --root . --json
```

By default this writes both `current.md` and `current.html` under `.brains-build/dashboards/`. Markdown is canonical; HTML is the visual view for browser sharing.

To pick a format explicitly:
```powershell
python -m build_platform.cli.dashboard --root . --format md --json    # markdown only
python -m build_platform.cli.dashboard --root . --format html --json  # HTML only
```

Quote the dashboard's "Plan position" and "What I'd do next" sections to the user, and offer to open `dashboards/current.md` (or `current.html` in a browser) for the full view.

## HTML view

The HTML dashboard is a single self-contained file (inline CSS, no external assets, no JS). Brand-styled with Gold Deep (`#D99518`) on white, accessible contrast, no italic body text, no justified text, auto light/dark mode. Open directly in any browser:

```powershell
start .brains-build\dashboards\current.html
```

## Don't

- Don't write directly to `current.md` or `current.html`. The renderer is deterministic; manual edits get overwritten on next refresh.
