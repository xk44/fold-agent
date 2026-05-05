"""Tests for derive_operator_context / format_operator_context — pure functions, no Streamlit dependency.

Covers:
- Empty session state → "No active selections"
- Event label extraction from live_event_drilldown_select
- Job label extraction from job_detail_select, enrichment from job_cards
- Case ID extraction from pipeline-case-selector (preferred) and inspect-case-selector (fallback)
- Report ID extraction from report-detail-{case_id}
- Structure job ID extraction from structure-job-{case_id}
- Filter suppression of FILTER_ALL sentinel
- Filter inclusion of specific filter values
- Prefocus key extraction
- Summary line composition
- format_operator_context: empty dict, partial context, full context
- Truncation of long event labels / job labels
- Enriched job when job_cards match
- Enriched job fallback when job_cards do not match
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_stream import (
    FILTER_ALL,
    derive_operator_context,
    format_operator_context,
    _CTX_EVENT_KEY,
    _CTX_JOB_KEY,
    _CTX_PIPELINE_CASE_KEY,
    _CTX_INSPECT_CASE_KEY,
    _CTX_REPORT_KEY_PREFIX,
    _CTX_STRUCTURE_JOB_KEY_PREFIX,
    _CTX_FILTER_STATUS_KEY,
    _CTX_FILTER_JOB_TYPE_KEY,
    _CTX_FILTER_CASE_ID_KEY,
    _CTX_PREFOCUS_REPORT_KEY,
    _CTX_PREFOCUS_CASE_KEY,
    _CTX_PREFOCUS_ARTIFACT_KEY,
)


# ---------------------------------------------------------------------------
# derive_operator_context — empty / minimal state
# ---------------------------------------------------------------------------

class TestDeriveOperatorContextEmpty:
    """Empty session state yields no active selections."""

    def test_empty_dict(self):
        ctx = derive_operator_context({})
        assert ctx["event_label"] == ""
        assert ctx["job_label"] == ""
        assert ctx["case_id"] == ""
        assert ctx["report_id"] == ""
        assert ctx["structure_job_id"] == ""
        assert ctx["filters"] == {}
        assert ctx["prefocus"] == {}
        assert ctx["summary_line"] == "No active selections"
        assert ctx["job_id"] == ""
        assert ctx["job_type"] == ""
        assert ctx["job_status"] == ""

    def test_none_values_treated_as_empty(self):
        ctx = derive_operator_context({
            _CTX_EVENT_KEY: None,
            _CTX_JOB_KEY: None,
            _CTX_PIPELINE_CASE_KEY: None,
        })
        assert ctx["event_label"] == ""
        assert ctx["job_label"] == ""
        assert ctx["case_id"] == ""


# ---------------------------------------------------------------------------
# Event label
# ---------------------------------------------------------------------------

class TestDeriveOperatorContextEvent:
    """Event label extraction."""

    def test_event_label_present(self):
        ctx = derive_operator_context({
            _CTX_EVENT_KEY: "case.created @ 2025-04-20 | case=c1",
        })
        assert ctx["event_label"] == "case.created @ 2025-04-20 | case=c1"
        assert "event:" in ctx["summary_line"]

    def test_event_label_empty_string(self):
        ctx = derive_operator_context({_CTX_EVENT_KEY: ""})
        assert ctx["event_label"] == ""
        assert "event:" not in ctx["summary_line"]

    def test_event_label_truncation(self):
        long_label = "x" * 120
        ctx = derive_operator_context({_CTX_EVENT_KEY: long_label})
        assert ctx["event_label"] == long_label  # stored raw
        # summary_line truncates display
        assert "event:" in ctx["summary_line"]
        assert "..." in ctx["summary_line"]


# ---------------------------------------------------------------------------
# Job label + enrichment from job_cards
# ---------------------------------------------------------------------------

class TestDeriveOperatorContextJob:
    """Job label extraction and enrichment."""

    def test_job_label_present_no_cards(self):
        ctx = derive_operator_context({
            _CTX_JOB_KEY: "pipeline_run — running (abc12345)",
        })
        assert ctx["job_label"] == "pipeline_run — running (abc12345)"
        assert ctx["job_id"] == ""
        assert ctx["job_type"] == ""
        assert ctx["job_status"] == ""
        assert "job:" in ctx["summary_line"]

    def test_job_label_enriched_from_cards(self):
        card = {
            "job_id": "abc123456789",
            "job_type": "pipeline_run",
            "status": "running",
        }
        label = "pipeline_run — running (abc12345)"
        ctx = derive_operator_context(
            {_CTX_JOB_KEY: label},
            job_cards=[card],
        )
        assert ctx["job_id"] == "abc123456789"
        assert ctx["job_type"] == "pipeline_run"
        assert ctx["job_status"] == "running"
        assert "pipeline_run · running · abc12345" in ctx["summary_line"]

    def test_job_label_no_match_in_cards_falls_back(self):
        card = {
            "job_id": "zzz99999",
            "job_type": "other_type",
            "status": "completed",
        }
        label = "pipeline_run — running (abc12345)"
        ctx = derive_operator_context(
            {_CTX_JOB_KEY: label},
            job_cards=[card],
        )
        # No match → enriched_job = job_label, no id/type/status
        assert ctx["job_id"] == ""
        assert ctx["job_type"] == ""
        assert ctx["job_status"] == ""
        assert "job:" in ctx["summary_line"]

    def test_job_label_empty(self):
        ctx = derive_operator_context({_CTX_JOB_KEY: ""}, job_cards=[])
        assert ctx["job_label"] == ""
        assert "job:" not in ctx["summary_line"]


# ---------------------------------------------------------------------------
# Case ID — pipeline preferred over inspect
# ---------------------------------------------------------------------------

class TestDeriveOperatorContextCase:
    """Case ID extraction with pipeline/inspect fallback."""

    def test_pipeline_case_selected(self):
        ctx = derive_operator_context({
            _CTX_PIPELINE_CASE_KEY: "case-alpha",
            _CTX_INSPECT_CASE_KEY: "case-beta",
        })
        assert ctx["case_id"] == "case-alpha"

    def test_inspect_case_fallback(self):
        ctx = derive_operator_context({
            _CTX_INSPECT_CASE_KEY: "case-beta",
        })
        assert ctx["case_id"] == "case-beta"

    def test_no_case(self):
        ctx = derive_operator_context({})
        assert ctx["case_id"] == ""

    def test_pipeline_empty_falls_to_inspect(self):
        ctx = derive_operator_context({
            _CTX_PIPELINE_CASE_KEY: "",
            _CTX_INSPECT_CASE_KEY: "case-gamma",
        })
        assert ctx["case_id"] == "case-gamma"


# ---------------------------------------------------------------------------
# Report ID — keyed per case
# ---------------------------------------------------------------------------

class TestDeriveOperatorContextReport:
    """Report ID extraction from report-detail-{case_id}."""

    def test_report_id_present(self):
        case_id = "case-42"
        ctx = derive_operator_context({
            _CTX_PIPELINE_CASE_KEY: case_id,
            f"{_CTX_REPORT_KEY_PREFIX}{case_id}": "rep-99ab",
        })
        assert ctx["report_id"] == "rep-99ab"
        assert "report:" in ctx["summary_line"]

    def test_no_report_id_without_case(self):
        ctx = derive_operator_context({
            f"{_CTX_REPORT_KEY_PREFIX}case-42": "rep-99ab",
        })
        # No case selected → report-detail key not consulted
        assert ctx["report_id"] == ""

    def test_report_id_empty(self):
        case_id = "case-42"
        ctx = derive_operator_context({
            _CTX_PIPELINE_CASE_KEY: case_id,
            f"{_CTX_REPORT_KEY_PREFIX}{case_id}": "",
        })
        assert ctx["report_id"] == ""


# ---------------------------------------------------------------------------
# Structure job ID — keyed per case
# ---------------------------------------------------------------------------

class TestDeriveOperatorContextStructureJob:
    """Structure job ID extraction from structure-job-{case_id}."""

    def test_structure_job_id_present(self):
        case_id = "case-42"
        ctx = derive_operator_context({
            _CTX_PIPELINE_CASE_KEY: case_id,
            f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}{case_id}": "sj-42b1",
        })
        assert ctx["structure_job_id"] == "sj-42b1"
        assert "struct:" in ctx["summary_line"]

    def test_no_structure_job_without_case(self):
        ctx = derive_operator_context({
            f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}case-42": "sj-42b1",
        })
        assert ctx["structure_job_id"] == ""


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

class TestDeriveOperatorContextFilters:
    """Filter extraction: specific values included, FILTER_ALL suppressed."""

    def test_specific_filters(self):
        ctx = derive_operator_context({
            _CTX_FILTER_STATUS_KEY: "running",
            _CTX_FILTER_JOB_TYPE_KEY: "pipeline_run",
            _CTX_FILTER_CASE_ID_KEY: "case-42",
        })
        assert ctx["filters"]["status"] == "running"
        assert ctx["filters"]["job_type"] == "pipeline_run"
        assert ctx["filters"]["case_id"] == "case-42"
        assert "filter:" in ctx["summary_line"]

    def test_filter_all_suppressed(self):
        ctx = derive_operator_context({
            _CTX_FILTER_STATUS_KEY: FILTER_ALL,
            _CTX_FILTER_JOB_TYPE_KEY: FILTER_ALL,
            _CTX_FILTER_CASE_ID_KEY: FILTER_ALL,
        })
        assert ctx["filters"] == {}

    def test_mixed_filters(self):
        ctx = derive_operator_context({
            _CTX_FILTER_STATUS_KEY: "running",
            _CTX_FILTER_JOB_TYPE_KEY: FILTER_ALL,
        })
        assert "status" in ctx["filters"]
        assert "job_type" not in ctx["filters"]

    def test_empty_filter_values_omitted(self):
        ctx = derive_operator_context({
            _CTX_FILTER_STATUS_KEY: "",
            _CTX_FILTER_JOB_TYPE_KEY: "",
        })
        assert ctx["filters"] == {}


# ---------------------------------------------------------------------------
# Prefocus
# ---------------------------------------------------------------------------

class TestDeriveOperatorContextPrefocus:
    """Prefocus key extraction (pre-consumption state)."""

    def test_prefocus_report(self):
        ctx = derive_operator_context({
            _CTX_PREFOCUS_REPORT_KEY: "rep-99ab",
        })
        assert ctx["prefocus"]["report_id"] == "rep-99ab"
        assert "prefocus:" in ctx["summary_line"]

    def test_prefocus_case(self):
        ctx = derive_operator_context({
            _CTX_PREFOCUS_CASE_KEY: "case-42",
        })
        assert ctx["prefocus"]["case_id"] == "case-42"

    def test_prefocus_artifact(self):
        ctx = derive_operator_context({
            _CTX_PREFOCUS_ARTIFACT_KEY: "/tmp/demo.pdb",
        })
        assert ctx["prefocus"]["artifact_path"] == "/tmp/demo.pdb"

    def test_no_prefocus_keys(self):
        ctx = derive_operator_context({})
        assert ctx["prefocus"] == {}

    def test_prefocus_none_values_omitted(self):
        ctx = derive_operator_context({
            _CTX_PREFOCUS_REPORT_KEY: None,
            _CTX_PREFOCUS_CASE_KEY: None,
        })
        assert ctx["prefocus"] == {}


# ---------------------------------------------------------------------------
# Summary line
# ---------------------------------------------------------------------------

class TestDeriveOperatorContextSummaryLine:
    """Summary line composition."""

    def test_no_selections(self):
        ctx = derive_operator_context({})
        assert ctx["summary_line"] == "No active selections"

    def test_single_event(self):
        ctx = derive_operator_context({
            _CTX_EVENT_KEY: "case.created",
        })
        assert ctx["summary_line"] == "event: case.created"

    def test_multiple_selections(self):
        case_id = "case-42"
        ctx = derive_operator_context({
            _CTX_EVENT_KEY: "pipeline.completed",
            _CTX_JOB_KEY: "pipeline_run — running (abc12345)",
            _CTX_PIPELINE_CASE_KEY: case_id,
            f"{_CTX_REPORT_KEY_PREFIX}{case_id}": "rep-99",
            f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}{case_id}": "sj-42",
        })
        assert "event:" in ctx["summary_line"]
        assert "job:" in ctx["summary_line"]
        assert "case:" in ctx["summary_line"]
        assert "report:" in ctx["summary_line"]
        assert "struct:" in ctx["summary_line"]
        # Parts joined by " | "
        assert " | " in ctx["summary_line"]

    def test_case_id_shortened_in_summary(self):
        ctx = derive_operator_context({
            _CTX_PIPELINE_CASE_KEY: "case-with-a-very-long-id-1234567890",
        })
        assert "case: case-wit" in ctx["summary_line"]  # first 8 chars


# ---------------------------------------------------------------------------
# format_operator_context
# ---------------------------------------------------------------------------

class TestFormatOperatorContext:
    """format_operator_context renders a compact multi-line block."""

    def test_empty_dict(self):
        result = format_operator_context({})
        assert "No operator context" in result

    def test_no_selections(self):
        ctx = derive_operator_context({})
        result = format_operator_context(ctx)
        assert "Operator context" in result
        assert "no active selections" in result

    def test_event_only(self):
        ctx = derive_operator_context({_CTX_EVENT_KEY: "case.created"})
        result = format_operator_context(ctx)
        assert "event:" in result
        assert "case.created" in result
        assert "job:" not in result

    def test_full_context(self):
        case_id = "case-42abcdef"
        card = {
            "job_id": "job-abc1234567",
            "job_type": "pipeline_run",
            "status": "running",
        }
        ctx = derive_operator_context(
            {
                _CTX_EVENT_KEY: "pipeline.completed",
                _CTX_JOB_KEY: "pipeline_run — running (job-abc1)",
                _CTX_PIPELINE_CASE_KEY: case_id,
                f"{_CTX_REPORT_KEY_PREFIX}{case_id}": "rep-99abcdef",
                f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}{case_id}": "sj-42abcdef",
                _CTX_FILTER_STATUS_KEY: "running",
            },
            job_cards=[card],
        )
        result = format_operator_context(ctx)
        assert "Operator context" in result
        assert "event:" in result
        assert "pipeline_run · running · job-abc1" in result
        assert "case:" in result
        assert "report:" in result
        assert "struct:" in result
        assert "filters:" in result
        assert "status=running" in result

    def test_job_label_without_enrichment(self):
        ctx = derive_operator_context({
            _CTX_JOB_KEY: "some_custom_label",
        })
        result = format_operator_context(ctx)
        assert "job:" in result
        assert "some_custom_label" in result

    def test_long_event_label_truncated(self):
        long_label = "A" * 120
        ctx = derive_operator_context({_CTX_EVENT_KEY: long_label})
        result = format_operator_context(ctx)
        assert "..." in result
        # The raw 120 chars should not appear
        assert "A" * 60 not in result

    def test_prefocus_shown(self):
        ctx = derive_operator_context({
            _CTX_PREFOCUS_REPORT_KEY: "rep-99ab",
        })
        result = format_operator_context(ctx)
        assert "prefocus:" in result
        assert "report_id=rep-99ab" in result

    def test_filters_sorted(self):
        ctx = derive_operator_context({
            _CTX_FILTER_STATUS_KEY: "running",
            _CTX_FILTER_CASE_ID_KEY: "c1",
        })
        result = format_operator_context(ctx)
        # case_id comes before status alphabetically
        assert result.index("case_id=c1") < result.index("status=running")


# ---------------------------------------------------------------------------
# Integration: constants match expected session state keys
# ---------------------------------------------------------------------------

class TestOperatorContextConstants:
    """Verify constants match the session state key conventions."""

    def test_event_key(self):
        assert _CTX_EVENT_KEY == "live_event_drilldown_select"

    def test_job_key(self):
        assert _CTX_JOB_KEY == "job_detail_select"

    def test_pipeline_case_key(self):
        assert _CTX_PIPELINE_CASE_KEY == "pipeline-case-selector"

    def test_inspect_case_key(self):
        assert _CTX_INSPECT_CASE_KEY == "inspect-case-selector"

    def test_report_key_prefix(self):
        assert _CTX_REPORT_KEY_PREFIX == "report-detail-"

    def test_structure_job_key_prefix(self):
        assert _CTX_STRUCTURE_JOB_KEY_PREFIX == "structure-job-"

    def test_prefocus_report_key(self):
        assert _CTX_PREFOCUS_REPORT_KEY == "prefocus_report_id"

    def test_prefocus_case_key(self):
        assert _CTX_PREFOCUS_CASE_KEY == "prefocus_case_id"

    def test_prefocus_artifact_key(self):
        assert _CTX_PREFOCUS_ARTIFACT_KEY == "prefocus_artifact_path"
