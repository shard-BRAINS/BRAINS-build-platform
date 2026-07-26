"""Tests for console-safe output.

The bug these pin down does not reproduce under CliRunner: it buffers UTF-8, so
every typeset character encodes fine and the tests stay green while the real
Windows console raises UnicodeEncodeError. So these tests drive the encoding
decision directly, with a stub stream standing in for a cp1252 terminal.
"""
import io
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.init import init_cmd
from build_platform.cli.package import package_cmd
from build_platform.cli.status import status_cmd, _human
from build_platform.console import console_safe
from build_platform.state import load_wp_state


class _Stream(io.StringIO):
    """A stream that reports an encoding, the way a real terminal does."""

    def __init__(self, encoding: str):
        super().__init__()
        self._encoding = encoding

    @property
    def encoding(self) -> str:
        return self._encoding


def test_utf8_stream_keeps_typography():
    text = "WP-0001 · title — done"
    assert console_safe(text, _Stream("utf-8")) == text


def test_cp1252_stream_gets_ascii_equivalents():
    out = console_safe("WP-0001 · title — done → next", _Stream("cp1252"))
    assert out == "WP-0001 * title -- done -> next"
    out.encode("cp1252")  # must not raise; that is the whole point


def test_characters_outside_the_table_degrade_rather_than_crash():
    out = console_safe("progress: 50▓ done", _Stream("cp1252"))
    out.encode("cp1252")
    assert "progress" in out and "done" in out


def test_ascii_only_text_is_untouched_on_any_stream():
    text = "plain ascii output"
    assert console_safe(text, _Stream("cp1252")) == text
    assert console_safe(text, _Stream("utf-8")) == text


def test_stream_without_an_encoding_attribute_is_assumed_utf8():
    text = "kept · verbatim"
    assert console_safe(text, io.StringIO()) == text


def test_json_payloads_survive_a_cp1252_console():
    """JSON output must stay parseable after transliteration."""
    payload = {"escalation": "WP-0001 failed — hand to build-debug-sme"}
    raw = console_safe(json.dumps(payload), _Stream("cp1252"))
    raw.encode("cp1252")
    assert json.loads(raw)["escalation"].endswith("build-debug-sme")


def test_status_human_output_is_printable_on_a_cp1252_console(tmp_path: Path):
    """The regression: `status --wp` used to mangle its separators."""
    runner = CliRunner()
    runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:Title:why:accept", "--json",
    ])
    r = runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "thing", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "1", "--executor", "build-backend-sme",
        "--spec", "do stuff", "--file", "src/foo.py",
        "--accept", "tests pass", "--json",
    ])
    wp_id = json.loads(r.output)["wp_id"]

    rendered = _human(load_wp_state(tmp_path)[wp_id])
    safe = console_safe(rendered, _Stream("cp1252"))
    safe.encode("cp1252")
    assert "?" not in safe, "output degraded to replacement characters"
    assert wp_id in safe

    # And the command itself still works end to end.
    r = runner.invoke(status_cmd, ["--root", str(tmp_path), "--wp", wp_id])
    assert r.exit_code == 0, r.output
