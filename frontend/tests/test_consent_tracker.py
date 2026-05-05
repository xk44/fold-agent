"""Tests for the consent tracker helper module."""

from __future__ import annotations

import pytest

from frontend.app.consent_tracker import (
    build_consent_case_table_row,
    build_consent_timeline,
    normalize_consent_status,
    summarize_consent_state,
)


class TestNormalizeConsentStatus:
    def test_pending_variants(self):
        assert normalize_consent_status("pending") == "pending"
        assert normalize_consent_status("awaiting") == "pending"
        assert normalize_consent_status("not_received") == "pending"

    def test_received_variants(self):
        assert normalize_consent_status("received") == "received"
        assert normalize_consent_status("granted") == "received"
        assert normalize_consent_status("approved") == "received"

    def test_withdrawn_variants(self):
        assert normalize_consent_status("withdrawn") == "withdrawn"
        assert normalize_consent_status("revoked") == "withdrawn"
        assert normalize_consent_status("denied") == "withdrawn"

    def test_unknown_and_none(self):
        assert normalize_consent_status("foo") == "unknown"
        assert normalize_consent_status(None) == "unknown"
        assert normalize_consent_status("") == "unknown"


class TestBuildConsentTimeline:
    def test_empty_audit_log(self):
        case = {"id": "c1", "consent_status": "pending", "created_at": "2024-01-01T00:00:00"}
        timeline = build_consent_timeline(case, [])
        assert len(timeline) == 1
        assert timeline[0]["event_type"] == "case_created"
        assert timeline[0]["status_after"] == "pending"

    def test_consent_update_detected(self):
        case = {"id": "c1", "consent_status": "received", "created_at": "2024-01-01T00:00:00"}
        audit = [
            {
                "action": "case.updated",
                "actor": "api",
                "timestamp": "2024-01-02T00:00:00",
                "inputs": {"consent_status": "received"},
                "details": {},
            }
        ]
        timeline = build_consent_timeline(case, audit)
        assert len(timeline) == 2
        assert timeline[1]["event_type"] == "consent_updated"
        assert timeline[1]["status_after"] == "received"

    def test_redaction_event(self):
        case = {"id": "c1", "consent_status": "pending", "created_at": "2024-01-01T00:00:00"}
        audit = [
            {
                "action": "case.redacted",
                "actor": "api",
                "timestamp": "2024-01-03T00:00:00",
                "inputs": {},
                "details": {"redaction_level": "anonymous"},
            }
        ]
        timeline = build_consent_timeline(case, audit)
        assert timeline[1]["event_type"] == "redacted"
        assert timeline[1]["status_after"] == "withdrawn"

    def test_soft_delete_event(self):
        case = {"id": "c1", "consent_status": "pending", "created_at": "2024-01-01T00:00:00"}
        audit = [
            {
                "action": "case.deleted",
                "actor": "api",
                "timestamp": "2024-01-04T00:00:00",
                "inputs": {},
                "details": {"hard_delete": False},
            }
        ]
        timeline = build_consent_timeline(case, audit)
        assert timeline[1]["event_type"] == "deleted"
        assert timeline[1]["status_after"] == "withdrawn"

    def test_chronological_sort(self):
        case = {"id": "c1", "consent_status": "pending", "created_at": "2024-01-01T00:00:00"}
        audit = [
            {
                "action": "case.updated",
                "actor": "api",
                "timestamp": "2024-01-03T00:00:00",
                "inputs": {"consent_status": "received"},
                "details": {},
            },
            {
                "action": "case.updated",
                "actor": "api",
                "timestamp": "2024-01-02T00:00:00",
                "inputs": {"consent_status": "withdrawn"},
                "details": {},
            },
        ]
        timeline = build_consent_timeline(case, audit)
        assert timeline[1]["status_after"] == "withdrawn"
        assert timeline[2]["status_after"] == "received"


class TestSummarizeConsentState:
    def test_basic_summary(self):
        case = {
            "id": "c1",
            "consent_status": "pending",
            "review_status": "unreviewed",
            "species": "dog",
            "created_at": "2024-01-01T00:00:00",
        }
        timeline = build_consent_timeline(case, [])
        summary = summarize_consent_state(case, timeline)
        assert summary["case_id"] == "c1"
        assert summary["current_status"] == "pending"
        assert summary["review_status"] == "unreviewed"
        assert summary["needs_attention"] is True
        assert summary["is_redacted"] is False

    def test_no_attention_when_received(self):
        case = {
            "id": "c1",
            "consent_status": "received",
            "review_status": "unreviewed",
            "species": "human",
        }
        timeline = build_consent_timeline(case, [])
        summary = summarize_consent_state(case, timeline)
        assert summary["needs_attention"] is False

    def test_redaction_flag(self):
        case = {"id": "c1", "consent_status": "pending", "review_status": "unreviewed", "species": "demo"}
        audit = [
            {
                "action": "case.redacted",
                "actor": "api",
                "timestamp": "2024-01-02T00:00:00",
                "inputs": {},
                "details": {"redaction_level": "deidentify"},
            }
        ]
        timeline = build_consent_timeline(case, audit)
        summary = summarize_consent_state(case, timeline)
        assert summary["is_redacted"] is True


class TestBuildConsentCaseTableRow:
    def test_row_structure(self):
        case = {
            "id": "abc-123",
            "consent_status": "received",
            "review_status": "expert_accepted_for_further_research",
            "species": "dog",
        }
        timeline = build_consent_timeline(case, [])
        row = build_consent_case_table_row(case, timeline)
        assert row["ID"] == "abc-123"
        assert "received" in row["Consent"]
        assert row["Review"] == "expert_accepted_for_further_research"
        assert row["Needs attention"] == "—"
