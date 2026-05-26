---
name: build-portfolio
description: Cross-project portfolio view. Register multiple BRAINS Build Platform projects, then render an aggregated dashboard showing each project's deliverable progress, active WPs, blockers, and last activity. Use when the user asks "how are all my projects doing?", "portfolio view", or wants to track multiple builds at once.
---

# Cross-project portfolio

Registry lives at `~/.brains-build-portfolio.yml`. It holds a list of project root paths. The `view` command scans each registered project and renders an aggregated table (markdown and/or HTML).

## Subcommands

### `register <path>`

Add a project to the portfolio. Path must contain a `.brains-build/project.yml`.

```powershell
python -m build_platform.cli.portfolio register c:\path\to\project --json
```

Idempotent: re-registering the same path returns `already_registered: true` without duplicating.

### `unregister <path>`

Remove a project from the portfolio (does not delete `.brains-build/`).

```powershell
python -m build_platform.cli.portfolio unregister c:\path\to\project --json
```

### `list`

Show registry contents without scanning project state.

```powershell
python -m build_platform.cli.portfolio list --json
```

### `view`

Scan every registered project and render the aggregated view. Default format `md` streams to stdout; `html` writes a single self-contained file under `~/brains-build-portfolio.html`; `both` writes both at `~/brains-build-portfolio.{md,html}`.

```powershell
python -m build_platform.cli.portfolio view --format both --json
```

Each row shows: project name, mission, deliverable progress (done/total + %), active WP count, blocked WP count, last activity timestamp, and the absolute path. Projects whose `.brains-build/` is missing or invalid render as `_error_` rows — the scan never fails outright.

## Flow when the user asks for a portfolio view

1. Read `~/.brains-build-portfolio.yml` (via `list --json`) to see what's registered.
2. If empty: prompt the user for the project paths they want included. For each one, run `register <path>`.
3. Run `view --format both --json`.
4. Report the row count, summarize any `[USER ACTION]` blockers across projects (sum of `wps_blocked`), and link to the HTML view for the browser.

## When to use this vs `/build-dashboard`

- **`/build-dashboard`** — single active project, deep view.
- **`/build-portfolio view`** — cross-project rollup, shallow view per project.

Both are deterministic, no LLM call. Both can be re-run any time.

## Don't

- Don't edit `~/.brains-build-portfolio.yml` by hand. Always go through the CLI so schema validation runs.
- Don't include a project in the portfolio if its `.brains-build/` lives on removable media or a path that may not be mounted when the view fires — it'll just render as an error row.
