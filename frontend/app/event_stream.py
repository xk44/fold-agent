"""Backward-compatible facade for the event_stream module.

All public symbols that were previously defined in this single file are now
re-exported from their modular homes.  Existing imports like::

    from frontend.app.event_stream import derive_job_status_cards

continue to work unchanged.  New code should prefer importing from the
specific sub-module for clarity, but the facade ensures zero churn for
dashboards and tests.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Auto-refresh configuration
# ---------------------------------------------------------------------------
from frontend.app.event_stream_auto_refresh import (
    AutoRefreshConfig,
    compute_auto_refresh_config,
    format_auto_refresh_mode_label,
)

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
from frontend.app.event_stream_filters import (
    FILTER_ALL,
    derive_filter_options,
    apply_filters,
)

# ---------------------------------------------------------------------------
# Event formatting (pure, no Streamlit)
# ---------------------------------------------------------------------------
from frontend.app.event_stream_format import (
    format_sse_event_summary,
    format_sse_event_feed,
    format_sse_event_table_rows,
)

# ---------------------------------------------------------------------------
# Job status cards
# ---------------------------------------------------------------------------
from frontend.app.event_stream_job_status import (
    derive_job_status_cards,
    format_job_status_cards,
    build_job_status_table_rows,
    _severity_for_status,
)

# ---------------------------------------------------------------------------
# Retry / re-dispatch helpers
# ---------------------------------------------------------------------------
from frontend.app.event_stream_job_retry import (
    is_retry_eligible,
    retry_eligibility_reason,
    format_retry_status_badge,
    enrich_cards_with_retry_info,
    format_retry_action_summary,
    is_cancel_eligible,
    cancel_eligibility_reason,
    format_cancel_status_badge,
    enrich_cards_with_cancel_info,
    format_cancel_action_summary,
    _RETRYABLE_STATUSES,
)

# ---------------------------------------------------------------------------
# Job detail, linkback, and diagnosis
# ---------------------------------------------------------------------------
from frontend.app.event_stream_job_detail import (
    derive_structure_linkback,
    _STRUCTURE_JOB_TYPES,
    derive_blocked_failed_diagnosis,
    format_blocked_failed_diagnosis,
    _DIAGNOSIS_STATUSES,
    derive_job_detail,
    _derive_lifecycle_events,
    _format_lifecycle_entry,
    _format_payload_preview,
    format_job_detail,
    build_job_detail_table,
)

# ---------------------------------------------------------------------------
# Action chips, prefocus, macro focus, exact-open
# ---------------------------------------------------------------------------
from frontend.app.event_stream_action_chips import (
    CHIP_RETRY,
    CHIP_VIEW_STRUCTURE,
    CHIP_VIEW_REPORT,
    CHIP_VIEW_ARTIFACTS,
    CHIP_MACRO_FOCUS,
    derive_chip_prefocus,
    derive_macro_focus_bundle,
    derive_macro_focus_prefocus,
    derive_exact_open_metadata,
    derive_job_detail_actions,
    format_action_chips,
    format_action_chip_summary,
)

# ---------------------------------------------------------------------------
# Operator timeline
# ---------------------------------------------------------------------------
from frontend.app.event_stream_timeline import (
    _TL_CREATED,
    _TL_STATUS,
    _TL_LIFECYCLE,
    _TL_LINKBACK,
    _TL_RETRY,
    _TL_RESULT,
    _TL_ERROR,
    _TL_TYPE_LABELS,
    derive_operator_timeline,
    _severity_from_event_action,
    format_operator_timeline,
    build_operator_timeline_rows,
)

# ---------------------------------------------------------------------------
# Event detail helpers
# ---------------------------------------------------------------------------
from frontend.app.event_stream_event_detail import (
    derive_event_detail,
    derive_event_shortcuts,
    format_event_detail,
    format_event_payload_json,
)

# ---------------------------------------------------------------------------
# Operator context / focus restore
# ---------------------------------------------------------------------------
from frontend.app.event_stream_context import (
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
    _CTX_PREFOCUS_AUTO_OPEN_KEY,
    _RESTORABLE_FOCUS_KEYS,
    _RESTORABLE_FOCUS_PREFIXES,
    extract_restorable_focus,
    apply_restored_focus,
    derive_operator_context,
    format_operator_context,
)

# ---------------------------------------------------------------------------
# LiveEventFeed and auto-refresh renderer
# ---------------------------------------------------------------------------
from frontend.app.event_stream_live_feed import (
    LiveEventFeed,
    render_auto_refresh,
)

# ---------------------------------------------------------------------------
# Event-prefix presets per view role
# ---------------------------------------------------------------------------
from frontend.app.event_prefix_presets import (
    DASHBOARD_PREFIXES,
    OPERATOR_PREFIXES,
    PIPELINE_PREFIXES,
    SAFETY_PREFIXES,
    PREFIX_CASE,
    PREFIX_AGENT_TASK,
    PREFIX_PIPELINE,
    PREFIX_SAFETY,
    PREFIX_STRUCTURE,
    PREFIX_ALPHAFOLD_BACKEND,
    PREFIX_ALPHAFOLD_STRUCTURE,
    PREFIX_REPORT,
    merge_prefixes,
    prefixes_for_families,
    resolve_prefixes,
    validate_prefixes,
)

# Re-export the original top-level aliases that some consumers expect
# (e.g. the legacy name format_sse_event_table_rows was also
#  known as format_sse_event_table_rows in early versions)
__all__ = [
    # Auto-refresh
    "AutoRefreshConfig",
    "compute_auto_refresh_config",
    "format_auto_refresh_mode_label",
    # Filters
    "FILTER_ALL",
    "derive_filter_options",
    "apply_filters",
    # Event formatting
    "format_sse_event_summary",
    "format_sse_event_feed",
    "format_sse_event_table_rows",
    # Job status cards
    "derive_job_status_cards",
    "format_job_status_cards",
    "build_job_status_table_rows",
    "_severity_for_status",
    # Retry helpers
    "is_retry_eligible",
    "retry_eligibility_reason",
    "format_retry_status_badge",
    "enrich_cards_with_retry_info",
    "format_retry_action_summary",
    "is_cancel_eligible",
    "cancel_eligibility_reason",
    "format_cancel_status_badge",
    "enrich_cards_with_cancel_info",
    "format_cancel_action_summary",
    "_RETRYABLE_STATUSES",
    # Job detail / linkback / diagnosis
    "derive_structure_linkback",
    "_STRUCTURE_JOB_TYPES",
    "derive_blocked_failed_diagnosis",
    "format_blocked_failed_diagnosis",
    "_DIAGNOSIS_STATUSES",
    "derive_job_detail",
    "_derive_lifecycle_events",
    "_format_lifecycle_entry",
    "_format_payload_preview",
    "format_job_detail",
    "build_job_detail_table",
    # Action chips / focus
    "CHIP_RETRY",
    "CHIP_VIEW_STRUCTURE",
    "CHIP_VIEW_REPORT",
    "CHIP_VIEW_ARTIFACTS",
    "CHIP_MACRO_FOCUS",
    "derive_chip_prefocus",
    "derive_macro_focus_bundle",
    "derive_macro_focus_prefocus",
    "derive_exact_open_metadata",
    "derive_job_detail_actions",
    "format_action_chips",
    "format_action_chip_summary",
    # Operator timeline
    "_TL_CREATED",
    "_TL_STATUS",
    "_TL_LIFECYCLE",
    "_TL_LINKBACK",
    "_TL_RETRY",
    "_TL_RESULT",
    "_TL_ERROR",
    "_TL_TYPE_LABELS",
    "derive_operator_timeline",
    "_severity_from_event_action",
    "format_operator_timeline",
    "build_operator_timeline_rows",
    # Event detail
    "derive_event_detail",
    "derive_event_shortcuts",
    "format_event_detail",
    "format_event_payload_json",
    # Operator context / focus
    "_CTX_EVENT_KEY",
    "_CTX_JOB_KEY",
    "_CTX_PIPELINE_CASE_KEY",
    "_CTX_INSPECT_CASE_KEY",
    "_CTX_REPORT_KEY_PREFIX",
    "_CTX_STRUCTURE_JOB_KEY_PREFIX",
    "_CTX_FILTER_STATUS_KEY",
    "_CTX_FILTER_JOB_TYPE_KEY",
    "_CTX_FILTER_CASE_ID_KEY",
    "_CTX_PREFOCUS_REPORT_KEY",
    "_CTX_PREFOCUS_CASE_KEY",
    "_CTX_PREFOCUS_ARTIFACT_KEY",
    "_CTX_PREFOCUS_AUTO_OPEN_KEY",
    "_RESTORABLE_FOCUS_KEYS",
    "_RESTORABLE_FOCUS_PREFIXES",
    "extract_restorable_focus",
    "apply_restored_focus",
    "derive_operator_context",
    "format_operator_context",
    # Live feed
    "LiveEventFeed",
    "render_auto_refresh",
    # Event-prefix presets
    "DASHBOARD_PREFIXES",
    "OPERATOR_PREFIXES",
    "PIPELINE_PREFIXES",
    "SAFETY_PREFIXES",
    "PREFIX_CASE",
    "PREFIX_AGENT_TASK",
    "PREFIX_PIPELINE",
    "PREFIX_SAFETY",
    "PREFIX_STRUCTURE",
    "PREFIX_ALPHAFOLD_BACKEND",
    "PREFIX_ALPHAFOLD_STRUCTURE",
    "PREFIX_REPORT",
    "merge_prefixes",
    "prefixes_for_families",
    "resolve_prefixes",
    "validate_prefixes",
]