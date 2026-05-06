"""Tests for retry/re-dispatch UX for background jobs — pure helpers, no Streamlit.

Covers:
- is_retry_eligible: determines which jobs can be retried
- retry_eligibility_reason: human-readable reason for why a job is/isn't eligible
- format_retry_status_badge: compact status label for retry-eligible jobs
- enrich_cards_with_retry_info: adds retry metadata to job status cards
- format_retry_action_summary: operator-facing summary of retry-eligible jobs
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_stream import (
    build_job_status_table_rows,
    derive_job_status_cards,
    enrich_cards_with_retry_info,
    format_retry_action_summary,
    format_retry_status_badge,
    is_retry_eligible,
    retry_eligibility_reason,
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
) -> dict:
    return {
        "id": job_id,
        "case_id": case_id,
        "job_type": job_type,
        "status": status,
        "payload": {},
        "result": {"status": status} if status == "completed" else None,
        "error": error,
        "attempt": attempt,
        "max_retries": max_retries,
        "timed_out": timed_out,
        "created_at": "2025-04-20T09:55:00",
    }


# ---------------------------------------------------------------------------
# is_retry_eligible
# ---------------------------------------------------------------------------


class TestIsRetryEligible:
    """Retry is eligible when:
    - status is 'failed' or 'timed_out'
    - AND attempt <= max_retries (next attempt would be within budget)
    """

    def test_failed_with_remaining_retries(self):
        job = _make_api_job(status="failed", attempt=1, max_retries=2)
        assert is_retry_eligible(job) is True

    def test_failed_with_no_max_retries(self):
        """max_retries=0 means no retries allowed — only the first attempt."""
        job = _make_api_job(status="failed", attempt=1, max_retries=0)
        assert is_retry_eligible(job) is False

    def test_failed_at_max_attempts(self):
        """attempt=3, max_retries=2 → 3 > 2+1=3 would exceed on next try?
        Actually: next_attempt = 4, max_retries+1 = 3, so 4 > 3 — not eligible."""
        job = _make_api_job(status="failed", attempt=3, max_retries=2)
        assert is_retry_eligible(job) is False

    def test_timed_out_with_remaining_retries(self):
        job = _make_api_job(status="timed_out", attempt=1, max_retries=3)
        assert is_retry_eligible(job) is True

    def test_timed_out_with_no_retries(self):
        job = _make_api_job(status="timed_out", attempt=1, max_retries=0)
        assert is_retry_eligible(job) is False

    def test_completed_not_eligible(self):
        job = _make_api_job(status="completed", attempt=1, max_retries=2)
        assert is_retry_eligible(job) is False

    def test_running_not_eligible(self):
        job = _make_api_job(status="running", attempt=1, max_retries=2)
        assert is_retry_eligible(job) is False

    def test_pending_not_eligible(self):
        job = _make_api_job(status="pending", attempt=1, max_retries=2)
        assert is_retry_eligible(job) is False

    def test_cancelled_not_eligible(self):
        job = _make_api_job(status="cancelled", attempt=1, max_retries=2)
        assert is_retry_eligible(job) is False

    def test_failed_second_attempt_with_one_retry_left(self):
        """attempt=2, max_retries=3 → next_attempt=3 <= 4 → eligible."""
        job = _make_api_job(status="failed", attempt=2, max_retries=3)
        assert is_retry_eligible(job) is True

    def test_failed_at_exact_boundary(self):
        """attempt=3, max_retries=2 → next_attempt=4 > 3 → NOT eligible.
        (max_retries=2 means 2 retries permitted, i.e. 3 total attempts.)"""
        job = _make_api_job(status="failed", attempt=3, max_retries=2)
        assert is_retry_eligible(job) is False

    def test_failed_at_boundary_minus_one(self):
        """attempt=2, max_retries=2 → next_attempt=3 <= 3 → eligible."""
        job = _make_api_job(status="failed", attempt=2, max_retries=2)
        assert is_retry_eligible(job) is True

    def test_missing_attempt_defaults_to_one(self):
        """If attempt field is missing, treat as attempt=1."""
        job = {"status": "failed", "max_retries": 2}
        assert is_retry_eligible(job) is True

    def test_missing_max_retries_defaults_to_zero(self):
        """If max_retries is missing, treat as 0 (no retries)."""
        job = {"status": "failed", "attempt": 1}
        assert is_retry_eligible(job) is False

    def test_missing_status_not_eligible(self):
        """If status field is missing, not retry-eligible."""
        job = {"attempt": 1, "max_retries": 2}
        assert is_retry_eligible(job) is False

    def test_event_sourced_card_never_eligible(self):
        """Cards sourced from events (no job_id) cannot be retried."""
        card = {
            "source": "event",
            "job_id": None,
            "job_type": "pipeline",
            "case_id": "c1",
            "status": "failed",
            "attempt": 1,
            "max_retries": 2,
        }
        assert is_retry_eligible(card) is False


# ---------------------------------------------------------------------------
# retry_eligibility_reason
# ---------------------------------------------------------------------------


class TestRetryEligibilityReason:
    def test_eligible_failed(self):
        job = _make_api_job(status="failed", attempt=1, max_retries=2)
        reason = retry_eligibility_reason(job)
        assert "eligible" in reason.lower()
        assert "retry" in reason.lower()

    def test_not_eligible_completed(self):
        job = _make_api_job(status="completed", attempt=1, max_retries=0)
        reason = retry_eligibility_reason(job)
        assert "completed" in reason.lower() or "not" in reason.lower()

    def test_not_eligible_exhausted(self):
        job = _make_api_job(status="failed", attempt=3, max_retries=2)
        reason = retry_eligibility_reason(job)
        assert "max" in reason.lower() or "exceed" in reason.lower() or "not" in reason.lower()

    def test_no_job_id_event_card(self):
        card = {
            "source": "event",
            "job_id": None,
            "status": "failed",
            "attempt": 1,
            "max_retries": 2,
        }
        reason = retry_eligibility_reason(card)
        assert "no job id" in reason.lower() or "event" in reason.lower()


# ---------------------------------------------------------------------------
# format_retry_status_badge
# ---------------------------------------------------------------------------


class TestFormatRetryStatusBadge:
    def test_eligible_badge(self):
        job = _make_api_job(status="failed", attempt=1, max_retries=2)
        badge = format_retry_status_badge(job)
        assert "retry" in badge.lower() or "eligible" in badge.lower()

    def test_not_eligible_badge(self):
        job = _make_api_job(status="completed", attempt=1, max_retries=0)
        badge = format_retry_status_badge(job)
        assert (
            "—" in badge
            or "—" in badge
            or "none" in badge.lower()
            or "n/a" in badge.lower()
            or badge == ""
        )

    def test_exhausted_badge(self):
        job = _make_api_job(status="failed", attempt=3, max_retries=2)
        badge = format_retry_status_badge(job)
        assert "exhaust" in badge.lower() or "max" in badge.lower() or "—" in badge


# ---------------------------------------------------------------------------
# enrich_cards_with_retry_info
# ---------------------------------------------------------------------------


class TestEnrichCardsWithRetryInfo:
    def test_adds_retry_eligible_field(self):
        cards = derive_job_status_cards(
            [],
            [_make_api_job(status="failed", attempt=1, max_retries=2)],
        )
        enriched = enrich_cards_with_retry_info(cards)
        assert len(enriched) == 1
        assert enriched[0]["retry_eligible"] is True

    def test_not_eligible_completed(self):
        cards = derive_job_status_cards(
            [],
            [_make_api_job(status="completed", attempt=1, max_retries=0)],
        )
        enriched = enrich_cards_with_retry_info(cards)
        assert enriched[0]["retry_eligible"] is False

    def test_mixed_cards(self):
        jobs = [
            _make_api_job(job_id="j1", status="failed", attempt=1, max_retries=2),
            _make_api_job(job_id="j2", status="completed", attempt=1, max_retries=0),
            _make_api_job(job_id="j3", status="timed_out", attempt=2, max_retries=3),
        ]
        cards = derive_job_status_cards([], jobs)
        enriched = enrich_cards_with_retry_info(cards)
        # Sort order is by status priority; check by job_id instead of by index
        by_id = {c["job_id"]: c for c in enriched}
        assert by_id["j1"]["retry_eligible"] is True
        assert by_id["j2"]["retry_eligible"] is False
        assert by_id["j3"]["retry_eligible"] is True

    def test_event_sourced_card_not_eligible(self):
        from skills.shared.event_stream_client import SSEEvent

        events = [
            SSEEvent(
                event="pipeline.failed",
                data={"case_id": "c1", "status": "failed"},
            )
        ]
        cards = derive_job_status_cards(events, [])
        enriched = enrich_cards_with_retry_info(cards)
        # Event-sourced cards have no job_id, so not retry-eligible
        assert enriched[0]["retry_eligible"] is False

    def test_adds_retry_reason(self):
        cards = derive_job_status_cards(
            [],
            [_make_api_job(status="failed", attempt=1, max_retries=2)],
        )
        enriched = enrich_cards_with_retry_info(cards)
        assert "retry_reason" in enriched[0]
        assert enriched[0]["retry_reason"] is not None

    def test_adds_retry_status_badge(self):
        cards = derive_job_status_cards(
            [],
            [_make_api_job(status="failed", attempt=1, max_retries=2)],
        )
        enriched = enrich_cards_with_retry_info(cards)
        assert "retry_badge" in enriched[0]

    def test_preserves_original_card_fields(self):
        cards = derive_job_status_cards(
            [],
            [_make_api_job(status="failed", attempt=1, max_retries=2)],
        )
        enriched = enrich_cards_with_retry_info(cards)
        assert enriched[0]["job_id"] == "j1"
        assert enriched[0]["status"] == "failed"
        assert enriched[0]["source"] == "api"


# ---------------------------------------------------------------------------
# format_retry_action_summary
# ---------------------------------------------------------------------------


class TestFormatRetryActionSummary:
    def test_no_eligible_jobs(self):
        cards = derive_job_status_cards(
            [],
            [_make_api_job(status="completed", attempt=1, max_retries=0)],
        )
        enriched = enrich_cards_with_retry_info(cards)
        summary = format_retry_action_summary(enriched)
        assert "no" in summary.lower() or "0" in summary or "none" in summary.lower()

    def test_with_eligible_jobs(self):
        jobs = [
            _make_api_job(job_id="j1", status="failed", attempt=1, max_retries=2),
            _make_api_job(
                job_id="j2", status="timed_out", attempt=1, max_retries=1, timed_out=True
            ),
        ]
        cards = derive_job_status_cards([], jobs)
        enriched = enrich_cards_with_retry_info(cards)
        summary = format_retry_action_summary(enriched)
        assert "2" in summary

    def test_empty_cards(self):
        summary = format_retry_action_summary([])
        assert "no" in summary.lower() or "0" in summary or "none" in summary.lower()


# ---------------------------------------------------------------------------
# build_job_status_table_rows with retry info
# ---------------------------------------------------------------------------


class TestBuildJobStatusTableRowsWithRetry:
    def test_retry_eligible_column_in_rows(self):
        jobs = [
            _make_api_job(job_id="j1", status="failed", attempt=1, max_retries=2),
        ]
        cards = derive_job_status_cards([], jobs)
        enriched = enrich_cards_with_retry_info(cards)
        rows = build_job_status_table_rows(enriched)
        assert len(rows) == 1
        # The retry_eligible field should propagate through
        assert "retry_eligible" in rows[0]
        assert rows[0]["retry_eligible"] is True

    def test_exhausted_retry_shows_in_table(self):
        jobs = [
            _make_api_job(job_id="j1", status="failed", attempt=3, max_retries=2),
        ]
        cards = derive_job_status_cards([], jobs)
        enriched = enrich_cards_with_retry_info(cards)
        rows = build_job_status_table_rows(enriched)
        assert rows[0]["retry_eligible"] is False
