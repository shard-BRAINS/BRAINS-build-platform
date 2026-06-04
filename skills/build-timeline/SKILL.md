---
name: build-timeline
description: Chronological view of work-package dispatches with timestamps. Read-only window over the audit log. The BRAINS-native equivalent of chat-timestamps, scoped to build events instead of chat messages.
---

# Build timeline

## Flow

For the last 20 dispatches (default), oldest-first within the window:

```powershell
python -m build_platform.cli.timeline --root . --count 20
```

For a larger window:

```powershell
python -m build_platform.cli.timeline --root . --count 50
```

For machine-readable output (drives other tools / dashboards):

```powershell
python -m build_platform.cli.timeline --root . --count 50 --json
```

## Output shape

Each line is one audit entry, padded for column alignment:

```text
HH:MM             persona                   wp-id       tier-N  result              runtime  cost
```

- Same-day dispatches: `HH:MM` (local time)
- Older: `YYYY-MM-DD HH:MM` (local time)
- Empty audit log: `No audit entries found. Has a work package been dispatched yet?` (exit 0)

## When to invoke

- The user asks "what's happened recently?", "show me today's dispatches", "when did WP-X land", "build history".
- The user asks for a build recap that needs a chronological frame.
- Pairs naturally with `build-status` (state snapshot) and `build-dashboard` (markdown rollup).

## Constraints

- Read-only — never edits `.brains-build/audit/index.jsonl`.
- `--count` must be a positive integer. Non-positive values exit non-zero.
- Always quote the actual CLI output; don't paraphrase it.
