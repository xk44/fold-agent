"""Consent status tracker helpers and timeline builder.

Pure functions for rendering a consent timeline from case metadata and
audit-log entries.  No Streamlit imports here so the logic is testable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

ConsentStatus = Literal["pending", "received", "withdrawn", "unknown"]


CONSENT_STATUS_COLORS: dict[str, str] = {
    "pending": "orange",
    "received": "green",
    "withdrawn": "red",
    "unknown": "gray",
}

CONSENT_STATUS_ICONS: dict[str, str] = {
    "pending": "⏳",
    "received": "✅",
    "withdrawn": "❌",
    "unknown": "❓",
}


def normalize_consent_status(value: str | None) -> str:
    """Map arbitrary consent status strings to canonical values."""
    if not value:
        return "unknown"
    v = str(value).lower().strip()
    if v in {"pending", "awaiting", "not_received"}:
        return "pending"
    if v in {"received", "granted", "approved", "consented"}:
        return "received"
    if v in {"withdrawn", "revoked", "denied"}:
        return "withdrawn"
    return "unknown"


def build_consent_timeline(
    case: dict,
    audit_log: list[dict],
) -> list[dict]:
    """Build a chronological consent timeline for a case.

    The timeline is derived from audit-log entries that mention
    consent_status changes, redactions, deletions, or ethics reports.
    """
    timeline: list[dict] = []

    # Anchor: case creation
    created_at = case.get("created_at")
    timeline.append(
        {
            "timestamp": created_at,
            "event_type": "case_created",
            "title": "Case created",
            "description": f"Case opened with initial consent status: {case.get('consent_status', 'unknown')}",
            "actor": "system",
            "status_after": normalize_consent_status(case.get("consent_status")),
        }
    )

    for entry in audit_log:
        action = entry.get("action", "")
        details = entry.get("details") or {}
        inputs = entry.get("inputs") or {}
        ts = entry.get("timestamp")
        actor = entry.get("actor", "unknown")

        if action == "case.updated":
            # Detect consent_status changes in inputs
            consent_change = inputs.get("consent_status")
            if consent_change is not None:
                timeline.append(
                    {
                        "timestamp": ts,
                        "event_type": "consent_updated",
                        "title": f"Consent marked {normalize_consent_status(consent_change)}",
                        "description": f"Actor: {actor}",
                        "actor": actor,
                        "status_after": normalize_consent_status(consent_change),
                    }
                )

        elif action == "case.redacted":
            level = details.get("redaction_level", "unknown")
            timeline.append(
                {
                    "timestamp": ts,
                    "event_type": "redacted",
                    "title": f"Case redacted ({level})",
                    "description": f"Actor: {actor}",
                    "actor": actor,
                    "status_after": "withdrawn",
                }
            )

        elif action == "case.deleted":
            hard = details.get("hard_delete", False)
            timeline.append(
                {
                    "timestamp": ts,
                    "event_type": "deleted",
                    "title": "Case deleted" + (" (hard)" if hard else " (soft)"),
                    "description": f"Actor: {actor}",
                    "actor": actor,
                    "status_after": "withdrawn",
                }
            )

        elif action == "report.generated":
            report_type = details.get("report_type", "unknown")
            if report_type == "ethics_package":
                timeline.append(
                    {
                        "timestamp": ts,
                        "event_type": "ethics_report",
                        "title": "Ethics package generated",
                        "description": f"Actor: {actor}",
                        "actor": actor,
                        "status_after": None,
                    }
                )

    # Sort by timestamp, None last
    def _sort_key(item: dict):
        ts = item.get("timestamp")
        if ts is None:
            return datetime.max.isoformat()
        return str(ts)

    timeline.sort(key=_sort_key)
    return timeline


def summarize_consent_state(
    case: dict,
    timeline: list[dict],
) -> dict:
    """Return a compact consent-state summary for a case."""
    current_status = normalize_consent_status(case.get("consent_status"))
    review_status = case.get("review_status", "unknown")
    species = case.get("species", "unknown")

    # Count events
    update_events = [e for e in timeline if e["event_type"] == "consent_updated"]
    redacted = any(e["event_type"] == "redacted" for e in timeline)
    deleted = any(e["event_type"] == "deleted" for e in timeline)

    # Days since last consent update (best-effort)
    days_since_update: float | None = None
    if update_events:
        last_ts = update_events[-1].get("timestamp")
        if last_ts:
            try:
                dt = datetime.fromisoformat(str(last_ts).replace("Z", "+00:00"))
                days_since_update = (datetime.now(dt.tzinfo) - dt).total_seconds() / 86400
            except Exception:
                pass

    return {
        "case_id": case.get("id", "unknown"),
        "species": species,
        "current_status": current_status,
        "review_status": review_status,
        "status_icon": CONSENT_STATUS_ICONS.get(current_status, "❓"),
        "status_color": CONSENT_STATUS_COLORS.get(current_status, "gray"),
        "timeline_event_count": len(timeline),
        "consent_update_count": len(update_events),
        "days_since_last_update": days_since_update,
        "is_redacted": redacted,
        "is_deleted": deleted,
        "needs_attention": current_status == "pending" and review_status == "unreviewed",
    }


def build_consent_case_table_row(case: dict, timeline: list[dict]) -> dict:
    """Flatten a case + timeline into a single table row dict."""
    summary = summarize_consent_state(case, timeline)
    return {
        "ID": summary["case_id"],
        "Species": summary["species"],
        "Consent": f"{summary['status_icon']} {summary['current_status']}",
        "Review": summary["review_status"],
        "Updates": summary["consent_update_count"],
        "Days since update": (
            f"{summary['days_since_last_update']:.1f}"
            if summary["days_since_last_update"] is not None
            else "—"
        ),
        "Needs attention": "⚠️ yes" if summary["needs_attention"] else "—",
    }
