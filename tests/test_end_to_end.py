"""End-to-end smoke test that mirrors the v1 acceptance criteria from the spec."""
import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from build_platform.cli.dashboard import dashboard_cmd
from build_platform.cli.dispatch import dispatch_cmd
from build_platform.cli.init import init_cmd
from build_platform.cli.package import package_cmd
from build_platform.cli.scrum import scrum_cmd
from build_platform.cli.status import status_cmd


def test_full_loop(tmp_path: Path):
    """Init -> add 3 WPs (1 tier-1, 2 tier-2) -> dispatch all -> scrum -> dashboard."""
    runner = CliRunner()

    # 1. Init
    r = runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "SmokeProject", "--mission", "Verify the platform end-to-end",
        "--stack", "python",
        "--deliverable", "D-core:Core feature:we need a function:tests pass;module importable",
        "--json",
    ])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["ok"] is True

    # Stub a source file the WPs touch
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "core.py").write_text('def hello(): return "old"\n', encoding="utf-8")

    # 2. Add 1 tier-1 WP
    r = runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "Update hello() return", "--workstream", "backend", "--deliverable", "D-core",
        "--tier", "1", "--executor", "build-backend-sme",
        "--spec", "Change hello() return value to 'new'", "--file", "src/core.py",
        "--accept", "function returns 'new'",
        "--json",
    ])
    assert r.exit_code == 0, r.output

    # 3. Add 2 tier-2 WPs
    for title in ("Add greeting parameter", "Add farewell function"):
        r = runner.invoke(package_cmd, [
            "--root", str(tmp_path),
            "--title", title, "--workstream", "backend", "--deliverable", "D-core",
            "--tier", "2", "--executor", "build-backend-sme",
            "--spec", "See title", "--file", "src/core.py",
            "--accept", "tests pass",
            "--json",
        ])
        assert r.exit_code == 0, r.output

    # 4. Dispatch all 3 (tier-1 needs Ollama mocked)
    diff = ('--- a/src/core.py\n+++ b/src/core.py\n@@ -1,1 +1,1 @@\n'
            '-def hello(): return "old"\n+def hello(): return "new"\n')
    with patch("build_platform.cli.dispatch.OllamaClient") as MockClient:
        instance = MockClient.return_value
        instance.preflight.return_value = None
        instance.chat_with_metrics.return_value = (diff, {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
        r = runner.invoke(dispatch_cmd, ["--root", str(tmp_path), "--wp", "WP-0001", "--json"])
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["tier"] == 1

    r = runner.invoke(dispatch_cmd, ["--root", str(tmp_path), "--wp", "WP-0002", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["tier"] == 2

    r = runner.invoke(dispatch_cmd, ["--root", str(tmp_path), "--wp", "WP-0003", "--json"])
    assert r.exit_code == 0, r.output

    # 5. Status reflects the 3 WPs
    r = runner.invoke(status_cmd, ["--root", str(tmp_path), "--json"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["total_wps"] == 3
    assert payload["by_state"]["dispatched"] == 3

    # 6. Scrum produces recap stub
    r = runner.invoke(scrum_cmd, ["--root", str(tmp_path), "--json"])
    assert r.exit_code == 0, r.output
    recap_path = Path(json.loads(r.output)["recap_stub"])
    assert recap_path.exists()
    assert "TO BE FILLED" in recap_path.read_text(encoding="utf-8")

    # 7. Dashboard shows all sections
    r = runner.invoke(dashboard_cmd, ["--root", str(tmp_path), "--json"])
    assert r.exit_code == 0, r.output
    dash_path = Path(json.loads(r.output)["path"])
    dash = dash_path.read_text(encoding="utf-8")
    for section in [
        "Plan position", "Live", "Health", "Deliverables", "Workstreams",
        "Persona activity", "Daily completed work", "Open blockers",
        "Recent decisions", "Up next",
    ]:
        assert section in dash, f"Missing section: {section}"

    # 8. Audit entries exist for all 3 dispatches
    audit_files = list((tmp_path / ".brains-build" / "audit").glob("WP-*.md"))
    assert len(audit_files) >= 3
