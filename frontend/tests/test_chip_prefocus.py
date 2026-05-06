"""Tests for derive_chip_prefocus — pure function, no Streamlit dependency.

Covers:
- view_report chip: derives prefocus_report_id when available, case-switch keys
- view_artifacts chip: derives prefocus_artifact_path when available, case-switch keys
- view_structure chip: derives structure-job key, case-switch keys
- No case_id → returns None
- Unknown action → returns None
- Missing / empty data fields → graceful degradation
- Chip with report_id=None omits prefocus_report_id
- Chip with empty artifact_paths omits prefocus_artifact_path
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_stream import (
    CHIP_RETRY,
    CHIP_VIEW_ARTIFACTS,
    CHIP_VIEW_REPORT,
    CHIP_VIEW_STRUCTURE,
    derive_chip_prefocus,
)

# ---------------------------------------------------------------------------
# view_report chip
# ---------------------------------------------------------------------------


class TestDeriveChipPrefocusViewReport:
    """view_report chip derives report and case prefocus keys."""

    def test_report_id_present(self):
        chip = {
            "action": CHIP_VIEW_REPORT,
            "label": "View report",
            "enabled": True,
            "data": {
                "job_id": "j1",
                "case_id": "case-42",
                "report_id": "rep-99",
                "job_type": "pipeline_run",
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is not None
        assert result["prefocus_report_id"] == "rep-99"
        assert result["prefocus_case_id"] == "case-42"
        assert result["pipeline-case-selector"] == "case-42"
        assert result["inspect-case-selector"] == "case-42"

    def test_report_id_none_omits_prefocus_key(self):
        chip = {
            "action": CHIP_VIEW_REPORT,
            "label": "View report",
            "enabled": True,
            "data": {
                "job_id": "j1",
                "case_id": "case-5",
                "report_id": None,
                "job_type": "pipeline_run",
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is not None
        assert "prefocus_report_id" not in result
        assert result["prefocus_case_id"] == "case-5"

    def test_report_id_missing_omits_prefocus_key(self):
        chip = {
            "action": CHIP_VIEW_REPORT,
            "label": "View report",
            "enabled": True,
            "data": {
                "job_id": "j1",
                "case_id": "case-5",
                "job_type": "pipeline_run",
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is not None
        assert "prefocus_report_id" not in result

    def test_no_case_id_returns_none(self):
        chip = {
            "action": CHIP_VIEW_REPORT,
            "label": "View report",
            "enabled": True,
            "data": {
                "job_id": "j1",
                "report_id": "rep-1",
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is None

    def test_empty_case_id_returns_none(self):
        chip = {
            "action": CHIP_VIEW_REPORT,
            "label": "View report",
            "enabled": True,
            "data": {
                "job_id": "j1",
                "case_id": "",
                "report_id": "rep-1",
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is None

    def test_no_data_returns_none(self):
        chip = {
            "action": CHIP_VIEW_REPORT,
            "label": "View report",
            "enabled": True,
            "data": None,
        }
        result = derive_chip_prefocus(chip)
        # No case_id derivable → None
        assert result is None


# ---------------------------------------------------------------------------
# view_artifacts chip
# ---------------------------------------------------------------------------


class TestDeriveChipPrefocusViewArtifacts:
    """view_artifacts chip derives artifact path and case prefocus keys."""

    def test_artifact_paths_present(self):
        chip = {
            "action": CHIP_VIEW_ARTIFACTS,
            "label": "View artifacts",
            "enabled": True,
            "data": {
                "job_id": "j2",
                "case_id": "case-7",
                "artifact_paths": ["/tmp/out.csv", "/tmp/log.txt"],
                "job_type": "pipeline_run",
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is not None
        assert result["prefocus_artifact_path"] == "/tmp/out.csv"
        assert result["prefocus_case_id"] == "case-7"
        assert result["pipeline-case-selector"] == "case-7"
        assert result["inspect-case-selector"] == "case-7"

    def test_empty_artifact_paths_omits_prefocus_path(self):
        chip = {
            "action": CHIP_VIEW_ARTIFACTS,
            "label": "View artifacts",
            "enabled": True,
            "data": {
                "job_id": "j2",
                "case_id": "case-7",
                "artifact_paths": [],
                "job_type": "pipeline_run",
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is not None
        assert "prefocus_artifact_path" not in result

    def test_missing_artifact_paths_omits_prefocus_path(self):
        chip = {
            "action": CHIP_VIEW_ARTIFACTS,
            "label": "View artifacts",
            "enabled": True,
            "data": {
                "job_id": "j2",
                "case_id": "case-7",
                "job_type": "pipeline_run",
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is not None
        assert "prefocus_artifact_path" not in result

    def test_no_case_id_returns_none(self):
        chip = {
            "action": CHIP_VIEW_ARTIFACTS,
            "label": "View artifacts",
            "enabled": True,
            "data": {
                "job_id": "j2",
                "artifact_paths": ["/tmp/out.csv"],
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is None

    def test_single_artifact_path(self):
        chip = {
            "action": CHIP_VIEW_ARTIFACTS,
            "label": "View artifacts",
            "enabled": True,
            "data": {
                "job_id": "j2",
                "case_id": "case-1",
                "artifact_paths": ["/tmp/model.cif"],
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is not None
        assert result["prefocus_artifact_path"] == "/tmp/model.cif"


# ---------------------------------------------------------------------------
# view_structure chip
# ---------------------------------------------------------------------------


class TestDeriveChipPrefocusViewStructure:
    """view_structure chip derives structure job and case prefocus keys."""

    def test_with_structure_job_id(self):
        chip = {
            "action": CHIP_VIEW_STRUCTURE,
            "label": "View structure",
            "enabled": True,
            "data": {
                "job_id": "j3",
                "case_id": "case-10",
                "structure_job_id": "sj-42",
                "candidate_id": "cand-1",
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is not None
        assert result["structure-job-case-10"] == "sj-42"
        assert result["pipeline-case-selector"] == "case-10"
        assert result["prefocus_case_id"] == "case-10"

    def test_without_structure_job_id(self):
        chip = {
            "action": CHIP_VIEW_STRUCTURE,
            "label": "View structure",
            "enabled": True,
            "data": {
                "job_id": "j3",
                "case_id": "case-10",
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is not None
        assert "structure-job-case-10" not in result
        assert result["pipeline-case-selector"] == "case-10"

    def test_no_case_id_returns_none(self):
        chip = {
            "action": CHIP_VIEW_STRUCTURE,
            "label": "View structure",
            "enabled": True,
            "data": {
                "job_id": "j3",
                "structure_job_id": "sj-42",
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is None


# ---------------------------------------------------------------------------
# Edge cases and unsupported chips
# ---------------------------------------------------------------------------


class TestDeriveChipPrefocusEdgeCases:
    """Edge cases: unknown actions, missing fields, empty chips."""

    def test_retry_chip_returns_none(self):
        chip = {
            "action": CHIP_RETRY,
            "label": "Retry",
            "enabled": True,
            "data": {
                "job_id": "j1",
                "attempt": 1,
                "max_retries": 2,
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is None

    def test_unknown_action_returns_none(self):
        chip = {
            "action": "custom_action",
            "label": "Custom",
            "enabled": True,
            "data": {"case_id": "c1"},
        }
        result = derive_chip_prefocus(chip)
        assert result is None

    def test_empty_action_returns_none(self):
        chip = {
            "action": "",
            "label": "None",
            "enabled": True,
            "data": {"case_id": "c1"},
        }
        result = derive_chip_prefocus(chip)
        assert result is None

    def test_chip_without_data_key(self):
        chip = {
            "action": CHIP_VIEW_REPORT,
            "label": "View report",
            "enabled": True,
        }
        result = derive_chip_prefocus(chip)
        # data defaults to {} → no case_id → None
        assert result is None

    def test_prefocus_keys_are_consumable_by_session_state(self):
        """Verify that the returned dict has string keys (valid session_state keys)."""
        chip = {
            "action": CHIP_VIEW_REPORT,
            "label": "View report",
            "enabled": True,
            "data": {
                "case_id": "case-x",
                "report_id": "rep-y",
            },
        }
        result = derive_chip_prefocus(chip)
        assert result is not None
        for key in result:
            assert isinstance(key, str), f"Key {key!r} is not a string"
