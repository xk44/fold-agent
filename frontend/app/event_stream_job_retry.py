"""Retry / re-dispatch helpers — pure functions, no Streamlit dependency.

Extracted from event_stream.py for modularity.
"""
from __future__ import annotations


# Terminal statuses that can be retried (match backend BackgroundJobStatusEnum)
_RETRYABLE_STATUSES = {"failed", "timed_out"}
_CANCELLABLE_STATUSES = {"pending", "running"}


def is_retry_eligible(card_or_job: dict) -> bool:
    """Determine whether a job card/dict is eligible for retry.

    A job is retry-eligible when:
    - Its ``source`` is ``"api"`` (i.e. it has a concrete job_id we can POST to)
    - Its ``status`` is ``"failed"`` or ``"timed_out"``
    - The next attempt would not exceed ``max_retries + 1``
      (attempt starts at 1; max_retries counts additional attempts)

    Returns True if the job can be retried via ``POST /jobs/{id}/retry``.
    """
    # Only API-sourced cards have a job_id we can act on
    source = card_or_job.get("source", "api")
    if source != "api" and not card_or_job.get("job_id"):
        return False

    status = card_or_job.get("status", "")
    if status not in _RETRYABLE_STATUSES:
        return False

    attempt = card_or_job.get("attempt", 1) or 1
    max_retries = card_or_job.get("max_retries", 0) or 0

    # Retry allowed when next_attempt <= max_retries + 1
    # next_attempt = attempt + 1
    # boundary: attempt + 1 <= max_retries + 1  →  attempt <= max_retries
    next_attempt = attempt + 1
    return next_attempt <= max_retries + 1


def retry_eligibility_reason(card_or_job: dict) -> str:
    """Return a human-readable reason string for why a job is/isn't retry-eligible.

    Ready for display in operator dashboards and audit surfaces.
    """
    source = card_or_job.get("source", "api")
    job_id = card_or_job.get("job_id")

    # No job_id means it's an event-sourced card — can't retry
    if source != "api" and not job_id:
        return "No job ID — event-sourced cards cannot be retried"

    status = card_or_job.get("status", "")
    attempt = card_or_job.get("attempt", 1) or 1
    max_retries = card_or_job.get("max_retries", 0) or 0

    if status not in _RETRYABLE_STATUSES:
        return f"Status '{status}' is not retryable (only failed/timed_out)"

    next_attempt = attempt + 1
    limit = max_retries + 1

    if next_attempt > limit:
        return (
            f"Retry budget exhausted: attempt {attempt}/{limit}, "
            f"max_retries={max_retries}"
        )

    retries_remaining = limit - attempt
    return (
        f"Eligible for retry: attempt {attempt}/{limit}, "
        f"{retries_remaining} retry(s) remaining"
    )


def format_retry_status_badge(card_or_job: dict) -> str:
    """Return a compact status badge string for retry eligibility.

    Examples: ``"↻ RETRY OK"``, ``"✕ EXHAUSTED"``, ``"—"``
    """
    # Accept both card format (job_id) and raw API format (id)
    has_identity = card_or_job.get("job_id") or card_or_job.get("id")
    source = card_or_job.get("source", "api")
    if not has_identity and source != "api":
        return "—"

    status = card_or_job.get("status", "")
    attempt = card_or_job.get("attempt", 1) or 1
    max_retries = card_or_job.get("max_retries", 0) or 0

    if status not in _RETRYABLE_STATUSES:
        return "—"

    next_attempt = attempt + 1
    limit = max_retries + 1
    if next_attempt > limit:
        return f"✕ EXHAUSTED ({attempt}/{limit})"

    retries_remaining = limit - attempt
    return f"↻ RETRY OK ({retries_remaining} left)"


def enrich_cards_with_retry_info(cards: list[dict]) -> list[dict]:
    """Add retry and cancel eligibility metadata to each job status card.

    For each card, adds:
    - ``retry_eligible`` (bool): whether the job can be retried
    - ``retry_reason`` (str): human-readable reason
    - ``retry_badge`` (str): compact badge for UI display
    - ``cancel_eligible`` (bool): whether the job can be cancelled
    - ``cancel_reason`` (str): human-readable cancellation reason
    - ``cancel_badge`` (str): compact cancellation badge for UI display

    Returns a new list of card dicts with the extra fields.  The original
    cards are not mutated.
    """
    enriched: list[dict] = []
    for card in cards:
        new_card = dict(card)
        new_card["retry_eligible"] = is_retry_eligible(card)
        new_card["retry_reason"] = retry_eligibility_reason(card)
        new_card["retry_badge"] = format_retry_status_badge(card)
        new_card["cancel_eligible"] = is_cancel_eligible(card)
        new_card["cancel_reason"] = cancel_eligibility_reason(card)
        new_card["cancel_badge"] = format_cancel_status_badge(card)
        enriched.append(new_card)
    return enriched


def format_retry_action_summary(enriched_cards: list[dict]) -> str:
    """Render an operator-facing summary of retry-eligible jobs.

    Takes the output of :func:`enrich_cards_with_retry_info` and produces
    a human-readable multi-line string suitable for a Streamlit code block
    or terminal view.

    Pure function — no Streamlit dependency.
    """
    eligible = [c for c in enriched_cards if c.get("retry_eligible")]
    if not eligible:
        return "No jobs eligible for retry."

    lines = [f"Retry-eligible jobs — {len(eligible)} job(s)"]
    for card in eligible:
        job_id = card.get("job_id") or "?"
        short_id = job_id[:8] if len(job_id) >= 8 else job_id
        job_type = card.get("job_type", "unknown")
        status = card.get("status", "unknown")
        reason = card.get("retry_reason", "")
        lines.append(f"  [{short_id}] {job_type} ({status}) — {reason}")

    return "\n".join(lines)


def is_cancel_eligible(card_or_job: dict) -> bool:
    """Determine whether a job card/dict is eligible for cancellation."""
    source = card_or_job.get("source", "api")
    if source != "api" and not card_or_job.get("job_id"):
        return False
    return card_or_job.get("status", "") in _CANCELLABLE_STATUSES



def cancel_eligibility_reason(card_or_job: dict) -> str:
    """Return a human-readable reason for job cancellation eligibility."""
    source = card_or_job.get("source", "api")
    job_id = card_or_job.get("job_id")
    if source != "api" and not job_id:
        return "No job ID — event-sourced cards cannot be cancelled"

    status = card_or_job.get("status", "")
    if status in _CANCELLABLE_STATUSES:
        return f"Eligible for cancellation: status '{status}' is cancellable"
    return f"Status '{status}' is not cancellable (only pending/running)"



def format_cancel_status_badge(card_or_job: dict) -> str:
    """Return a compact status badge string for cancellation eligibility."""
    has_identity = card_or_job.get("job_id") or card_or_job.get("id")
    source = card_or_job.get("source", "api")
    if not has_identity and source != "api":
        return "—"
    if card_or_job.get("status", "") not in _CANCELLABLE_STATUSES:
        return "—"
    return "■ CANCEL OK"



def enrich_cards_with_cancel_info(cards: list[dict]) -> list[dict]:
    """Add cancellation eligibility metadata to each job status card."""
    enriched: list[dict] = []
    for card in cards:
        new_card = dict(card)
        new_card["cancel_eligible"] = is_cancel_eligible(card)
        new_card["cancel_reason"] = cancel_eligibility_reason(card)
        new_card["cancel_badge"] = format_cancel_status_badge(card)
        enriched.append(new_card)
    return enriched



def format_cancel_action_summary(enriched_cards: list[dict]) -> str:
    """Render an operator-facing summary of cancel-eligible jobs."""
    eligible = [c for c in enriched_cards if c.get("cancel_eligible")]
    if not eligible:
        return "No jobs eligible for cancellation."

    lines = [f"Cancel-eligible jobs — {len(eligible)} job(s)"]
    for card in eligible:
        job_id = card.get("job_id") or "?"
        short_id = job_id[:8] if len(job_id) >= 8 else job_id
        job_type = card.get("job_type", "unknown")
        status = card.get("status", "unknown")
        reason = card.get("cancel_reason", "")
        lines.append(f"  [{short_id}] {job_type} ({status}) — {reason}")

    return "\n".join(lines)
