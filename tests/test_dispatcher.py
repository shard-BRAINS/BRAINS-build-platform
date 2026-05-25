"""Tests for dispatcher.py."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from build_platform.dispatcher import (
    DiffValidationError,
    DispatchError,
    dispatch_tier1,
    prepare_tier2_brief,
    validate_diff,
)
from build_platform.ollama_client import OllamaClient
from build_platform.paths import state_dir
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
    client.chat = MagicMock(return_value=DIFF_SAMPLE)  # type: ignore

    proposed_path = dispatch_tier1(project_root, wp, client)
    assert proposed_path.exists()
    assert proposed_path.parent.name == "WP-0001"


def test_dispatch_tier1_retries_then_raises(tmp_path: Path):
    project_root, wp = _seed(tmp_path)
    config = OllamaConfig(models=OllamaModels())
    client = OllamaClient(config)
    client.chat = MagicMock(return_value="not a diff")  # type: ignore

    with pytest.raises(DispatchError):
        dispatch_tier1(project_root, wp, client)
    assert client.chat.call_count == 2


def test_prepare_tier2_brief_emits_instruction_file(tmp_path: Path):
    project_root, wp = _seed(tmp_path)
    wp = wp.model_copy(update={"tier": WPTier.TWO})
    brief_path = prepare_tier2_brief(project_root, wp)
    assert brief_path.exists()
    content = brief_path.read_text(encoding="utf-8")
    assert "build-backend-sme" in content
    assert "WP-0001" in content
    assert "src/foo.py" in content


def test_dispatch_tier1_refuses_oversized_scope(tmp_path: Path):
    """A tier-1 WP whose scope_files exceed 50KB total must raise before hitting Ollama."""
    project_root, wp = _seed(tmp_path)
    big = "x" * 60_000  # 60KB > 50KB cap
    (project_root / "src" / "foo.py").write_text(big, encoding="utf-8")

    config = OllamaConfig(models=OllamaModels())
    client = OllamaClient(config)
    client.chat = MagicMock()  # type: ignore

    with pytest.raises(DispatchError) as ei:
        dispatch_tier1(project_root, wp, client)
    assert "50000" in str(ei.value) or "50,000" in str(ei.value) or "scope exceeds" in str(ei.value)
    assert client.chat.call_count == 0  # never reached Ollama
