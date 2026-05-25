"""`/build-schedule-scrum` entry point — generate the routine spec for a weekly
scrum reminder, and persist the schedule intent in config.yml.

This CLI does NOT call the `schedule` skill itself. It produces the cron
expression, routine prompt, and project metadata so the user (or the skill
layer) can hand them to `/schedule` to register the actual remote routine.
"""
import json
import sys
from pathlib import Path

import click

from build_platform.paths import find_brains_build_root
from build_platform.state import load_config, load_project, save_config

_DOW_TO_CRON = {
    "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0,
}


def _to_cron(day: str, hour: int, minute: int) -> str:
    if day not in _DOW_TO_CRON:
        raise click.BadParameter(f"day must be one of {list(_DOW_TO_CRON)}")
    if not 0 <= hour <= 23:
        raise click.BadParameter("hour must be in [0, 23]")
    if not 0 <= minute <= 59:
        raise click.BadParameter("minute must be in [0, 59]")
    return f"{minute} {hour} * * {_DOW_TO_CRON[day]}"


def _build_routine_prompt(project_name: str, project_root: Path) -> str:
    return (
        f"You are the BRAINS Build Platform scrum reminder for "
        f'project "{project_name}" at {project_root}.\n\n'
        f"Send a PushNotification to the user with the body:\n\n"
        f'  "BRAINS scrum reminder — {project_name}\n'
        f"  It is time for the weekly scrum. Open Claude Code in "
        f"{project_root} and run /build-scrum to generate the recap, "
        f"refresh the dashboard, and surface any blockers needing your input."
        f'"\n\n'
        f"After sending the notification, exit. Do not attempt to read "
        f"local project files — this routine runs remotely and cannot "
        f"reach the user's machine."
    )


@click.command("schedule-scrum")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--day", type=click.Choice(list(_DOW_TO_CRON)), default="mon",
              show_default=True, help="Day of week to fire the reminder.")
@click.option("--hour", type=int, default=9, show_default=True,
              help="Hour of day (0-23, server timezone).")
@click.option("--minute", type=int, default=0, show_default=True)
@click.option("--timezone", default="UTC", show_default=True,
              help="Tz identifier the schedule should interpret (informational; "
                   "the `schedule` skill applies its own tz handling).")
@click.option("--routine-id", default=None,
              help="If you've already created the routine via /schedule, "
                   "record its id here so it can be tracked/unscheduled later.")
@click.option("--disable", is_flag=True,
              help="Mark scrum_schedule.enabled = False in config (does NOT "
                   "delete the remote routine — use /schedule for that).")
@click.option("--json", "as_json", is_flag=True)
def schedule_scrum_cmd(root, day, hour, minute, timezone, routine_id, disable, as_json):
    """Generate the scrum reminder routine spec and persist the schedule intent."""
    root_path = Path(root).resolve() if root else find_brains_build_root()
    config = load_config(root_path)
    project = load_project(root_path)

    cron = _to_cron(day, hour, minute)
    prompt = _build_routine_prompt(project.name, root_path)

    config.scrum_schedule.enabled = not disable
    config.scrum_schedule.cron = cron
    config.scrum_schedule.timezone = timezone
    if routine_id is not None:
        config.scrum_schedule.routine_id = routine_id
    save_config(root_path, config)

    payload = {
        "ok": True,
        "project": project.name,
        "project_root": str(root_path),
        "enabled": config.scrum_schedule.enabled,
        "cron": cron,
        "timezone": timezone,
        "routine_id": config.scrum_schedule.routine_id,
        "routine_prompt": prompt,
        "next": (
            "Pass cron + routine_prompt to /schedule to create the routine. "
            "Then re-run with --routine-id <id> to record it."
        ) if not config.scrum_schedule.routine_id else "Tracked routine recorded.",
    }
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(f"Project: {project.name}")
        click.echo(f"Cron: {cron}  (timezone: {timezone})")
        click.echo(f"Enabled: {config.scrum_schedule.enabled}")
        if config.scrum_schedule.routine_id:
            click.echo(f"Routine id: {config.scrum_schedule.routine_id}")
        click.echo("")
        click.echo("Routine prompt to pass to /schedule:")
        click.echo("-" * 60)
        click.echo(prompt)
        click.echo("-" * 60)
    sys.exit(0)


if __name__ == "__main__":
    schedule_scrum_cmd()
