"""Tests for job/event filter helpers — pure functions, no Streamlit dependency.

Covers:
- derive_filter_options: derive available filter options from job cards and events
- apply_filters: apply selected filter values to cards and events
- FILTER_ALL sentinel behavior
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_stream import (
    FILTER_ALL,
    apply_filters,
    derive_filter_options,
)
from skills.shared.event_stream_client import SSEEvent

# ---------------------------------------------------------------------------
# Fixtures — sample data
# ---------------------------------------------------------------------------


def _make_card(
    status: str = "completed",
    job_type: str = "pipeline_run",
    case_id: str | None = "c1",
    job_id: str | None = "j1",
) -> dict:
    return {
        "source": "api",
        "job_id": job_id,
        "job_type": job_type,
        "case_id": case_id,
        "status": status,
        "latest_status": status,
        "event_count": 0,
        "error": None,
        "created_at": "2025-04-20T09:55:00",
    }


def _make_event(
    event: str = "pipeline.completed",
    case_id: str = "c1",
    action: str = "pipeline.completed",
    ts: str = "2025-04-20T10:00:00",
) -> SSEEvent:
    return SSEEvent(
        event=event,
        data={
            "case_id": case_id,
            "action": action,
            "timestamp": ts,
        },
    )


# ---------------------------------------------------------------------------
# derive_filter_options
# ---------------------------------------------------------------------------


class TestDeriveFilterOptionsEmpty:
    def test_no_cards_no_events(self):
        options = derive_filter_options([], [])
        # Status should still contain canonical statuses
        assert "running" in options["status"]
        assert "completed" in options["status"]
        assert "failed" in options["status"]
        # job_type and case_id should be empty
        assert options["job_type"] == []
        assert options["case_id"] == []

    def test_no_events_with_cards(self):
        cards = [
            _make_card(status="running", job_type="pipeline_run", case_id="c1"),
            _make_card(status="failed", job_type="alphafold_structure", case_id="c2"),
        ]
        options = derive_filter_options(cards, [])
        assert "running" in options["status"]
        assert "failed" in options["status"]
        assert "pipeline_run" in options["job_type"]
        assert "alphafold_structure" in options["job_type"]
        assert "c1" in options["case_id"]
        assert "c2" in options["case_id"]

    def test_no_cards_with_events(self):
        events = [
            _make_event(event="safety.preflight", case_id="c3"),
            _make_event(event="pipeline.started", case_id="c4"),
        ]
        options = derive_filter_options([], events)
        assert "safety" in options["job_type"]
        assert "pipeline" in options["job_type"]
        assert "c3" in options["case_id"]
        assert "c4" in options["case_id"]


class TestDeriveFilterOptionsFromCards:
    def test_status_values_from_cards(self):
        cards = [
            _make_card(status="running"),
            _make_card(status="failed"),
            _make_card(status="completed"),
        ]
        options = derive_filter_options(cards, [])
        # Should contain card statuses AND canonical statuses
        for s in ["running", "failed", "completed", "pending", "blocked", "timed_out", "cancelled"]:
            assert s in options["status"]

    def test_job_type_values_from_cards(self):
        cards = [
            _make_card(job_type="pipeline_run"),
            _make_card(job_type="alphafold_structure"),
        ]
        options = derive_filter_options(cards, [])
        assert "pipeline_run" in options["job_type"]
        assert "alphafold_structure" in options["job_type"]

    def test_case_id_values_from_cards(self):
        cards = [
            _make_card(case_id="case-alpha"),
            _make_card(case_id="case-beta"),
        ]
        options = derive_filter_options(cards, [])
        assert "case-alpha" in options["case_id"]
        assert "case-beta" in options["case_id"]

    def test_card_with_none_case_id_excluded(self):
        cards = [_make_card(case_id=None)]
        options = derive_filter_options(cards, [])
        # None should not appear in case_id options
        assert None not in options["case_id"]
        assert options["case_id"] == []

    def test_card_with_empty_status_excluded(self):
        cards = [{"job_type": "test", "status": "", "source": "api"}]
        options = derive_filter_options(cards, [])
        # Empty string status should not pollute the options
        # (But canonical statuses are still there)
        assert "" not in options["status"]


class TestDeriveFilterOptionsFromEvents:
    def test_job_type_from_event_family(self):
        events = [
            _make_event(event="pipeline.started"),
            _make_event(event="alphafold.completed"),
            _make_event(event="safety.preflight"),
        ]
        options = derive_filter_options([], events)
        assert "pipeline" in options["job_type"]
        assert "alphafold" in options["job_type"]
        assert "safety" in options["job_type"]

    def test_case_id_from_event_data(self):
        events = [
            _make_event(case_id="c1"),
            _make_event(case_id="c2"),
        ]
        options = derive_filter_options([], events)
        assert "c1" in options["case_id"]
        assert "c2" in options["case_id"]

    def test_event_with_none_event(self):
        events = [SSEEvent(event=None, data={"case_id": "c1"})]
        options = derive_filter_options([], events)
        # None event → family="" → should not add "unknown" or "" to job_type
        # (the function skips empty families and "unknown")
        assert "unknown" not in options["job_type"]

    def test_event_with_no_case_id(self):
        events = [SSEEvent(event="pipeline.started", data={})]
        options = derive_filter_options([], events)
        # No case_id in data → nothing added to case_id options
        assert "pipeline" in options["job_type"]
        assert options["case_id"] == []


class TestDeriveFilterOptionsCombined:
    def test_cards_and_events_merged(self):
        cards = [
            _make_card(status="running", job_type="pipeline_run", case_id="c1"),
            _make_card(status="completed", job_type="alphafold_structure", case_id="c2"),
        ]
        events = [
            _make_event(event="safety.preflight", case_id="c3"),
        ]
        options = derive_filter_options(cards, events)
        # Status from cards + canonical
        assert "running" in options["status"]
        assert "completed" in options["status"]
        # Job types from both cards and events
        assert "pipeline_run" in options["job_type"]
        assert "alphafold_structure" in options["job_type"]
        assert "safety" in options["job_type"]
        # Case IDs from both sources
        assert "c1" in options["case_id"]
        assert "c2" in options["case_id"]
        assert "c3" in options["case_id"]

    def test_sorted_output(self):
        cards = [
            _make_card(status="failed", job_type="z-type", case_id="z-case"),
            _make_card(status="running", job_type="a-type", case_id="a-case"),
        ]
        options = derive_filter_options(cards, [])
        # All lists should be sorted
        assert options["job_type"] == sorted(options["job_type"])
        assert options["case_id"] == sorted(options["case_id"])
        assert options["status"] == sorted(options["status"])


# ---------------------------------------------------------------------------
# apply_filters
# ---------------------------------------------------------------------------


class TestApplyFiltersAllDefaults:
    """When all filters are FILTER_ALL (default), no filtering occurs."""

    def test_all_default_returns_original(self):
        cards = [
            _make_card(status="running", job_type="pipeline_run", case_id="c1"),
            _make_card(status="completed", job_type="alphafold_structure", case_id="c2"),
        ]
        events = [
            _make_event(event="pipeline.started", case_id="c1"),
            _make_event(event="safety.preflight", case_id="c2"),
        ]
        filtered_cards, filtered_events = apply_filters(cards, events)
        assert filtered_cards == cards
        assert filtered_events == events

    def test_all_explicit_all_same_as_default(self):
        cards = [_make_card()]
        events = [_make_event()]
        filtered_cards, filtered_events = apply_filters(
            cards,
            events,
            status=FILTER_ALL,
            job_type=FILTER_ALL,
            case_id=FILTER_ALL,
        )
        assert filtered_cards == cards
        assert filtered_events == events

    def test_empty_inputs_with_defaults(self):
        filtered_cards, filtered_events = apply_filters([], [])
        assert filtered_cards == []
        assert filtered_events == []


class TestApplyFiltersByStatus:
    def test_filter_by_running_status(self):
        cards = [
            _make_card(status="running", job_type="pipeline_run", case_id="c1"),
            _make_card(status="completed", job_type="alphafold_structure", case_id="c2"),
            _make_card(status="running", job_type="pipeline_run", case_id="c3"),
        ]
        filtered_cards, filtered_events = apply_filters(cards, [], status="running")
        assert len(filtered_cards) == 2
        assert all(c["status"] == "running" for c in filtered_cards)

    def test_filter_by_failed_status(self):
        cards = [
            _make_card(status="completed"),
            _make_card(status="failed"),
        ]
        filtered_cards, _ = apply_filters(cards, [], status="failed")
        assert len(filtered_cards) == 1
        assert filtered_cards[0]["status"] == "failed"

    def test_filter_by_status_with_no_match(self):
        cards = [_make_card(status="completed")]
        filtered_cards, _ = apply_filters(cards, [], status="running")
        assert filtered_cards == []

    def test_status_filter_does_not_affect_events(self):
        """Status filter only applies to cards, not events (events don't have a status field)."""
        cards = [_make_card(status="running")]
        events = [_make_event(event="pipeline.started", case_id="c1")]
        filtered_cards, filtered_events = apply_filters(
            cards,
            events,
            status="completed",
        )
        # Cards filtered, events untouched (no status filter on events)
        assert len(filtered_cards) == 0
        assert filtered_events == events


class TestApplyFiltersByJobType:
    def test_filter_by_pipeline_run(self):
        cards = [
            _make_card(job_type="pipeline_run", case_id="c1"),
            _make_card(job_type="alphafold_structure", case_id="c2"),
        ]
        events = [
            _make_event(event="pipeline.started", case_id="c1"),
            _make_event(event="safety.preflight", case_id="c2"),
        ]
        filtered_cards, filtered_events = apply_filters(
            cards,
            events,
            job_type="pipeline_run",
        )
        assert len(filtered_cards) == 1
        assert filtered_cards[0]["job_type"] == "pipeline_run"
        # Events: family "pipeline" matches "pipeline" not "pipeline_run"
        # So the pipeline.started event has family "pipeline" != "pipeline_run"
        assert len(filtered_events) == 0

    def test_filter_by_event_family(self):
        """Filtering events by job_type matches the event family."""
        events = [
            _make_event(event="pipeline.started", case_id="c1"),
            _make_event(event="safety.preflight", case_id="c1"),
            _make_event(event="pipeline.completed", case_id="c2"),
        ]
        cards = [
            _make_card(job_type="pipeline", case_id="c1"),
            _make_card(job_type="safety", case_id="c2"),
        ]
        _, filtered_events = apply_filters(
            cards,
            events,
            job_type="pipeline",
        )
        assert len(filtered_events) == 2
        families = {(e.event or "").split(".")[0] for e in filtered_events}
        assert families == {"pipeline"}

    def test_job_type_filter_on_cards(self):
        cards = [
            _make_card(job_type="pipeline_run"),
            _make_card(job_type="alphafold_structure"),
            _make_card(job_type="pipeline_run"),
        ]
        filtered_cards, _ = apply_filters(cards, [], job_type="pipeline_run")
        assert len(filtered_cards) == 2
        assert all(c["job_type"] == "pipeline_run" for c in filtered_cards)

    def test_job_type_with_no_match(self):
        cards = [_make_card(job_type="pipeline_run")]
        filtered_cards, filtered_events = apply_filters(
            cards,
            [],
            job_type="nonexistent_type",
        )
        assert len(filtered_cards) == 0
        assert len(filtered_events) == 0


class TestApplyFiltersByCaseId:
    def test_filter_by_case_id_cards(self):
        cards = [
            _make_card(case_id="c1"),
            _make_card(case_id="c2"),
            _make_card(case_id="c1"),
        ]
        filtered_cards, _ = apply_filters(cards, [], case_id="c1")
        assert len(filtered_cards) == 2
        assert all(c["case_id"] == "c1" for c in filtered_cards)

    def test_filter_by_case_id_events(self):
        events = [
            _make_event(event="pipeline.started", case_id="c1"),
            _make_event(event="safety.preflight", case_id="c2"),
            _make_event(event="pipeline.completed", case_id="c1"),
        ]
        _, filtered_events = apply_filters([], events, case_id="c1")
        assert len(filtered_events) == 2
        assert all((e.data or {}).get("case_id") == "c1" for e in filtered_events)

    def test_case_id_filter_cards_and_events_together(self):
        cards = [
            _make_card(job_type="pipeline_run", case_id="c1"),
            _make_card(job_type="alphafold_structure", case_id="c2"),
        ]
        events = [
            _make_event(event="pipeline.started", case_id="c1"),
            _make_event(event="safety.preflight", case_id="c2"),
        ]
        filtered_cards, filtered_events = apply_filters(
            cards,
            events,
            case_id="c1",
        )
        assert len(filtered_cards) == 1
        assert filtered_cards[0]["case_id"] == "c1"
        assert len(filtered_events) == 1
        assert (filtered_events[0].data or {}).get("case_id") == "c1"

    def test_case_id_with_no_match(self):
        cards = [_make_card(case_id="c1")]
        events = [_make_event(case_id="c1")]
        filtered_cards, filtered_events = apply_filters(cards, events, case_id=" nonexistent")
        assert len(filtered_cards) == 0
        assert len(filtered_events) == 0


class TestApplyFiltersCombined:
    def test_status_and_job_type_together(self):
        cards = [
            _make_card(status="running", job_type="pipeline_run", case_id="c1"),
            _make_card(status="running", job_type="alphafold_structure", case_id="c2"),
            _make_card(status="completed", job_type="pipeline_run", case_id="c3"),
        ]
        events = [
            _make_event(event="pipeline.started", case_id="c1"),
            _make_event(event="alphafold.completed", case_id="c2"),
        ]
        # Filtering by job_type="pipeline" matches event family "pipeline"
        filtered_cards, filtered_events = apply_filters(
            cards,
            events,
            status="running",
            job_type="pipeline",
        )
        # Cards: only "running" cards, but no card has job_type "pipeline"
        # (they have "pipeline_run"). So 0 cards match.
        # Events: "pipeline" family matches
        assert len(filtered_cards) == 0
        assert len(filtered_events) == 1

    def test_all_three_filters(self):
        cards = [
            _make_card(status="running", job_type="pipeline_run", case_id="c1"),
            _make_card(status="running", job_type="pipeline_run", case_id="c2"),
            _make_card(status="completed", job_type="alphafold_structure", case_id="c1"),
        ]
        events = [
            _make_event(event="pipeline.started", case_id="c1"),
            _make_event(event="pipeline.completed", case_id="c2"),
            _make_event(event="alphafold.done", case_id="c1"),
        ]
        # Status and job_type filters on cards, job_type and case_id on events
        filtered_cards, filtered_events = apply_filters(
            cards,
            events,
            status="running",
            job_type="pipeline_run",
            case_id="c1",
        )
        # Only first card: running + pipeline_run + c1
        assert len(filtered_cards) == 1
        assert filtered_cards[0]["case_id"] == "c1"
        # Events: job_type="pipeline_run" doesn't match event family "pipeline"
        # and job_type="pipeline_run" doesn't match "alphafold" either
        # So filtering events by job_type="pipeline_run" yields 0 events
        assert len(filtered_events) == 0

    def test_partial_filter_status_only(self):
        cards = [
            _make_card(status="running", job_type="a", case_id="c1"),
            _make_card(status="completed", job_type="b", case_id="c2"),
        ]
        events = [_make_event(event="x.y", case_id="c1")]
        filtered_cards, filtered_events = apply_filters(
            cards,
            events,
            status="running",
        )
        assert len(filtered_cards) == 1
        assert filtered_cards[0]["status"] == "running"
        # Events unaffected by status filter
        assert len(filtered_events) == 1

    def test_partial_filter_job_type_only(self):
        cards = [
            _make_card(status="running", job_type="a", case_id="c1"),
            _make_card(status="completed", job_type="b", case_id="c2"),
        ]
        events = [
            _make_event(event="a.y", case_id="c1"),
            _make_event(event="b.z", case_id="c2"),
        ]
        filtered_cards, filtered_events = apply_filters(
            cards,
            events,
            job_type="a",
        )
        assert len(filtered_cards) == 1
        assert filtered_cards[0]["job_type"] == "a"
        assert len(filtered_events) == 1
        assert (filtered_events[0].event or "").startswith("a")

    def test_case_id_on_cards_with_none(self):
        """Cards with case_id=None should be excluded by a case_id filter."""
        cards = [
            _make_card(case_id=None),
            _make_card(case_id="c1"),
        ]
        filtered_cards, _ = apply_filters(cards, [], case_id="c1")
        assert len(filtered_cards) == 1
        assert filtered_cards[0]["case_id"] == "c1"


class TestFilterAllSentinel:
    def test_sentinel_value(self):
        assert FILTER_ALL == "__all__"

    def test_sentinel_is_distinct_from_real_values(self):
        """FILTER_ALL should not collide with typical status/job_type/case_id values."""
        assert FILTER_ALL != "running"
        assert FILTER_ALL != "completed"
        assert FILTER_ALL != "pipeline_run"
        assert FILTER_ALL != "c1"


class TestApplyFiltersEdgeCases:
    def test_empty_cards_and_events_with_filter(self):
        """Filtering empty lists should return empty lists."""
        filtered_cards, filtered_events = apply_filters(
            [],
            [],
            status="running",
        )
        assert filtered_cards == []
        assert filtered_events == []

    def test_event_with_no_data_dict(self):
        """Events with None data should not crash the filter."""
        events = [SSEEvent(event="pipeline.started", data=None)]
        _, filtered_events = apply_filters([], events, job_type="pipeline")
        # data=None → (None or {}).get("case_id", "") returns ""
        # family="pipeline" matches, so it should be included
        assert len(filtered_events) == 1

    def test_event_with_empty_data(self):
        """Events with empty data dict but matching family."""
        events = [SSEEvent(event="safety.preflight", data={})]
        _, filtered_events = apply_filters([], events, job_type="safety")
        assert len(filtered_events) == 1

    def test_event_family_matching_with_case_id_mismatch(self):
        """Events that match job_type but not case_id should be excluded."""
        events = [
            _make_event(event="pipeline.started", case_id="c1"),
        ]
        _, filtered_events = apply_filters(
            [],
            events,
            job_type="pipeline",
            case_id="c2",
        )
        assert len(filtered_events) == 0

    def test_duplicate_statuses_in_options(self):
        """derive_filter_options should deduplicate statuses."""
        cards = [
            _make_card(status="running"),
            _make_card(status="running"),
            _make_card(status="running"),
        ]
        options = derive_filter_options(cards, [])
        running_count = options["status"].count("running")
        assert running_count == 1

    def test_duplicate_job_types_in_options(self):
        """derive_filter_options should deduplicate job types."""
        cards = [
            _make_card(job_type="pipeline_run"),
            _make_card(job_type="pipeline_run"),
        ]
        events = [
            _make_event(event="pipeline.started"),
            _make_event(event="pipeline.completed"),
        ]
        options = derive_filter_options(cards, events)
        pipeline_run_count = options["job_type"].count("pipeline_run")
        assert pipeline_run_count == 1
        # Event family "pipeline" is distinct from card type "pipeline_run"
        pipeline_count = options["job_type"].count("pipeline")
        assert pipeline_count == 1
