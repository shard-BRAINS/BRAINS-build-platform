"""Pydantic models for all .brains-build/ state files."""
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class WPState(str, Enum):
    DEFINED = "defined"
    DISPATCHED = "dispatched"
    IN_REVIEW = "in_review"
    DONE = "done"
    BLOCKED = "blocked"


class WPTier(int, Enum):
    ONE = 1
    TWO = 2


class WPHistoryEvent(BaseModel):
    at: str  # ISO-8601
    by: str  # persona id or user:<name>
    event: str


class WorkPackage(BaseModel):
    id: str
    title: str
    workstream: str
    deliverable_id: str
    tier: WPTier
    executor_persona: str
    spec: str
    spec_files: list[str] = Field(default_factory=list)
    acceptance: list[str]
    depends_on: list[str] = Field(default_factory=list)
    consult: list[str] = Field(default_factory=list)
    state: WPState
    created_by: str
    created_at: str  # ISO-8601
    history: list[WPHistoryEvent] = Field(default_factory=list)


class Deliverable(BaseModel):
    id: str
    title: str
    why: str
    acceptance: list[str] = Field(min_length=1)
    sequence: int
    state: Literal["not_started", "in_progress", "acceptance_review", "done"]


class Workstream(BaseModel):
    id: str
    owner_persona: str
    review_persona: str
    description: str


class Project(BaseModel):
    name: str
    mission: str
    stack: list[str]
    constraints: list[str]
    # "local" — files are canonical (v1 default).
    # "github" — files are still canonical for writes; GitHub is a one-way mirror (v2.5).
    # Future "github-canonical" would mean GitHub is source of truth.
    ground_truth: Literal["local", "github"] = "local"
    created: str  # ISO-8601


class OllamaModels(BaseModel):
    tier1_default: str = "qwen2.5-coder:7b"
    summarizer: str = "llama3.2:3b"
    fallback: str = "qwen2.5-coder:7b"


class OllamaPreflight(BaseModel):
    require_running: bool = True
    auto_pull_missing: bool = False


class OllamaConfig(BaseModel):
    url: str = "http://localhost:11434"
    timeout_seconds: int = 300
    max_retries: int = 3  # transient network errors only; HTTP error codes not retried
    retry_backoff_base_seconds: float = 1.0  # backoff is base * 2**attempt
    models: OllamaModels = Field(default_factory=OllamaModels)
    preflight: OllamaPreflight = Field(default_factory=OllamaPreflight)


class ProjectConfig(BaseModel):
    test_command: str = "pytest"
    lint_command: str = "ruff check"


class ScrumSchedule(BaseModel):
    """Optional cron reminder for the weekly scrum.

    Registered via the user's `schedule` skill (remote routine). Routines run
    in Claude's cloud and cannot read the local .brains-build/ directory — so
    this fires a PushNotification reminding the user to open Claude Code and
    run /build-scrum themselves. The PMO Lead pass still happens locally.
    """
    enabled: bool = False
    cron: str = "0 9 * * 1"  # 09:00 every Monday (5-field cron: M H DOM MON DOW)
    routine_id: str | None = None  # populated after the user creates the routine
    timezone: str = "UTC"


class GitHubMirrorConfig(BaseModel):
    """One-way push mirror to GitHub Issues + Milestones (v2.5).

    Disabled by default. Configure via `/build-mirror init --owner X --repo Y`.
    """
    enabled: bool = False
    owner: str | None = None
    repo: str | None = None
    label_prefix: str = "bbp:"  # namespace for platform-managed labels
    last_synced_at: str | None = None  # ISO-8601 of last successful push


class Config(BaseModel):
    ollama: OllamaConfig
    project: ProjectConfig
    scrum_schedule: ScrumSchedule = Field(default_factory=ScrumSchedule)
    github: GitHubMirrorConfig = Field(default_factory=GitHubMirrorConfig)
