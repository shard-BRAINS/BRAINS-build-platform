"""Tests for schemas.py."""
import pytest
from pydantic import ValidationError

from build_platform.schemas import (
    Config,
    Deliverable,
    OllamaConfig,
    OllamaModels,
    Project,
    ProjectConfig,
    WorkPackage,
    Workstream,
    WPState,
    WPTier,
)


def test_project_minimal():
    p = Project(
        name="demo",
        mission="Build a demo",
        stack=["python"],
        constraints=[],
        ground_truth="local",
        created="2026-05-25T10:00:00Z",
    )
    assert p.name == "demo"
    assert p.ground_truth == "local"


def test_project_rejects_unknown_ground_truth():
    with pytest.raises(ValidationError):
        Project(
            name="x", mission="y", stack=[], constraints=[],
            ground_truth="s3-bucket", created="2026-05-25T10:00:00Z",
        )


def test_project_accepts_local_and_github_ground_truth():
    # local is v1, github is v2.5 (one-way mirror; files still canonical for writes)
    Project(name="x", mission="y", stack=[], constraints=[],
            ground_truth="local", created="2026-05-25T10:00:00Z")
    Project(name="x", mission="y", stack=[], constraints=[],
            ground_truth="github", created="2026-05-25T10:00:00Z")


def test_deliverable_acceptance_required():
    with pytest.raises(ValidationError):
        Deliverable(id="D-x", title="X", why="y", acceptance=[], sequence=1, state="not_started")


def test_work_package_tier_must_be_1_or_2():
    base = dict(
        id="WP-0001", title="t", workstream="backend", deliverable_id="D-x",
        executor_persona="build-backend-sme", spec="s", spec_files=["f.py"],
        acceptance=["a"], depends_on=[], consult=[], state=WPState.DEFINED,
        created_by="build-dev-orchestrator", created_at="2026-05-25T10:00:00Z",
        history=[],
    )
    WorkPackage(**base, tier=WPTier.ONE)
    WorkPackage(**base, tier=WPTier.TWO)
    with pytest.raises(ValidationError):
        WorkPackage(**base, tier=3)


def test_work_package_state_transitions_are_strings():
    wp = WorkPackage(
        id="WP-0001", title="t", workstream="backend", deliverable_id="D-x",
        tier=WPTier.ONE, executor_persona="build-backend-sme", spec="s",
        spec_files=["f.py"], acceptance=["a"], depends_on=[], consult=[],
        state=WPState.DEFINED, created_by="build-dev-orchestrator",
        created_at="2026-05-25T10:00:00Z", history=[],
    )
    assert wp.state.value == "defined"


def test_config_defaults_for_ollama_url():
    c = Config(ollama=OllamaConfig(models=OllamaModels()), project=ProjectConfig(test_command="pytest"))
    assert c.ollama.url == "http://localhost:11434"
    assert c.ollama.models.tier1_default == "qwen2.5-coder:7b"
    assert c.ollama.models.summarizer == "llama3.2:3b"


def test_workstream_minimal():
    ws = Workstream(
        id="backend",
        owner_persona="build-backend-sme",
        review_persona="build-dev-orchestrator",
        description="Server-side code",
    )
    assert ws.id == "backend"
