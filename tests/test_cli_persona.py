"""Tests for cli/persona.py."""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.init import init_cmd
from build_platform.cli.persona import persona_group


def _init(tmp_path: Path):
    runner = CliRunner()
    r = runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:T:why:accept",
        "--json",
    ])
    assert r.exit_code == 0, r.output


def test_register_creates_persona_file(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    r = runner.invoke(persona_group, [
        "register", "--root", str(tmp_path),
        "--id", "build-data-sme",
        "--description", "Data engineering SME for pipelines and warehousing",
        "--mission", "Execute data work packages — pipelines, schemas, data tests.",
        "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["ok"] is True
    assert payload["id"] == "build-data-sme"
    persona_path = Path(payload["path"])
    assert persona_path.exists()
    content = persona_path.read_text(encoding="utf-8")
    assert "name: build-data-sme" in content
    assert "claude-sonnet-5" in content  # default executor model
    assert "Data engineering SME" in content
    assert "# Mission" in content


def test_register_rejects_invalid_id(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    r = runner.invoke(persona_group, [
        "register", "--root", str(tmp_path),
        "--id", "not-prefixed",
        "--description", "x", "--mission", "y", "--json",
    ])
    assert r.exit_code == 2
    assert "Invalid id" in r.output


def test_register_refuses_overwrite_without_force(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    args = [
        "register", "--root", str(tmp_path),
        "--id", "build-data-sme",
        "--description", "x", "--mission", "y", "--json",
    ]
    runner.invoke(persona_group, args)
    r = runner.invoke(persona_group, args)  # second time, no --force
    assert r.exit_code == 3
    assert "already exists" in r.output


def test_register_overwrites_with_force(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    runner.invoke(persona_group, [
        "register", "--root", str(tmp_path),
        "--id", "build-data-sme",
        "--description", "first", "--mission", "first mission", "--json",
    ])
    r = runner.invoke(persona_group, [
        "register", "--root", str(tmp_path),
        "--id", "build-data-sme",
        "--description", "second", "--mission", "second mission",
        "--force", "--json",
    ])
    assert r.exit_code == 0
    persona_path = Path(json.loads(r.output)["path"])
    assert "second mission" in persona_path.read_text(encoding="utf-8")


def test_register_with_leadership_tier_picks_opus(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    r = runner.invoke(persona_group, [
        "register", "--root", str(tmp_path),
        "--id", "build-research-lead",
        "--tier", "leadership",
        "--description", "Research lead for synthesis",
        "--mission", "Synthesize findings across the team.",
        "--json",
    ])
    assert r.exit_code == 0
    content = Path(json.loads(r.output)["path"]).read_text(encoding="utf-8")
    assert "claude-opus-4-8" in content
    assert "TodoWrite" in content  # leadership default tools


def test_register_with_read_only_tier_omits_write_tools(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    r = runner.invoke(persona_group, [
        "register", "--root", str(tmp_path),
        "--id", "build-audit-sme",
        "--tier", "read-only",
        "--description", "Auditor",
        "--mission", "Audit, do not modify.",
        "--json",
    ])
    assert r.exit_code == 0
    content = Path(json.loads(r.output)["path"]).read_text(encoding="utf-8")
    # Read-only tier should not include Write/Edit/Bash full-set
    tools_line = next(line for line in content.splitlines() if line.startswith("tools:"))
    assert "Write" not in tools_line
    assert "Edit" not in tools_line


def test_list_shows_local_personas(tmp_path: Path):
    _init(tmp_path)
    runner = CliRunner()
    runner.invoke(persona_group, [
        "register", "--root", str(tmp_path),
        "--id", "build-data-sme",
        "--description", "x", "--mission", "y", "--json",
    ])
    r = runner.invoke(persona_group, ["list", "--root", str(tmp_path), "--json"])
    assert r.exit_code == 0
    payload = json.loads(r.output)
    local_ids = [p["id"] for p in payload["personas"] if p["scope"] == "local"]
    assert "build-data-sme" in local_ids


def test_install_copies_to_global(tmp_path: Path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    _init(tmp_path)
    runner = CliRunner()
    runner.invoke(persona_group, [
        "register", "--root", str(tmp_path),
        "--id", "build-data-sme",
        "--description", "x", "--mission", "y", "--json",
    ])
    r = runner.invoke(persona_group, [
        "install", "build-data-sme", "--root", str(tmp_path), "--json",
    ])
    assert r.exit_code == 0, r.output
    dest = fake_home / ".claude" / "agents" / "build" / "build-data-sme.md"
    assert dest.exists()


def test_install_refuses_when_missing(tmp_path: Path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    _init(tmp_path)
    runner = CliRunner()
    r = runner.invoke(persona_group, [
        "install", "build-missing", "--root", str(tmp_path), "--json",
    ])
    assert r.exit_code == 1
    assert "No local persona" in r.output
