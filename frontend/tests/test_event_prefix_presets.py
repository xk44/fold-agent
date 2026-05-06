from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_prefix_presets import (
    DASHBOARD_PREFIXES,
    OPERATOR_PREFIXES,
    PIPELINE_PREFIXES,
    PREFIX_AGENT_TASK,
    PREFIX_ALPHAFOLD,
    PREFIX_BACKGROUND_JOB,
    PREFIX_CASE,
    PREFIX_EXPERT,
    PREFIX_PIPELINE,
    PREFIX_REPORT,
    PREFIX_SAFETY,
    PREFIX_STRUCTURE_JOB,
    SAFETY_PREFIXES,
    merge_prefixes,
    prefixes_for_families,
    resolve_prefixes,
    validate_prefixes,
)
from frontend.app.event_stream_live_feed import LiveEventFeed
from skills.shared.event_stream_client import SSEEvent


class TestResolvePrefixes:
    def test_dashboard_matches_full_known_backend_family_set(self) -> None:
        result = resolve_prefixes("dashboard")
        assert result == DASHBOARD_PREFIXES
        assert PREFIX_CASE in result
        assert PREFIX_BACKGROUND_JOB in result
        assert PREFIX_PIPELINE in result
        assert PREFIX_REPORT in result
        assert PREFIX_STRUCTURE_JOB in result
        assert PREFIX_ALPHAFOLD in result

    def test_operator_is_narrower_than_dashboard(self) -> None:
        result = resolve_prefixes("operator")
        assert result is not None
        assert PREFIX_BACKGROUND_JOB in result
        assert PREFIX_PIPELINE in result
        assert PREFIX_SAFETY in result
        assert PREFIX_STRUCTURE_JOB in result
        assert PREFIX_ALPHAFOLD in result
        assert PREFIX_CASE not in result
        assert PREFIX_REPORT not in result
        assert set(result) < set(DASHBOARD_PREFIXES)

    def test_pipeline_is_narrower_than_dashboard(self) -> None:
        result = resolve_prefixes("pipeline")
        assert result is not None
        assert PREFIX_BACKGROUND_JOB in result
        assert PREFIX_PIPELINE in result
        assert PREFIX_STRUCTURE_JOB in result
        assert PREFIX_CASE not in result
        assert PREFIX_REPORT not in result
        assert PREFIX_AGENT_TASK not in result
        assert set(result) < set(DASHBOARD_PREFIXES)

    def test_safety_is_narrowest(self) -> None:
        assert resolve_prefixes("safety") == SAFETY_PREFIXES
        assert SAFETY_PREFIXES == (PREFIX_SAFETY, PREFIX_EXPERT)

    def test_all_returns_none(self) -> None:
        assert resolve_prefixes("all") is None

    def test_unknown_returns_none(self) -> None:
        assert resolve_prefixes("wat") is None


class TestValidatePrefixes:
    def test_known_presets_validate(self) -> None:
        assert validate_prefixes(DASHBOARD_PREFIXES) == []
        assert validate_prefixes(OPERATOR_PREFIXES) == []
        assert validate_prefixes(PIPELINE_PREFIXES) == []
        assert validate_prefixes(SAFETY_PREFIXES) == []

    def test_none_validates(self) -> None:
        assert validate_prefixes(None) == []

    def test_unknown_prefix_reported(self) -> None:
        assert validate_prefixes((PREFIX_CASE, "bogus.")) == ["bogus."]


class TestMergePrefixes:
    def test_merge_deduplicates_and_sorts(self) -> None:
        result = merge_prefixes(
            (PREFIX_PIPELINE, PREFIX_BACKGROUND_JOB),
            (PREFIX_BACKGROUND_JOB, PREFIX_SAFETY),
        )
        assert result == tuple(sorted({PREFIX_PIPELINE, PREFIX_BACKGROUND_JOB, PREFIX_SAFETY}))

    def test_merge_with_none_returns_none(self) -> None:
        assert merge_prefixes(OPERATOR_PREFIXES, None) is None


class TestPrefixesForFamilies:
    def test_maps_backend_families(self) -> None:
        assert prefixes_for_families("background_job", "pipeline", "alphafold") == (
            PREFIX_BACKGROUND_JOB,
            PREFIX_PIPELINE,
            PREFIX_ALPHAFOLD,
        )

    def test_aliases_round_trip(self) -> None:
        assert prefixes_for_families("structure", "alphafold_backend", "alphafold_structure") == (
            PREFIX_STRUCTURE_JOB,
            PREFIX_ALPHAFOLD,
            PREFIX_ALPHAFOLD,
        )


class _FakeSSEClient:
    def __init__(self, responses: list[list[SSEEvent]]):
        self._responses = responses
        self.calls: list[tuple[str, dict | None]] = []

    def snapshot(self, path: str, params: dict | None = None):
        self.calls.append((path, params))
        return self._responses.pop(0) if self._responses else []


class TestLiveEventFeedPrefixIntegration:
    def test_live_feed_serializes_operator_prefixes(self, monkeypatch) -> None:
        fake_streamlit = SimpleNamespace(session_state={})
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        feed = LiveEventFeed(
            api_url="http://localhost:8000",
            poll_limit=5,
            event_prefixes=OPERATOR_PREFIXES,
            transport="sse",
        )
        feed._sse_client = _FakeSSEClient(
            [[SSEEvent(event="pipeline.started", data={"timestamp": "t1"}, event_id="evt-1")]]
        )
        feed.poll()

        assert feed._sse_client.calls[0] == (
            "/agent/events",
            {"limit": 5, "prefix": ",".join(OPERATOR_PREFIXES)},
        )

    def test_dashboard_prefixes_cover_operator_and_pipeline_needs(self) -> None:
        assert set(OPERATOR_PREFIXES) <= set(DASHBOARD_PREFIXES)
        assert set(PIPELINE_PREFIXES) <= set(DASHBOARD_PREFIXES)
        assert set(SAFETY_PREFIXES) <= set(DASHBOARD_PREFIXES)
