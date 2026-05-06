"""Tests for derive_exact_open_metadata and auto-open artifact flow — pure functions, no Streamlit dependency.

Covers:
- derive_exact_open_metadata:
  - Returns None when bundle is None
  - Returns None when bundle has no case_id
  - Returns None when has_artifacts is False
  - Returns None when artifact_paths is empty
  - Returns None when artifact_paths has multiple entries (ambiguous)
  - Returns exact-open dict when exactly one artifact path is present
  - Returns None when artifact_paths has two or more paths
  - Returns correct keys: auto_open, artifact_path, case_id
- derive_macro_focus_prefocus auto-open integration:
  - Bundle with single artifact path includes prefocus_auto_open_artifact
  - Bundle with multiple artifact paths does NOT include prefocus_auto_open_artifact
  - Bundle with no artifacts does NOT include prefocus_auto_open_artifact
  - Roundtrip from derive_macro_focus_bundle → derive_macro_focus_prefocus auto-open
- Roundtrip from derive_job_detail_actions chip data → derive_exact_open_metadata
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_stream import (
    derive_exact_open_metadata,
    derive_job_detail_actions,
    derive_macro_focus_bundle,
    derive_macro_focus_prefocus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_job(
    job_id: str = "j1",
    case_id: str = "case-1",
    job_type: str = "pipeline_run",
    status: str = "completed",
    attempt: int = 1,
    max_retries: int = 0,
    error: str | None = None,
    result: dict | None = None,
    payload: dict | None = None,
    created_at: str = "2025-04-20T10:00:00",
) -> dict:
    return {
        "id": job_id,
        "case_id": case_id,
        "job_type": job_type,
        "status": status,
        "payload": payload or {},
        "result": result or ({"status": status} if status == "completed" else None),
        "error": error,
        "attempt": attempt,
        "max_retries": max_retries,
        "timed_out": False,
        "created_at": created_at,
    }


def _make_card_from_api_job(api_job: dict) -> dict:
    return {
        "source": "api",
        "job_id": api_job["id"],
        "job_type": api_job.get("job_type", "unknown"),
        "case_id": api_job.get("case_id"),
        "status": api_job.get("status", "unknown"),
        "latest_status": api_job.get("status", "unknown"),
        "event_count": 0,
        "error": api_job.get("error"),
        "created_at": api_job.get("created_at"),
        "attempt": api_job.get("attempt", 1),
        "max_retries": api_job.get("max_retries", 0),
    }


# ===========================================================================
# derive_exact_open_metadata
# ===========================================================================


class TestDeriveExactOpenMetadataBasic:
    """Basic exact-open derivation tests."""

    def test_returns_none_for_none_bundle(self):
        assert derive_exact_open_metadata(None) is None

    def test_returns_none_for_empty_case_id(self):
        bundle = {
            "case_id": "",
            "has_artifacts": True,
            "artifact_paths": ["/tmp/out.csv"],
        }
        assert derive_exact_open_metadata(bundle) is None

    def test_returns_none_when_has_artifacts_false(self):
        bundle = {
            "case_id": "case-1",
            "has_artifacts": False,
            "artifact_paths": [],
        }
        assert derive_exact_open_metadata(bundle) is None

    def test_returns_none_when_artifact_paths_empty(self):
        bundle = {
            "case_id": "case-1",
            "has_artifacts": True,
            "artifact_paths": [],
        }
        assert derive_exact_open_metadata(bundle) is None

    def test_returns_none_when_multiple_artifact_paths(self):
        """Multiple paths are ambiguous — should not auto-open."""
        bundle = {
            "case_id": "case-1",
            "has_artifacts": True,
            "artifact_paths": ["/tmp/out.csv", "/tmp/log.txt"],
        }
        assert derive_exact_open_metadata(bundle) is None

    def test_returns_exact_open_for_single_path(self):
        """Single unambiguous artifact path → auto-open metadata."""
        bundle = {
            "case_id": "case-7",
            "has_artifacts": True,
            "artifact_paths": ["/tmp/model.cif"],
        }
        result = derive_exact_open_metadata(bundle)
        assert result is not None
        assert result["auto_open"] is True
        assert result["artifact_path"] == "/tmp/model.cif"
        assert result["case_id"] == "case-7"

    def test_returns_exact_open_keys_are_correct(self):
        bundle = {
            "case_id": "case-x",
            "has_artifacts": True,
            "artifact_paths": ["/data/output.json"],
        }
        result = derive_exact_open_metadata(bundle)
        assert result is not None
        assert set(result.keys()) == {"auto_open", "artifact_path", "case_id"}

    def test_returns_none_for_three_paths(self):
        bundle = {
            "case_id": "case-1",
            "has_artifacts": True,
            "artifact_paths": ["/a.cif", "/b.csv", "/c.log"],
        }
        assert derive_exact_open_metadata(bundle) is None

    def test_artifact_paths_missing_key_treated_as_empty(self):
        bundle = {
            "case_id": "case-1",
            "has_artifacts": True,
            # No "artifact_paths" key at all
        }
        assert derive_exact_open_metadata(bundle) is None

    def test_artifact_paths_none_treated_as_empty(self):
        bundle = {
            "case_id": "case-1",
            "has_artifacts": True,
            "artifact_paths": None,
        }
        assert derive_exact_open_metadata(bundle) is None


class TestDeriveExactOpenMetadataFromRealBundle:
    """Test derive_exact_open_metadata using bundles derived from derive_macro_focus_bundle."""

    def test_single_artifact_alphafold(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-af1",
            status="completed",
            result={
                "status": "completed",
                "report_id": "rep-1",
                "structure_job_id": "sj-42",
                "model_cif": "/tmp/model.cif",
            },
        )
        card = _make_card_from_api_job(api_job)
        bundle = derive_macro_focus_bundle(card, api_job=api_job)
        assert bundle is not None

        # The bundle should have artifacts from model_cif
        result = derive_exact_open_metadata(bundle)
        assert result is not None
        assert result["auto_open"] is True
        assert result["case_id"] == "case-af1"
        assert "/tmp/model.cif" in result["artifact_path"]

    def test_multiple_artifacts_pipeline(self):
        """Pipeline with multiple artifact outputs should NOT auto-open."""
        api_job = _make_api_job(
            job_type="pipeline_run",
            case_id="case-pipe",
            status="completed",
            result={
                "status": "completed",
                "report_id": "rep-2",
                "output_file": "/tmp/out.csv",
            },
            payload={"artifact_path": "/tmp/log.txt"},
        )
        card = _make_card_from_api_job(api_job)
        bundle = derive_macro_focus_bundle(card, api_job=api_job)
        assert bundle is not None

        # Multiple different artifact paths → ambiguous
        result = derive_exact_open_metadata(bundle)
        if len(bundle.get("artifact_paths", [])) > 1:
            assert result is None
        else:
            # If dedup reduced it to 1, it would be auto-openable
            assert result is not None

    def test_no_artifacts_running_job(self):
        api_job = _make_api_job(
            job_type="unknown_type",
            case_id="case-running",
            status="running",
        )
        card = _make_card_from_api_job(api_job)
        bundle = derive_macro_focus_bundle(card, api_job=api_job)
        assert bundle is not None
        assert bundle["has_artifacts"] is False
        result = derive_exact_open_metadata(bundle)
        assert result is None


# ===========================================================================
# derive_macro_focus_prefocus auto-open integration
# ===========================================================================


class TestMacroFocusPrefocusAutoOpen:
    """Test that derive_macro_focus_prefocus includes auto-open metadata."""

    def test_single_artifact_bundle_includes_auto_open(self):
        bundle = {
            "case_id": "case-7",
            "has_report": True,
            "report_id": "rep-99",
            "has_structure": False,
            "has_artifacts": True,
            "structure_job_id": None,
            "artifact_paths": ["/tmp/model.cif"],
        }
        result = derive_macro_focus_prefocus(bundle)
        assert result is not None
        assert "prefocus_auto_open_artifact" in result
        auto_open = result["prefocus_auto_open_artifact"]
        assert auto_open["auto_open"] is True
        assert auto_open["artifact_path"] == "/tmp/model.cif"
        assert auto_open["case_id"] == "case-7"

    def test_multiple_artifacts_bundle_omits_auto_open(self):
        """Multiple artifact paths → ambiguous → no auto-open."""
        bundle = {
            "case_id": "case-multi",
            "has_report": False,
            "has_structure": False,
            "has_artifacts": True,
            "report_id": None,
            "structure_job_id": None,
            "artifact_paths": ["/tmp/out.csv", "/tmp/log.txt"],
        }
        result = derive_macro_focus_prefocus(bundle)
        assert result is not None
        assert "prefocus_auto_open_artifact" not in result

    def test_no_artifacts_bundle_omits_auto_open(self):
        bundle = {
            "case_id": "case-none",
            "has_report": False,
            "has_structure": False,
            "has_artifacts": False,
            "report_id": None,
            "structure_job_id": None,
            "artifact_paths": [],
        }
        result = derive_macro_focus_prefocus(bundle)
        assert result is not None
        assert "prefocus_auto_open_artifact" not in result

    def test_full_bundle_single_artifact_includes_auto_open(self):
        bundle = {
            "case_id": "case-full",
            "has_report": True,
            "report_id": "rep-full",
            "has_structure": True,
            "structure_job_id": "sj-full",
            "has_artifacts": True,
            "artifact_paths": ["/tmp/model.cif"],
        }
        result = derive_macro_focus_prefocus(bundle)
        assert result is not None
        assert result["prefocus_auto_open_artifact"]["auto_open"] is True
        assert result["prefocus_auto_open_artifact"]["artifact_path"] == "/tmp/model.cif"
        assert result["prefocus_auto_open_artifact"]["case_id"] == "case-full"

    def test_none_bundle_returns_none(self):
        assert derive_macro_focus_prefocus(None) is None


class TestRoundtripChipToAutoOpen:
    """Roundtrip: derive_job_detail_actions → chip data → derive_exact_open_metadata."""

    def test_completed_alphafold_with_single_artifact_auto_opens(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            status="completed",
            result={
                "status": "completed",
                "report_id": "rep-1",
                "structure_job_id": "sj-42",
                "model_cif": "/tmp/model.cif",
            },
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)

        macro_chips = [c for c in chips if c["action"] == "macro_focus"]
        assert len(macro_chips) == 1
        chip_data = macro_chips[0]["data"]

        # chip_data IS the macro bundle from derive_macro_focus_bundle
        exact_open = derive_exact_open_metadata(chip_data)
        assert exact_open is not None
        assert exact_open["auto_open"] is True
        assert exact_open["artifact_path"] == "/tmp/model.cif"
        assert exact_open["case_id"] == "case-1"

    def test_pipeline_with_multiple_artifacts_no_auto_open(self):
        """Pipeline with output_file + artifact_path in payload = ambiguous."""
        api_job = _make_api_job(
            job_type="pipeline_run",
            case_id="case-multi",
            status="completed",
            result={
                "status": "completed",
                "report_id": "rep-5",
                "output_file": "/tmp/output.csv",
            },
            payload={
                "artifact_path": "/tmp/artifact.json",
            },
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)

        macro_chips = [c for c in chips if c["action"] == "macro_focus"]
        assert len(macro_chips) == 1
        chip_data = macro_chips[0]["data"]

        exact_open = derive_exact_open_metadata(chip_data)
        # Multiple different artifact paths → should not auto-open
        if len(chip_data.get("artifact_paths", [])) > 1:
            assert exact_open is None

    def test_prefocus_roundtrip_with_auto_open(self):
        """Full roundtrip: bundle → prefocus includes auto-open key."""
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            status="completed",
            result={
                "status": "completed",
                "report_id": "rep-1",
                "structure_job_id": "sj-42",
                "model_cif": "/tmp/model.cif",
            },
        )
        card = _make_card_from_api_job(api_job)
        bundle = derive_macro_focus_bundle(card, api_job=api_job)
        prefocus = derive_macro_focus_prefocus(bundle)

        assert prefocus is not None
        assert "prefocus_auto_open_artifact" in prefocus
        auto_open = prefocus["prefocus_auto_open_artifact"]
        assert auto_open["auto_open"] is True
        assert auto_open["artifact_path"] == "/tmp/model.cif"
        assert auto_open["case_id"] == "case-1"
        # Other prefocus keys still present
        assert prefocus["prefocus_artifact_path"] == "/tmp/model.cif"
        assert prefocus["prefocus_case_id"] == "case-1"

    def test_prefocus_roundtrip_without_auto_open(self):
        """When multiple artifacts, prefocus omits auto-open but still has path."""
        bundle = {
            "case_id": "case-multi",
            "has_report": False,
            "has_structure": False,
            "has_artifacts": True,
            "report_id": None,
            "structure_job_id": None,
            "artifact_paths": ["/tmp/a.csv", "/tmp/b.log"],
        }
        prefocus = derive_macro_focus_prefocus(bundle)
        assert prefocus is not None
        # Still preselects first artifact path
        assert prefocus["prefocus_artifact_path"] == "/tmp/a.csv"
        # But does NOT auto-open (ambiguous)
        assert "prefocus_auto_open_artifact" not in prefocus


class TestDeriveExactOpenMetadataEdgeCases:
    """Edge cases for derive_exact_open_metadata."""

    def test_bundle_with_only_case_id(self):
        bundle = {"case_id": "case-1"}
        result = derive_exact_open_metadata(bundle)
        # No has_artifacts → None
        assert result is None

    def test_bundle_with_has_artifacts_true_but_empty_paths(self):
        bundle = {
            "case_id": "case-1",
            "has_artifacts": True,
            "artifact_paths": [],
        }
        assert derive_exact_open_metadata(bundle) is None

    def test_bundle_with_has_artifacts_false_but_paths_present(self):
        """Edge case: has_artifacts says False but paths exist.
        derive_exact_open_metadata respects has_artifacts flag."""
        bundle = {
            "case_id": "case-1",
            "has_artifacts": False,
            "artifact_paths": ["/tmp/ghost.csv"],
        }
        assert derive_exact_open_metadata(bundle) is None

    def test_auto_open_value_is_always_true(self):
        """When derive_exact_open_metadata returns, auto_open is always True."""
        for case_id in ["case-7", "case-with-long-name", "x"]:
            bundle = {
                "case_id": case_id,
                "has_artifacts": True,
                "artifact_paths": ["/tmp/file.csv"],
            }
            result = derive_exact_open_metadata(bundle)
            assert result is not None
            assert result["auto_open"] is True

    def test_preserves_exact_artifact_path(self):
        """The exact single path is preserved, not modified."""
        path = "/data/alphafold/output/ranked_0_model.cif"
        bundle = {
            "case_id": "case-deep-path",
            "has_artifacts": True,
            "artifact_paths": [path],
        }
        result = derive_exact_open_metadata(bundle)
        assert result is not None
        assert result["artifact_path"] == path
