"""Tests for Hermes NeoVax skill pack.

Validates skill files exist and are non-empty, install.md references correct
paths, and audit_integration.md references valid log_action patterns.
"""
from __future__ import annotations

from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).parent.parent

REQUIRED_SKILL_FILES = [
    "SKILL.md",
    "install.md",
    "emergent_improvements.md",
    "audit_integration.md",
]

# ~/.hermes/skills/ path that install.md must reference
HERMES_INSTALL_PATH = "~/.hermes/skills/"

# log_action patterns that audit_integration.md must document
REQUIRED_LOG_ACTION_PATTERNS = [
    "case.created",
    "pipeline.run.started",
    "report.generated",
    "log_action",
]

# Prohibited self-improvement terms that emergent_improvements.md must cover
REQUIRED_PROHIBITED_TERMS = [
    "safety preflight",
    "SKILL.md",
    "dosing",
    "audit",
]


# ---------------------------------------------------------------------------
# Test 1: All required skill-level files exist and are non-empty
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("filename", REQUIRED_SKILL_FILES)
def test_skill_file_exists_and_non_empty(filename: str) -> None:
    path = SKILL_ROOT / filename
    assert path.exists(), f"Required file not found: {path}"
    assert path.stat().st_size > 0, f"{filename} is empty"


# ---------------------------------------------------------------------------
# Test 2: install.md references the correct ~/.hermes/skills/ install path
# ---------------------------------------------------------------------------
def test_install_md_references_hermes_path() -> None:
    install_md = SKILL_ROOT / "install.md"
    assert install_md.exists(), f"install.md not found at {install_md}"
    text = install_md.read_text()
    assert HERMES_INSTALL_PATH in text, (
        f"install.md does not reference install path '{HERMES_INSTALL_PATH}'"
    )


# ---------------------------------------------------------------------------
# Test 3: install.md references the neovax-hermes skill directory name
# ---------------------------------------------------------------------------
def test_install_md_references_skill_name() -> None:
    text = (SKILL_ROOT / "install.md").read_text()
    assert "neovax-hermes" in text, "install.md does not reference skill name 'neovax-hermes'"


# ---------------------------------------------------------------------------
# Test 4: audit_integration.md references required log_action patterns
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("pattern", REQUIRED_LOG_ACTION_PATTERNS)
def test_audit_integration_references_log_action_pattern(pattern: str) -> None:
    audit_md = SKILL_ROOT / "audit_integration.md"
    assert audit_md.exists(), f"audit_integration.md not found at {audit_md}"
    text = audit_md.read_text()
    assert pattern in text, (
        f"audit_integration.md does not reference log_action pattern '{pattern}'"
    )


# ---------------------------------------------------------------------------
# Test 5: emergent_improvements.md covers required prohibited patterns
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("term", REQUIRED_PROHIBITED_TERMS)
def test_emergent_improvements_covers_prohibited_patterns(term: str) -> None:
    ei_md = SKILL_ROOT / "emergent_improvements.md"
    assert ei_md.exists(), f"emergent_improvements.md not found at {ei_md}"
    text = ei_md.read_text().lower()
    assert term.lower() in text, (
        f"emergent_improvements.md does not cover prohibited pattern '{term}'"
    )
