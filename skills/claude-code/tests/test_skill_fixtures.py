"""Tests for Claude Code NeoVax skill fixtures.

Validates that all skill markdown files exist, are non-empty, have required
frontmatter fields, and reference valid NeoVax API endpoints.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

SKILL_ROOT = Path(__file__).parent.parent
ACTIONS_DIR = SKILL_ROOT / "actions"

REQUIRED_SKILL_FRONTMATTER = {
    "name",
    "description",
    "version",
    "license",
    "framework",
    "tags",
}

REQUIRED_ACTION_FRONTMATTER = {
    "name",
    "description",
    "action_type",
    "primary_endpoint",
    "framework",
}

EXPECTED_ACTION_FILES = [
    "create_case.md",
    "run_pipeline.md",
    "review_candidates.md",
    "generate_report.md",
    "check_safety.md",
]

# Endpoints that must be referenced across all action files combined.
REQUIRED_ENDPOINTS = [
    "/cases",
    "/cases/{case_id}/pipeline/run",
    "/cases/{case_id}/candidates",
    "/cases/{case_id}/reports/candidate-review",
    "/safety/preflight",
]


def _extract_frontmatter(path: Path) -> dict:
    """Parse YAML frontmatter delimited by '---' from a markdown file."""
    text = path.read_text()
    parts = text.split("---")
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def _all_action_text() -> str:
    """Return combined text of all action markdown files."""
    return "\n".join(
        (ACTIONS_DIR / f).read_text()
        for f in EXPECTED_ACTION_FILES
        if (ACTIONS_DIR / f).exists()
    )


# ---------------------------------------------------------------------------
# Test 1: SKILL.md exists and is non-empty
# ---------------------------------------------------------------------------
def test_skill_md_exists_and_non_empty() -> None:
    skill_md = SKILL_ROOT / "SKILL.md"
    assert skill_md.exists(), f"SKILL.md not found at {skill_md}"
    assert skill_md.stat().st_size > 0, "SKILL.md is empty"


# ---------------------------------------------------------------------------
# Test 2: SKILL.md frontmatter has all required fields
# ---------------------------------------------------------------------------
def test_skill_md_required_frontmatter() -> None:
    skill_md = SKILL_ROOT / "SKILL.md"
    fm = _extract_frontmatter(skill_md)
    missing = REQUIRED_SKILL_FRONTMATTER - set(fm.keys())
    assert not missing, f"SKILL.md missing frontmatter fields: {missing}"


# ---------------------------------------------------------------------------
# Test 3: All expected action files exist
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("filename", EXPECTED_ACTION_FILES)
def test_action_file_exists(filename: str) -> None:
    action_file = ACTIONS_DIR / filename
    assert action_file.exists(), f"Action file not found: {action_file}"


# ---------------------------------------------------------------------------
# Test 4: All action files are non-empty
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("filename", EXPECTED_ACTION_FILES)
def test_action_file_non_empty(filename: str) -> None:
    action_file = ACTIONS_DIR / filename
    if action_file.exists():
        assert action_file.stat().st_size > 0, f"{filename} is empty"


# ---------------------------------------------------------------------------
# Test 5: Each action file has required frontmatter
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("filename", EXPECTED_ACTION_FILES)
def test_action_file_frontmatter(filename: str) -> None:
    action_file = ACTIONS_DIR / filename
    if not action_file.exists():
        pytest.skip(f"{filename} does not exist")
    fm = _extract_frontmatter(action_file)
    missing = REQUIRED_ACTION_FRONTMATTER - set(fm.keys())
    assert not missing, f"{filename} missing frontmatter fields: {missing}"


# ---------------------------------------------------------------------------
# Test 6: Action files reference valid NeoVax API endpoints
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("endpoint", REQUIRED_ENDPOINTS)
def test_required_endpoints_referenced(endpoint: str) -> None:
    combined = _all_action_text()
    assert endpoint in combined, (
        f"Required endpoint '{endpoint}' not referenced in any action file"
    )


# ---------------------------------------------------------------------------
# Test 7: SKILL.md tags field is a non-empty list including 'neovax-agent'
# ---------------------------------------------------------------------------
def test_skill_md_tags_include_neovax_agent() -> None:
    fm = _extract_frontmatter(SKILL_ROOT / "SKILL.md")
    tags = fm.get("tags", [])
    assert isinstance(tags, list) and len(tags) > 0, "tags must be a non-empty list"
    assert "neovax-agent" in tags, "tags must include 'neovax-agent'"


# ---------------------------------------------------------------------------
# Test 8: SKILL.md action table references all action files
# ---------------------------------------------------------------------------
def test_skill_md_references_all_actions() -> None:
    skill_md = SKILL_ROOT / "SKILL.md"
    text = skill_md.read_text()
    for filename in EXPECTED_ACTION_FILES:
        stem = filename.replace(".md", "")
        assert stem in text, (
            f"SKILL.md does not reference action '{stem}'"
        )
