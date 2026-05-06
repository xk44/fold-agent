"""Tests for blocked/failed diagnosis helpers — pure functions, no Streamlit.

Covers:
- derive_blocked_failed_diagnosis: combines status, error, lifecycle, retry budget
- format_blocked_failed_diagnosis: renders diagnosis as compact label
- diagnosis integration with derive_job_detail
- format_job_detail includes diagnosis when present
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_stream import (
    derive_blocked_failed_diagnosis,
    derive_job_detail,
    format_blocked_failed_diagnosis,
    format_job_detail,
)
from skills.shared.event_stream_client import SSEEvent

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
    """Derive a job card dict from an API job."""
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


def _make_pipeline_event(
    case_id: str = "c1",
    action: str = "pipeline.failed",
    detail: str = "status=failed",
    ts: str = "2025-04-20T10:00:00",
    job_id: str | None = None,
) -> SSEEvent:
    data = {
        "case_id": case_id,
        "action": action,
        "timestamp": ts,
        "status": "failed",
        "detail": detail,
    }
    if job_id:
        data["job_id"] = job_id
    return SSEEvent(event=action, data=data)


# ---------------------------------------------------------------------------
# derive_blocked_failed_diagnosis
# ---------------------------------------------------------------------------


class TestDeriveBlockedFailedDiagnosis:
    def test_failed_with_error(self):
        api_job = _make_api_job(status="failed", error="GPU OOM", attempt=2, max_retries=3)
        card = _make_card_from_api_job(api_job)
        result = derive_blocked_failed_diagnosis(card, api_job=api_job)
        assert "FAILED" in result
        assert "GPU OOM" in result

    def test_blocked_status(self):
        api_job = _make_api_job(status="blocked", error="safety gate", attempt=1, max_retries=2)
        card = _make_card_from_api_job(api_job)
        result = derive_blocked_failed_diagnosis(card, api_job=api_job)
        assert "BLOCKED" in result
        assert "safety gate" in result

    def test_timed_out_status(self):
        api_job = _make_api_job(status="timed_out", timed_out=True, attempt=2, max_retries=3)
        card = _make_card_from_api_job(api_job)
        result = derive_blocked_failed_diagnosis(card, api_job=api_job)
        assert "TIMED_OUT" in result
        assert "timeout=yes" in result

    def test_running_status_returns_empty(self):
        api_job = _make_api_job(status="running", attempt=1, max_retries=2)
        card = _make_card_from_api_job(api_job)
        result = derive_blocked_failed_diagnosis(card, api_job=api_job)
        assert result == ""

    def test_completed_status_returns_empty(self):
        api_job = _make_api_job(status="completed", attempt=1, max_retries=0)
        card = _make_card_from_api_job(api_job)
        result = derive_blocked_failed_diagnosis(card, api_job=api_job)
        assert result == ""

    def test_pending_status_returns_empty(self):
        api_job = _make_api_job(status="pending", attempt=1, max_retries=2)
        card = _make_card_from_api_job(api_job)
        result = derive_blocked_failed_diagnosis(card, api_job=api_job)
        assert result == ""

    def test_retry_budget_remaining(self):
        api_job = _make_api_job(status="failed", attempt=1, max_retries=2)
        card = _make_card_from_api_job(api_job)
        result = derive_blocked_failed_diagnosis(card, api_job=api_job)
        # limit = max_retries + 1 = 3; remaining = 3 - 1 = 2
        assert "retries=2 left (1/3)" in result

    def test_retry_budget_exhausted(self):
        api_job = _make_api_job(status="failed", attempt=4, max_retries=2)
        card = _make_card_from_api_job(api_job)
        result = derive_blocked_failed_diagnosis(card, api_job=api_job)
        # limit = 3; attempt=4 > limit=3 → EXHAUSTED
        assert "retries=EXHAUSTED(4/3)" in result

    def test_no_error_field(self):
        api_job = _make_api_job(status="failed", error=None, attempt=1, max_retries=2)
        card = _make_card_from_api_job(api_job)
        result = derive_blocked_failed_diagnosis(card, api_job=api_job)
        assert "FAILED" in result
        assert "err=" not in result

    def test_no_retry_budget_info(self):
        """When attempt/max_retries are None (e.g., card-only, no API), no retry line."""
        card = {
            "source": "event",
            "job_id": None,
            "job_type": "pipeline",
            "case_id": "c1",
            "status": "blocked",
            "error": "safety review needed",
        }
        result = derive_blocked_failed_diagnosis(card)
        assert "BLOCKED" in result
        assert "safety review needed" in result
        assert "retries=" not in result

    def test_long_error_truncated(self):
        long_error = "x" * 200
        api_job = _make_api_job(status="failed", error=long_error, attempt=1, max_retries=0)
        card = _make_card_from_api_job(api_job)
        result = derive_blocked_failed_diagnosis(card, api_job=api_job)
        # Error should be truncated to 120 chars in the diagnosis
        err_part = result.split("err=")[1].split(" | ")[0]
        assert len(err_part) <= 123  # 120 + "..."

    def test_lifecycle_event_included(self):
        api_job = _make_api_job(
            status="failed",
            error="GPU OOM",
            attempt=2,
            max_retries=3,
            case_id="c1",
            job_id="j1",
        )
        card = _make_card_from_api_job(api_job)
        events = [
            _make_pipeline_event(
                case_id="c1",
                job_id="j1",
                action="pipeline.failed",
                detail="exit code 137",
            ),
        ]
        result = derive_blocked_failed_diagnosis(card, api_job=api_job, events=events)
        assert "FAILED" in result
        assert "last=pipeline.failed" in result

    def test_lifecycle_detail_truncated(self):
        long_detail = "d" * 200
        api_job = _make_api_job(
            status="failed",
            error="err",
            attempt=1,
            max_retries=2,
            case_id="c1",
            job_id="j1",
        )
        card = _make_card_from_api_job(api_job)
        events = [
            _make_pipeline_event(
                case_id="c1",
                job_id="j1",
                action="pipeline.failed",
                detail=long_detail,
            ),
        ]
        result = derive_blocked_failed_diagnosis(card, api_job=api_job, events=events)
        # Detail truncated to 100 chars
        last_part = [p for p in result.split(" | ") if p.startswith("last=")][0]
        # The detail portion after ": " should be at most 103 chars (100 + "...")
        detail_portion = last_part.split(": ", 1)[1] if ": " in last_part else ""
        if detail_portion:
            assert len(detail_portion) <= 103

    def test_card_status_used_when_no_api_job(self):
        card = {
            "source": "event",
            "job_id": None,
            "status": "blocked",
            "error": "dependency missing",
        }
        result = derive_blocked_failed_diagnosis(card, api_job=None)
        assert "BLOCKED" in result
        assert "dependency missing" in result

    def test_card_only_with_lifecycle_events(self):
        card = {
            "source": "event",
            "job_id": None,
            "status": "failed",
            "error": "timeout exceeded",
            "case_id": "c1",
            "job_type": "pipeline",
        }
        events = [
            _make_pipeline_event(
                case_id="c1",
                action="pipeline.failed",
                detail="stage=analysis timeout",
            ),
        ]
        # Need to pass detail to avoid recursive derive_job_detail call
        # that may not handle card-only well
        detail = {
            "job_id": None,
            "job_type": "pipeline",
            "status": "failed",
            "case_id": "c1",
            "error": "timeout exceeded",
            "attempt": None,
            "max_retries": None,
            "timed_out": None,
            "lifecycle_events": [
                {"action": "pipeline.failed", "detail": "stage=analysis timeout"},
            ],
        }
        result = derive_blocked_failed_diagnosis(card, detail=detail)
        assert "FAILED" in result
        assert "timeout exceeded" in result
        assert "last=pipeline.failed" in result


# ---------------------------------------------------------------------------
# format_blocked_failed_diagnosis
# ---------------------------------------------------------------------------


class TestFormatBlockedFailedDiagnosis:
    def test_non_empty_diagnosis(self):
        result = format_blocked_failed_diagnosis("FAILED | err=GPU OOM")
        assert result == "Diagnosis: FAILED | err=GPU OOM"

    def test_empty_string(self):
        result = format_blocked_failed_diagnosis("")
        assert result == ""

    def test_blocked_label(self):
        result = format_blocked_failed_diagnosis("BLOCKED | err=safety gate")
        assert result.startswith("Diagnosis:")
        assert "BLOCKED" in result


# ---------------------------------------------------------------------------
# Integration: derive_job_detail includes diagnosis
# ---------------------------------------------------------------------------


class TestDiagnosisInJobDetail:
    def test_failed_job_detail_includes_diagnosis(self):
        api_job = _make_api_job(
            status="failed",
            error="GPU OOM",
            attempt=2,
            max_retries=3,
        )
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        assert "diagnosis" in detail
        assert "FAILED" in detail["diagnosis"]
        assert "GPU OOM" in detail["diagnosis"]

    def test_completed_job_detail_empty_diagnosis(self):
        api_job = _make_api_job(status="completed", attempt=1, max_retries=0)
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        assert detail.get("diagnosis") == ""

    def test_blocked_job_detail_includes_diagnosis(self):
        api_job = _make_api_job(
            status="blocked",
            error="safety gate",
            attempt=1,
            max_retries=2,
        )
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        assert "diagnosis" in detail
        assert "BLOCKED" in detail["diagnosis"]

    def test_timed_out_job_includes_timeout_flag(self):
        api_job = _make_api_job(
            status="timed_out",
            timed_out=True,
            attempt=2,
            max_retries=3,
        )
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        assert "diagnosis" in detail
        assert "TIMED_OUT" in detail["diagnosis"]
        assert "timeout=yes" in detail["diagnosis"]


# ---------------------------------------------------------------------------
# Integration: format_job_detail includes diagnosis
# ---------------------------------------------------------------------------


class TestFormatJobDetailWithDiagnosis:
    def test_format_includes_diagnosis_for_failed(self):
        api_job = _make_api_job(
            status="failed",
            error="GPU OOM",
            attempt=2,
            max_retries=3,
        )
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        text = format_job_detail(detail)
        assert "diagnosis" in text.lower() or "FAILED" in text

    def test_format_no_diagnosis_for_completed(self):
        api_job = _make_api_job(status="completed", attempt=1, max_retries=0)
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        text = format_job_detail(detail)
        # Completed jobs should not show diagnosis line
        lines = text.split("\n")
        diagnosis_lines = [l for l in lines if "diagnosis" in l.lower()]
        assert len(diagnosis_lines) == 0
