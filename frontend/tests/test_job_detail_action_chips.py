"""Tests for job-detail action chip helpers — pure functions, no Streamlit dependency.

Covers:
- derive_job_detail_actions: derives available action chips from a job card + API payload
- format_action_chips: renders chips as a compact text line
- format_action_chip_summary: renders chips as a multi-line detail summary
- Integration with derive_job_detail: action_chips field populated automatically
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
    derive_job_detail,
    derive_job_detail_actions,
    format_action_chip_summary,
    format_action_chips,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_api_job(
    job_id: str = "j1",
    case_id: str = "c1",
    job_type: str = "pipeline_run",
    status: str = "completed",
    attempt: int = 1,
    max_retries: int = 0,
    error: str | None = None,
    timed_out: bool = False,
    result: dict | None = None,
    payload: dict | None = None,
    created_at: str = "2025-04-20T09:55:00",
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
        "timed_out": timed_out,
        "created_at": created_at,
    }


def _make_card_from_api_job(api_job: dict) -> dict:
    """Derive a job card dict from an API job, mimicking derive_job_status_cards."""
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


# ---------------------------------------------------------------------------
# derive_job_detail_actions — retry chip
# ---------------------------------------------------------------------------


class TestDeriveRetryChip:
    """Retry chip appears when the job is retry-eligible."""

    def test_failed_job_with_retries_produces_retry_chip(self):
        api_job = _make_api_job(status="failed", attempt=1, max_retries=2)
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        retry_chips = [c for c in chips if c["action"] == CHIP_RETRY]
        assert len(retry_chips) == 1
        assert retry_chips[0]["enabled"] is True
        assert retry_chips[0]["data"]["job_id"] == "j1"
        assert "2 attempt(s) remaining" in retry_chips[0]["description"]

    def test_timed_out_job_with_retries_produces_retry_chip(self):
        api_job = _make_api_job(status="timed_out", attempt=1, max_retries=3, timed_out=True)
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        retry_chips = [c for c in chips if c["action"] == CHIP_RETRY]
        assert len(retry_chips) == 1

    def test_completed_job_no_retry_chip(self):
        api_job = _make_api_job(status="completed", attempt=1, max_retries=0)
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        retry_chips = [c for c in chips if c["action"] == CHIP_RETRY]
        assert len(retry_chips) == 0

    def test_running_job_no_retry_chip(self):
        api_job = _make_api_job(status="running")
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        retry_chips = [c for c in chips if c["action"] == CHIP_RETRY]
        assert len(retry_chips) == 0

    def test_exhausted_retry_budget_no_retry_chip(self):
        api_job = _make_api_job(status="failed", attempt=3, max_retries=2)
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        retry_chips = [c for c in chips if c["action"] == CHIP_RETRY]
        assert len(retry_chips) == 0

    def test_event_sourced_card_no_retry_chip(self):
        """Event-sourced cards have no job_id — can't be retried."""
        card = {
            "source": "event",
            "job_id": None,
            "job_type": "pipeline",
            "case_id": "c1",
            "status": "failed",
        }
        chips = derive_job_detail_actions(card)
        retry_chips = [c for c in chips if c["action"] == CHIP_RETRY]
        assert len(retry_chips) == 0

    def test_retry_chip_data_has_attempt_info(self):
        api_job = _make_api_job(status="failed", attempt=1, max_retries=3)
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        retry_chip = [c for c in chips if c["action"] == CHIP_RETRY][0]
        assert retry_chip["data"]["attempt"] == 1
        assert retry_chip["data"]["max_retries"] == 3


# ---------------------------------------------------------------------------
# derive_job_detail_actions — view_structure chip
# ---------------------------------------------------------------------------


class TestDeriveViewStructureChip:
    """View structure chip appears when derive_structure_linkback returns a result."""

    def test_alphafold_backend_produces_structure_chip(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        struct_chips = [c for c in chips if c["action"] == CHIP_VIEW_STRUCTURE]
        assert len(struct_chips) == 1
        assert struct_chips[0]["data"]["case_id"] == "case-1"
        assert struct_chips[0]["label"] == "View AlphaFold structure"

    def test_alphafold_structure_produces_structure_chip(self):
        api_job = _make_api_job(
            job_type="alphafold_structure",
            case_id="case-2",
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        struct_chips = [c for c in chips if c["action"] == CHIP_VIEW_STRUCTURE]
        assert len(struct_chips) == 1

    def test_pipeline_run_no_structure_chip(self):
        api_job = _make_api_job(job_type="pipeline_run", case_id="case-1")
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        struct_chips = [c for c in chips if c["action"] == CHIP_VIEW_STRUCTURE]
        assert len(struct_chips) == 0

    def test_structure_chip_carries_structure_job_id(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            result={"status": "completed", "structure_job_id": "sj-42"},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        struct_chip = [c for c in chips if c["action"] == CHIP_VIEW_STRUCTURE][0]
        assert struct_chip["data"]["structure_job_id"] == "sj-42"

    def test_structure_chip_candidate_id(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            payload={"candidate_id": "cand-1", "sequence": "MALWMR"},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        struct_chip = [c for c in chips if c["action"] == CHIP_VIEW_STRUCTURE][0]
        assert struct_chip["data"]["candidate_id"] == "cand-1"


# ---------------------------------------------------------------------------
# derive_job_detail_actions — view_report chip
# ---------------------------------------------------------------------------


class TestDeriveViewReportChip:
    """View report chip appears when report is derivable from payload/result."""

    def test_explicit_report_id_in_result(self):
        api_job = _make_api_job(
            job_type="pipeline_run",
            status="completed",
            result={"status": "completed", "report_id": "rep-123"},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        report_chips = [c for c in chips if c["action"] == CHIP_VIEW_REPORT]
        assert len(report_chips) == 1
        assert report_chips[0]["data"]["report_id"] == "rep-123"
        assert "rep-123" in report_chips[0]["description"]

    def test_report_id_in_payload(self):
        api_job = _make_api_job(
            job_type="pipeline_run",
            status="completed",
            payload={"report_id": "rep-456"},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        report_chips = [c for c in chips if c["action"] == CHIP_VIEW_REPORT]
        assert len(report_chips) == 1
        assert report_chips[0]["data"]["report_id"] == "rep-456"

    def test_nested_report_id_in_result(self):
        api_job = _make_api_job(
            job_type="pipeline_run",
            status="completed",
            result={"status": "completed", "report": {"id": "rep-nested"}},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        report_chips = [c for c in chips if c["action"] == CHIP_VIEW_REPORT]
        assert len(report_chips) == 1
        assert report_chips[0]["data"]["report_id"] == "rep-nested"

    def test_completed_pipeline_generates_report_chip(self):
        """Completed pipeline runs implicitly produce reports."""
        api_job = _make_api_job(job_type="pipeline_run", status="completed")
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        report_chips = [c for c in chips if c["action"] == CHIP_VIEW_REPORT]
        assert len(report_chips) == 1
        # No explicit report_id, but still a chip
        assert report_chips[0]["data"]["report_id"] is None

    def test_failed_pipeline_no_report_chip(self):
        """Failed pipeline does not implicitly produce a report chip."""
        api_job = _make_api_job(job_type="pipeline_run", status="failed")
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        report_chips = [c for c in chips if c["action"] == CHIP_VIEW_REPORT]
        assert len(report_chips) == 0

    def test_report_url_in_result(self):
        api_job = _make_api_job(
            job_type="pipeline_run",
            status="completed",
            result={"status": "completed", "report_url": "/reports/abc"},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        report_chips = [c for c in chips if c["action"] == CHIP_VIEW_REPORT]
        assert len(report_chips) == 1

    def test_non_pipeline_no_implicit_report(self):
        """Report generation type without completed status should not produce a chip."""
        api_job = _make_api_job(job_type="report_generation", status="running")
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        report_chips = [c for c in chips if c["action"] == CHIP_VIEW_REPORT]
        assert len(report_chips) == 0


# ---------------------------------------------------------------------------
# derive_job_detail_actions — view_artifacts chip
# ---------------------------------------------------------------------------


class TestDeriveViewArtifactsChip:
    """View artifacts chip appears when artifact paths are derivable or job type produces artifacts."""

    def test_result_with_output_file(self):
        api_job = _make_api_job(
            job_type="pipeline_run",
            status="completed",
            result={"status": "completed", "output_file": "/tmp/result.csv"},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        artifact_chips = [c for c in chips if c["action"] == CHIP_VIEW_ARTIFACTS]
        assert len(artifact_chips) == 1
        assert "/tmp/result.csv" in artifact_chips[0]["data"]["artifact_paths"]

    def test_result_with_model_cif(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            status="completed",
            result={"status": "completed", "model_cif": "/tmp/model.cif"},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        artifact_chips = [c for c in chips if c["action"] == CHIP_VIEW_ARTIFACTS]
        assert len(artifact_chips) == 1

    def test_completed_alphafold_implicit_artifacts(self):
        """Completed alphafold_backend jobs implicitly produce artifacts."""
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            status="completed",
            result={"status": "completed"},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        artifact_chips = [c for c in chips if c["action"] == CHIP_VIEW_ARTIFACTS]
        assert len(artifact_chips) == 1

    def test_failed_job_no_implicit_artifacts(self):
        """Failed jobs don't implicitly produce artifact chips (but explicit paths still count)."""
        api_job = _make_api_job(job_type="pipeline_run", status="failed")
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        artifact_chips = [c for c in chips if c["action"] == CHIP_VIEW_ARTIFACTS]
        assert len(artifact_chips) == 0

    def test_nested_execution_paths(self):
        api_job = _make_api_job(
            job_type="shell_execution",
            status="completed",
            result={
                "status": "completed",
                "execution": {"output_path": "/tmp/out.txt", "log_path": "/tmp/log.txt"},
            },
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        artifact_chips = [c for c in chips if c["action"] == CHIP_VIEW_ARTIFACTS]
        assert len(artifact_chips) == 1
        assert "/tmp/out.txt" in artifact_chips[0]["data"]["artifact_paths"]
        assert "/tmp/log.txt" in artifact_chips[0]["data"]["artifact_paths"]

    def test_payload_artifact_path(self):
        api_job = _make_api_job(
            job_type="pipeline_run",
            status="running",
            payload={"artifact_path": "/tmp/artifact.bin"},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        artifact_chips = [c for c in chips if c["action"] == CHIP_VIEW_ARTIFACTS]
        assert len(artifact_chips) == 1

    def test_pdb_file_in_result(self):
        api_job = _make_api_job(
            job_type="alphafold_structure",
            case_id="case-1",
            status="completed",
            result={"status": "completed", "pdb_file": "/tmp/struct.pdb"},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        artifact_chips = [c for c in chips if c["action"] == CHIP_VIEW_ARTIFACTS]
        assert len(artifact_chips) == 1
        assert "/tmp/struct.pdb" in artifact_chips[0]["data"]["artifact_paths"]


# ---------------------------------------------------------------------------
# derive_job_detail_actions — combined / multi-chip scenarios
# ---------------------------------------------------------------------------


class TestDeriveJobDetailActionsCombined:
    """Test that multiple chip types can co-exist on a single job."""

    def test_failed_alphafold_produces_retry_and_structure(self):
        """A failed alphafold_backend job should have retry + structure chips."""
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            status="failed",
            attempt=1,
            max_retries=2,
            error="GPU OOM",
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        actions = [c["action"] for c in chips]
        assert CHIP_RETRY in actions
        assert CHIP_VIEW_STRUCTURE in actions

    def test_completed_pipeline_produces_report_and_artifacts(self):
        """A completed pipeline run should have report + artifact chips."""
        api_job = _make_api_job(
            job_type="pipeline_run",
            status="completed",
            result={"status": "completed", "output_file": "/tmp/out.csv"},
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        actions = [c["action"] for c in chips]
        assert CHIP_VIEW_REPORT in actions
        assert CHIP_VIEW_ARTIFACTS in actions

    def test_completed_alphafold_produces_all_three(self):
        """A completed alphafold job (not retryable) should have structure + report + artifact chips."""
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            status="completed",
            result={
                "status": "completed",
                "report_id": "rep-1",
                "model_cif": "/tmp/model.cif",
            },
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        actions = [c["action"] for c in chips]
        assert CHIP_VIEW_STRUCTURE in actions
        assert CHIP_VIEW_REPORT in actions
        assert CHIP_VIEW_ARTIFACTS in actions
        # No retry — it's completed
        assert CHIP_RETRY not in actions

    def test_no_chips_for_simple_pending_job(self):
        """A pending pipeline run with no special result/payload — minimal chips."""
        api_job = _make_api_job(job_type="pipeline_run", status="pending")
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        # Pending, no result references, no structure — expect no chips
        assert len(chips) == 0

    def test_card_only_no_api_job(self):
        """When only a card is provided (no api_job), chips still derive from card fields."""
        card = {
            "source": "api",
            "job_id": "j-retry",
            "job_type": "pipeline_run",
            "case_id": "c1",
            "status": "failed",
            "attempt": 1,
            "max_retries": 1,
        }
        chips = derive_job_detail_actions(card)
        actions = [c["action"] for c in chips]
        assert CHIP_RETRY in actions

    def test_all_four_chips_possible(self):
        """A failed alphafold with report and artifacts gets all four chip types."""
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            status="failed",
            attempt=1,
            max_retries=2,
            error="transient error",
            result={
                "status": "failed",
                "report_id": "rep-x",
                "model_cif": "/tmp/partial.cif",
            },
        )
        card = _make_card_from_api_job(api_job)
        chips = derive_job_detail_actions(card, api_job=api_job)
        actions = [c["action"] for c in chips]
        assert CHIP_RETRY in actions
        assert CHIP_VIEW_STRUCTURE in actions
        # Failed job with explicit report_id still gets report chip
        assert CHIP_VIEW_REPORT in actions
        assert CHIP_VIEW_ARTIFACTS in actions


# ---------------------------------------------------------------------------
# format_action_chips
# ---------------------------------------------------------------------------


class TestFormatActionChips:
    def test_empty_chips(self):
        assert format_action_chips([]) == "No actions available."

    def test_single_chip(self):
        chips = [
            {
                "action": CHIP_RETRY,
                "label": "Retry",
                "description": "Re-dispatch this failed job",
                "enabled": True,
                "data": {"job_id": "j1"},
            }
        ]
        result = format_action_chips(chips)
        assert "↻" in result
        assert "Retry" in result

    def test_multiple_chips_joined_by_separator(self):
        chips = [
            {
                "action": CHIP_RETRY,
                "label": "Retry",
                "description": "",
                "enabled": True,
                "data": {},
            },
            {
                "action": CHIP_VIEW_STRUCTURE,
                "label": "View structure",
                "description": "",
                "enabled": True,
                "data": {},
            },
        ]
        result = format_action_chips(chips)
        assert " · " in result
        assert "↻" in result
        assert "🔬" in result

    def test_disabled_chip_shows_unavailable(self):
        chips = [
            {
                "action": CHIP_RETRY,
                "label": "Retry",
                "description": "",
                "enabled": False,
                "data": {},
            }
        ]
        result = format_action_chips(chips)
        assert "unavailable" in result

    def test_all_icon_types(self):
        chips = [
            {
                "action": CHIP_RETRY,
                "label": "Retry",
                "description": "",
                "enabled": True,
                "data": {},
            },
            {
                "action": CHIP_VIEW_STRUCTURE,
                "label": "View structure",
                "description": "",
                "enabled": True,
                "data": {},
            },
            {
                "action": CHIP_VIEW_REPORT,
                "label": "View report",
                "description": "",
                "enabled": True,
                "data": {},
            },
            {
                "action": CHIP_VIEW_ARTIFACTS,
                "label": "View artifacts",
                "description": "",
                "enabled": True,
                "data": {},
            },
        ]
        result = format_action_chips(chips)
        assert "↻" in result
        assert "🔬" in result
        assert "📄" in result
        assert "📦" in result


# ---------------------------------------------------------------------------
# format_action_chip_summary
# ---------------------------------------------------------------------------


class TestFormatActionChipSummary:
    def test_empty_chips(self):
        assert format_action_chip_summary([]) == "No actions available."

    def test_single_chip_summary(self):
        chips = [
            {
                "action": CHIP_RETRY,
                "label": "Retry",
                "description": "Re-dispatch this failed job (2 attempt(s) remaining)",
                "enabled": True,
                "data": {},
            }
        ]
        result = format_action_chip_summary(chips)
        assert "1 chip(s)" in result
        assert "[retry]" in result
        assert "Retry" in result
        assert "2 attempt(s) remaining" in result

    def test_multiple_chips_summary(self):
        chips = [
            {
                "action": CHIP_RETRY,
                "label": "Retry",
                "description": "Re-dispatch",
                "enabled": True,
                "data": {},
            },
            {
                "action": CHIP_VIEW_STRUCTURE,
                "label": "View structure",
                "description": "Open explorer",
                "enabled": True,
                "data": {},
            },
        ]
        result = format_action_chip_summary(chips)
        assert "2 chip(s)" in result
        assert "[retry]" in result
        assert "[view_structure]" in result

    def test_disabled_chip_summary(self):
        chips = [
            {
                "action": CHIP_RETRY,
                "label": "Retry",
                "description": "Cannot retry",
                "enabled": False,
                "data": {},
            }
        ]
        result = format_action_chip_summary(chips)
        assert "unavailable" in result


# ---------------------------------------------------------------------------
# Integration: derive_job_detail populates action_chips
# ---------------------------------------------------------------------------


class TestDeriveJobDetailActionChipsIntegration:
    """Verify that derive_job_detail automatically includes action_chips."""

    def test_completed_pipeline_has_action_chips(self):
        api_job = _make_api_job(
            job_type="pipeline_run",
            status="completed",
            result={"status": "completed", "output_file": "/tmp/out.csv"},
        )
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        assert "action_chips" in detail
        actions = [c["action"] for c in detail["action_chips"]]
        assert CHIP_VIEW_REPORT in actions
        assert CHIP_VIEW_ARTIFACTS in actions

    def test_failed_alphafold_has_retry_and_structure_chips(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            status="failed",
            attempt=1,
            max_retries=2,
        )
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        actions = [c["action"] for c in detail["action_chips"]]
        assert CHIP_RETRY in actions
        assert CHIP_VIEW_STRUCTURE in actions

    def test_format_job_detail_includes_actions(self):
        """format_job_detail should include the actions line when chips exist."""
        from frontend.app.event_stream import format_job_detail as _fmt

        api_job = _make_api_job(
            job_type="pipeline_run",
            status="completed",
            result={"status": "completed", "report_id": "rep-x"},
        )
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        text = _fmt(detail)
        assert "actions:" in text

    def test_no_actions_for_pending_job(self):
        api_job = _make_api_job(job_type="pipeline_run", status="pending")
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        assert detail["action_chips"] == []
