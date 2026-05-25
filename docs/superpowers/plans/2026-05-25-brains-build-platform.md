# BRAINS Build Platform v1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the BRAINS Build Platform v1 as a family of 8 Claude skills + 8 subagent definitions + a shared Python package, capable of running a full deliverable → work-package → dispatch → scrum loop on any project.

**Architecture:** Three-tier shape. (1) Thin Claude skills (`build-*`) provide user-facing verbs. (2) Subagents (PMO Lead, Dev Orchestrator, Product Owner, 5 executor SMEs) own judgment work. (3) Shared Python package (`build_platform`) owns deterministic state I/O, schema validation, Ollama HTTP, dashboard rendering, audit writing. Local files under `.brains-build/` are canonical source of truth; Ollama is tier-1 executor for mechanical work; Claude subagents are tier-2 for judgment work.

**Tech Stack:** Python 3.11+, pydantic v2 (schemas), pytest (tests), Jinja2 (templates), httpx (Ollama HTTP), ruamel.yaml (YAML I/O), Claude Code skills + subagents, Ollama runtime.

**Source spec:** [docs/superpowers/specs/2026-05-25-brains-build-platform-design.md](../specs/2026-05-25-brains-build-platform-design.md)

---

## File structure

**Development repo** (`c:\BRAINS_Build_Platform\`):

```
c:\BRAINS_Build_Platform\
├── pyproject.toml                     # Python package metadata + deps
├── README.md                          # Quickstart
├── install.ps1                        # Copies skills/agents to ~/.claude/, installs Python pkg
├── src/
│   └── build_platform/
│       ├── __init__.py                # Public API surface
│       ├── paths.py                   # Resolve .brains-build/ root for current project
│       ├── schemas.py                 # Pydantic models for all state files
│       ├── state.py                   # Read/write/validate state files
│       ├── audit.py                   # Append audit entries
│       ├── git_utils.py               # Read-only git ops (commit log since timestamp)
│       ├── ollama_client.py           # Ollama HTTP client + preflight
│       ├── digest.py                  # Pre-digest helper using summarizer model
│       ├── dispatcher.py              # Core dispatch logic (tier-1 + tier-2 paths)
│       ├── render_dashboard.py        # Dashboard markdown renderer
│       └── cli/
│           ├── __init__.py
│           ├── init.py                # /build-init entry point
│           ├── package.py             # /build-package entry point
│           ├── dispatch.py            # /build-dispatch entry point
│           ├── scrum.py               # /build-scrum entry point
│           ├── status.py              # /build-status entry point
│           ├── decision.py            # /build-decision entry point
│           └── dashboard.py           # /build-dashboard entry point
├── skills/                            # Source skill files (copied to ~/.claude/skills/)
│   ├── build-platform/SKILL.md
│   ├── build-init/SKILL.md
│   ├── build-package/SKILL.md
│   ├── build-dispatch/SKILL.md
│   ├── build-scrum/SKILL.md
│   ├── build-status/SKILL.md
│   ├── build-decision/SKILL.md
│   └── build-dashboard/SKILL.md
├── agents/                            # Source subagent defs (copied to ~/.claude/agents/build/)
│   ├── build-pmo-lead.md
│   ├── build-dev-orchestrator.md
│   ├── build-product-owner.md
│   ├── build-frontend-sme.md
│   ├── build-backend-sme.md
│   ├── build-qa-sme.md
│   ├── build-security-sme.md
│   └── build-devops-sme.md
├── templates/                         # Jinja2 templates (packaged with build_platform)
│   ├── tier1_executor.j2
│   ├── dashboard.md.j2
│   ├── audit_entry.md.j2
│   ├── decision_entry.md.j2
│   └── sprint_recap.md.j2
└── tests/
    ├── conftest.py
    ├── test_schemas.py
    ├── test_state.py
    ├── test_audit.py
    ├── test_git_utils.py
    ├── test_ollama_client.py
    ├── test_digest.py
    ├── test_dispatcher.py
    ├── test_render_dashboard.py
    ├── test_cli_init.py
    ├── test_cli_dispatch.py
    └── fixtures/
        └── seed_project/              # Pre-built .brains-build/ for tests
```

**Installed layout** (after `install.ps1`):
- `C:\Users\matth\.claude\skills\build-*\SKILL.md` — 8 skill files
- `C:\Users\matth\.claude\agents\build\*.md` — 8 subagent files
- `build_platform` Python package installed editable (`pip install -e c:\BRAINS_Build_Platform`)
- Skills call `python -m build_platform.cli.<verb>` from their SKILL.md instructions

---

## Task 0: Repo initialization

**Files:**
- Create: `c:\BRAINS_Build_Platform\.gitignore`
- Create: `c:\BRAINS_Build_Platform\pyproject.toml`
- Create: `c:\BRAINS_Build_Platform\README.md`
- Create: `c:\BRAINS_Build_Platform\src\build_platform\__init__.py`
- Create: `c:\BRAINS_Build_Platform\tests\__init__.py`
- Create: `c:\BRAINS_Build_Platform\tests\conftest.py`

- [ ] **Step 1: Initialize git repo**

Run:
```powershell
cd c:\BRAINS_Build_Platform
git init -b main
```

- [ ] **Step 2: Create .gitignore**

```
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.venv/
dist/
build/
.brains-build/         # Per-project state; never committed to platform repo itself
.ruff_cache/
```

- [ ] **Step 3: Create pyproject.toml**

```toml
[project]
name = "build-platform"
version = "0.1.0"
description = "BRAINS Build Platform — agentic end-to-end software delivery"
requires-python = ">=3.11"
dependencies = [
  "pydantic>=2.6",
  "ruamel.yaml>=0.18",
  "jinja2>=3.1",
  "httpx>=0.27",
  "click>=8.1",
  "rich>=13.7",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "pytest-mock>=3.12", "ruff>=0.4"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
build_platform = ["templates/*.j2", "templates/*.md.j2"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 4: Create README.md**

```markdown
# BRAINS Build Platform

Agentic end-to-end software delivery — Claude skills + subagents + local Python tooling.

See [docs/superpowers/specs/2026-05-25-brains-build-platform-design.md](docs/superpowers/specs/2026-05-25-brains-build-platform-design.md) for the design.

## Install (Windows)

```powershell
cd c:\BRAINS_Build_Platform
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
.\install.ps1
ollama pull qwen2.5-coder:7b
ollama pull llama3.2:3b
```

## Quickstart

```powershell
mkdir c:\path\to\new-project
cd c:\path\to\new-project
# In Claude Code: /build-init
```
```

- [ ] **Step 5: Create empty __init__.py for the package**

`src/build_platform/__init__.py`:
```python
"""BRAINS Build Platform — v1."""

__version__ = "0.1.0"
```

- [ ] **Step 6: Create tests/__init__.py and conftest.py**

`tests/__init__.py`:
```python
```

`tests/conftest.py`:
```python
"""Shared pytest fixtures."""
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """An empty project directory with no .brains-build/ yet."""
    return tmp_path


@pytest.fixture
def seeded_project(tmp_path: Path) -> Path:
    """A project directory with a pre-built .brains-build/ tree."""
    fixture = Path(__file__).parent / "fixtures" / "seed_project"
    shutil.copytree(fixture, tmp_path / "project")
    return tmp_path / "project"
```

- [ ] **Step 7: Create empty fixtures dir**

```powershell
New-Item -ItemType Directory -Force -Path c:\BRAINS_Build_Platform\tests\fixtures\seed_project\.brains-build | Out-Null
```

- [ ] **Step 8: Verify Python package installs**

Run:
```powershell
cd c:\BRAINS_Build_Platform
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```
Expected: installs without error.

- [ ] **Step 9: Run empty test suite**

Run: `pytest`
Expected: `0 passed`, no errors.

- [ ] **Step 10: Commit**

```powershell
git add -A
git commit -m "chore: repo scaffolding (pyproject, package skeleton, test harness)"
```

---

## Task 1: Path resolver

Locates the `.brains-build/` root for the current working directory. Walks up the tree like git does.

**Files:**
- Create: `src/build_platform/paths.py`
- Test: `tests/test_paths.py`

- [ ] **Step 1: Write failing test**

`tests/test_paths.py`:
```python
"""Tests for paths.py."""
from pathlib import Path

import pytest

from build_platform.paths import (
    BrainsBuildNotFoundError,
    find_brains_build_root,
    state_dir,
)


def test_find_brains_build_root_walks_up(tmp_path: Path):
    root = tmp_path / "project"
    (root / ".brains-build").mkdir(parents=True)
    nested = root / "src" / "deep" / "dir"
    nested.mkdir(parents=True)

    found = find_brains_build_root(nested)
    assert found == root


def test_find_brains_build_root_returns_at_root(tmp_path: Path):
    (tmp_path / ".brains-build").mkdir()
    assert find_brains_build_root(tmp_path) == tmp_path


def test_find_brains_build_root_raises_when_missing(tmp_path: Path):
    with pytest.raises(BrainsBuildNotFoundError):
        find_brains_build_root(tmp_path)


def test_state_dir_returns_brains_build_subdir(tmp_path: Path):
    (tmp_path / ".brains-build").mkdir()
    assert state_dir(tmp_path) == tmp_path / ".brains-build"
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_paths.py -v`
Expected: ImportError (module doesn't exist).

- [ ] **Step 3: Implement paths.py**

`src/build_platform/paths.py`:
```python
"""Resolve .brains-build/ root for the current project."""
from pathlib import Path

STATE_DIR_NAME = ".brains-build"


class BrainsBuildNotFoundError(RuntimeError):
    """Raised when no .brains-build/ directory found walking up from cwd."""


def find_brains_build_root(start: Path | None = None) -> Path:
    """Walk up from `start` (default cwd) until a .brains-build/ dir is found.

    Returns the directory CONTAINING .brains-build/, not .brains-build/ itself.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / STATE_DIR_NAME).is_dir():
            return candidate
    raise BrainsBuildNotFoundError(
        f"No {STATE_DIR_NAME}/ found in {current} or parents. "
        f"Run /build-init to set up a new build project."
    )


def state_dir(project_root: Path) -> Path:
    """Return the .brains-build/ subdirectory for a project root."""
    return project_root / STATE_DIR_NAME
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_paths.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/build_platform/paths.py tests/test_paths.py
git commit -m "feat(paths): resolve .brains-build/ root from cwd"
```

---

## Task 2: Schemas

Pydantic models for every state file. Single source of truth for field names and types.

**Files:**
- Create: `src/build_platform/schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Write failing tests**

`tests/test_schemas.py`:
```python
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
    WPHistoryEvent,
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
            ground_truth="github", created="2026-05-25T10:00:00Z",
        )


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
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_schemas.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement schemas.py**

`src/build_platform/schemas.py`:
```python
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
    ground_truth: Literal["local"]  # v2 will add "github"
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
    models: OllamaModels = Field(default_factory=OllamaModels)
    preflight: OllamaPreflight = Field(default_factory=OllamaPreflight)


class ProjectConfig(BaseModel):
    test_command: str = "pytest"
    lint_command: str = "ruff check"


class Config(BaseModel):
    ollama: OllamaConfig
    project: ProjectConfig
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_schemas.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/build_platform/schemas.py tests/test_schemas.py
git commit -m "feat(schemas): pydantic models for all state files"
```

---

## Task 3: State I/O

Read/write the typed state files. YAML for human-edit files, JSONL for the work-package log.

**Files:**
- Create: `src/build_platform/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write failing tests**

`tests/test_state.py`:
```python
"""Tests for state.py."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from build_platform.schemas import (
    Config,
    Deliverable,
    OllamaConfig,
    OllamaModels,
    Project,
    ProjectConfig,
    Workstream,
    WorkPackage,
    WPState,
    WPTier,
)
from build_platform.state import (
    StateNotInitializedError,
    append_work_package,
    init_state_tree,
    load_config,
    load_deliverables,
    load_project,
    load_work_packages,
    load_wp_state,
    load_workstreams,
    next_wp_id,
    save_config,
    save_deliverables,
    save_project,
    save_workstreams,
    update_wp_state,
)


def test_init_state_tree_creates_directories(tmp_path: Path):
    init_state_tree(tmp_path)
    assert (tmp_path / ".brains-build").is_dir()
    assert (tmp_path / ".brains-build" / "sprints").is_dir()
    assert (tmp_path / ".brains-build" / "audit").is_dir()
    assert (tmp_path / ".brains-build" / "dashboards").is_dir()
    assert (tmp_path / ".brains-build" / "runs").is_dir()


def test_save_and_load_project(tmp_path: Path):
    init_state_tree(tmp_path)
    p = Project(
        name="x", mission="y", stack=["python"], constraints=["no GPL"],
        ground_truth="local", created="2026-05-25T10:00:00Z",
    )
    save_project(tmp_path, p)
    loaded = load_project(tmp_path)
    assert loaded.name == "x"
    assert loaded.constraints == ["no GPL"]


def test_load_project_raises_when_uninitialized(tmp_path: Path):
    with pytest.raises(StateNotInitializedError):
        load_project(tmp_path)


def test_save_and_load_deliverables(tmp_path: Path):
    init_state_tree(tmp_path)
    deliverables = [
        Deliverable(id="D-a", title="Auth", why="we need auth",
                    acceptance=["users can log in"], sequence=1, state="not_started"),
        Deliverable(id="D-b", title="UI", why="needs UI",
                    acceptance=["page renders"], sequence=2, state="not_started"),
    ]
    save_deliverables(tmp_path, deliverables)
    loaded = load_deliverables(tmp_path)
    assert len(loaded) == 2
    assert loaded[0].id == "D-a"


def test_save_and_load_workstreams(tmp_path: Path):
    init_state_tree(tmp_path)
    ws = [Workstream(id="backend", owner_persona="build-backend-sme",
                     review_persona="build-dev-orchestrator", description="x")]
    save_workstreams(tmp_path, ws)
    assert load_workstreams(tmp_path)[0].id == "backend"


def test_append_and_load_work_packages(tmp_path: Path):
    init_state_tree(tmp_path)
    wp = WorkPackage(
        id="WP-0001", title="t", workstream="backend", deliverable_id="D-a",
        tier=WPTier.ONE, executor_persona="build-backend-sme", spec="s",
        spec_files=["f.py"], acceptance=["a"], depends_on=[], consult=[],
        state=WPState.DEFINED, created_by="build-dev-orchestrator",
        created_at="2026-05-25T10:00:00Z", history=[],
    )
    append_work_package(tmp_path, wp)
    loaded = load_work_packages(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].id == "WP-0001"


def test_next_wp_id_starts_at_0001(tmp_path: Path):
    init_state_tree(tmp_path)
    assert next_wp_id(tmp_path) == "WP-0001"


def test_next_wp_id_increments(tmp_path: Path):
    init_state_tree(tmp_path)
    wp = WorkPackage(
        id="WP-0001", title="t", workstream="backend", deliverable_id="D-a",
        tier=WPTier.ONE, executor_persona="build-backend-sme", spec="s",
        spec_files=[], acceptance=["a"], depends_on=[], consult=[],
        state=WPState.DEFINED, created_by="build-dev-orchestrator",
        created_at="2026-05-25T10:00:00Z", history=[],
    )
    append_work_package(tmp_path, wp)
    assert next_wp_id(tmp_path) == "WP-0002"


def test_wp_state_derived_from_history(tmp_path: Path):
    init_state_tree(tmp_path)
    wp = WorkPackage(
        id="WP-0001", title="t", workstream="backend", deliverable_id="D-a",
        tier=WPTier.ONE, executor_persona="build-backend-sme", spec="s",
        spec_files=[], acceptance=["a"], depends_on=[], consult=[],
        state=WPState.DEFINED, created_by="build-dev-orchestrator",
        created_at="2026-05-25T10:00:00Z", history=[],
    )
    append_work_package(tmp_path, wp)
    update_wp_state(tmp_path, "WP-0001", WPState.DISPATCHED,
                    by="build-dev-orchestrator", event="dispatched to tier-1")
    state = load_wp_state(tmp_path)
    assert state["WP-0001"].state == WPState.DISPATCHED
    assert len(state["WP-0001"].history) == 1


def test_config_round_trip(tmp_path: Path):
    init_state_tree(tmp_path)
    c = Config(
        ollama=OllamaConfig(models=OllamaModels()),
        project=ProjectConfig(test_command="pytest -q"),
    )
    save_config(tmp_path, c)
    loaded = load_config(tmp_path)
    assert loaded.project.test_command == "pytest -q"
    assert loaded.ollama.url == "http://localhost:11434"
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_state.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement state.py**

`src/build_platform/state.py`:
```python
"""Read/write state files under .brains-build/."""
import json
from pathlib import Path
from typing import Iterable

from ruamel.yaml import YAML

from build_platform.paths import STATE_DIR_NAME, state_dir
from build_platform.schemas import (
    Config,
    Deliverable,
    Project,
    Workstream,
    WorkPackage,
    WPHistoryEvent,
    WPState,
)

_yaml = YAML(typ="safe")
_yaml.default_flow_style = False


class StateNotInitializedError(RuntimeError):
    """Raised when expected state file is missing."""


def init_state_tree(project_root: Path) -> None:
    sd = state_dir(project_root)
    for sub in ("", "sprints", "audit", "dashboards", "runs"):
        (sd / sub).mkdir(parents=True, exist_ok=True)
    wp_log = sd / "work-packages.jsonl"
    if not wp_log.exists():
        wp_log.write_text("", encoding="utf-8")
    decisions = sd / "decisions.md"
    if not decisions.exists():
        decisions.write_text("# Decisions\n\n", encoding="utf-8")


def _require(path: Path) -> Path:
    if not path.exists():
        raise StateNotInitializedError(
            f"Missing {path}. Run /build-init to set up the project."
        )
    return path


def save_project(project_root: Path, project: Project) -> None:
    path = state_dir(project_root) / "project.yml"
    with path.open("w", encoding="utf-8") as f:
        _yaml.dump(project.model_dump(mode="json"), f)


def load_project(project_root: Path) -> Project:
    path = _require(state_dir(project_root) / "project.yml")
    with path.open("r", encoding="utf-8") as f:
        return Project.model_validate(_yaml.load(f))


def save_deliverables(project_root: Path, deliverables: Iterable[Deliverable]) -> None:
    path = state_dir(project_root) / "deliverables.yml"
    payload = {"deliverables": [d.model_dump(mode="json") for d in deliverables]}
    with path.open("w", encoding="utf-8") as f:
        _yaml.dump(payload, f)


def load_deliverables(project_root: Path) -> list[Deliverable]:
    path = _require(state_dir(project_root) / "deliverables.yml")
    with path.open("r", encoding="utf-8") as f:
        data = _yaml.load(f)
    return [Deliverable.model_validate(d) for d in data.get("deliverables", [])]


def save_workstreams(project_root: Path, workstreams: Iterable[Workstream]) -> None:
    path = state_dir(project_root) / "workstreams.yml"
    payload = {"workstreams": [w.model_dump(mode="json") for w in workstreams]}
    with path.open("w", encoding="utf-8") as f:
        _yaml.dump(payload, f)


def load_workstreams(project_root: Path) -> list[Workstream]:
    path = _require(state_dir(project_root) / "workstreams.yml")
    with path.open("r", encoding="utf-8") as f:
        data = _yaml.load(f)
    return [Workstream.model_validate(w) for w in data.get("workstreams", [])]


def append_work_package(project_root: Path, wp: WorkPackage) -> None:
    path = state_dir(project_root) / "work-packages.jsonl"
    line = json.dumps(wp.model_dump(mode="json"), separators=(",", ":"))
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_work_packages(project_root: Path) -> list[WorkPackage]:
    path = state_dir(project_root) / "work-packages.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(WorkPackage.model_validate_json(line))
    return out


def next_wp_id(project_root: Path) -> str:
    existing = load_work_packages(project_root)
    if not existing:
        return "WP-0001"
    max_n = max(int(wp.id.split("-")[1]) for wp in existing)
    return f"WP-{max_n + 1:04d}"


def update_wp_state(
    project_root: Path,
    wp_id: str,
    new_state: WPState,
    *,
    by: str,
    event: str,
    at: str | None = None,
) -> WorkPackage:
    """Mutate a WP's state by appending a history event; rewrite the JSONL line.

    Returns the updated WorkPackage.
    """
    from datetime import datetime, timezone

    at = at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = state_dir(project_root) / "work-packages.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out_lines: list[str] = []
    updated: WorkPackage | None = None
    for raw in lines:
        if not raw.strip():
            continue
        wp = WorkPackage.model_validate_json(raw)
        if wp.id == wp_id:
            wp = wp.model_copy(update={
                "state": new_state,
                "history": [*wp.history, WPHistoryEvent(at=at, by=by, event=event)],
            })
            updated = wp
        out_lines.append(json.dumps(wp.model_dump(mode="json"), separators=(",", ":")))
    if updated is None:
        raise KeyError(f"WP {wp_id} not found")
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return updated


def load_wp_state(project_root: Path) -> dict[str, WorkPackage]:
    """Derived view: current state of every WP."""
    return {wp.id: wp for wp in load_work_packages(project_root)}


def save_config(project_root: Path, config: Config) -> None:
    path = state_dir(project_root) / "config.yml"
    with path.open("w", encoding="utf-8") as f:
        _yaml.dump(config.model_dump(mode="json"), f)


def load_config(project_root: Path) -> Config:
    path = _require(state_dir(project_root) / "config.yml")
    with path.open("r", encoding="utf-8") as f:
        return Config.model_validate(_yaml.load(f))
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_state.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/build_platform/state.py tests/test_state.py
git commit -m "feat(state): read/write/validate all .brains-build/ state files"
```

---

## Task 4: Audit writer

One audit entry per dispatch. Markdown for greppability.

**Files:**
- Create: `src/build_platform/audit.py`
- Create: `templates/audit_entry.md.j2`
- Test: `tests/test_audit.py`

- [ ] **Step 1: Write failing tests**

`tests/test_audit.py`:
```python
"""Tests for audit.py."""
from pathlib import Path

from build_platform.audit import AuditEntry, write_audit
from build_platform.state import init_state_tree


def test_write_audit_creates_file(tmp_path: Path):
    init_state_tree(tmp_path)
    entry = AuditEntry(
        wp_id="WP-0001",
        timestamp="2026-05-25T14:02:00Z",
        persona="build-backend-sme",
        model="claude-sonnet-4-6",
        tier=2,
        runtime_seconds=401,
        result="done",
        inputs_read=["src/auth/login.py"],
        outputs_written=["src/auth/login.py", "tests/test_login.py"],
        decisions_logged=["D-2026-05-25-argon2"],
        tests_run=[("pytest tests/auth/", "14 passed")],
        notes="Legacy bcrypt in src/auth/legacy.py left untouched.",
    )
    path = write_audit(tmp_path, entry)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "WP-0001" in content
    assert "build-backend-sme" in content
    assert "claude-sonnet-4-6" in content
    assert "argon2" in content


def test_write_audit_filename_uses_wp_id_and_timestamp(tmp_path: Path):
    init_state_tree(tmp_path)
    entry = AuditEntry(
        wp_id="WP-0042", timestamp="2026-05-25T14:02:00Z",
        persona="build-frontend-sme", model="claude-sonnet-4-6", tier=2,
        runtime_seconds=120, result="done",
        inputs_read=[], outputs_written=[], decisions_logged=[],
        tests_run=[], notes="",
    )
    path = write_audit(tmp_path, entry)
    assert "WP-0042" in path.name
    assert path.parent.name == "audit"
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_audit.py -v`
Expected: ImportError.

- [ ] **Step 3: Create the template**

`templates/audit_entry.md.j2`:
```jinja
# {{ wp_id }} dispatch · {{ timestamp }}

**Persona:** {{ persona }} · **Model:** {{ model }} · **Tier:** {{ tier }}
**Runtime:** {{ runtime_seconds }}s · **Result:** {{ result }}

## Inputs read
{% if inputs_read %}{% for f in inputs_read %}- {{ f }}
{% endfor %}{% else %}_None_
{% endif %}
## Outputs written
{% if outputs_written %}{% for f in outputs_written %}- {{ f }}
{% endfor %}{% else %}_None_
{% endif %}
## Decisions logged
{% if decisions_logged %}{% for d in decisions_logged %}- {{ d }}
{% endfor %}{% else %}_None_
{% endif %}
## Tests run
{% if tests_run %}{% for cmd, result in tests_run %}- `{{ cmd }}` → {{ result }}
{% endfor %}{% else %}_None_
{% endif %}
## Notes
{{ notes or "_None_" }}
```

- [ ] **Step 4: Implement audit.py**

`src/build_platform/audit.py`:
```python
"""Append-only audit trail under .brains-build/audit/."""
from pathlib import Path
from importlib.resources import files

from jinja2 import Template
from pydantic import BaseModel, Field

from build_platform.paths import state_dir


class AuditEntry(BaseModel):
    wp_id: str
    timestamp: str  # ISO-8601
    persona: str
    model: str
    tier: int
    runtime_seconds: float
    result: str  # done | blocked | requested_changes | rejected
    inputs_read: list[str] = Field(default_factory=list)
    outputs_written: list[str] = Field(default_factory=list)
    decisions_logged: list[str] = Field(default_factory=list)
    tests_run: list[tuple[str, str]] = Field(default_factory=list)
    notes: str = ""


def _template() -> Template:
    src = files("build_platform.templates").joinpath("audit_entry.md.j2").read_text(encoding="utf-8")
    return Template(src, keep_trailing_newline=True)


def write_audit(project_root: Path, entry: AuditEntry) -> Path:
    audit_dir = state_dir(project_root) / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    safe_ts = entry.timestamp.replace(":", "").replace("-", "")
    filename = f"{entry.wp_id}-{safe_ts}.md"
    path = audit_dir / filename
    rendered = _template().render(**entry.model_dump())
    path.write_text(rendered, encoding="utf-8")
    return path
```

- [ ] **Step 5: Move templates into the package**

The Jinja template needs to be findable via `importlib.resources`. Make it part of the package:

```powershell
New-Item -ItemType Directory -Force -Path c:\BRAINS_Build_Platform\src\build_platform\templates | Out-Null
Move-Item c:\BRAINS_Build_Platform\templates\audit_entry.md.j2 c:\BRAINS_Build_Platform\src\build_platform\templates\audit_entry.md.j2
New-Item -ItemType File -Path c:\BRAINS_Build_Platform\src\build_platform\templates\__init__.py | Out-Null
```

Also update `pyproject.toml` package data:

Change in `pyproject.toml`:
```toml
[tool.setuptools.package-data]
build_platform = ["templates/*.j2", "templates/*.md.j2"]
```

(Already set in Task 0.)

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_audit.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```powershell
git add src/build_platform/audit.py src/build_platform/templates/ tests/test_audit.py
git commit -m "feat(audit): write per-dispatch audit entries via jinja template"
```

---

## Task 5: Git utilities

Read-only git helpers for "since last scrum" diffs. Gracefully no-ops when project isn't a git repo.

**Files:**
- Create: `src/build_platform/git_utils.py`
- Test: `tests/test_git_utils.py`

- [ ] **Step 1: Write failing tests**

`tests/test_git_utils.py`:
```python
"""Tests for git_utils.py."""
import subprocess
from pathlib import Path

from build_platform.git_utils import commits_since, is_git_repo


def _init_git(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True, capture_output=True)


def test_is_git_repo_false_for_non_repo(tmp_path: Path):
    assert is_git_repo(tmp_path) is False


def test_is_git_repo_true_after_init(tmp_path: Path):
    _init_git(tmp_path)
    assert is_git_repo(tmp_path) is True


def test_commits_since_returns_empty_for_non_repo(tmp_path: Path):
    assert commits_since(tmp_path, "2026-01-01T00:00:00Z") == []


def test_commits_since_returns_commits(tmp_path: Path):
    _init_git(tmp_path)
    (tmp_path / "a.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "first"], cwd=tmp_path, check=True, capture_output=True)
    commits = commits_since(tmp_path, "2020-01-01T00:00:00Z")
    assert len(commits) == 1
    assert "first" in commits[0]["message"]
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_git_utils.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement git_utils.py**

`src/build_platform/git_utils.py`:
```python
"""Read-only git helpers. Safe on non-git directories."""
import subprocess
from pathlib import Path


def is_git_repo(project_root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=project_root, capture_output=True, text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def commits_since(project_root: Path, since_iso: str) -> list[dict]:
    """Return commits authored since the given ISO-8601 timestamp.

    Returns a list of {sha, author, date, message} dicts. Empty list if not a repo.
    """
    if not is_git_repo(project_root):
        return []
    fmt = "%H%x09%an%x09%aI%x09%s"
    result = subprocess.run(
        ["git", "log", f"--since={since_iso}", f"--pretty=format:{fmt}"],
        cwd=project_root, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    out: list[dict] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 3)
        if len(parts) != 4:
            continue
        sha, author, date, message = parts
        out.append({"sha": sha, "author": author, "date": date, "message": message})
    return out
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_git_utils.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/build_platform/git_utils.py tests/test_git_utils.py
git commit -m "feat(git): read-only commits-since helper"
```

---

## Task 6: Ollama client

HTTP client + preflight check.

**Files:**
- Create: `src/build_platform/ollama_client.py`
- Test: `tests/test_ollama_client.py`

- [ ] **Step 1: Write failing tests**

`tests/test_ollama_client.py`:
```python
"""Tests for ollama_client.py — mock httpx; do not hit a real Ollama."""
from unittest.mock import MagicMock

import httpx
import pytest

from build_platform.ollama_client import (
    OllamaClient,
    OllamaError,
    OllamaUnreachableError,
    ModelNotPulledError,
)
from build_platform.schemas import OllamaConfig, OllamaModels, OllamaPreflight


def _config() -> OllamaConfig:
    return OllamaConfig(
        url="http://localhost:11434",
        timeout_seconds=10,
        models=OllamaModels(),
        preflight=OllamaPreflight(),
    )


def test_preflight_raises_when_server_unreachable(monkeypatch):
    def fake_get(*a, **kw):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    client = OllamaClient(_config())
    with pytest.raises(OllamaUnreachableError):
        client.preflight(required_models=["qwen2.5-coder:7b"])


def test_preflight_raises_when_model_missing(monkeypatch):
    fake_response = MagicMock()
    fake_response.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
    fake_response.raise_for_status.return_value = None

    def fake_get(self, url, **kw):
        return fake_response

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    client = OllamaClient(_config())
    with pytest.raises(ModelNotPulledError) as ei:
        client.preflight(required_models=["qwen2.5-coder:7b"])
    assert "qwen2.5-coder:7b" in str(ei.value)


def test_preflight_passes_when_all_models_present(monkeypatch):
    fake_response = MagicMock()
    fake_response.json.return_value = {"models": [
        {"name": "qwen2.5-coder:7b"},
        {"name": "llama3.2:3b"},
    ]}
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **kw: fake_response)
    client = OllamaClient(_config())
    client.preflight(required_models=["qwen2.5-coder:7b", "llama3.2:3b"])


def test_chat_returns_content(monkeypatch):
    fake_response = MagicMock()
    fake_response.json.return_value = {"message": {"role": "assistant", "content": "hello"}}
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kw: fake_response)
    client = OllamaClient(_config())
    out = client.chat(model="qwen2.5-coder:7b", prompt="hi")
    assert out == "hello"


def test_chat_raises_ollama_error_on_http_error(monkeypatch):
    fake_response = MagicMock()

    def raise_(): raise httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())

    fake_response.raise_for_status.side_effect = raise_
    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kw: fake_response)
    client = OllamaClient(_config())
    with pytest.raises(OllamaError):
        client.chat(model="qwen2.5-coder:7b", prompt="hi")
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_ollama_client.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement ollama_client.py**

`src/build_platform/ollama_client.py`:
```python
"""HTTP client for a locally-running Ollama instance."""
import httpx

from build_platform.schemas import OllamaConfig


class OllamaError(RuntimeError):
    """Base class for Ollama errors."""


class OllamaUnreachableError(OllamaError):
    """Raised when Ollama HTTP server is not reachable."""


class ModelNotPulledError(OllamaError):
    """Raised when a required model is not pulled."""


class OllamaClient:
    def __init__(self, config: OllamaConfig):
        self.config = config
        self._client = httpx.Client(
            base_url=config.url, timeout=config.timeout_seconds,
        )

    def preflight(self, required_models: list[str]) -> None:
        """Verify Ollama is reachable and required models are pulled."""
        try:
            r = self._client.get("/api/tags")
            r.raise_for_status()
        except httpx.ConnectError as e:
            raise OllamaUnreachableError(
                f"Ollama not reachable at {self.config.url}. "
                f"Start it with `ollama serve` and try again."
            ) from e
        except httpx.HTTPError as e:
            raise OllamaUnreachableError(f"Ollama returned HTTP error: {e}") from e

        present = {m["name"] for m in r.json().get("models", [])}
        missing = [m for m in required_models if m not in present]
        if missing:
            cmds = "\n".join(f"  ollama pull {m}" for m in missing)
            raise ModelNotPulledError(
                f"Required Ollama models not pulled: {missing}.\n"
                f"Run:\n{cmds}"
            )

    def chat(self, model: str, prompt: str, *, system: str | None = None) -> str:
        """Send a one-shot chat request; return assistant content."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": model, "messages": messages, "stream": False}
        try:
            r = self._client.post("/api/chat", json=payload)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise OllamaError(f"Ollama chat failed: {e}") from e
        return r.json()["message"]["content"]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_ollama_client.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/build_platform/ollama_client.py tests/test_ollama_client.py
git commit -m "feat(ollama): HTTP client with preflight and chat"
```

---

## Task 7: Digest helper

Pre-digest large inputs using the summarizer model.

**Files:**
- Create: `src/build_platform/digest.py`
- Test: `tests/test_digest.py`

- [ ] **Step 1: Write failing tests**

`tests/test_digest.py`:
```python
"""Tests for digest.py."""
from pathlib import Path
from unittest.mock import MagicMock

from build_platform.digest import digest_text, digest_file
from build_platform.ollama_client import OllamaClient
from build_platform.schemas import OllamaConfig, OllamaModels, OllamaPreflight


def _client_returning(content: str) -> OllamaClient:
    config = OllamaConfig(models=OllamaModels(), preflight=OllamaPreflight())
    client = OllamaClient(config)
    client.chat = MagicMock(return_value=content)  # type: ignore
    return client


def test_digest_text_calls_summarizer_model():
    client = _client_returning("- key fact A\n- key fact B")
    out = digest_text(client, "lots of words about A and B", target_tokens=200)
    assert "key fact A" in out
    client.chat.assert_called_once()
    _, kwargs = client.chat.call_args
    assert client.chat.call_args.kwargs["model"] == "llama3.2:3b"


def test_digest_file_writes_output(tmp_path: Path):
    src = tmp_path / "big.log"
    src.write_text("line1\nline2\nline3\n" * 200, encoding="utf-8")
    client = _client_returning("- summary")
    out_path = tmp_path / "digest.md"

    digest_file(client, src, out_path, target_tokens=300)
    assert out_path.read_text(encoding="utf-8").strip() == "- summary"
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_digest.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement digest.py**

`src/build_platform/digest.py`:
```python
"""Token-saving pre-digest helper using a small local model."""
from pathlib import Path

from build_platform.ollama_client import OllamaClient

DIGEST_PROMPT = """\
You are a fact-preserving summarizer. Read the input and produce a bulleted summary
under {target_tokens} tokens that preserves every concrete fact, number, identifier,
file path, and decision. Drop prose, rhetorical flourishes, and repeated content.

INPUT:
{content}

OUTPUT (markdown bullets only, no preamble):
"""


def digest_text(client: OllamaClient, content: str, *, target_tokens: int = 1500) -> str:
    """Return a digest of `content` produced by the summarizer model."""
    prompt = DIGEST_PROMPT.format(target_tokens=target_tokens, content=content)
    return client.chat(model=client.config.models.summarizer, prompt=prompt)


def digest_file(
    client: OllamaClient,
    source: Path,
    destination: Path,
    *,
    target_tokens: int = 1500,
) -> Path:
    """Read `source`, digest it, write to `destination`. Returns the destination path."""
    content = source.read_text(encoding="utf-8")
    digest = digest_text(client, content, target_tokens=target_tokens)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(digest, encoding="utf-8")
    return destination
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_digest.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/build_platform/digest.py tests/test_digest.py
git commit -m "feat(digest): pre-summarize large inputs via summarizer model"
```

---

## Task 8: Dashboard renderer

Deterministic markdown emitter from current state.

**Files:**
- Create: `src/build_platform/render_dashboard.py`
- Create: `src/build_platform/templates/dashboard.md.j2`
- Test: `tests/test_render_dashboard.py`

- [ ] **Step 1: Write failing tests**

`tests/test_render_dashboard.py`:
```python
"""Tests for render_dashboard.py."""
from datetime import datetime, timezone
from pathlib import Path

from build_platform.render_dashboard import render_dashboard
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
from build_platform.state import (
    append_work_package,
    init_state_tree,
    save_config,
    save_deliverables,
    save_project,
    save_workstreams,
)


def _seed(tmp_path: Path) -> Path:
    init_state_tree(tmp_path)
    save_project(tmp_path, Project(
        name="Demo", mission="Demonstrate", stack=["python"], constraints=[],
        ground_truth="local", created="2026-05-25T10:00:00Z",
    ))
    save_deliverables(tmp_path, [
        Deliverable(id="D-auth", title="Auth", why="users", acceptance=["login works"],
                    sequence=1, state="in_progress"),
        Deliverable(id="D-ui", title="UI", why="users", acceptance=["page renders"],
                    sequence=2, state="not_started"),
    ])
    save_workstreams(tmp_path, [
        Workstream(id="backend", owner_persona="build-backend-sme",
                   review_persona="build-dev-orchestrator", description="Server"),
    ])
    save_config(tmp_path, Config(
        ollama=OllamaConfig(models=OllamaModels()),
        project=ProjectConfig(test_command="pytest"),
    ))
    append_work_package(tmp_path, WorkPackage(
        id="WP-0001", title="Login endpoint", workstream="backend", deliverable_id="D-auth",
        tier=WPTier.TWO, executor_persona="build-backend-sme", spec="implement login",
        spec_files=["src/auth/login.py"], acceptance=["test passes"], depends_on=[], consult=[],
        state=WPState.DONE, created_by="build-dev-orchestrator",
        created_at="2026-05-24T10:00:00Z", history=[],
    ))
    append_work_package(tmp_path, WorkPackage(
        id="WP-0002", title="Session refresh", workstream="backend", deliverable_id="D-auth",
        tier=WPTier.TWO, executor_persona="build-backend-sme", spec="refresh sessions",
        spec_files=["src/auth/session.py"], acceptance=["test passes"], depends_on=[], consult=[],
        state=WPState.DEFINED, created_by="build-dev-orchestrator",
        created_at="2026-05-25T10:00:00Z", history=[],
    ))
    return tmp_path


def test_render_dashboard_writes_file(tmp_path: Path):
    _seed(tmp_path)
    out = render_dashboard(tmp_path)
    assert out.exists()
    assert out.name == "current.md"
    assert out.parent.name == "dashboards"


def test_render_dashboard_includes_required_sections(tmp_path: Path):
    _seed(tmp_path)
    out = render_dashboard(tmp_path)
    text = out.read_text(encoding="utf-8")
    for section in [
        "# Demo — PMO Dashboard",
        "## Plan position",
        "## Live (right now)",
        "## Health",
        "## Deliverables",
        "## Workstreams",
        "## Persona activity",
        "## Daily completed work",
        "## Open blockers",
        "## Recent decisions",
        "## Up next",
    ]:
        assert section in text, f"Missing section: {section}"


def test_render_dashboard_lists_open_wp(tmp_path: Path):
    _seed(tmp_path)
    out = render_dashboard(tmp_path)
    assert "WP-0002" in out.read_text(encoding="utf-8")


def test_render_dashboard_empty_sections_render_as_none(tmp_path: Path):
    init_state_tree(tmp_path)
    save_project(tmp_path, Project(
        name="Empty", mission="x", stack=[], constraints=[],
        ground_truth="local", created="2026-05-25T10:00:00Z",
    ))
    save_deliverables(tmp_path, [])
    save_workstreams(tmp_path, [])
    save_config(tmp_path, Config(
        ollama=OllamaConfig(models=OllamaModels()),
        project=ProjectConfig(test_command="pytest"),
    ))
    out = render_dashboard(tmp_path)
    text = out.read_text(encoding="utf-8")
    assert "_None_" in text
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_render_dashboard.py -v`
Expected: ImportError.

- [ ] **Step 3: Create the template**

`src/build_platform/templates/dashboard.md.j2`:
```jinja
# {{ project.name }} — PMO Dashboard
_Generated: {{ generated_at }} · Sprint: {{ sprint_number }} · Day {{ day_of_sprint }} of sprint_

## Plan position
Deliverable sequence: {{ deliverable_sequence or "_None_" }}
{% if deliverables_total %}Progress: {{ deliverables_done }}/{{ deliverables_total }} deliverables done ({{ progress_pct }}%)
Current focus: {{ current_focus or "_None_" }}
Next milestone: {{ next_milestone or "_None_" }}
What I'd do next: {{ next_action or "_None_" }}
{% else %}_None_
{% endif %}
## Live (right now)
{% if live %}{% for item in live %}- {{ item }}
{% endfor %}{% else %}_None_
{% endif %}
## Health
- Active WPs: {{ health.active }} · Blocked: {{ health.blocked }} · Done this sprint: {{ health.done_this_sprint }} · Velocity (3-sprint avg): {{ health.velocity }}
- Open user-action blockers: {{ health.user_blockers }}{% if health.user_blockers %} ⚠️{% endif %}

## Deliverables
{% if deliverables %}| ID | Title | Acceptance met | WPs done/total | State |
|---|---|---|---|---|
{% for d in deliverables %}| {{ d.id }} | {{ d.title }} | {{ d.acceptance_met }}/{{ d.acceptance_total }} | {{ d.wp_done }}/{{ d.wp_total }} | {{ d.state }} |
{% endfor %}{% else %}_None_
{% endif %}
## Workstreams (this sprint)
{% if workstreams %}| Workstream | Owner persona | Done | In review | Blocked | Next up |
|---|---|---|---|---|---|
{% for w in workstreams %}| {{ w.id }} | {{ w.owner }} | {{ w.done }} | {{ w.in_review }} | {{ w.blocked }} | {{ w.next_up or "—" }} |
{% endfor %}{% else %}_None_
{% endif %}
## Persona activity (last 7 days)
{% if persona_activity %}| Persona | Dispatches | Avg runtime | Tier-1 share |
|---|---|---|---|
{% for p in persona_activity %}| {{ p.persona }} | {{ p.dispatches }} | {{ p.avg_runtime }} | {{ p.tier1_share }} |
{% endfor %}{% else %}_None_
{% endif %}
## Daily completed work (last 7 days)
{% if daily %}{% for day in daily %}- {{ day.date }}: {{ day.items }}
{% endfor %}{% else %}_None_
{% endif %}
## Open blockers
{% if blockers %}{% for b in blockers %}- **{{ b.wp_id }}** ({{ b.workstream }}): _{{ b.reason }}_{% if b.needs_user %} → needs user input{% endif %}
{% if b.suggestion %}  Suggested resolution: {{ b.suggestion }}
{% endif %}{% endfor %}{% else %}_None_
{% endif %}
## Recent decisions (last 7 days)
{% if decisions %}{% for d in decisions %}- {{ d.date }}: {{ d.title }} (owner: {{ d.owner }}) → {{ d.related }}
{% endfor %}{% else %}_None_
{% endif %}
## Up next (this sprint, in priority order)
{% if up_next %}{% for wp in up_next %}{{ loop.index }}. {{ wp.id }} — {{ wp.title }} ({{ wp.workstream }}, tier-{{ wp.tier }})
{% endfor %}{% else %}_None_
{% endif %}
```

- [ ] **Step 4: Implement render_dashboard.py**

`src/build_platform/render_dashboard.py`:
```python
"""Render the markdown PMO dashboard from current state."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

from jinja2 import Template

from build_platform.paths import state_dir
from build_platform.schemas import WPState
from build_platform.state import (
    load_deliverables,
    load_project,
    load_work_packages,
    load_workstreams,
)


def _template() -> Template:
    src = files("build_platform.templates").joinpath("dashboard.md.j2").read_text(encoding="utf-8")
    return Template(src, keep_trailing_newline=True)


def _sprint_number(project_root: Path) -> int:
    sprints = sorted((state_dir(project_root) / "sprints").glob("sprint-*.md"))
    return len(sprints) + 1 if not sprints else len(sprints)


def _day_of_sprint(project_root: Path) -> int:
    sprints = sorted((state_dir(project_root) / "sprints").glob("sprint-*.md"))
    if not sprints:
        return 1
    last = sprints[-1].stat().st_mtime
    delta = (datetime.now(timezone.utc).timestamp() - last) / 86400
    return max(1, int(delta) + 1)


def _live(project_root: Path) -> list[str]:
    runs = state_dir(project_root) / "runs"
    if not runs.exists():
        return []
    out = []
    cutoff = datetime.now(timezone.utc).timestamp() - 3600  # 1h sliding window
    for run_dir in runs.iterdir():
        if not run_dir.is_dir():
            continue
        if run_dir.stat().st_mtime < cutoff:
            continue
        out.append(f"{run_dir.name} · started {datetime.fromtimestamp(run_dir.stat().st_mtime).isoformat(timespec='seconds')}")
    return out


def render_dashboard(project_root: Path) -> Path:
    project = load_project(project_root)
    deliverables = load_deliverables(project_root)
    workstreams = load_workstreams(project_root)
    wps = load_work_packages(project_root)

    # Health counts
    by_state = Counter(wp.state for wp in wps)
    health = {
        "active": by_state.get(WPState.DEFINED, 0) + by_state.get(WPState.DISPATCHED, 0) + by_state.get(WPState.IN_REVIEW, 0),
        "blocked": by_state.get(WPState.BLOCKED, 0),
        "done_this_sprint": by_state.get(WPState.DONE, 0),
        "velocity": 0,  # populated by scrum
        "user_blockers": by_state.get(WPState.BLOCKED, 0),
    }

    # Plan position
    sorted_deliverables = sorted(deliverables, key=lambda d: d.sequence)
    deliverable_sequence = " ▶ ".join(d.id for d in sorted_deliverables) or None
    done_count = sum(1 for d in sorted_deliverables if d.state == "done")
    progress_pct = int(done_count * 100 / len(sorted_deliverables)) if sorted_deliverables else 0
    current_focus_d = next((d for d in sorted_deliverables if d.state == "in_progress"), None)
    current_focus = f"{current_focus_d.id} ({current_focus_d.title})" if current_focus_d else None
    next_milestone = None
    if current_focus_d:
        open_wps = [wp for wp in wps if wp.deliverable_id == current_focus_d.id and wp.state != WPState.DONE]
        if open_wps:
            next_milestone = f"{current_focus_d.id} acceptance review (est. on {', '.join(w.id for w in open_wps[:2])} completion)"
    next_action = None
    next_defined = next((wp for wp in wps if wp.state == WPState.DEFINED), None)
    if next_defined:
        next_action = f"dispatch {next_defined.id} ({next_defined.title})"

    # Deliverable rows
    wp_by_deliverable: dict[str, list] = defaultdict(list)
    for wp in wps:
        wp_by_deliverable[wp.deliverable_id].append(wp)
    deliverable_rows = []
    for d in sorted_deliverables:
        d_wps = wp_by_deliverable.get(d.id, [])
        deliverable_rows.append({
            "id": d.id,
            "title": d.title,
            "acceptance_met": 0,
            "acceptance_total": len(d.acceptance),
            "wp_done": sum(1 for w in d_wps if w.state == WPState.DONE),
            "wp_total": len(d_wps),
            "state": d.state,
        })

    # Workstream rows
    workstream_rows = []
    for ws in workstreams:
        ws_wps = [wp for wp in wps if wp.workstream == ws.id]
        next_up = next((wp for wp in ws_wps if wp.state == WPState.DEFINED), None)
        workstream_rows.append({
            "id": ws.id,
            "owner": ws.owner_persona,
            "done": sum(1 for w in ws_wps if w.state == WPState.DONE),
            "in_review": sum(1 for w in ws_wps if w.state == WPState.IN_REVIEW),
            "blocked": sum(1 for w in ws_wps if w.state == WPState.BLOCKED),
            "next_up": next_up.id if next_up else None,
        })

    # Persona activity, daily completed, decisions, up next — minimal v1 (extended in scrum)
    persona_activity: list[dict] = []
    daily: list[dict] = []
    blockers = [{
        "wp_id": wp.id, "workstream": wp.workstream,
        "reason": (wp.history[-1].event if wp.history else "unknown"),
        "needs_user": True, "suggestion": "investigate via audit log",
    } for wp in wps if wp.state == WPState.BLOCKED]
    decisions: list[dict] = []
    up_next = [{
        "id": wp.id, "title": wp.title, "workstream": wp.workstream, "tier": int(wp.tier.value),
    } for wp in sorted(wps, key=lambda w: w.id) if wp.state == WPState.DEFINED][:10]

    rendered = _template().render(
        project=project,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        sprint_number=_sprint_number(project_root),
        day_of_sprint=_day_of_sprint(project_root),
        deliverable_sequence=deliverable_sequence,
        deliverables_total=len(sorted_deliverables),
        deliverables_done=done_count,
        progress_pct=progress_pct,
        current_focus=current_focus,
        next_milestone=next_milestone,
        next_action=next_action,
        live=_live(project_root),
        health=health,
        deliverables=deliverable_rows,
        workstreams=workstream_rows,
        persona_activity=persona_activity,
        daily=daily,
        blockers=blockers,
        decisions=decisions,
        up_next=up_next,
    )

    out_dir = state_dir(project_root) / "dashboards"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "current.md"
    out.write_text(rendered, encoding="utf-8")
    return out
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_render_dashboard.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```powershell
git add src/build_platform/render_dashboard.py src/build_platform/templates/dashboard.md.j2 tests/test_render_dashboard.py
git commit -m "feat(dashboard): deterministic markdown renderer from state"
```

---

## Task 9: Dispatcher core

The tier-1 (Ollama) and tier-2 (Claude subagent stub) paths. Tier-2 dispatch in v1 emits an instruction file that the Claude orchestrator picks up — the subagent itself runs in the Claude session, not invoked from Python.

**Files:**
- Create: `src/build_platform/dispatcher.py`
- Create: `src/build_platform/templates/tier1_executor.j2`
- Test: `tests/test_dispatcher.py`

- [ ] **Step 1: Write failing tests**

`tests/test_dispatcher.py`:
```python
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
    # Tier-2 WP variant
    wp = wp.model_copy(update={"tier": WPTier.TWO})
    brief_path = prepare_tier2_brief(project_root, wp)
    assert brief_path.exists()
    content = brief_path.read_text(encoding="utf-8")
    assert "build-backend-sme" in content
    assert "WP-0001" in content
    assert "src/foo.py" in content
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_dispatcher.py -v`
Expected: ImportError.

- [ ] **Step 3: Create the tier-1 prompt template**

`src/build_platform/templates/tier1_executor.j2`:
```jinja
You are a mechanical-tier code executor. Output ONLY a unified diff. No prose. No backticks. No explanations.

# Mission
{{ persona_mission }}

# Project context
- Name: {{ project.name }}
- Mission: {{ project.mission }}
- Stack: {{ project.stack | join(", ") }}

# Work package
- ID: {{ wp.id }}
- Title: {{ wp.title }}
- Spec: {{ wp.spec }}
- Acceptance: {{ wp.acceptance | join("; ") }}

# Files in scope (touch ONLY these)
{% for path, content in files %}
## {{ path }}
```
{{ content }}
```
{% endfor %}

# Hard constraints
- Output a single unified diff covering ONLY the files in scope.
- Use exact paths matching the files in scope.
- Do not include prose, headers, or backticks around the diff.
- Each file diff must start with `--- a/<path>` and `+++ b/<path>`.
{% if review_feedback %}

# Review feedback from previous attempt
{{ review_feedback }}

Apply the feedback. Retry the diff.
{% endif %}
```

- [ ] **Step 4: Implement dispatcher.py**

`src/build_platform/dispatcher.py`:
```python
"""Core dispatch: tier-1 (Ollama) and tier-2 (Claude subagent brief)."""
import re
from importlib.resources import files
from pathlib import Path

from jinja2 import Template

from build_platform.ollama_client import OllamaClient
from build_platform.paths import state_dir
from build_platform.schemas import WorkPackage, WPState
from build_platform.state import load_project

TIER1_MAX_BYTES = 50_000


class DispatchError(RuntimeError):
    """Dispatch failed in a recoverable-by-human way (e.g., 2 retries exhausted)."""


class DiffValidationError(DispatchError):
    """Diff failed structural or scope validation."""


_DIFF_HEADER = re.compile(r"^---\s+a/(?P<path>.+)$", re.MULTILINE)
_DIFF_HEADER_PLUS = re.compile(r"^\+\+\+\s+b/(?P<path>.+)$", re.MULTILINE)
_DIFF_HUNK = re.compile(r"^@@\s+-\d+", re.MULTILINE)


def validate_diff(diff_text: str, *, allowed_files: list[str]) -> None:
    """Raise DiffValidationError if diff is malformed or touches files outside scope."""
    minus = _DIFF_HEADER.findall(diff_text)
    plus = _DIFF_HEADER_PLUS.findall(diff_text)
    hunks = _DIFF_HUNK.findall(diff_text)
    if not minus or not plus or not hunks:
        raise DiffValidationError("Diff lacks valid headers or hunks.")
    if minus != plus:
        raise DiffValidationError(f"Diff --- and +++ paths mismatch: {minus} vs {plus}.")
    disallowed = [p for p in minus if p not in allowed_files]
    if disallowed:
        raise DiffValidationError(
            f"Diff touches files outside scope: {disallowed}. Allowed: {allowed_files}."
        )


def _read_scope_files(project_root: Path, paths: list[str]) -> list[tuple[str, str]]:
    out = []
    total = 0
    for rel in paths:
        path = project_root / rel
        if not path.exists():
            out.append((rel, ""))  # file to be created
            continue
        content = path.read_text(encoding="utf-8")
        total += len(content.encode("utf-8"))
        if total > TIER1_MAX_BYTES:
            raise DispatchError(
                f"Tier-1 scope exceeds {TIER1_MAX_BYTES} bytes. "
                f"Split the WP or re-tag as tier-2."
            )
        out.append((rel, content))
    return out


def _tier1_template() -> Template:
    src = files("build_platform.templates").joinpath("tier1_executor.j2").read_text(encoding="utf-8")
    return Template(src, keep_trailing_newline=True)


PERSONA_MISSIONS = {
    "build-backend-sme": "Implement backend code per the work package, write tests, keep changes minimal.",
    "build-frontend-sme": "Implement UI per the work package, follow existing patterns, write tests.",
    "build-qa-sme": "Write or update tests to verify acceptance criteria.",
    "build-security-sme": "Read-only audit; produce findings, do not modify code.",
    "build-devops-sme": "Update CI/CD/deploy configs per the work package.",
}


def dispatch_tier1(project_root: Path, wp: WorkPackage, client: OllamaClient) -> Path:
    """Send WP to Ollama, validate diff, write to runs/<wp-id>/proposed.diff.

    Retries once with stricter prompt on validation failure. Raises DispatchError
    after second failure.
    """
    scope = _read_scope_files(project_root, wp.spec_files)
    config = client.config
    project = load_project(project_root)
    runs = state_dir(project_root) / "runs" / wp.id
    runs.mkdir(parents=True, exist_ok=True)

    review_feedback: str | None = None
    for attempt in range(2):
        prompt = _tier1_template().render(
            persona_mission=PERSONA_MISSIONS.get(wp.executor_persona, ""),
            project=project,
            wp=wp,
            files=scope,
            review_feedback=review_feedback,
        )
        (runs / f"prompt-attempt{attempt + 1}.txt").write_text(prompt, encoding="utf-8")
        raw = client.chat(model=config.models.tier1_default, prompt=prompt)
        (runs / f"raw-attempt{attempt + 1}.txt").write_text(raw, encoding="utf-8")
        try:
            validate_diff(raw, allowed_files=wp.spec_files)
        except DiffValidationError as e:
            review_feedback = (
                f"Previous attempt failed validation: {e}\n"
                f"Output a unified diff only. No prose. No backticks. Use exact paths."
            )
            continue
        diff_path = runs / "proposed.diff"
        diff_path.write_text(raw, encoding="utf-8")
        return diff_path
    raise DispatchError(
        f"Tier-1 dispatch for {wp.id} failed validation twice. "
        f"See runs/{wp.id}/ for prompts and raw outputs."
    )


def prepare_tier2_brief(project_root: Path, wp: WorkPackage) -> Path:
    """Write a structured brief file the Claude session reads when spawning the SME subagent."""
    runs = state_dir(project_root) / "runs" / wp.id
    runs.mkdir(parents=True, exist_ok=True)
    project = load_project(project_root)
    brief = f"""\
# Tier-2 dispatch brief — {wp.id}

**Executor persona:** {wp.executor_persona}
**Workstream:** {wp.workstream}
**Deliverable:** {wp.deliverable_id}
**Tier:** 2

## Project context
- Name: {project.name}
- Mission: {project.mission}
- Stack: {", ".join(project.stack)}
- Constraints: {", ".join(project.constraints) or "_None_"}

## Work package
**Title:** {wp.title}

**Spec:**
{wp.spec}

**Acceptance criteria:**
{chr(10).join(f"- {a}" for a in wp.acceptance)}

**Files in scope:**
{chr(10).join(f"- {f}" for f in wp.spec_files)}

**Consult personas:** {", ".join(wp.consult) or "_None_"}

## Instructions to the executor subagent
1. Read project context and only the files listed above.
2. Implement the spec; use Edit/Write to modify files; follow existing patterns.
3. Run the project's test command after changes; do not mark complete if tests fail.
4. Produce a result block at the end: files changed, decisions made, blockers, handoff notes.
5. Log any non-trivial decisions to `.brains-build/decisions.md` via `/build-decision`.
6. The PMO/Dev Orchestrator will write the audit entry once you return.
"""
    path = runs / "tier2-brief.md"
    path.write_text(brief, encoding="utf-8")
    return path
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_dispatcher.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```powershell
git add src/build_platform/dispatcher.py src/build_platform/templates/tier1_executor.j2 tests/test_dispatcher.py
git commit -m "feat(dispatcher): tier-1 Ollama path + tier-2 brief emitter"
```

---

## Task 10: CLI entry points

Each verb's Python entry point. Skills call these via `python -m build_platform.cli.<verb>`. CLI uses Click; output is structured JSON when `--json` flag set (for skill consumption), human markdown otherwise.

**Files:**
- Create: `src/build_platform/cli/__init__.py`
- Create: `src/build_platform/cli/init.py`
- Create: `src/build_platform/cli/package.py`
- Create: `src/build_platform/cli/dispatch.py`
- Create: `src/build_platform/cli/scrum.py`
- Create: `src/build_platform/cli/status.py`
- Create: `src/build_platform/cli/decision.py`
- Create: `src/build_platform/cli/dashboard.py`
- Test: `tests/test_cli_init.py`
- Test: `tests/test_cli_dispatch.py`

- [ ] **Step 1: Write failing tests for init CLI**

`tests/test_cli_init.py`:
```python
"""Tests for cli/init.py."""
import json
from pathlib import Path

from click.testing import CliRunner

from build_platform.cli.init import init_cmd


def test_init_refuses_when_already_initialized(tmp_path: Path):
    (tmp_path / ".brains-build").mkdir()
    runner = CliRunner()
    result = runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "x", "--mission", "y", "--stack", "python",
        "--constraint", "none", "--deliverable", "D-a:Title:why:acceptance",
        "--json",
    ])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"]


def test_init_creates_state_tree(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "Demonstrate the platform",
        "--stack", "python", "--stack", "react",
        "--constraint", "no GPL",
        "--deliverable", "D-auth:Authentication:users need to log in:login works",
        "--deliverable", "D-ui:Onboarding UI:users need an interface:page renders",
        "--json",
    ])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert (tmp_path / ".brains-build" / "project.yml").exists()
    assert (tmp_path / ".brains-build" / "deliverables.yml").exists()
    assert (tmp_path / ".brains-build" / "workstreams.yml").exists()
    assert (tmp_path / ".brains-build" / "config.yml").exists()
    assert (tmp_path / ".brains-build" / "work-packages.jsonl").exists()
    assert (tmp_path / ".brains-build" / "decisions.md").exists()
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_cli_init.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement cli/__init__.py**

`src/build_platform/cli/__init__.py`:
```python
"""CLI entry points called from build-* Claude skills."""
```

- [ ] **Step 4: Implement cli/init.py**

`src/build_platform/cli/init.py`:
```python
"""`/build-init` entry point — scaffolds a project."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from build_platform.schemas import (
    Config,
    Deliverable,
    OllamaConfig,
    OllamaModels,
    Project,
    ProjectConfig,
    Workstream,
)
from build_platform.state import (
    init_state_tree,
    save_config,
    save_deliverables,
    save_project,
    save_workstreams,
)

DEFAULT_WORKSTREAMS = [
    Workstream(id="backend", owner_persona="build-backend-sme",
               review_persona="build-dev-orchestrator",
               description="Server-side code, data layer, APIs"),
    Workstream(id="frontend", owner_persona="build-frontend-sme",
               review_persona="build-dev-orchestrator",
               description="UI, components, styling"),
    Workstream(id="qa", owner_persona="build-qa-sme",
               review_persona="build-pmo-lead",
               description="Tests, regression matrices, bug repro"),
    Workstream(id="security", owner_persona="build-security-sme",
               review_persona="build-dev-orchestrator",
               description="Threat modeling, dependency audit, OWASP review"),
    Workstream(id="devops", owner_persona="build-devops-sme",
               review_persona="build-dev-orchestrator",
               description="CI/CD, build, deploy, environment management"),
]


def _emit(payload: dict, *, as_json: bool, exit_code: int = 0) -> None:
    if as_json:
        click.echo(json.dumps(payload))
    else:
        if "error" in payload:
            click.echo(f"Error: {payload['error']}", err=True)
        else:
            click.echo(payload.get("message", ""))
    sys.exit(exit_code)


@click.command("init")
@click.option("--root", type=click.Path(file_okay=False), default=".",
              help="Project root directory.")
@click.option("--name", required=True, help="Project name.")
@click.option("--mission", required=True, help="One-sentence mission.")
@click.option("--stack", "stack", multiple=True, required=True,
              help="Stack element (repeatable).")
@click.option("--constraint", "constraints", multiple=True, default=(),
              help="Constraint (repeatable).")
@click.option("--deliverable", "deliverables", multiple=True, required=True,
              help="Deliverable as 'id:title:why:acceptance' (repeatable). "
                   "Use ';' to separate multiple acceptance criteria.")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
def init_cmd(root, name, mission, stack, constraints, deliverables, as_json):
    """Initialize a new build project."""
    root_path = Path(root).resolve()
    if (root_path / ".brains-build").exists():
        _emit({"error": f".brains-build/ already exists at {root_path}. Use /build-status."},
              as_json=as_json, exit_code=1)

    parsed_deliverables = []
    for i, raw in enumerate(deliverables, start=1):
        parts = raw.split(":", 3)
        if len(parts) != 4:
            _emit({"error": f"Invalid deliverable format: {raw!r}"}, as_json=as_json, exit_code=2)
        d_id, title, why, accept = parts
        acceptance = [a.strip() for a in accept.split(";") if a.strip()]
        parsed_deliverables.append(Deliverable(
            id=d_id, title=title, why=why, acceptance=acceptance,
            sequence=i, state="not_started",
        ))

    init_state_tree(root_path)
    project = Project(
        name=name, mission=mission, stack=list(stack), constraints=list(constraints),
        ground_truth="local",
        created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    save_project(root_path, project)
    save_deliverables(root_path, parsed_deliverables)
    save_workstreams(root_path, DEFAULT_WORKSTREAMS)
    save_config(root_path, Config(
        ollama=OllamaConfig(models=OllamaModels()),
        project=ProjectConfig(test_command="pytest"),
    ))

    # Seed decisions.md with the init event.
    decisions = root_path / ".brains-build" / "decisions.md"
    decisions.write_text(
        f"# Decisions\n\n"
        f"## {datetime.now(timezone.utc).date().isoformat()} — Project initialized\n"
        f"**Owner:** user\n"
        f"**Decision:** Initialized BRAINS Build Platform for project '{name}'.\n"
        f"**Why:** {mission}\n",
        encoding="utf-8",
    )

    next_steps = (
        f"Initialized at {root_path}\n"
        f"Next:\n"
        f"  1. Pull Ollama models: `ollama pull qwen2.5-coder:7b && ollama pull llama3.2:3b`\n"
        f"  2. Run /build-package to break a deliverable into work packages."
    )
    _emit({"ok": True, "message": next_steps, "root": str(root_path)}, as_json=as_json)


if __name__ == "__main__":
    init_cmd()
```

- [ ] **Step 5: Run init tests**

Run: `pytest tests/test_cli_init.py -v`
Expected: 2 passed.

- [ ] **Step 6: Implement cli/dashboard.py**

`src/build_platform/cli/dashboard.py`:
```python
"""`/build-dashboard` entry point — renders current dashboard."""
import json
import sys
from pathlib import Path

import click

from build_platform.paths import find_brains_build_root
from build_platform.render_dashboard import render_dashboard


@click.command("dashboard")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--json", "as_json", is_flag=True)
def dashboard_cmd(root, as_json):
    """Render the markdown PMO dashboard."""
    root_path = Path(root).resolve() if root else find_brains_build_root()
    out = render_dashboard(root_path)
    payload = {"ok": True, "path": str(out)}
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    dashboard_cmd()
```

- [ ] **Step 7: Implement cli/status.py**

`src/build_platform/cli/status.py`:
```python
"""`/build-status` entry point — read-only status query."""
import json
import sys
from collections import Counter
from pathlib import Path

import click

from build_platform.paths import find_brains_build_root
from build_platform.schemas import WPState
from build_platform.state import load_project, load_work_packages


@click.command("status")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--wp", default=None, help="Show status for a specific WP id.")
@click.option("--json", "as_json", is_flag=True)
def status_cmd(root, wp, as_json):
    root_path = Path(root).resolve() if root else find_brains_build_root()
    project = load_project(root_path)
    wps = load_work_packages(root_path)
    if wp:
        match = next((w for w in wps if w.id == wp), None)
        if not match:
            click.echo(json.dumps({"error": f"WP {wp} not found"}) if as_json else f"WP {wp} not found", err=True)
            sys.exit(1)
        payload = match.model_dump(mode="json")
        click.echo(json.dumps(payload) if as_json else _human(match))
        return
    counts = Counter(w.state for w in wps)
    payload = {
        "project": project.name,
        "total_wps": len(wps),
        "by_state": {k.value: v for k, v in counts.items()},
    }
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(f"Project: {project.name}")
        click.echo(f"Total WPs: {len(wps)}")
        for state, n in counts.items():
            click.echo(f"  {state.value}: {n}")


def _human(wp) -> str:
    return (
        f"{wp.id} · {wp.title}\n"
        f"  workstream: {wp.workstream} · deliverable: {wp.deliverable_id}\n"
        f"  tier: {wp.tier.value} · state: {wp.state.value} · persona: {wp.executor_persona}\n"
        f"  spec: {wp.spec}\n"
        f"  acceptance: {'; '.join(wp.acceptance)}\n"
        f"  history: {len(wp.history)} events"
    )


if __name__ == "__main__":
    status_cmd()
```

- [ ] **Step 8: Implement cli/package.py**

`src/build_platform/cli/package.py`:
```python
"""`/build-package` entry point — add a WP. Heavy lifting is done by the Dev Orchestrator
subagent in the Claude session; this CLI validates and writes."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from build_platform.paths import find_brains_build_root
from build_platform.schemas import WorkPackage, WPState, WPTier
from build_platform.state import append_work_package, next_wp_id


@click.command("package")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--title", required=True)
@click.option("--workstream", required=True)
@click.option("--deliverable", "deliverable_id", required=True)
@click.option("--tier", type=click.Choice(["1", "2"]), required=True)
@click.option("--executor", "executor_persona", required=True)
@click.option("--spec", required=True)
@click.option("--file", "spec_files", multiple=True)
@click.option("--accept", "acceptance", multiple=True, required=True)
@click.option("--depends-on", "depends_on", multiple=True, default=())
@click.option("--consult", multiple=True, default=())
@click.option("--created-by", default="build-dev-orchestrator")
@click.option("--json", "as_json", is_flag=True)
def package_cmd(root, title, workstream, deliverable_id, tier, executor_persona,
                spec, spec_files, acceptance, depends_on, consult, created_by, as_json):
    root_path = Path(root).resolve() if root else find_brains_build_root()
    wp_id = next_wp_id(root_path)
    wp = WorkPackage(
        id=wp_id, title=title, workstream=workstream, deliverable_id=deliverable_id,
        tier=WPTier(int(tier)), executor_persona=executor_persona,
        spec=spec, spec_files=list(spec_files), acceptance=list(acceptance),
        depends_on=list(depends_on), consult=list(consult),
        state=WPState.DEFINED, created_by=created_by,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        history=[],
    )
    if wp.tier == WPTier.ONE:
        if len(wp.spec_files) > 3:
            payload = {"error": f"Tier-1 WP must touch ≤ 3 files; got {len(wp.spec_files)}"}
            click.echo(json.dumps(payload) if as_json else payload["error"], err=True)
            sys.exit(2)
    append_work_package(root_path, wp)
    payload = {"ok": True, "wp_id": wp.id}
    click.echo(json.dumps(payload) if as_json else f"Created {wp.id}: {title}")


if __name__ == "__main__":
    package_cmd()
```

- [ ] **Step 9: Implement cli/dispatch.py**

`src/build_platform/cli/dispatch.py`:
```python
"""`/build-dispatch` entry point — execute a WP via tier-1 (Ollama) or tier-2 (Claude brief)."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import click

from build_platform.audit import AuditEntry, write_audit
from build_platform.dispatcher import (
    DispatchError,
    dispatch_tier1,
    prepare_tier2_brief,
)
from build_platform.ollama_client import OllamaClient, OllamaError
from build_platform.paths import find_brains_build_root
from build_platform.render_dashboard import render_dashboard
from build_platform.schemas import WPState, WPTier
from build_platform.state import load_config, load_wp_state, update_wp_state


@click.command("dispatch")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--wp", "wp_id", required=True, help="WP id to dispatch.")
@click.option("--json", "as_json", is_flag=True)
def dispatch_cmd(root, wp_id, as_json):
    root_path = Path(root).resolve() if root else find_brains_build_root()
    config = load_config(root_path)
    wps = load_wp_state(root_path)
    if wp_id not in wps:
        _err(f"WP {wp_id} not found", as_json, 1)
    wp = wps[wp_id]
    if wp.state != WPState.DEFINED:
        _err(f"WP {wp_id} is in state {wp.state.value}, expected 'defined'", as_json, 1)
    unmet = [dep for dep in wp.depends_on if wps.get(dep) is None or wps[dep].state != WPState.DONE]
    if unmet:
        _err(f"WP {wp_id} blocked by unmet deps: {unmet}", as_json, 1)

    start = time.monotonic()
    if wp.tier == WPTier.ONE:
        client = OllamaClient(config.ollama)
        try:
            client.preflight(required_models=[
                config.ollama.models.tier1_default,
                config.ollama.models.summarizer,
            ])
        except OllamaError as e:
            _err(str(e), as_json, 2)
        try:
            diff_path = dispatch_tier1(root_path, wp, client)
        except DispatchError as e:
            update_wp_state(root_path, wp_id, WPState.BLOCKED,
                            by="build-dev-orchestrator", event=f"tier-1 dispatch failed: {e}")
            render_dashboard(root_path)
            _err(str(e), as_json, 3)
        update_wp_state(root_path, wp_id, WPState.DISPATCHED,
                        by="build-dev-orchestrator",
                        event=f"tier-1 diff at {diff_path.relative_to(root_path)}")
        write_audit(root_path, AuditEntry(
            wp_id=wp.id, timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            persona=wp.executor_persona, model=config.ollama.models.tier1_default,
            tier=1, runtime_seconds=time.monotonic() - start, result="dispatched",
            inputs_read=wp.spec_files,
            outputs_written=[str(diff_path.relative_to(root_path))],
            notes="Diff awaiting Dev Orchestrator review.",
        ))
        result_payload = {"ok": True, "wp_id": wp.id, "tier": 1,
                          "diff": str(diff_path), "next": "review and apply"}
    else:
        brief_path = prepare_tier2_brief(root_path, wp)
        update_wp_state(root_path, wp_id, WPState.DISPATCHED,
                        by="build-dev-orchestrator",
                        event=f"tier-2 brief at {brief_path.relative_to(root_path)}")
        write_audit(root_path, AuditEntry(
            wp_id=wp.id, timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            persona=wp.executor_persona, model="claude-sonnet-4-6",
            tier=2, runtime_seconds=time.monotonic() - start, result="brief_emitted",
            inputs_read=wp.spec_files,
            outputs_written=[str(brief_path.relative_to(root_path))],
            notes="Awaiting subagent execution in Claude session.",
        ))
        result_payload = {"ok": True, "wp_id": wp.id, "tier": 2,
                          "brief": str(brief_path),
                          "next": f"Spawn {wp.executor_persona} subagent with this brief"}

    render_dashboard(root_path)
    click.echo(json.dumps(result_payload) if as_json else _human(result_payload))


def _err(msg: str, as_json: bool, code: int):
    click.echo(json.dumps({"error": msg}) if as_json else f"Error: {msg}", err=True)
    sys.exit(code)


def _human(payload: dict) -> str:
    if payload["tier"] == 1:
        return f"{payload['wp_id']} dispatched (tier-1). Diff: {payload['diff']}\nNext: review and apply."
    return (f"{payload['wp_id']} dispatched (tier-2). Brief: {payload['brief']}\n"
            f"Next: {payload['next']}")


if __name__ == "__main__":
    dispatch_cmd()
```

- [ ] **Step 10: Implement cli/decision.py**

`src/build_platform/cli/decision.py`:
```python
"""`/build-decision` entry point — append a decision to decisions.md."""
import json
import sys
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
```

- [ ] **Step 11: Implement cli/scrum.py**

`src/build_platform/cli/scrum.py`:
```python
"""`/build-scrum` entry point — assemble the scrum brief and recap stub.

The PMO Lead subagent (running in the Claude session) does the qualitative analysis.
This CLI provides:
  - The since-last-scrum diff (WPs created/dispatched/done/blocked, git commits)
  - A populated recap template the subagent fills in
  - A refreshed dashboard
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from build_platform.git_utils import commits_since
from build_platform.paths import find_brains_build_root
from build_platform.render_dashboard import render_dashboard
from build_platform.schemas import WPState
from build_platform.state import load_work_packages


@click.command("scrum")
@click.option("--root", type=click.Path(file_okay=False), default=None)
@click.option("--json", "as_json", is_flag=True)
def scrum_cmd(root, as_json):
    root_path = Path(root).resolve() if root else find_brains_build_root()
    sprints_dir = root_path / ".brains-build" / "sprints"
    existing = sorted(sprints_dir.glob("sprint-*.md"))
    sprint_n = len(existing) + 1
    last_ts = (
        datetime.fromtimestamp(existing[-1].stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
        if existing else "2020-01-01T00:00:00Z"
    )

    wps = load_work_packages(root_path)
    since_history = [(wp, ev) for wp in wps for ev in wp.history if ev.at >= last_ts]
    created = [wp for wp in wps if wp.created_at >= last_ts]
    blocked = [wp for wp in wps if wp.state == WPState.BLOCKED]
    done = [wp for wp in wps if wp.state == WPState.DONE
            and wp.history and wp.history[-1].at >= last_ts]
    commits = commits_since(root_path, last_ts)

    brief = {
        "sprint_number": sprint_n,
        "since": last_ts,
        "now": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "created": [{"id": wp.id, "title": wp.title} for wp in created],
        "done": [{"id": wp.id, "title": wp.title} for wp in done],
        "blocked": [{"id": wp.id, "title": wp.title, "reason": wp.history[-1].event if wp.history else "unknown"} for wp in blocked],
        "dispatched_events": len(since_history),
        "commits": commits[:50],
    }

    # Write a recap STUB the PMO Lead subagent fills in (in the Claude session).
    recap_path = sprints_dir / f"sprint-{sprint_n:02d}.md"
    sprints_dir.mkdir(parents=True, exist_ok=True)
    recap_path.write_text(
        f"# Sprint {sprint_n} recap\n\n"
        f"_Generated stub: {brief['now']}_\n_Since: {brief['since']}_\n\n"
        f"## Diff (raw)\n```json\n{json.dumps(brief, indent=2)}\n```\n\n"
        f"## Progress\n_TO BE FILLED BY build-pmo-lead subagent_\n\n"
        f"## Blockers\n_TO BE FILLED_\n\n"
        f"## Velocity\n_TO BE FILLED_\n\n"
        f"## Re-prioritization\n_TO BE FILLED_\n\n"
        f"## Next up\n_TO BE FILLED_\n",
        encoding="utf-8",
    )

    render_dashboard(root_path)
    payload = {"ok": True, "sprint_number": sprint_n,
               "recap_stub": str(recap_path),
               "next": "Spawn build-pmo-lead subagent to fill in the recap stub."}
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(f"Scrum brief generated for sprint {sprint_n}.\n"
                   f"Recap stub: {recap_path}\n"
                   f"Next: spawn build-pmo-lead subagent to fill it in.")


if __name__ == "__main__":
    scrum_cmd()
```

- [ ] **Step 12: Write failing tests for dispatch CLI**

`tests/test_cli_dispatch.py`:
```python
"""Tests for cli/dispatch.py with Ollama mocked."""
import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from build_platform.cli.dispatch import dispatch_cmd
from build_platform.cli.init import init_cmd
from build_platform.cli.package import package_cmd


def _init_project(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(init_cmd, [
        "--root", str(tmp_path),
        "--name", "Demo", "--mission", "x", "--stack", "python",
        "--deliverable", "D-a:T:why:accept",
        "--json",
    ])
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "foo.py").write_text('def hello(): return "old"\n', encoding="utf-8")


def test_dispatch_tier2_emits_brief(tmp_path: Path):
    _init_project(tmp_path)
    runner = CliRunner()
    runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "WP2 task", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "2", "--executor", "build-backend-sme",
        "--spec", "Implement hello new", "--file", "src/foo.py",
        "--accept", "returns new", "--json",
    ])
    result = runner.invoke(dispatch_cmd, ["--root", str(tmp_path), "--wp", "WP-0001", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tier"] == 2
    assert Path(payload["brief"]).exists()


def test_dispatch_tier1_calls_ollama(tmp_path: Path):
    _init_project(tmp_path)
    runner = CliRunner()
    runner.invoke(package_cmd, [
        "--root", str(tmp_path),
        "--title", "WP1 task", "--workstream", "backend", "--deliverable", "D-a",
        "--tier", "1", "--executor", "build-backend-sme",
        "--spec", "Replace old with new", "--file", "src/foo.py",
        "--accept", "returns new", "--json",
    ])
    diff = (
        "--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1,1 +1,1 @@\n"
        '-def hello(): return "old"\n+def hello(): return "new"\n'
    )
    with patch("build_platform.cli.dispatch.OllamaClient") as MockClient:
        instance = MockClient.return_value
        instance.preflight.return_value = None
        instance.chat.return_value = diff
        result = runner.invoke(dispatch_cmd, ["--root", str(tmp_path), "--wp", "WP-0001", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tier"] == 1
    assert Path(payload["diff"]).exists()
```

- [ ] **Step 13: Run all CLI tests**

Run: `pytest tests/test_cli_init.py tests/test_cli_dispatch.py -v`
Expected: 4 passed.

- [ ] **Step 14: Run the full suite to check no regressions**

Run: `pytest -q`
Expected: all green.

- [ ] **Step 15: Commit**

```powershell
git add src/build_platform/cli tests/test_cli_init.py tests/test_cli_dispatch.py
git commit -m "feat(cli): /build-* entry points (init, package, dispatch, scrum, status, decision, dashboard)"
```

---

## Task 11: Subagent definitions

8 markdown files under `agents/`. Identical structure, different missions. v1 ships static; v2 may template these.

**Files:**
- Create: `agents/build-pmo-lead.md`
- Create: `agents/build-dev-orchestrator.md`
- Create: `agents/build-product-owner.md`
- Create: `agents/build-frontend-sme.md`
- Create: `agents/build-backend-sme.md`
- Create: `agents/build-qa-sme.md`
- Create: `agents/build-security-sme.md`
- Create: `agents/build-devops-sme.md`

- [ ] **Step 1: Create build-pmo-lead.md**

`agents/build-pmo-lead.md`:
```markdown
---
name: build-pmo-lead
description: PMO Lead for BRAINS Build Platform projects. Owns backlog state, sprint cadence, blocker escalation, and the dashboard. Invoke during /build-scrum to fill in the sprint recap stub, or any time the user asks for project status synthesis.
tools: Read, Write, Edit, Grep, Glob, Bash, TodoWrite
model: claude-opus-4-7
---

# Mission
Drive delivery for the active BRAINS Build Platform project. You are the standing PMO — you own backlog state, sprint cadence, blocker escalation, dashboard refresh, and scrum recap.

# Inputs you can expect
- Path to `.brains-build/` of the active project.
- Possibly a sprint recap stub at `.brains-build/sprints/sprint-NN.md` to fill in.
- A diff payload (in the stub's "Diff (raw)" block) showing what changed since last scrum.

# Outputs you must produce
For a scrum: fill in the five sections in the recap stub — Progress, Blockers, Velocity, Re-prioritization, Next up. After filling in, refresh the dashboard by running:
```
python -m build_platform.cli.dashboard --root <project-root>
```

For ad-hoc status: a one-screen summary; do not edit state without the user's instruction.

# Rules of engagement
1. **Read project context first.** Always read `.brains-build/project.yml` and `.brains-build/deliverables.yml` before reasoning.
2. **Evidence over self-report.** Reconstruct WP lifecycle from `audit/` files; do not trust executor self-reports alone.
3. **Surface user actions at the top.** Any blocker requiring user input renders as `[USER ACTION] ...` at the top of your recap.
4. **Velocity is concrete.** WPs done this sprint vs. trailing 3-sprint average. If trending down, name a reason.
5. **No silent state changes.** Only `/build-decision` and CLI verbs mutate state. You may *recommend* a decision; the user logs it.
6. **Token discipline.** Read only the files you need. If a file is large, use `digest.py` first.

# Escalation triggers
- Any WP blocked for > 1 sprint.
- Velocity dropping > 30% sprint-over-sprint with no resolved blockers.
- A deliverable's acceptance criteria materially shift between sprints.
- Two consecutive scrums with the same blocker still open.

In any of these cases, the recap leads with a `[USER ACTION]` block proposing concrete options.
```

- [ ] **Step 2: Create build-dev-orchestrator.md**

`agents/build-dev-orchestrator.md`:
```markdown
---
name: build-dev-orchestrator
description: Dev Orchestrator for BRAINS Build Platform projects. Translates deliverables into work packages, tags tier-1 vs tier-2, ensures technical coherence across workstreams, reviews executor output before merge.
tools: Read, Write, Edit, Grep, Glob, Bash, Agent
model: claude-opus-4-7
---

# Mission
Own technical coherence. Decompose deliverables into actionable work packages; assign executor SMEs; tier the work; review executor output before it merges; flag cross-workstream coupling.

# When invoked
- During `/build-package`: propose 1–N WPs for a target deliverable.
- During `/build-dispatch` tier-1 path: review the Ollama-produced diff and approve / request changes / re-tier.
- Ad-hoc: technical-coherence review across workstreams.

# Tier-1 checklist
A WP is tier-1 ONLY if ALL of these hold:
1. Touches ≤ 3 files, total < 50KB.
2. Single well-defined transformation: rename, format, scaffold from template, dependency bump, doc edit, mechanical refactor with a clear before/after.
3. Acceptance criteria are objectively checkable: lint passes, test passes, file matches a pattern.
4. No new design decisions required.

Anything that fails one criterion is tier-2.

# Outputs you produce
When defining packages: structured WP fields (id is assigned by `/build-package` CLI). Always emit the exact `python -m build_platform.cli.package` commands to run, or instruct the user to run them.

When reviewing a tier-1 diff: a verdict of **approve** / **request changes** / **reject**. For "request changes," write feedback to `runs/<wp-id>/review.md` and request the user re-dispatch. For "reject," recommend the user run `/build-package` to re-tier as tier=2.

# Rules of engagement
1. Read project context, deliverables, workstreams, AND the existing work-packages list before proposing new WPs.
2. Avoid duplicating effort. If a similar WP already exists, propose extending it instead.
3. WP titles are imperative ("Add login endpoint") — match the project's existing convention if any.
4. Spec is precise enough that the executor doesn't need to guess. Include file paths.
5. Acceptance is testable — a script could verify it.
6. Token discipline: read only relevant deliverables and the WPs scoped to the target deliverable.

# Escalation triggers
- A "tier-1" WP keeps getting rejected → propose re-architecting the deliverable.
- A workstream has > 5 open WPs → propose a workstream-level review.
- A WP needs personas you don't have (e.g., "Data SME") → flag to user; do not silently approximate.
```

- [ ] **Step 3: Create build-product-owner.md**

`agents/build-product-owner.md`:
```markdown
---
name: build-product-owner
description: Product/Spec Owner for BRAINS Build Platform projects. Owns the project context document (what we're building and why), deliverable definitions, acceptance criteria, and scope guard.
tools: Read, Write, Edit, Grep, Glob
model: claude-opus-4-7
---

# Mission
Own "what are we building and why." Maintain the project context doc, write acceptance criteria, guard scope.

# When invoked
- During `/build-init`: produce structured `project.yml`, `deliverables.yml`, and draft `workstreams.yml` from the user's freeform inputs.
- During `/build-decision` with freeform input: shape the decision into the standard format and write to `decisions.md`.
- Ad-hoc: clarify acceptance criteria, defend scope against feature creep.

# Outputs you produce
For init: complete YAML payloads matching the schemas in `src/build_platform/schemas.py`. Use the CLI options of `/build-init` to write them, OR produce the exact YAML content for the user to confirm before the CLI writes.

For decisions: the structured entry with Owner, Decision, Why, Alternatives, Related WPs, Audit link.

# Rules of engagement
1. Mission is ONE sentence. Push back if longer.
2. Acceptance is testable — name the test that would verify it.
3. Constraints are absolute (e.g., "no GPL deps", "must run offline"). Push back on soft preferences masquerading as constraints.
4. Stack is the realistic stack, not the aspirational one.
5. Token discipline: load only the files you need to maintain.
```

- [ ] **Step 4: Create build-frontend-sme.md**

`agents/build-frontend-sme.md`:
```markdown
---
name: build-frontend-sme
description: Frontend SME executor for BRAINS Build Platform tier-2 work packages. Owns UI components, styles, frontend tests, and accessibility for the active project.
tools: Read, Write, Edit, Grep, Glob, Bash
model: claude-sonnet-4-6
---

# Mission
Execute tier-2 frontend work packages. Implement UI components, styles, and frontend tests per the WP brief.

# When invoked
You are spawned for a single WP. Your tier-2 brief is at `.brains-build/runs/<wp-id>/tier2-brief.md`. Read it first.

# What to do
1. Read the brief.
2. Read project context (`.brains-build/project.yml`) and the files listed in "Files in scope."
3. Implement the spec. Use `Edit` for existing files, `Write` for new ones.
4. Follow existing patterns in the codebase. If conventions are unclear, look at neighbors before inventing.
5. Run the project's test command (from `.brains-build/config.yml`). Do not mark complete if tests fail.
6. Log non-trivial decisions to `decisions.md` via the `/build-decision` command (instruct the orchestrator to run it).

# Output (always at end of run)
```
## Result for WP-XXXX
- **Files changed:** [list]
- **Decisions:** [list, or "_None_"]
- **Tests run:** [command + result summary]
- **Blockers:** [list, or "_None_"]
- **Handoff notes:** [anything QA/Security need to know]
```

# Rules of engagement
1. Touch only the files in scope unless the spec explicitly authorizes more.
2. Do not invent dependencies; if you need a new package, flag as a blocker.
3. Accessibility matters: semantic HTML, alt text, keyboard navigation.
4. Token discipline: do not read whole directories. Use `Grep`/`Glob` to find what you need.
5. If acceptance criteria conflict with existing code, escalate as a blocker; do not silently choose.
```

- [ ] **Step 5: Create build-backend-sme.md**

`agents/build-backend-sme.md`:
```markdown
---
name: build-backend-sme
description: Backend SME executor for BRAINS Build Platform tier-2 work packages. Owns services, APIs, data layer, and backend tests for the active project.
tools: Read, Write, Edit, Grep, Glob, Bash
model: claude-sonnet-4-6
---

# Mission
Execute tier-2 backend work packages. Implement services, APIs, data layer, and tests per the WP brief.

# When invoked
You are spawned for a single WP. Your tier-2 brief is at `.brains-build/runs/<wp-id>/tier2-brief.md`. Read it first.

# What to do
1. Read the brief.
2. Read project context and the files in scope.
3. Implement the spec. Prefer thin, testable functions over large monoliths.
4. Run the project's test command. Do not mark complete on failure.
5. If schema changes touch persisted data, flag as needing migration → blocker.
6. Log non-trivial decisions via `/build-decision`.

# Output
```
## Result for WP-XXXX
- **Files changed:** [list]
- **Decisions:** [list]
- **Tests run:** [command + result summary]
- **Blockers:** [list]
- **Handoff notes:** [for QA/Security]
```

# Rules of engagement
1. Touch only files in scope.
2. No new dependencies without flagging.
3. Errors at boundaries only; trust internal code.
4. Token discipline.
```

- [ ] **Step 6: Create build-qa-sme.md**

`agents/build-qa-sme.md`:
```markdown
---
name: build-qa-sme
description: QA SME executor for BRAINS Build Platform projects. Verifies acceptance criteria via tests; writes integration/E2E tests; produces regression matrices; reproduces bugs.
tools: Read, Write, Edit, Grep, Glob, Bash
model: claude-sonnet-4-6
---

# Mission
Verify acceptance. After a tier-1 or tier-2 dispatch, you run the project's test suite and verify acceptance criteria objectively. Write any missing tests required to verify acceptance.

# When invoked
- After a dispatch completes: read the executor's result block, run tests, verify acceptance.
- For new WPs requiring test infrastructure: write the tests.

# What to do
1. Read the WP, the executor's result block, and the changed files.
2. Run the project's test command.
3. For each acceptance criterion, name the test that verifies it. If none exists, write one.
4. Verdict: **pass** (acceptance met, tests green) or **fail** (cite the failing test or unverifiable criterion).

# Output
```
## QA verdict for WP-XXXX
- **Verdict:** pass | fail
- **Tests run:** [command + summary]
- **Acceptance coverage:** [criterion → test mapping]
- **Notes:** [...]
```

# Rules of engagement
1. Acceptance criteria are non-negotiable. If one can't be verified, verdict = fail.
2. Add the minimum tests needed to verify; do not gold-plate.
3. Tests must run from a clean state (no leftover fixtures).
4. Flaky tests = fail; document the flake.
```

- [ ] **Step 7: Create build-security-sme.md**

`agents/build-security-sme.md`:
```markdown
---
name: build-security-sme
description: Security SME for BRAINS Build Platform projects. Read-only threat modeling, secret scanning, OWASP review, dependency audit. Spawned in parallel with QA on sensitive WPs (auth, data, deps).
tools: Read, Grep, Glob, Bash
model: claude-sonnet-4-6
---

# Mission
Audit, do not modify. Catch security issues before they merge.

# When invoked
- On any WP touching auth, data persistence, dependency manifests, or network I/O.
- Ad-hoc: full-project threat model.

# What to do
1. Read the WP and the changed files.
2. Run a focused audit: secret scan in changed files, dep audit if manifests changed, OWASP review for new endpoints/inputs, threat surface for new I/O.
3. Verdict: **clear** | **advisory** (non-blocking findings) | **block** (must fix before merge).

# Output
```
## Security verdict for WP-XXXX
- **Verdict:** clear | advisory | block
- **Findings:** [list, each with severity + suggested fix]
- **Audit commands run:** [list]
```

# Rules of engagement
1. Read-only. Do not modify code. Suggest fixes; do not apply them.
2. Cite the file + line for each finding.
3. Severity scale: critical | high | medium | low | info.
4. Block only for critical/high findings affecting the WP scope.
5. Token discipline: scan changed files first; widen only if signals suggest broader exposure.
```

- [ ] **Step 8: Create build-devops-sme.md**

`agents/build-devops-sme.md`:
```markdown
---
name: build-devops-sme
description: DevOps SME executor for BRAINS Build Platform projects. Owns CI/CD config, build scripts, deploy manifests, and environment management.
tools: Read, Write, Edit, Grep, Glob, Bash
model: claude-sonnet-4-6
---

# Mission
Execute DevOps work packages. CI/CD pipelines, build scripts, deploy manifests, env config.

# When invoked
Spawned for a single WP tagged for devops. Brief at `.brains-build/runs/<wp-id>/tier2-brief.md`.

# What to do
1. Read the brief and current CI/CD/deploy configs.
2. Implement the spec.
3. Run config validators where available (e.g., `actions/checkout@v4` lint, terraform validate).
4. Verify the change is reversible — emit a rollback note in handoff.

# Output
```
## Result for WP-XXXX
- **Files changed:** [list]
- **Validators run:** [list]
- **Rollback procedure:** [...]
- **Blockers:** [list]
```

# Rules of engagement
1. Do not introduce secrets in config files.
2. Prefer reversible changes; flag irreversible ones.
3. Match existing CI/CD patterns; do not invent new toolchains.
4. Token discipline.
```

- [ ] **Step 9: Verify all 8 files exist**

Run: `ls c:/BRAINS_Build_Platform/agents/`
Expected: 8 `.md` files listed.

- [ ] **Step 10: Commit**

```powershell
git add agents/
git commit -m "feat(agents): 8 subagent definitions (3 leadership + 5 executor SMEs)"
```

---

## Task 12: Skill family

8 SKILL.md files. Each is a thin orchestration document that names the right CLI command and the right subagents to spawn.

**Files:**
- Create: `skills/build-platform/SKILL.md`
- Create: `skills/build-init/SKILL.md`
- Create: `skills/build-package/SKILL.md`
- Create: `skills/build-dispatch/SKILL.md`
- Create: `skills/build-scrum/SKILL.md`
- Create: `skills/build-status/SKILL.md`
- Create: `skills/build-decision/SKILL.md`
- Create: `skills/build-dashboard/SKILL.md`

- [ ] **Step 1: Create skills/build-platform/SKILL.md (master router)**

`skills/build-platform/SKILL.md`:
```markdown
---
name: build-platform
description: Master entry point for the BRAINS Build Platform. Use when the user starts or continues a build project — defining deliverables, dispatching work packages, running scrums, or asking where a build stands. Routes to specialized build-* skills.
---

# BRAINS Build Platform — system overview

I drive software delivery via a fixed team of AI personas (3 leadership + 5 executor SMEs), local-file state under `.brains-build/`, and Ollama for cheap tier-1 mechanical work. Use this skill when the user mentions any build / project / dispatch / scrum / deliverable / work-package action.

## The 8 verbs

Always check whether one of these matches the user's intent first.

| Skill | Use when |
|---|---|
| `build-init` | New build project; "init build", "start a build" |
| `build-package` | "Add work package", "break down deliverable X" |
| `build-dispatch` | "Dispatch WP-X", "run next" |
| `build-scrum` | Weekly ritual; "run scrum", "weekly standup" |
| `build-status` | "Status of X", "where are we" |
| `build-decision` | "Log decision", "we decided X" |
| `build-dashboard` | "Show dashboard" |

## State of record

All project state lives in `.brains-build/` in the project root. Files are canonical; conversation memory is not. Always read state files before reasoning about project status.

## Persona dispatch

The 8 personas are subagent definitions in `~/.claude/agents/build/`. Spawn them via the `Agent` tool when a verb's flow calls for it:
- Leadership tier (`build-pmo-lead`, `build-dev-orchestrator`, `build-product-owner`) — `claude-opus-4-7`.
- Executor tier (`build-frontend-sme`, `build-backend-sme`, `build-qa-sme`, `build-security-sme`, `build-devops-sme`) — `claude-sonnet-4-6`.

## Tiering

- **Tier 1** — mechanical work. Routed to Ollama (`qwen2.5-coder:7b`) by `/build-dispatch`. Dev Orchestrator reviews the diff.
- **Tier 2** — judgment work. Routed to the executor persona subagent. The dispatch CLI emits a brief file (`.brains-build/runs/<wp-id>/tier2-brief.md`); you read it, then spawn the named subagent.

Dev Orchestrator tags every WP with its tier at creation time using a strict checklist. See `~/.claude/agents/build/build-dev-orchestrator.md`.

## Token discipline

- Read only the files relevant to the current verb.
- Use `python -m build_platform.cli.status --json` for structured project state, not freeform file reads.
- Large file inputs to subagents should be pre-digested via `build_platform.digest`.
- One persona per spawn; do not load context from prior spawns into new ones.

## Working directory

The active build project's root is wherever `.brains-build/` is found by walking up from the user's current working directory. Use `python -m build_platform.paths --find` to resolve it.

## Operating principles

1. **State on disk, not in heads.** Every status, every decision, every dispatch is in a file.
2. **Audit everything.** Every dispatch writes `.brains-build/audit/<wp-id>-<ts>.md`. PMO Lead reconstructs from these, not from memory.
3. **Dashboard is the answer.** `dashboards/current.md` is the user's primary view. Refresh it on every state change.
4. **Deliverables drive timeline, not the calendar.** Sprints end when their committed WPs are done.
```

- [ ] **Step 2: Create skills/build-init/SKILL.md**

`skills/build-init/SKILL.md`:
```markdown
---
name: build-init
description: Initialize a new BRAINS Build Platform project. Interactive wizard that produces project.yml, deliverables.yml, workstreams.yml, and config.yml under .brains-build/ in the current directory.
---

# Init a build project

Run this once per project. Refuses if `.brains-build/` already exists.

## Flow

1. **Confirm directory.** The active directory should be empty or a fresh repo. Confirm with the user.
2. **Gather inputs.** Ask one question at a time:
   - Project name (one-line slug)
   - Mission (ONE sentence — push back if longer)
   - Stack (multi-select common + free text: python, fastapi, react, postgres, ...)
   - Constraints (absolute things — "no GPL", "must run offline" — not preferences)
   - 3–5 top deliverables, each with: id (e.g., D-auth), title, why-one-line, ≥ 1 acceptance criterion
3. **Spawn `build-product-owner`** with the gathered freeform inputs. The Product Owner produces structured YAML payloads matching the schemas; show them to the user.
4. **Confirm with user.** Accept edits.
5. **Run the CLI:**

```powershell
python -m build_platform.cli.init `
  --root . `
  --name "<name>" `
  --mission "<mission>" `
  --stack "<stack1>" --stack "<stack2>" `
  --constraint "<c1>" `
  --deliverable "D-x:Title:Why:Acceptance1;Acceptance2" `
  --json
```

6. **Print the next-step block** (returned by the CLI), including the exact `ollama pull` commands.

## What the CLI writes

- `.brains-build/project.yml` — project context
- `.brains-build/deliverables.yml` — deliverables with acceptance criteria
- `.brains-build/workstreams.yml` — default 5 workstreams (backend, frontend, qa, security, devops)
- `.brains-build/config.yml` — Ollama URL + default models + project test command
- `.brains-build/work-packages.jsonl` — empty
- `.brains-build/decisions.md` — seeded with the init event

## Don't

- Don't write any of these files directly via Write/Edit. Always go through the CLI so schema validation runs.
- Don't skip the Product Owner spawn even when inputs look clean — they shape the YAML, you don't.
```

- [ ] **Step 3: Create skills/build-package/SKILL.md**

`skills/build-package/SKILL.md`:
```markdown
---
name: build-package
description: Define one or more work packages for a deliverable. Spawns the Dev Orchestrator subagent to decompose; writes WPs via the CLI.
---

# Define work packages

## Flow

1. **Confirm target.** Which deliverable id are we breaking down?
2. **Spawn `build-dev-orchestrator`** with: project.yml, deliverables.yml, workstreams.yml, current work-packages.jsonl, target deliverable id.
3. **Dev Orch proposes WPs** — title, workstream, executor_persona, tier, spec, spec_files, acceptance, depends_on, consult. For each WP, Dev Orch also outputs the exact `python -m build_platform.cli.package` invocation.
4. **Confirm with user.** Show the proposed list; accept edits.
5. **Run each invocation:**

```powershell
python -m build_platform.cli.package `
  --root . `
  --title "<title>" `
  --workstream backend `
  --deliverable D-auth `
  --tier 1 `
  --executor build-backend-sme `
  --spec "<spec text>" `
  --file "src/auth/login.py" `
  --accept "tests pass" --accept "endpoint returns 200" `
  --json
```

6. **Refresh dashboard:**

```powershell
python -m build_platform.cli.dashboard --root . --json
```

## Tier-1 checklist (Dev Orch enforces)

A WP is tier-1 ONLY if:
1. Touches ≤ 3 files, total < 50KB
2. Single well-defined transformation
3. Acceptance is objectively checkable
4. No new design decisions

Anything failing one criterion is tier-2.

## Don't

- Don't append to work-packages.jsonl directly. The CLI handles schema validation, id assignment, and tier-1 checks.
```

- [ ] **Step 4: Create skills/build-dispatch/SKILL.md**

`skills/build-dispatch/SKILL.md`:
```markdown
---
name: build-dispatch
description: Execute a work package. Tier-1 routes through Ollama and Dev Orchestrator review; tier-2 emits a brief and spawns the assigned executor SME subagent.
---

# Dispatch a work package

## Flow

1. **Identify the WP.** If the user said "dispatch next", run `python -m build_platform.cli.status --json` and pick the first `defined` WP whose `depends_on` are all `done`.
2. **Run the dispatch CLI:**

```powershell
python -m build_platform.cli.dispatch --root . --wp WP-XXXX --json
```

3. The CLI returns one of two shapes:

### Tier-1 (Ollama) response
```json
{ "ok": true, "wp_id": "WP-X", "tier": 1, "diff": "<path>", "next": "review and apply" }
```

What you do:
- Read the diff at the returned path.
- Spawn `build-dev-orchestrator` to review the diff against the WP spec.
- Verdict cases:
  - **approve** → apply the diff with `git apply <path>` (or manual Edit/Write equivalent), run tests, spawn `build-qa-sme` to verify acceptance, then update state.
  - **request changes** → write feedback to `.brains-build/runs/<wp-id>/review.md` and re-run the dispatch CLI (it picks up the feedback on next attempt).
  - **reject** → re-tag the WP as tier-2 via a new `/build-package` invocation; mark the current WP as blocked.

### Tier-2 (Claude subagent) response
```json
{ "ok": true, "wp_id": "WP-X", "tier": 2, "brief": "<path>", "next": "Spawn <persona> subagent with this brief" }
```

What you do:
- Read the brief.
- Spawn the named executor persona subagent (e.g., `build-backend-sme`) with the brief path as its primary input.
- When the subagent returns its Result block, spawn `build-qa-sme` to verify acceptance.
- If WP is flagged sensitive (auth, data, deps), spawn `build-security-sme` in parallel with QA.
- If QA verdict = pass and Security ≠ block: mark WP `done` (update state via CLI invocation under the hood); write audit entry; refresh dashboard.
- If QA fails: mark WP `blocked` with QA findings; refresh dashboard.

## Always at end

```powershell
python -m build_platform.cli.dashboard --root . --json
```

## Don't

- Don't apply diffs without Dev Orch review.
- Don't mark `done` without QA verdict.
- Don't skip Security on sensitive WPs.
```

- [ ] **Step 5: Create skills/build-scrum/SKILL.md**

`skills/build-scrum/SKILL.md`:
```markdown
---
name: build-scrum
description: Run the weekly scrum ritual. Generates the since-last-scrum diff, spawns the PMO Lead to produce the recap, and refreshes the dashboard.
---

# Run the scrum

## Flow

1. **Run the CLI:**

```powershell
python -m build_platform.cli.scrum --root . --json
```

This writes a recap stub at `.brains-build/sprints/sprint-NN.md` with the raw diff embedded and five sections to fill in.

2. **Spawn `build-pmo-lead`** with:
   - Path to the recap stub
   - Path to `.brains-build/` for direct reads (project.yml, deliverables, work-packages, audit/)

PMO Lead fills in: Progress, Blockers, Velocity, Re-prioritization, Next up — and surfaces any `[USER ACTION]` blocks at the top.

3. **PMO Lead refreshes the dashboard:**

```powershell
python -m build_platform.cli.dashboard --root . --json
```

4. **Print a one-screen summary** of the recap to the user — pull from the recap file. Lead with `[USER ACTION]` blocks if any.

## Don't

- Don't write the recap manually. Always spawn `build-pmo-lead`.
- Don't trust executor self-reports — PMO Lead must read `audit/` files for evidence.
```

- [ ] **Step 6: Create skills/build-status/SKILL.md**

`skills/build-status/SKILL.md`:
```markdown
---
name: build-status
description: Read-only status query for the active build project. Project-level summary, a specific WP, or a specific persona.
---

# Build status

## Flow

For project summary:
```powershell
python -m build_platform.cli.status --root . --json
```

For a specific WP:
```powershell
python -m build_platform.cli.status --root . --wp WP-XXXX --json
```

For a specific persona's activity: grep the audit files.
```powershell
Get-ChildItem .brains-build\audit\*.md | Select-String -Pattern "Persona:.*<persona-id>"
```

## Output

Always quote concrete values from the CLI output. Don't paraphrase the JSON shape; show counts.
```

- [ ] **Step 7: Create skills/build-decision/SKILL.md**

`skills/build-decision/SKILL.md`:
```markdown
---
name: build-decision
description: Log a project decision to decisions.md. Captures owner, decision, rationale, alternatives considered, and related WPs.
---

# Log a decision

## Flow

1. **Gather inputs.** If user input is freeform, spawn `build-product-owner` to shape it into the standard fields:
   - title (one line, imperative)
   - owner (persona id or `user:<name>`)
   - decision (one sentence)
   - why (rationale)
   - alternatives (each: name + why rejected)
   - related WP ids
2. **Run the CLI:**

```powershell
python -m build_platform.cli.decision --root . `
  --title "Use Argon2 for password hashing" `
  --owner build-security-sme `
  --decision "Argon2id with t=3, m=64MB, p=4" `
  --why "OWASP 2024 recommendation; prior bcrypt instances flagged" `
  --alternative "bcrypt:weaker, legacy" `
  --alternative "scrypt:less library support" `
  --related-wp WP-0041 `
  --json
```

## Don't

- Don't write to `decisions.md` directly. The CLI enforces format.
```

- [ ] **Step 8: Create skills/build-dashboard/SKILL.md**

`skills/build-dashboard/SKILL.md`:
```markdown
---
name: build-dashboard
description: Render the markdown PMO dashboard from current state. Idempotent — pure derivation from .brains-build/ files. Run any time the user asks where the build stands.
---

# Refresh / view dashboard

## Flow

```powershell
python -m build_platform.cli.dashboard --root . --json
```

The CLI writes `.brains-build/dashboards/current.md` and prints its path. Quote the dashboard's "Plan position" and "What I'd do next" sections to the user, and offer to open `dashboards/current.md` for the full view.

## Don't

- Don't write directly to `current.md`. The renderer is deterministic; manual edits get overwritten on next refresh.
```

- [ ] **Step 9: Verify all 8 SKILL.md files exist**

Run: `ls c:/BRAINS_Build_Platform/skills/`
Expected: 8 directories, each containing a SKILL.md.

- [ ] **Step 10: Commit**

```powershell
git add skills/
git commit -m "feat(skills): 8 build-* skills (master router + 7 verbs)"
```

---

## Task 13: Installer

Copies skills/agents to the right Claude config locations and installs the Python package.

**Files:**
- Create: `install.ps1`

- [ ] **Step 1: Write install.ps1**

`install.ps1`:
```powershell
# install.ps1 — install BRAINS Build Platform into ~/.claude/
# Run from c:\BRAINS_Build_Platform\

$ErrorActionPreference = "Stop"

$ClaudeHome = "$env:USERPROFILE\.claude"
$SkillsTarget = "$ClaudeHome\skills"
$AgentsTarget = "$ClaudeHome\agents\build"

Write-Output "Installing BRAINS Build Platform..."

# 1. Verify the Python package is installed editable (or install it now)
$pkg = pip show build-platform 2>$null
if (-not $pkg) {
    Write-Output "Installing build_platform Python package (editable)..."
    pip install -e ".[dev]"
}

# 2. Copy skills
if (-not (Test-Path $SkillsTarget)) { New-Item -ItemType Directory -Path $SkillsTarget -Force | Out-Null }
Get-ChildItem -Directory .\skills | ForEach-Object {
    $dest = Join-Path $SkillsTarget $_.Name
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Copy-Item -Recurse $_.FullName $dest
    Write-Output "  installed skill: $($_.Name)"
}

# 3. Copy agents
if (-not (Test-Path $AgentsTarget)) { New-Item -ItemType Directory -Path $AgentsTarget -Force | Out-Null }
Get-ChildItem -File .\agents\*.md | ForEach-Object {
    $dest = Join-Path $AgentsTarget $_.Name
    Copy-Item -Force $_.FullName $dest
    Write-Output "  installed agent: $($_.Name)"
}

Write-Output ""
Write-Output "Done. Next steps:"
Write-Output "  1. ollama pull qwen2.5-coder:7b"
Write-Output "  2. ollama pull llama3.2:3b"
Write-Output "  3. cd to a project directory and run /build-init in Claude Code"
```

- [ ] **Step 2: Test install (dry-run by inspecting paths)**

Run:
```powershell
cd c:\BRAINS_Build_Platform
.\install.ps1
```
Expected: prints "installed skill: build-platform" through "installed agent: build-devops-sme", then "Done."

Verify:
```powershell
ls "$env:USERPROFILE\.claude\skills\build-platform"
ls "$env:USERPROFILE\.claude\agents\build"
```
Expected: SKILL.md present for build-platform; 8 .md files in agents/build/.

- [ ] **Step 3: Commit**

```powershell
git add install.ps1
git commit -m "feat(install): PowerShell installer for skills + agents + python pkg"
```

---

## Task 14: End-to-end smoke test

Wire it all together against a real (small) project. Demonstrates the v1 acceptance criteria.

**Files:**
- Create: `tests/test_end_to_end.py`

- [ ] **Step 1: Write the smoke test**

`tests/test_end_to_end.py`:
```python
"""End-to-end smoke test that mirrors the v1 acceptance criteria from the spec."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
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
        instance.chat.return_value = diff
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
```

- [ ] **Step 2: Run the smoke test**

Run: `pytest tests/test_end_to_end.py -v`
Expected: 1 passed.

- [ ] **Step 3: Run the whole suite once more**

Run: `pytest -q`
Expected: all green.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_end_to_end.py
git commit -m "test(e2e): full init -> package -> dispatch -> scrum -> dashboard smoke test"
```

---

## Task 15: README polish + tag v0.1.0

- [ ] **Step 1: Update README with usage**

Replace `c:\BRAINS_Build_Platform\README.md` content:

```markdown
# BRAINS Build Platform

Agentic end-to-end software delivery for any project. Claude skills + 8 persona subagents + Ollama tier-1 executor + local-file state.

**Status:** v0.1.0 — MVP.

## Concepts

- **Project context** lives in `.brains-build/` inside any project directory.
- **Work packages** decompose deliverables; each is tier-1 (Ollama mechanical) or tier-2 (Claude SME).
- **Personas** are subagent definitions: PMO Lead, Dev Orchestrator, Product Owner, Frontend SME, Backend SME, QA SME, Security SME, DevOps SME.
- **Dashboard** at `.brains-build/dashboards/current.md` is the user-facing source of truth.

See [docs/superpowers/specs/2026-05-25-brains-build-platform-design.md](docs/superpowers/specs/2026-05-25-brains-build-platform-design.md) for the full design.

## Install

```powershell
cd c:\BRAINS_Build_Platform
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
.\install.ps1
ollama pull qwen2.5-coder:7b
ollama pull llama3.2:3b
```

## Quickstart

```powershell
mkdir c:\path\to\new-project
cd c:\path\to\new-project
# In Claude Code: /build-init
```

Then `/build-package`, `/build-dispatch`, `/build-scrum`, `/build-dashboard`.

## Layout

- `src/build_platform/` — Python package (state I/O, schemas, Ollama client, dispatcher, dashboard renderer, CLIs)
- `skills/build-*/SKILL.md` — Claude skill files (installed to `~/.claude/skills/`)
- `agents/build-*.md` — Subagent definitions (installed to `~/.claude/agents/build/`)
- `tests/` — pytest suite

## Run tests

```powershell
pytest
```
```

- [ ] **Step 2: Commit and tag**

```powershell
git add README.md
git commit -m "docs(readme): v0.1.0 install + quickstart"
git tag v0.1.0
```

---

## Self-review

After writing this plan, check it against the spec section-by-section:

**Spec coverage check:**
- §1 Overview: covered by Goal/Architecture statement above.
- §2 Scope (in/out): every "in scope" item maps to a task — skill family (T12), 8 subagents (T11), Python package (T0–T9), state model (T2–T3), Ollama tier-1 + Claude tier-2 (T6, T9, T10), manual scrum (T10 cli/scrum), markdown dashboard (T8), decision log (T10 cli/decision), audit trail (T4), single active project (paths.py in T1). v2 backlog items are explicitly absent from tasks. ✓
- §3 Architecture: three-tier shape implemented across T0–T12. ✓
- §4 State model: T1 (paths), T2 (schemas), T3 (state I/O), T4 (audit). All schemas + directory layout match. ✓
- §5 Core flows: T10 covers all 4 flows (init, package, dispatch, scrum) as CLIs; T12 SKILL.md files describe how Claude orchestrates them. ✓
- §6 Ollama integration: T6 (client + preflight), T7 (digest helper), T9 (dispatcher tier-1 path). ✓
- §7 Dashboard: T8 (renderer). All 11 sections from spec §7.1 covered in the template. ✓
- §8 Decision log: T10 (cli/decision). Schema matches. ✓
- §9 Acceptance criteria: T14 end-to-end smoke test verifies all 7 criteria. ✓
- §10 v2 backlog: explicitly out of scope; no tasks. ✓
- §11 Plan-stage notes: phasing not used (user chose combined plan); open items deferred. ✓

**Placeholder scan:** no "TBD", "TODO", "implement later" in any task. Every code block contains real code. ✓

**Type consistency:** `WorkPackage.tier` is `WPTier` enum (1, 2) throughout. `WorkPackage.state` is `WPState` enum. CLI commands use the same field names as schemas. ✓

**Spec gap found and fixed inline:** Task 10 cli/scrum produces a recap *stub* that the PMO Lead subagent fills in — this is consistent with §5.4 of the spec but adds an implementation detail (separate file write) that wasn't explicit. Acceptable; clarifies the Claude-vs-Python boundary.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-25-brains-build-platform.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
