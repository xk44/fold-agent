"""Tests for derive_macro_focus_bundle and derive_macro_focus_prefocus — pure functions, no Streamlit dependency.

Covers:
- derive_macro_focus_bundle:
  - Returns None when no case_id
  - Returns bundle with case_id always present when derivable
  - Detects report dimension from explicit report_id
  - Detects report dimension from completed pipeline_run (implicit)
  - Detects structure dimension from alphafold linkback
  - Detects artifact dimension from result paths and completed jobs
  - Computes dimensions correctly (1 = case only, 2+ = multi-dimension)
  - Merges report_id from nested result.report.id
  - Merges report_id from payload
  - Deduplicates artifact paths
  - Returns None for empty case_id string
- derive_macro_focus_prefocus:
  - Returns None when bundle is None
  - Returns None when bundle has no case_id
  - Produces prefocus_case_id, pipeline-case-selector, inspect-case-selector always
  - Produces prefocus_report_id when has_report and report_id present
  - Omits prefocus_report_id when has_report True but report_id None
  - Produces structure-job-{case_id} when has_structure and structure_job_id present
  - Produces prefocus_artifact_path when artifact_paths non-empty
  - Full bundle with all dimensions produces all prefocus keys
- Macro focus chip in derive_job_detail_actions:
  - Completed alphafold job with report and structure produces macro_focus chip
  - Completed pipeline_run with report produces macro_focus chip (case+report)
  - Pending pipeline with no derivable dimensions >1 does NOT produce macro_focus chip
  - Macro focus chip data equals the derive_macro_focus_bundle output
- Integration: derive_macro_focus_prefocus from chip data
  - Roundtrip: derive_job_detail_actions → chip → derive_macro_focus_prefocus
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_stream import (
    CHIP_MACRO_FOCUS,
    CHIP_RETRY,
    CHIP_VIEW_ARTIFACTS,
    CHIP_VIEW_REPORT,
    CHIP_VIEW_STRUCTURE,
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
# derive_macro_focus_bundle
# ===========================================================================


class TestDeriveMacroFocusBundleBasic:
    """Basic bundle derivation tests."""

    def test_returns_none_when_no_case_id(self):
        job_card = {
            "source": "api",
            "job_id": "j1",
            "job_type": "pipeline_run",
            "status": "completed",
        }
        result = derive_macro_focus_bundle(job_card)
        assert result is None

    def test_returns_none_when_case_id_empty(self):
        job_card = {
            "source": "api",
            "job_id": "j1",
            "case_id": "",
            "job_type": "pipeline_run",
            "status": "completed",
        }
        result = derive_macro_focus_bundle(job_card)
        assert result is None

    def test_returns_bundle_with_case_only(self):
        api_job = _make_api_job(job_type="unknown_type", status="running", result={})
        card = _make_card_from_api_job(api_job)
        # unknown_type, running status → no report, no structure, no artifacts
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        assert result["case_id"] == "case-1"
        assert result["dimensions"] == 1  # just case

    def test_bundle_has_required_keys(self):
        api_job = _make_api_job()
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        for key in (
            "case_id",
            "report_id",
            "structure_job_id",
            "candidate_id",
            "artifact_paths",
            "job_type",
            "has_report",
            "has_structure",
            "has_artifacts",
            "dimensions",
        ):
            assert key in result


class TestDeriveMacroFocusBundleReportDimension:
    """Report dimension detection."""

    def test_explicit_report_id(self):
        api_job = _make_api_job(result={"status": "completed", "report_id": "rep-42"})
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        assert result["has_report"] is True
        assert result["report_id"] == "rep-42"

    def test_implicit_report_from_completed_pipeline(self):
        api_job = _make_api_job(job_type="pipeline_run", status="completed")
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        assert result["has_report"] is True

    def test_implicit_report_from_report_url(self):
        api_job = _make_api_job(
            status="completed",
            result={"status": "completed", "report_url": "/reports/abc"},
        )
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        assert result["has_report"] is True

    def test_nested_report_id(self):
        api_job = _make_api_job(
            status="completed",
            result={"status": "completed", "report": {"id": "rep-nested"}},
        )
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        assert result["report_id"] == "rep-nested"
        assert result["has_report"] is True

    def test_no_report_for_failed_pipeline(self):
        api_job = _make_api_job(job_type="pipeline_run", status="failed")
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        assert result["has_report"] is False


class TestDeriveMacroFocusBundleStructureDimension:
    """Structure dimension detection via derive_structure_linkback."""

    def test_alphafold_backend_has_structure(self):
        api_job = _make_api_job(job_type="alphafold_backend", case_id="case-1")
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        assert result["has_structure"] is True

    def test_alphafold_structure_has_structure(self):
        api_job = _make_api_job(job_type="alphafold_structure", case_id="case-2")
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        assert result["has_structure"] is True

    def test_pipeline_run_has_no_structure(self):
        api_job = _make_api_job(job_type="pipeline_run")
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        assert result["has_structure"] is False

    def test_structure_job_id_from_result(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            result={"status": "completed", "structure_job_id": "sj-42"},
        )
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        assert result["structure_job_id"] == "sj-42"


class TestDeriveMacroFocusBundleArtifactDimension:
    """Artifact dimension detection."""

    def test_artifact_path_from_result(self):
        api_job = _make_api_job(
            job_type="pipeline_run",
            status="completed",
            result={"status": "completed", "output_file": "/tmp/out.csv"},
        )
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        assert result["has_artifacts"] is True
        assert "/tmp/out.csv" in result["artifact_paths"]

    def test_completed_alphafold_implicit_artifacts(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            status="completed",
        )
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        assert result["has_artifacts"] is True

    def test_deduplicates_artifact_paths(self):
        api_job = _make_api_job(
            job_type="pipeline_run",
            status="completed",
            result={"status": "completed", "output_file": "/tmp/out.csv"},
            payload={"artifact_path": "/tmp/out.csv"},
        )
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        # Same path should appear only once
        assert result["artifact_paths"].count("/tmp/out.csv") == 1


class TestDeriveMacroFocusBundleDimensions:
    """Dimensions counting."""

    def test_case_only_dimensions_1(self):
        api_job = _make_api_job(job_type="unknown_type", status="running")
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        assert result["dimensions"] == 1

    def test_case_plus_report_dimensions_2(self):
        api_job = _make_api_job(
            job_type="pipeline_run",
            status="completed",
            result={"status": "completed", "report_id": "rep-1"},
        )
        card = _make_card_from_api_job(api_job)
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        # case + report (completed pipeline also => implicit artifacts)
        assert result["dimensions"] >= 2

    def test_case_structure_report_dimensions_3plus(self):
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
        result = derive_macro_focus_bundle(card, api_job=api_job)
        assert result is not None
        # case + report + structure + artifacts = 4
        assert result["dimensions"] == 4

    def test_card_only_uses_card_fields(self):
        """When api_job is not provided, job_card fields are used."""
        card = {
            "source": "api",
            "job_id": "j-card-only",
            "job_type": "pipeline_run",
            "case_id": "case-card",
            "status": "completed",
        }
        result = derive_macro_focus_bundle(card)
        assert result is not None
        assert result["case_id"] == "case-card"
        # Completed pipeline => implicit report
        assert result["has_report"] is True


# ===========================================================================
# derive_macro_focus_prefocus
# ===========================================================================


class TestDeriveMacroFocusPrefocus:
    """Session state derivation from macro-focus bundle."""

    def test_returns_none_for_none_bundle(self):
        assert derive_macro_focus_prefocus(None) is None

    def test_returns_none_for_empty_case_id(self):
        bundle = {"case_id": "", "has_report": True, "report_id": "r1"}
        assert derive_macro_focus_prefocus(bundle) is None

    def test_returns_base_prefocus_with_case_only(self):
        bundle = {
            "case_id": "case-1",
            "has_report": False,
            "has_structure": False,
            "has_artifacts": False,
            "report_id": None,
            "structure_job_id": None,
            "artifact_paths": [],
        }
        result = derive_macro_focus_prefocus(bundle)
        assert result is not None
        assert result["prefocus_case_id"] == "case-1"
        assert result["pipeline-case-selector"] == "case-1"
        assert result["inspect-case-selector"] == "case-1"
        assert "prefocus_report_id" not in result
        assert "structure-job-case-1" not in result
        assert "prefocus_artifact_path" not in result

    def test_report_id_included(self):
        bundle = {
            "case_id": "case-5",
            "has_report": True,
            "report_id": "rep-99",
            "has_structure": False,
            "has_artifacts": False,
            "structure_job_id": None,
            "artifact_paths": [],
        }
        result = derive_macro_focus_prefocus(bundle)
        assert result is not None
        assert result["prefocus_report_id"] == "rep-99"

    def test_omits_report_id_when_null(self):
        bundle = {
            "case_id": "case-5",
            "has_report": True,
            "report_id": None,
            "has_structure": False,
            "has_artifacts": False,
            "structure_job_id": None,
            "artifact_paths": [],
        }
        result = derive_macro_focus_prefocus(bundle)
        assert result is not None
        assert "prefocus_report_id" not in result

    def test_structure_job_id_included(self):
        bundle = {
            "case_id": "case-10",
            "has_report": False,
            "has_structure": True,
            "has_artifacts": False,
            "report_id": None,
            "structure_job_id": "sj-42",
            "artifact_paths": [],
        }
        result = derive_macro_focus_prefocus(bundle)
        assert result is not None
        assert result["structure-job-case-10"] == "sj-42"

    def test_omits_structure_job_id_when_null(self):
        bundle = {
            "case_id": "case-10",
            "has_report": False,
            "has_structure": True,
            "has_artifacts": False,
            "report_id": None,
            "structure_job_id": None,
            "artifact_paths": [],
        }
        result = derive_macro_focus_prefocus(bundle)
        assert result is not None
        assert "structure-job-case-10" not in result

    def test_artifact_path_included(self):
        bundle = {
            "case_id": "case-7",
            "has_report": False,
            "has_structure": False,
            "has_artifacts": True,
            "report_id": None,
            "structure_job_id": None,
            "artifact_paths": ["/tmp/out.csv", "/tmp/log.txt"],
        }
        result = derive_macro_focus_prefocus(bundle)
        assert result is not None
        assert result["prefocus_artifact_path"] == "/tmp/out.csv"

    def test_artifact_path_omitted_when_empty(self):
        bundle = {
            "case_id": "case-7",
            "has_report": False,
            "has_structure": False,
            "has_artifacts": False,
            "report_id": None,
            "structure_job_id": None,
            "artifact_paths": [],
        }
        result = derive_macro_focus_prefocus(bundle)
        assert result is not None
        assert "prefocus_artifact_path" not in result

    def test_full_bundle_all_dimensions(self):
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
        assert result["prefocus_case_id"] == "case-full"
        assert result["pipeline-case-selector"] == "case-full"
        assert result["inspect-case-selector"] == "case-full"
        assert result["prefocus_report_id"] == "rep-full"
        assert result["structure-job-case-full"] == "sj-full"
        assert result["prefocus_artifact_path"] == "/tmp/model.cif"

    def test_all_keys_are_strings(self):
        """Verify all returned dict keys are strings (valid session_state keys)."""
        bundle = {
            "case_id": "case-x",
            "has_report": True,
            "report_id": "rep-y",
            "has_structure": True,
            "structure_job_id": "sj-z",
            "has_artifacts": True,
            "artifact_paths": ["/tmp/a.cif"],
        }
        result = derive_macro_focus_prefocus(bundle)
        assert result is not None
        for key in result:
            assert isinstance(key, str), f"Key {key!r} is not a string"


# ===========================================================================
# Macro focus chip in derive_job_detail_actions
# ===========================================================================


class TestMacroFocusChipDerivation:
    """Test that derive_job_detail_actions includes macro_focus chip."""

    def test_completed_alphafold_produces_macro_focus_chip(self):
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
        macro_chips = [c for c in chips if c["action"] == CHIP_MACRO_FOCUS]
        assert len(macro_chips) == 1
        # dimensions should be 4: case + report + structure + artifacts
        assert macro_chips[0]["data"]["dimensions"] == 4
        assert macro_chips[0]["data"]["has_report"] is True
        assert macro_chips[0]["data"]["has_structure"] is True
        assert macro_chips[0]["data"]["has_artifacts"] is True
        assert macro_chips[0]["label"] == "Focus all"
        assert "case + report + structure + artifacts" in macro_chips[0]["description"]

    def test_completed_pipeline_with_report_produces_macro_focus(self):
        api_job = _make_api_job(
            job_type="pipeline_run",
            status="completed",
            result={"status": "completed", "report_id": "rep-2"},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        macro_chips = [c for c in chips if c["action"] == CHIP_MACRO_FOCUS]
        assert len(macro_chips) == 1
        # Should have case + report (and implicit artifacts for completed pipeline)
        assert macro_chips[0]["data"]["dimensions"] >= 2

    def test_pending_job_no_extra_dimensions_no_macro_focus(self):
        """Pending job with no derivable report/structure/artifacts => dimensions=1, no macro_focus."""
        api_job = _make_api_job(job_type="pipeline_run", status="pending")
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        macro_chips = [c for c in chips if c["action"] == CHIP_MACRO_FOCUS]
        assert len(macro_chips) == 0

    def test_card_only_with_case_and_report_derives_macro(self):
        card = {
            "source": "api",
            "job_id": "j-card",
            "job_type": "pipeline_run",
            "case_id": "case-card",
            "status": "completed",
        }
        chips = derive_job_detail_actions(card)
        macro_chips = [c for c in chips if c["action"] == CHIP_MACRO_FOCUS]
        # Even card-only, completed pipeline => has_report=True, so dimensions >= 2
        assert len(macro_chips) == 1

    def test_macro_focus_chip_data_matches_bundle_output(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            status="completed",
            result={
                "status": "completed",
                "report_id": "rep-1",
                "structure_job_id": "sj-42",
            },
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        macro_chips = [c for c in chips if c["action"] == CHIP_MACRO_FOCUS]
        assert len(macro_chips) == 1
        chip_data = macro_chips[0]["data"]

        # Should match derive_macro_focus_bundle output
        bundle = derive_macro_focus_bundle(card, api_job=api_job)
        assert bundle is not None
        assert chip_data["case_id"] == bundle["case_id"]
        assert chip_data["dimensions"] == bundle["dimensions"]
        assert chip_data["has_report"] == bundle["has_report"]
        assert chip_data["has_structure"] == bundle["has_structure"]
        assert chip_data["has_artifacts"] == bundle["has_artifacts"]


class TestMacroFocusRoundtrip:
    """Roundtrip test: job detail actions → chip data → derive_macro_focus_prefocus."""

    def test_roundtrip_alphafold_completed(self):
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

        macro_chips = [c for c in chips if c["action"] == CHIP_MACRO_FOCUS]
        assert len(macro_chips) == 1
        chip_data = macro_chips[0]["data"]

        prefocus = derive_macro_focus_prefocus(chip_data)
        assert prefocus is not None
        assert prefocus["prefocus_case_id"] == "case-1"
        assert prefocus["pipeline-case-selector"] == "case-1"
        assert prefocus["inspect-case-selector"] == "case-1"
        assert prefocus["prefocus_report_id"] == "rep-1"
        assert prefocus["structure-job-case-1"] == "sj-42"
        assert prefocus["prefocus_artifact_path"] == "/tmp/model.cif"

    def test_roundtrip_pipeline_completed(self):
        api_job = _make_api_job(
            job_type="pipeline_run",
            status="completed",
            result={"status": "completed", "report_id": "rep-5"},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)

        macro_chips = [c for c in chips if c["action"] == CHIP_MACRO_FOCUS]
        assert len(macro_chips) == 1
        prefocus = derive_macro_focus_prefocus(macro_chips[0]["data"])
        assert prefocus is not None
        assert prefocus["prefocus_case_id"] == "case-1"
        assert prefocus["prefocus_report_id"] == "rep-5"

    def test_roundtrip_case_only_no_prefocus(self):
        """When bundle has dimensions=1, macro_focus chip is not produced."""
        api_job = _make_api_job(job_type="unknown_type", status="running")
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        macro_chips = [c for c in chips if c["action"] == CHIP_MACRO_FOCUS]
        assert len(macro_chips) == 0


class TestMacroFocusDoesNotBreakExistingChips:
    """Verify existing chip derivation is not affected by macro focus addition."""

    def test_existing_chips_still_produced(self):
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
        actions = [c["action"] for c in chips]
        # Macro focus chip is added
        assert CHIP_MACRO_FOCUS in actions
        # Existing chips still present
        assert CHIP_VIEW_STRUCTURE in actions
        assert CHIP_VIEW_REPORT in actions
        assert CHIP_VIEW_ARTIFACTS in actions

    def test_failed_retryable_job_still_has_retry_chip(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            status="failed",
            attempt=1,
            max_retries=2,
            error="GPU OOM",
            result={
                "status": "failed",
                "report_id": "rep-1",
                "structure_job_id": "sj-42",
            },
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        actions = [c["action"] for c in chips]
        assert CHIP_RETRY in actions
        assert CHIP_VIEW_STRUCTURE in actions
        assert CHIP_MACRO_FOCUS in actions
