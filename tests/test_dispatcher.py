"""Tests for dispatcher.py."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from build_platform.dispatcher import (
    DiffValidationError,
    DispatchError,
    check_diff_applies_cleanly,
    classify_tier1_failure,
    dispatch_tier1,
    prepare_tier2_brief,
    strip_markdown_fences,
    validate_diff,
)
from build_platform.ollama_client import OllamaClient
from build_platform.schemas import (
    Config,
    OllamaConfig,
    OllamaModels,
    Project,
    ProjectConfig,
    WorkPackage,
    WPState,
    WPTier,
)
from build_platform.state import (
    append_work_package,
    init_state_tree,
    save_config,
    save_project,
)

DIFF_SAMPLE = """\
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,2 +1,2 @@
-def hello(): return "old"
+def hello(): return "new"
"""


def _seed(tmp_path: Path) -> tuple[Path, WorkPackage]:
    init_state_tree(tmp_path)
    save_project(tmp_path, Project(
        name="D", mission="d", stack=["python"], constraints=[],
        ground_truth="local", created="2026-05-25T10:00:00Z",
    ))
    save_config(tmp_path, Config(
        ollama=OllamaConfig(models=OllamaModels()),
        project=ProjectConfig(test_command="pytest"),
    ))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text('def hello(): return "old"\n', encoding="utf-8")
    wp = WorkPackage(
        id="WP-0001", title="Update return", workstream="backend", deliverable_id="D-x",
        tier=WPTier.ONE, executor_persona="build-backend-sme",
        spec="Change return value to 'new'", spec_files=["src/foo.py"],
        acceptance=["function returns 'new'"], depends_on=[], consult=[],
        state=WPState.DEFINED, created_by="build-dev-orchestrator",
        created_at="2026-05-25T10:00:00Z", history=[],
    )
    append_work_package(tmp_path, wp)
    return tmp_path, wp


def test_validate_diff_accepts_well_formed(tmp_path: Path):
    validate_diff(DIFF_SAMPLE, allowed_files=["src/foo.py"])


def test_validate_diff_rejects_disallowed_file(tmp_path: Path):
    with pytest.raises(DiffValidationError):
        validate_diff(DIFF_SAMPLE, allowed_files=["src/bar.py"])


def test_validate_diff_rejects_garbage():
    with pytest.raises(DiffValidationError):
        validate_diff("not a diff at all", allowed_files=["src/foo.py"])


def test_dispatch_tier1_writes_proposed_diff(tmp_path: Path):
    project_root, wp = _seed(tmp_path)
    config = OllamaConfig(models=OllamaModels())
    client = OllamaClient(config)
    client.chat_with_metrics = MagicMock(  # type: ignore
        return_value=(DIFF_SAMPLE, {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
    )

    proposed_path, _ = dispatch_tier1(project_root, wp, client)
    assert proposed_path.exists()
    assert proposed_path.parent.name == "WP-0001"


def test_dispatch_tier1_retries_then_raises(tmp_path: Path):
    project_root, wp = _seed(tmp_path)
    config = OllamaConfig(models=OllamaModels())
    client = OllamaClient(config)
    client.chat_with_metrics = MagicMock(  # type: ignore
        return_value=("not a diff", {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
    )

    with pytest.raises(DispatchError):
        dispatch_tier1(project_root, wp, client)
    assert client.chat_with_metrics.call_count == 2


def test_prepare_tier2_brief_emits_instruction_file(tmp_path: Path):
    project_root, wp = _seed(tmp_path)
    wp = wp.model_copy(update={"tier": WPTier.TWO})
    brief_path = prepare_tier2_brief(project_root, wp)
    assert brief_path.exists()
    content = brief_path.read_text(encoding="utf-8")
    assert "build-backend-sme" in content
    assert "WP-0001" in content
    assert "src/foo.py" in content


def test_tier1_prompt_contains_scope_discipline_section(tmp_path: Path):
    """Finding #3: tier-1 prompt must contain explicit anti-speculation language."""
    project_root, wp = _seed(tmp_path)
    config = OllamaConfig(models=OllamaModels())
    client = OllamaClient(config)
    captured: dict = {}

    def capture_chat_with_metrics(*, model, prompt, system=None):
        captured["prompt"] = prompt
        return DIFF_SAMPLE, {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}

    client.chat_with_metrics = capture_chat_with_metrics  # type: ignore
    dispatch_tier1(project_root, wp, client)
    p = captured["prompt"]
    # Anti-speculation language
    assert "Scope discipline" in p
    assert "speculative" in p.lower() or "speculation" in p.lower()
    assert "SEPARATE work package" in p or "separate WP" in p.lower()
    # Self-check section
    assert "Self-check before outputting" in p
    # Empty-diff escape hatch
    assert "empty diff" in p.lower()


def test_strip_markdown_fences_removes_diff_block():
    """Ollama sometimes wraps output in ```diff ... ``` fences. Strip them."""
    wrapped = "```diff\n" + DIFF_SAMPLE.strip() + "\n```\n"
    cleaned = strip_markdown_fences(wrapped)
    assert cleaned.lstrip().startswith("--- a/src/foo.py")
    assert not cleaned.startswith("```")
    assert "```" not in cleaned.rstrip().split("\n")[-1]


def test_strip_markdown_fences_handles_plain_diff():
    """Plain diff (no fences) passes through unchanged (modulo trailing newline)."""
    cleaned = strip_markdown_fences(DIFF_SAMPLE)
    assert cleaned.lstrip().startswith("--- a/src/foo.py")


def test_validate_diff_accepts_fenced_input():
    """Finding #2: a valid diff wrapped in markdown fences must validate."""
    wrapped = "```diff\n" + DIFF_SAMPLE.strip() + "\n```\n"
    validate_diff(wrapped, allowed_files=["src/foo.py"])  # must not raise


def test_validate_diff_rejects_prose_before_diff():
    """Diff with explanatory text before the headers must be rejected."""
    polluted = "Sure! Here's the diff:\n\n" + DIFF_SAMPLE
    with pytest.raises(DiffValidationError) as ei:
        validate_diff(polluted, allowed_files=["src/foo.py"])
    assert "must start with" in str(ei.value)


def test_dispatch_tier1_persists_clean_diff_when_input_is_fenced(tmp_path: Path):
    """Finding #2: proposed.diff on disk must be clean (no fences), so git apply works."""
    project_root, wp = _seed(tmp_path)
    config = OllamaConfig(models=OllamaModels())
    client = OllamaClient(config)
    fenced = "```diff\n" + DIFF_SAMPLE.strip() + "\n```\n"
    client.chat_with_metrics = MagicMock(  # type: ignore
        return_value=(fenced, {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
    )

    proposed, _ = dispatch_tier1(project_root, wp, client)
    content = proposed.read_text(encoding="utf-8")
    assert not content.lstrip().startswith("```")
    assert content.lstrip().startswith("--- a/src/foo.py")


def test_check_diff_applies_cleanly_returns_true_for_non_git_dir(tmp_path: Path):
    """Finding #11: in a non-git directory, skip the apply-check (return True)."""
    ok, err = check_diff_applies_cleanly(tmp_path, DIFF_SAMPLE)
    assert ok is True
    assert err == ""


def test_check_diff_applies_cleanly_detects_bad_hunk_header(tmp_path: Path):
    """Finding #11: a diff with wrong @@ line counts is rejected by git apply --check.

    The real-world failure from re-dogfood: Ollama generated `@@ -21,6 +21,7 @@`
    when the actual content was 3 context lines + 2 added (should be `-21,3 +21,5`).
    """
    import subprocess
    # Set up a real tiny git repo
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text('def hello(): return "old"\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=tmp_path, check=True, capture_output=True)

    bad_hunk_counts = (
        "--- a/src/foo.py\n"
        "+++ b/src/foo.py\n"
        "@@ -1,6 +1,7 @@\n"            # wrong: source has only 1 line, says 6
        '-def hello(): return "old"\n'
        '+def hello(): return "new"\n'
    )
    ok, err = check_diff_applies_cleanly(tmp_path, bad_hunk_counts)
    assert ok is False
    assert err  # non-empty error message


def test_check_diff_applies_cleanly_accepts_well_formed(tmp_path: Path):
    """A diff with correct hunk counts and matching source content applies cleanly."""
    import subprocess
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text('def hello(): return "old"\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=tmp_path, check=True, capture_output=True)

    good = (
        "--- a/src/foo.py\n"
        "+++ b/src/foo.py\n"
        "@@ -1 +1 @@\n"
        '-def hello(): return "old"\n'
        '+def hello(): return "new"\n'
    )
    ok, err = check_diff_applies_cleanly(tmp_path, good)
    assert ok is True
    assert err == ""


def test_dispatch_tier1_retries_when_diff_passes_validation_but_fails_apply(tmp_path: Path):
    """Finding #11 end-to-end: Ollama returns a structurally valid but un-appliable
    diff on attempt 1, then a cleanly-appliable diff on attempt 2. Dispatch should
    succeed with the second one."""
    import subprocess
    project_root, wp = _seed(tmp_path)
    # Make the seeded project a real git repo so check_diff_applies_cleanly runs.
    subprocess.run(["git", "init", "-b", "main"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=project_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=project_root, check=True, capture_output=True)

    config = OllamaConfig(models=OllamaModels())
    client = OllamaClient(config)
    bad = (
        "--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1,6 +1,7 @@\n"
        '-def hello(): return "old"\n+def hello(): return "new"\n'
    )
    good = (
        "--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1 +1 @@\n"
        '-def hello(): return "old"\n+def hello(): return "new"\n'
    )
    client.chat_with_metrics = MagicMock(  # type: ignore
        side_effect=[
            (bad, {"tokens_in": 10, "tokens_out": 5, "cost_usd": 0.0}),
            (good, {"tokens_in": 10, "tokens_out": 5, "cost_usd": 0.0}),
        ]
    )

    proposed, _ = dispatch_tier1(project_root, wp, client)
    assert proposed.exists()
    assert client.chat_with_metrics.call_count == 2
    # Second prompt should mention the hunk-counts hint
    second_call_prompt = client.chat_with_metrics.call_args_list[1].kwargs["prompt"]
    assert "@@" in second_call_prompt
    assert "SOURCE_COUNT" in second_call_prompt


def test_dispatch_tier1_refuses_oversized_scope(tmp_path: Path):
    """A tier-1 WP whose scope_files exceed 50KB total must raise before hitting Ollama."""
    project_root, wp = _seed(tmp_path)
    big = "x" * 60_000  # 60KB > 50KB cap
    (project_root / "src" / "foo.py").write_text(big, encoding="utf-8")

    config = OllamaConfig(models=OllamaModels())
    client = OllamaClient(config)
    client.chat_with_metrics = MagicMock()  # type: ignore

    with pytest.raises(DispatchError) as ei:
        dispatch_tier1(project_root, wp, client)
    assert "50000" in str(ei.value) or "50,000" in str(ei.value) or "scope exceeds" in str(ei.value)
    assert client.chat_with_metrics.call_count == 0  # never reached Ollama


# ---------------------------------------------------------------------------
# WP-0014: classify_tier1_failure + DispatchError.suggested_action
# ---------------------------------------------------------------------------

def test_classify_tier1_failure_detects_undefined_name_marker():
    """'undefined name' or missing Optional/Literal import in outputs -> retier-to-2."""
    outputs = [
        "some attempt output",
        "NameError: undefined name 'Optional' not imported",
    ]
    result = classify_tier1_failure(outputs)
    assert result == "retier-to-2"


def test_classify_tier1_failure_detects_recurrent_backtick_fences():
    """3+ backtick fences after the prompt forbade them -> retier-to-2."""
    # Simulating raw outputs where the model keeps wrapping code in fences
    fence_output = "```diff\n--- a/x\n+++ b/x\n```\n```diff\nmore\n```\n```\nyet more\n```"
    outputs = ["first attempt no fence", fence_output]
    result = classify_tier1_failure(outputs)
    assert result == "retier-to-2"


def test_classify_tier1_failure_detects_duplicate_function_definitions():
    """Duplicate 'def foo(' in the proposed diff -> retier-to-2."""
    dup_def_output = (
        "--- a/src/x.py\n+++ b/src/x.py\n"
        "@@ -1 +1 @@\n"
        "+def process():\n"
        "+    pass\n"
        "+def process():\n"
        "+    return 1\n"
    )
    outputs = ["first attempt ok", dup_def_output]
    result = classify_tier1_failure(outputs)
    assert result == "retier-to-2"


def test_classify_tier1_failure_returns_none_on_clean_failure():
    """A plain diff-format failure (not a capability gap) returns None."""
    outputs = [
        "--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1 +1 @@\n-old\n+new\n",
        "--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1,6 +1,7 @@\n-old\n+new\n",
    ]
    result = classify_tier1_failure(outputs)
    assert result is None


def test_DispatchError_carries_suggested_action():
    """DispatchError.suggested_action attribute is accessible."""
    err = DispatchError("something went wrong")
    err.suggested_action = "retier-to-2"  # type: ignore[attr-defined]
    assert err.suggested_action == "retier-to-2"

    err2 = DispatchError("plain error")
    assert getattr(err2, "suggested_action", None) is None


def test_dispatch_tier1_raises_with_suggested_action_on_capability_gap(tmp_path: Path):
    """When both raw outputs show a capability-gap marker, DispatchError.suggested_action
    is set to 'retier-to-2'."""
    project_root, wp = _seed(tmp_path)
    config = OllamaConfig(models=OllamaModels())
    client = OllamaClient(config)
    # Both attempts return output with a clear capability gap marker
    bad_output = "NameError: undefined name 'Optional'"
    client.chat_with_metrics = MagicMock(  # type: ignore
        return_value=(bad_output, {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
    )

    with pytest.raises(DispatchError) as ei:
        dispatch_tier1(project_root, wp, client)
    assert getattr(ei.value, "suggested_action", None) == "retier-to-2"


# ---------------------------------------------------------------------------
# WP-0015: dispatch_tier1 returns (Path, metrics) tuple
# ---------------------------------------------------------------------------

def test_dispatch_tier1_returns_metrics_tuple(tmp_path: Path):
    """dispatch_tier1 must return (Path, dict) with token counts."""
    project_root, wp = _seed(tmp_path)
    config = OllamaConfig(models=OllamaModels())
    client = OllamaClient(config)
    # chat_with_metrics is the new underlying method; mock it directly
    client.chat_with_metrics = MagicMock(  # type: ignore
        return_value=(DIFF_SAMPLE, {"tokens_in": 100, "tokens_out": 50, "cost_usd": 0.0})
    )

    result = dispatch_tier1(project_root, wp, client)
    assert isinstance(result, tuple)
    diff_path, metrics = result
    assert diff_path.exists()
    assert metrics["tokens_in"] == 100
    assert metrics["tokens_out"] == 50
    assert metrics["cost_usd"] == 0.0
