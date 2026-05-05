"""Tests for cancel-background-job UX helpers — pure helpers, no Streamlit."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_stream import (
    enrich_cards_with_cancel_info,
    format_cancel_action_summary,
    format_cancel_status_badge,
    is_cancel_eligible,
    cancel_eligibility_reason,
)


def _make_api_job(
    job_id: str = "j1",
    case_id: str = "c1",
    job_type: str = "pipeline_run",
    status: str = "running",
    attempt: int = 1,
    max_retries: int = 0,
) -> dict:
    return {
        "id": job_id,
        "job_id": job_id,
        "case_id": case_id,
        "job_type": job_type,
        "status": status,
        "attempt": attempt,
        "max_retries": max_retries,
        "source": "api",
    }


class TestIsCancelEligible:
    def test_running_job_is_cancel_eligible(self):
        assert is_cancel_eligible(_make_api_job(status="running")) is True

    def test_pending_job_is_cancel_eligible(self):
        assert is_cancel_eligible(_make_api_job(status="pending")) is True

    def test_terminal_job_not_cancel_eligible(self):
        assert is_cancel_eligible(_make_api_job(status="completed")) is False
        assert is_cancel_eligible(_make_api_job(status="failed")) is False
        assert is_cancel_eligible(_make_api_job(status="cancelled")) is False

    def test_event_sourced_card_not_cancel_eligible(self):
        assert is_cancel_eligible({"source": "event", "status": "running"}) is False


class TestCancelEligibilityReason:
    def test_running_reason(self):
        text = cancel_eligibility_reason(_make_api_job(status="running"))
        assert "Eligible for cancellation" in text

    def test_terminal_reason(self):
        text = cancel_eligibility_reason(_make_api_job(status="completed"))
        assert "not cancellable" in text


class TestCancelBadgesAndSummary:
    def test_cancel_status_badge(self):
        assert format_cancel_status_badge(_make_api_job(status="running")) == "■ CANCEL OK"
        assert format_cancel_status_badge(_make_api_job(status="completed")) == "—"

    def test_enrich_cards_with_cancel_info(self):
        enriched = enrich_cards_with_cancel_info([
            _make_api_job(job_id="j1", status="running"),
            _make_api_job(job_id="j2", status="completed"),
        ])
        assert enriched[0]["cancel_eligible"] is True
        assert enriched[1]["cancel_eligible"] is False

    def test_cancel_action_summary(self):
        enriched = enrich_cards_with_cancel_info([
            _make_api_job(job_id="j1", status="running"),
            _make_api_job(job_id="j2", status="pending"),
            _make_api_job(job_id="j3", status="completed"),
        ])
        text = format_cancel_action_summary(enriched)
        assert "Cancel-eligible jobs — 2 job(s)" in text
        assert "pipeline_run (running)" in text
        assert "pipeline_run (pending)" in text
