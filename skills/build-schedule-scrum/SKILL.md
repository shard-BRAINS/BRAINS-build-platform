---
name: build-schedule-scrum
description: Register a weekly cron reminder for /build-scrum. Uses the user's existing `schedule` skill under the hood. The remote routine fires a push notification reminding the user to run /build-scrum locally — it does not run scrum remotely, because routines cannot read the local .brains-build/ state.
---

# Schedule a weekly scrum reminder

## Flow

1. **Confirm the active project.** Read `.brains-build/project.yml` to get the project name and root path.
2. **Ask the user** for the cadence:
   - Day of week (default Monday)
   - Hour (24h, default 09)
   - Minute (default 00)
   - Timezone (default UTC; user can specify e.g. `Europe/London`, `America/New_York`)
3. **Run the CLI** to generate the routine spec and persist the schedule intent:

```powershell
python -m build_platform.cli.schedule_scrum `
  --root . `
  --day mon `
  --hour 9 `
  --minute 0 `
  --timezone UTC `
  --json
```

The CLI returns a JSON payload with `cron`, `routine_prompt`, and project metadata.

4. **Hand off to the `schedule` skill.** Invoke the `schedule` skill with the returned `cron` expression and `routine_prompt`. The user's `schedule` skill creates the actual remote routine on Claude's cron infrastructure.
5. **Record the routine id.** Once `/schedule` returns a routine id (e.g., `rtn-abc-123`), re-run the CLI to persist it:

```powershell
python -m build_platform.cli.schedule_scrum `
  --root . `
  --routine-id rtn-abc-123 `
  --json
```

6. **Confirm to the user**: routine is registered, will fire weekly per the schedule, and reminds them via push notification to open Claude Code and run `/build-scrum`.

## Why the routine only sends a reminder

Remote routines created by `/schedule` execute in Claude's cloud. They cannot read the local `.brains-build/` directory on the user's machine, so they cannot:
- Generate the scrum recap stub (requires local state files)
- Spawn the PMO Lead with project context (requires local state files)
- Refresh the dashboard (writes to a local file)

What they CAN do: fire a `PushNotification` reminding the user that it's scrum time. That's the v2.1 cadence value — predictable weekly nudges without forgetting. The qualitative PMO Lead pass still happens when the user opens Claude Code and runs `/build-scrum` themselves.

A future v2.x with full GitHub mirror sync (state in issues/PRs) would unlock truly autonomous remote scrum — but that's a separate effort.

## Disabling the schedule

To disable without deleting the remote routine:

```powershell
python -m build_platform.cli.schedule_scrum --root . --disable --json
```

To delete the remote routine itself, invoke the `schedule` skill with the routine id and ask it to delete. The CLI does not call `/schedule` directly.

## Status

Whether a schedule is enabled for the current project lives in `.brains-build/config.yml` under `scrum_schedule`. `/build-status` does not surface this; check the file directly or re-run `/build-schedule-scrum` to see current state.

## Don't

- Don't try to make the routine itself run `/build-scrum`. It can't — see above.
- Don't store the routine prompt or cron in any file other than `config.yml` via the CLI.
- Don't bypass the CLI and edit `config.yml` directly — schema validation runs at the CLI boundary.
