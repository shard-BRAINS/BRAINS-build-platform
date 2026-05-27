"""Tests for cli/portfolio.py."""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.init import init_cmd
from build_platform.cli.portfolio import portfolio_group


def _init_project(tmp_path: Path, name: str = "Demo") -> Path:
    runner = CliRunner()
    project_root = tmp_path / name.lower()
    project_root.mkdir()
    r = runner.invoke(init_cmd, [
        "--root", str(project_root),
        "--name", name, "--mission", f"{name} mission",
        "--stack", "python",
        "--deliverable", f"D-{name.lower()}:Title:Why:accept criterion",
        "--json",
    ])
    assert r.exit_code == 0, r.output
    return project_root


def _fake_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def test_register_adds_project(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    project = _init_project(tmp_path, "Alpha")
    runner = CliRunner()
    r = runner.invoke(portfolio_group, [
        "register", str(project), "--home", str(home), "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert (home / ".brains-build-portfolio.yml").exists()


def test_register_rejects_non_project(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    runner = CliRunner()
    r = runner.invoke(portfolio_group, [
        "register", str(tmp_path), "--home", str(home), "--json",
    ])
    assert r.exit_code == 2
    assert "not a BRAINS" in r.output


def test_register_idempotent(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    project = _init_project(tmp_path, "Alpha")
    runner = CliRunner()
    runner.invoke(portfolio_group, ["register", str(project), "--home", str(home), "--json"])
    r = runner.invoke(portfolio_group, [
        "register", str(project), "--home", str(home), "--json",
    ])
    payload = json.loads(r.output)
    assert payload["ok"] is True
    assert payload.get("already_registered") is True


def test_unregister_removes_project(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    project = _init_project(tmp_path, "Alpha")
    runner = CliRunner()
    runner.invoke(portfolio_group, ["register", str(project), "--home", str(home), "--json"])
    r = runner.invoke(portfolio_group, [
        "unregister", str(project), "--home", str(home), "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["count"] == 0


def test_unregister_unknown_path(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    runner = CliRunner()
    r = runner.invoke(portfolio_group, [
        "unregister", str(tmp_path / "nope"), "--home", str(home), "--json",
    ])
    assert r.exit_code == 1


def test_list_shows_registered(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    p1 = _init_project(tmp_path, "Alpha")
    p2 = _init_project(tmp_path, "Beta")
    runner = CliRunner()
    runner.invoke(portfolio_group, ["register", str(p1), "--home", str(home), "--json"])
    runner.invoke(portfolio_group, ["register", str(p2), "--home", str(home), "--json"])
    r = runner.invoke(portfolio_group, ["list", "--home", str(home), "--json"])
    payload = json.loads(r.output)
    assert payload["count"] == 2
    assert any("alpha" in p.lower() for p in payload["projects"])
    assert any("beta" in p.lower() for p in payload["projects"])


def test_view_markdown_aggregates_projects(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    p1 = _init_project(tmp_path, "Alpha")
    p2 = _init_project(tmp_path, "Beta")
    runner = CliRunner()
    runner.invoke(portfolio_group, ["register", str(p1), "--home", str(home), "--json"])
    runner.invoke(portfolio_group, ["register", str(p2), "--home", str(home), "--json"])
    r = runner.invoke(portfolio_group, [
        "view", "--home", str(home), "--format", "md", "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["count"] == 2
    names = [row["name"] for row in payload["rows"]]
    assert "Alpha" in names and "Beta" in names


def test_view_html_writes_file(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    project = _init_project(tmp_path, "Alpha")
    runner = CliRunner()
    runner.invoke(portfolio_group, ["register", str(project), "--home", str(home), "--json"])
    r = runner.invoke(portfolio_group, [
        "view", "--home", str(home), "--format", "html", "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    html_path = Path(payload["written"]["html"])
    assert html_path.exists()
    content = html_path.read_text(encoding="utf-8")
    assert "<title>BRAINS Build Platform — Portfolio</title>" in content
    assert "Alpha" in content
    assert "#D99518" in content  # brand color


def test_view_handles_missing_project(tmp_path: Path):
    """A registered path that no longer has .brains-build/ produces an error row, not a crash."""
    home = tmp_path / "home"
    home.mkdir()
    project = _init_project(tmp_path, "Alpha")
    runner = CliRunner()
    runner.invoke(portfolio_group, ["register", str(project), "--home", str(home), "--json"])
    # Remove the state dir to simulate a deleted/moved project
    import shutil
    shutil.rmtree(project / ".brains-build")
    r = runner.invoke(portfolio_group, [
        "view", "--home", str(home), "--format", "md", "--json",
    ])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["rows"][0].get("error") == "not a build project"


def test_view_empty_portfolio(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    runner = CliRunner()
    r = runner.invoke(portfolio_group, [
        "view", "--home", str(home), "--format", "md", "--json",
    ])
    assert r.exit_code == 0
    payload = json.loads(r.output)
    assert payload["count"] == 0
    assert payload["rows"] == []
