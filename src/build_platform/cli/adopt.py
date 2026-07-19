"""`/build-adopt` entry point — survey an existing codebase for spec mining.

Emits facts only. Turning those facts into deliverables and acceptance criteria
is the analyst's job, and confirming them is the user's.
"""
import json
import sys
from pathlib import Path

import click

from build_platform.survey import render_survey, survey_repo, write_survey


@click.command("adopt")
@click.option("--root", type=click.Path(file_okay=False), default=".",
              help="Root of the codebase to survey.")
@click.option("--write/--no-write", "do_write", default=True,
              help="Write survey.json + survey.md under .brains-build/adopt/ (default: write).")
@click.option("--json", "as_json", is_flag=True, help="Emit the survey as JSON on stdout.")
def adopt_cmd(root, do_write, as_json):
    """Survey an existing codebase so a build project can be defined over it."""
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        msg = f"Not a directory: {root_path}"
        click.echo(json.dumps({"error": msg}) if as_json else f"Error: {msg}", err=True)
        sys.exit(1)

    survey = survey_repo(root_path)

    written: dict[str, str] = {}
    if do_write:
        json_path, md_path = write_survey(root_path, survey)
        written = {
            "json": str(json_path.relative_to(root_path)).replace("\\", "/"),
            "md": str(md_path.relative_to(root_path)).replace("\\", "/"),
        }

    if as_json:
        click.echo(json.dumps({"ok": True, "survey": survey, "written": written}))
        sys.exit(0)

    # The brief is typeset markdown (em-dashes, arrows) and the file on disk is
    # UTF-8, but a Windows console is often cp1252 and would raise on those
    # characters. Degrade the terminal copy rather than crash the command.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    click.echo(render_survey(survey))
    if written:
        click.echo(f"\nWritten: {written['json']}, {written['md']}")
    already_initialised = (root_path / ".brains-build" / "project.yml").exists()
    click.echo(
        "\nNext: spawn build-business-analyst with this survey to propose deliverables, "
        "then confirm them before "
        + ("updating deliverables.yml." if already_initialised else "running /build-init.")
    )
    sys.exit(0)


if __name__ == "__main__":
    adopt_cmd()
