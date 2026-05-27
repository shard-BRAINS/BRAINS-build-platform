"""Tests for triage.py — pure heuristic."""
from pathlib import Path

import pytest

from build_platform.triage import suggest_tier


# ---------------------------------------------------------------------------
# Tier-1 happy path
# ---------------------------------------------------------------------------

def test_clean_mechanical_renaming_suggests_tier_1():
    out = suggest_tier(
        spec="Rename get_cwd() to get_current_working_directory() across the module.",
        spec_files=["src/utils.py"],
        acceptance=["all tests pass", "lint passes"],
    )
    assert out["suggested_tier"] == 1
    assert all(c["pass"] for c in out["criteria"])


def test_format_pass_with_single_file():
    out = suggest_tier(
        spec="Format src/foo.py with ruff.",
        spec_files=["src/foo.py"],
        acceptance=["ruff check passes", "ruff format leaves no diff"],
    )
    assert out["suggested_tier"] == 1


def test_add_field_passes():
    out = suggest_tier(
        spec="Add field seen_comments: dict[str, list[int]] to MirrorMap. Default empty dict.",
        spec_files=["src/build_platform/github_mirror.py"],
        acceptance=["round-trip test passes", "new test for default value passes"],
    )
    assert out["suggested_tier"] == 1


# ---------------------------------------------------------------------------
# Tier-2 because of scope
# ---------------------------------------------------------------------------

def test_too_many_files_fails_scope():
    out = suggest_tier(
        spec="Rename function across the codebase.",
        spec_files=["a.py", "b.py", "c.py", "d.py"],  # 4 files
        acceptance=["tests pass"],
    )
    assert out["suggested_tier"] == 2
    scope = next(c for c in out["criteria"] if c["name"] == "scope")
    assert scope["pass"] is False
    assert "4 files" in scope["detail"]


def test_oversized_file_fails_scope(tmp_path: Path):
    big = tmp_path / "big.py"
    big.write_text("x" * 60_000, encoding="utf-8")
    out = suggest_tier(
        spec="Rename a function in big.py.",
        spec_files=["big.py"],
        acceptance=["tests pass"],
        project_root=tmp_path,
    )
    assert out["suggested_tier"] == 2
    scope = next(c for c in out["criteria"] if c["name"] == "scope")
    assert scope["pass"] is False
    assert "60000B exceeds" in scope["detail"]


# ---------------------------------------------------------------------------
# Tier-2 because of judgment / design content
# ---------------------------------------------------------------------------

def test_design_keyword_in_spec_fails():
    out = suggest_tier(
        spec="Rename get_cwd, but first decide which name is clearest.",
        spec_files=["src/utils.py"],
        acceptance=["tests pass"],
    )
    assert out["suggested_tier"] == 2
    nodk = next(c for c in out["criteria"] if c["name"] == "no_design_keywords")
    assert nodk["pass"] is False
    assert "decide" in nodk["detail"]


def test_architecture_keyword_fails():
    out = suggest_tier(
        spec="Replace bcrypt with a new password hash. Architecture decision needed.",
        spec_files=["src/auth.py"],
        acceptance=["tests pass"],
    )
    assert out["suggested_tier"] == 2


def test_no_mechanical_verb_fails():
    out = suggest_tier(
        spec="Implement the user login endpoint with sessions and rate limits.",
        spec_files=["src/auth/login.py"],
        acceptance=["test_login passes"],
    )
    assert out["suggested_tier"] == 2
    mv = next(c for c in out["criteria"] if c["name"] == "mechanical_verb")
    assert mv["pass"] is False


# ---------------------------------------------------------------------------
# Tier-2 because acceptance criteria aren't objective
# ---------------------------------------------------------------------------

def test_non_objective_acceptance_fails():
    out = suggest_tier(
        spec="Rename helper function.",
        spec_files=["src/utils.py"],
        acceptance=["the code is more readable", "follows good practice"],
    )
    assert out["suggested_tier"] == 2
    obj = next(c for c in out["criteria"] if c["name"] == "objective_acceptance")
    assert obj["pass"] is False
    assert "more readable" in obj["detail"]


def test_mixed_acceptance_with_one_non_objective_fails():
    out = suggest_tier(
        spec="Rename helper.",
        spec_files=["src/utils.py"],
        acceptance=["tests pass", "code looks cleaner"],
    )
    assert out["suggested_tier"] == 2


def test_empty_acceptance_fails():
    out = suggest_tier(
        spec="Rename helper.",
        spec_files=["src/utils.py"],
        acceptance=[],
    )
    assert out["suggested_tier"] == 2


# ---------------------------------------------------------------------------
# Output shape + rationale
# ---------------------------------------------------------------------------

def test_output_shape_includes_all_four_criteria():
    out = suggest_tier(
        spec="Rename foo.",
        spec_files=["a.py"],
        acceptance=["tests pass"],
    )
    names = [c["name"] for c in out["criteria"]]
    assert names == ["scope", "mechanical_verb", "no_design_keywords", "objective_acceptance"]


def test_rationale_lists_failed_criteria_for_tier_2():
    out = suggest_tier(
        spec="Implement complex thing requiring design.",
        spec_files=["a.py"],
        acceptance=["code is nice"],
    )
    assert "Failed criteria:" in out["rationale"]
    assert "mechanical_verb" in out["rationale"]
    assert "no_design_keywords" in out["rationale"]
    assert "objective_acceptance" in out["rationale"]


def test_rationale_concise_for_tier_1():
    out = suggest_tier(
        spec="Rename helper.",
        spec_files=["a.py"],
        acceptance=["tests pass"],
    )
    assert out["rationale"] == "All four tier-1 criteria pass."


# ---------------------------------------------------------------------------
# Scope measurement with project_root
# ---------------------------------------------------------------------------

def test_scope_measurement_with_real_files(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "small.py").write_text("x" * 100, encoding="utf-8")
    out = suggest_tier(
        spec="Rename function.",
        spec_files=["src/small.py"],
        acceptance=["tests pass"],
        project_root=tmp_path,
    )
    scope = next(c for c in out["criteria"] if c["name"] == "scope")
    assert scope["pass"] is True
    assert "100B" in scope["detail"]


def test_scope_treats_new_files_as_zero_bytes(tmp_path: Path):
    """Files that don't exist yet (new file creation) shouldn't fail scope on size."""
    out = suggest_tier(
        spec="Scaffold new module.",
        spec_files=["src/new_module.py"],
        acceptance=["tests pass"],
        project_root=tmp_path,
    )
    scope = next(c for c in out["criteria"] if c["name"] == "scope")
    assert scope["pass"] is True
    # Detail should report the 0B total without failing on a non-existent file
    assert "0B" in scope["detail"]
