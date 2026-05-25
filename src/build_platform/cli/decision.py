"""`/build-decision` entry point — append a decision to decisions.md."""
import json
from datetime import datetime, timezone
from pathlib import Path

import click

from build_platform.paths import find_brains_build_root


@click.command("decision")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--title", required=True)
@click.option("--owner", required=True, help="Persona id or 'user:<name>'.")
@click.option("--decision", required=True, help="What was decided (one sentence).")
@click.option("--why", required=True, help="Rationale.")
@click.option("--alternative", "alternatives", multiple=True, default=(),
              help="Alternative considered, format: 'name:why rejected' (repeatable).")
@click.option("--related-wp", "related_wps", multiple=True, default=())
@click.option("--audit-link", default=None)
@click.option("--json", "as_json", is_flag=True)
def decision_cmd(root, title, owner, decision, why, alternatives, related_wps, audit_link, as_json):
    root_path = Path(root).resolve() if root else find_brains_build_root()
    decisions_md = root_path / ".brains-build" / "decisions.md"

    date = datetime.now(timezone.utc).date().isoformat()
    alts_str = ", ".join(
        f"{a.split(':', 1)[0]} (rejected: {a.split(':', 1)[1] if ':' in a else '—'})"
        for a in alternatives
    ) or "_None_"
    related_str = ", ".join(related_wps) or "_None_"
    audit_str = f"[{audit_link}]({audit_link})" if audit_link else "_None_"

    entry = (
        f"\n## {date} — {title}\n"
        f"**Owner:** {owner}\n"
        f"**Decision:** {decision}\n"
        f"**Why:** {why}\n"
        f"**Alternatives considered:** {alts_str}\n"
        f"**Related WPs:** {related_str}\n"
        f"**Audit:** {audit_str}\n"
    )
    with decisions_md.open("a", encoding="utf-8") as f:
        f.write(entry)

    payload = {"ok": True, "decision_date": date, "title": title}
    click.echo(json.dumps(payload) if as_json else f"Decision logged: {title}")


if __name__ == "__main__":
    decision_cmd()
