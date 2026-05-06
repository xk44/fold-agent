"""Tests for OpenClaw FoldAgent skill pack.

Validates YAML task files parse correctly, reference valid API endpoints,
and that the OPSEC checklist covers required security items.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

SKILL_ROOT = Path(__file__).parent.parent
TASKS_DIR = SKILL_ROOT / "tasks"

EXPECTED_TASK_FILES = [
    "pipeline_run.yaml",
    "candidate_review.yaml",
    "safety_check.yaml",
]

REQUIRED_TASK_FIELDS = {"name", "description", "framework", "safety_gate", "inputs", "steps"}

# Endpoints that must appear across all task files combined.
REQUIRED_ENDPOINTS = [
    "/safety/preflight",
    "/pipeline/run",
    "/candidates",
    "/false-positive-risk",
    "/audit/",
]

# OPSEC checklist items that must be present (substring match).
REQUIRED_OPSEC_ITEMS = [
    "secrets",
    "TLS",
    "privacy",
    "safety gate",
    "audit",
    "access control",
]


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def _all_task_text() -> str:
    return "\n".join(
        (TASKS_DIR / f).read_text() for f in EXPECTED_TASK_FILES if (TASKS_DIR / f).exists()
    )


# ---------------------------------------------------------------------------
# Test 1: All task YAML files exist
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("filename", EXPECTED_TASK_FILES)
def test_task_file_exists(filename: str) -> None:
    assert (TASKS_DIR / filename).exists(), f"Task file not found: {TASKS_DIR / filename}"


# ---------------------------------------------------------------------------
# Test 2: All task YAML files parse without error and are non-empty
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("filename", EXPECTED_TASK_FILES)
def test_task_file_parses(filename: str) -> None:
    path = TASKS_DIR / filename
    if not path.exists():
        pytest.skip(f"{filename} does not exist")
    data = _load_yaml(path)
    assert isinstance(data, dict) and len(data) > 0, f"{filename} parsed to empty/non-dict"


# ---------------------------------------------------------------------------
# Test 3: Task files have required top-level fields
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("filename", EXPECTED_TASK_FILES)
def test_task_file_required_fields(filename: str) -> None:
    path = TASKS_DIR / filename
    if not path.exists():
        pytest.skip(f"{filename} does not exist")
    data = _load_yaml(path)
    missing = REQUIRED_TASK_FIELDS - set(data.keys())
    assert not missing, f"{filename} missing required fields: {missing}"


# ---------------------------------------------------------------------------
# Test 4: Task files reference valid FoldAgent API endpoints
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("endpoint", REQUIRED_ENDPOINTS)
def test_required_endpoints_in_tasks(endpoint: str) -> None:
    combined = _all_task_text()
    assert endpoint in combined, f"Required endpoint '{endpoint}' not found in any task file"


# ---------------------------------------------------------------------------
# Test 5: Each task file includes a safety_disclaimer field
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("filename", EXPECTED_TASK_FILES)
def test_task_file_has_safety_disclaimer(filename: str) -> None:
    path = TASKS_DIR / filename
    if not path.exists():
        pytest.skip(f"{filename} does not exist")
    data = _load_yaml(path)
    assert "safety_disclaimer" in data, f"{filename} missing 'safety_disclaimer' field"
    assert data["safety_disclaimer"].strip(), f"{filename} safety_disclaimer is empty"


# ---------------------------------------------------------------------------
# Test 6: OPSEC checklist covers required security categories
# ---------------------------------------------------------------------------
def test_opsec_checklist_covers_required_items() -> None:
    opsec_path = SKILL_ROOT / "OPSEC_CHECKLIST.md"
    assert opsec_path.exists(), f"OPSEC_CHECKLIST.md not found at {opsec_path}"
    text = opsec_path.read_text().lower()
    missing = [item for item in REQUIRED_OPSEC_ITEMS if item.lower() not in text]
    assert not missing, f"OPSEC checklist missing coverage for: {missing}"
