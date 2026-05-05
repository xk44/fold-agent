"""Job-detail action chips — derive available actions from job detail / card.

Also includes prefocus, macro focus, and exact-open helpers.

Extracted from event_stream.py for modularity.  This module depends on
:mod:`event_stream_job_detail` (for ``derive_structure_linkback``) and
:mod:`event_stream_job_retry` (for ``is_retry_eligible``).
"""
from __future__ import annotations

from frontend.app.event_stream_job_detail import derive_structure_linkback
from frontend.app.event_stream_job_retry import is_retry_eligible
from frontend.app.event_stream_context import (
    _CTX_PREFOCUS_ARTIFACT_KEY,
    _CTX_PREFOCUS_AUTO_OPEN_KEY,
)


# ---------------------------------------------------------------------------
# Chip action types
# ---------------------------------------------------------------------------

CHIP_RETRY = "retry"
CHIP_VIEW_STRUCTURE = "view_structure"
CHIP_VIEW_REPORT = "view_report"
CHIP_VIEW_ARTIFACTS = "view_artifacts"
CHIP_MACRO_FOCUS = "macro_focus"


def derive_chip_prefocus(chip: dict) -> dict | None:
    """Derive session-state preselection metadata from an action chip.

    Returns a dict of ``{session_state_key: value}`` pairs that the dashboard
    should apply before calling ``st.rerun()`` so the target item is
    pre-selected when the page re-renders.

    Supported chip types and the prefocus keys they produce:

    - **view_report**: sets ``prefocus_report_id`` (when derivable) and
      ``prefocus_case_id``, plus the ``pipeline-case-selector`` /
      ``inspect-case-selector`` case-switch keys.
    - **view_artifacts**: sets ``prefocus_artifact_path`` (first explicit path)
      and ``prefocus_case_id``, plus case-switch keys.
    - **view_structure**: sets ``structure-job-{case_id}`` and
      ``pipeline-case-selector`` (mirrors the existing strong linkback).

    Returns ``None`` when no prefocus metadata can be derived (e.g. no
    ``case_id``, or an unrecognised action).

    This is a **pure function** — no Streamlit dependency.
    """
    action = chip.get("action", "")
    data = chip.get("data") or {}

    if action == CHIP_VIEW_REPORT:
        case_id = data.get("case_id")
        report_id = data.get("report_id")
        if not case_id:
            return None
        prefocus: dict = {
            "prefocus_case_id": case_id,
            "pipeline-case-selector": case_id,
            "inspect-case-selector": case_id,
        }
        if report_id:
            prefocus["prefocus_report_id"] = report_id
        return prefocus

    if action == CHIP_VIEW_ARTIFACTS:
        case_id = data.get("case_id")
        artifact_paths = data.get("artifact_paths") or []
        if not case_id:
            return None
        prefocus = {
            "prefocus_case_id": case_id,
            "pipeline-case-selector": case_id,
            "inspect-case-selector": case_id,
        }
        if artifact_paths:
            prefocus[_CTX_PREFOCUS_ARTIFACT_KEY] = artifact_paths[0]
        return prefocus

    if action == CHIP_VIEW_STRUCTURE:
        case_id = data.get("case_id")
        structure_job_id = data.get("structure_job_id")
        if not case_id:
            return None
        prefocus = {
            "prefocus_case_id": case_id,
            "pipeline-case-selector": case_id,
        }
        if structure_job_id:
            prefocus[f"structure-job-{case_id}"] = structure_job_id
        return prefocus

    return None


def derive_macro_focus_bundle(
    job_card: dict,
    api_job: dict | None = None,
) -> dict | None:
    """Derive a macro-focus bundle from a job card and optional API payload.

    A **macro-focus bundle** is a dict that aggregates case, report, and
    structure identifiers from the same job.  When all three dimensions
    (case, report, structure) are derivable from the same job detail, the
    operator can jump to a fully pre-selected view with a single click,
    rather than navigating through individual chip actions.

    The returned dict (when not ``None``) contains:

    - ``case_id``: The case identifier (always present if derivable).
    - ``report_id``: Report ID, if the job references one (``None`` otherwise).
    - ``structure_job_id``: Structure job ID, if derivable (``None`` otherwise).
    - ``candidate_id``: Candidate ID from payload, if present (``None`` otherwise).
    - ``artifact_paths``: List of artifact paths if derivable (``[]`` otherwise).
    - ``job_type``: Job type string.
    - ``has_report``: ``True`` if a report is derivable.
    - ``has_structure``: ``True`` if a structure linkback is derivable.
    - ``has_artifacts``: ``True`` if artifacts are derivable.
    - ``dimensions``: Number of focusable dimensions (1–4, always >= 1
      because a ``case_id`` is required).

    Returns ``None`` when no ``case_id`` can be derived — a macro focus
    makes no sense without a case to focus on.

    This is a **pure function** — no Streamlit dependency.
    """
    detail = api_job or job_card
    case_id = detail.get("case_id") or job_card.get("case_id")
    if not case_id:
        return None

    job_type = detail.get("job_type", "")
    result = detail.get("result") or {}
    payload = detail.get("payload") or {}

    # --- Report dimension ---
    report_id = (
        (result.get("report_id") if isinstance(result, dict) else None)
        or (payload.get("report_id") if isinstance(payload, dict) else None)
    )
    if not report_id and isinstance(result, dict):
        nested_report = result.get("report") or {}
        if isinstance(nested_report, dict):
            report_id = nested_report.get("id") or nested_report.get("report_id")

    has_likely_report = bool(
        report_id is not None
        or (
            detail.get("status") == "completed"
            and job_type in {"pipeline_run", "report_generation"}
        )
        or (isinstance(result, dict) and result.get("report_url"))
    )

    # --- Structure dimension ---
    linkback = derive_structure_linkback(job_card, api_job=api_job)
    has_structure = linkback is not None
    structure_job_id = linkback.get("structure_job_id") if linkback else None
    candidate_id = linkback.get("candidate_id") if linkback else None

    # --- Artifacts dimension ---
    artifact_paths: list[str] = []
    seen_paths: set[str] = set()
    if isinstance(result, dict):
        for key in ("output_file", "artifact_path", "model_cif", "pdb_file"):
            val = result.get(key)
            if isinstance(val, str) and val and val not in seen_paths:
                artifact_paths.append(val)
                seen_paths.add(val)
        execution = result.get("execution") or {}
        if isinstance(execution, dict):
            for key in ("output_path", "log_path"):
                val = execution.get(key)
                if isinstance(val, str) and val and val not in seen_paths:
                    artifact_paths.append(val)
                    seen_paths.add(val)
    if isinstance(payload, dict):
        for key in ("output_path", "artifact_path"):
            val = payload.get(key)
            if isinstance(val, str) and val and val not in seen_paths:
                artifact_paths.append(val)
                seen_paths.add(val)

    artifact_producing_types = {
        "pipeline_run",
        "alphafold_backend",
        "alphafold_structure",
        "shell_execution",
    }
    status = detail.get("status", "unknown")
    has_artifacts = (
        len(artifact_paths) > 0
        or (status == "completed" and job_type in artifact_producing_types)
    )

    # --- Dimensions count ---
    dimensions = 1  # case_id always counts as 1
    if has_likely_report:
        dimensions += 1
    if has_structure:
        dimensions += 1
    if has_artifacts:
        dimensions += 1

    return {
        "case_id": case_id,
        "report_id": report_id,
        "structure_job_id": structure_job_id,
        "candidate_id": candidate_id,
        "artifact_paths": artifact_paths,
        "job_type": job_type,
        "has_report": has_likely_report,
        "has_structure": has_structure,
        "has_artifacts": has_artifacts,
        "dimensions": dimensions,
    }


def derive_macro_focus_prefocus(bundle: dict | None) -> dict | None:
    """Derive session-state preselection metadata from a macro-focus bundle.

    Takes the output of :func:`derive_macro_focus_bundle` and produces a
    flat dict of ``{session_state_key: value}`` pairs that the dashboard
    should apply before calling ``st.rerun()``.  This combines all
    derivable prefocus keys from the individual chips into a single
    consolidated set, so the operator lands with case, report, structure,
    and artifact selectors all pre-set.

    The returned dict includes (when applicable):

    - ``prefocus_case_id``
    - ``pipeline-case-selector``
    - ``inspect-case-selector``
    - ``prefocus_report_id`` (if report is derivable and has an explicit ID)
    - ``structure-job-{case_id}`` (if structure is derivable)
    - ``prefocus_artifact_path`` (first artifact path, when available)

    Returns ``None`` if *bundle* is ``None`` (no macro focus derivable).

    This is a **pure function** — no Streamlit dependency.
    """
    if bundle is None:
        return None

    case_id = bundle.get("case_id")
    if not case_id:
        return None

    prefocus: dict = {
        "prefocus_case_id": case_id,
        "pipeline-case-selector": case_id,
        "inspect-case-selector": case_id,
    }

    if bundle.get("has_report") and bundle.get("report_id"):
        prefocus["prefocus_report_id"] = bundle["report_id"]

    if bundle.get("has_structure") and bundle.get("structure_job_id"):
        prefocus[f"structure-job-{case_id}"] = bundle["structure_job_id"]

    artifact_paths = bundle.get("artifact_paths") or []
    if artifact_paths:
        prefocus["prefocus_artifact_path"] = artifact_paths[0]

    # When exactly one artifact path is derivable, mark it for auto-open
    # so the dashboard can load the content directly without a second click.
    exact_open = derive_exact_open_metadata(bundle)
    if exact_open is not None:
        prefocus[_CTX_PREFOCUS_AUTO_OPEN_KEY] = exact_open

    return prefocus


# ---------------------------------------------------------------------------
# Exact-open metadata — decide whether artifact content should auto-load
# ---------------------------------------------------------------------------

def derive_exact_open_metadata(bundle: dict | None) -> dict | None:
    """Derive exact-open metadata from a macro-focus bundle.

    When a single unambiguous artifact path is available, this helper
    returns a dict signalling that the dashboard should auto-load the
    artifact content into the focused state (without requiring a second
    click on "Load artifact file").

    The returned dict (when not ``None``) contains:

    - ``auto_open``: Always ``True`` — the caller should auto-open.
    - ``artifact_path``: The single artifact path to auto-open.
    - ``case_id``: The case ID (for constructing session-state keys).

    Returns ``None`` when:

    - *bundle* is ``None`` or has no ``case_id``
    - ``has_artifacts`` is ``False``
    - ``artifact_paths`` is empty or has more than one entry (ambiguous)

    The rationale for requiring exactly one artifact: when multiple paths
    exist, preselecting one is useful but auto-opening might select the
    wrong one.  With a single path the choice is unambiguous.

    This is a **pure function** — no Streamlit dependency.
    """
    if bundle is None:
        return None

    case_id = bundle.get("case_id")
    if not case_id:
        return None

    if not bundle.get("has_artifacts"):
        return None

    artifact_paths = bundle.get("artifact_paths") or []
    if len(artifact_paths) != 1:
        # Zero paths: nothing to open.  Multiple paths: ambiguous.
        return None

    return {
        "auto_open": True,
        "artifact_path": artifact_paths[0],
        "case_id": case_id,
    }


def derive_job_detail_actions(
    job_card: dict,
    api_job: dict | None = None,
) -> list[dict]:
    """Derive available action chips from a job card and optional API job payload.

    Each returned chip dict has:
      - ``action``: one of the CHIP_* constants (e.g. ``"retry"``, ``"view_structure"``)
      - ``label``: short human-readable label for the chip button
      - ``description``: one-line explanation of what the chip does
      - ``enabled``: whether the chip is currently actionable
      - ``data``: dict carrying key identifiers the dashboard needs to act
        (e.g. ``job_id``, ``structure_job_id``, ``case_id``, ``report_id``)

    Derivation rules:
    - **retry**: shown when ``is_retry_eligible`` is True.
    - **view_structure**: shown when ``derive_structure_linkback`` returns a
      non-None result (structure-related jobs).
    - **view_report**: shown when the job's ``result`` or ``payload`` references
      a report ID or the job is completed with a case that likely has reports.
    - **view_artifacts**: shown when the job's ``result`` or ``payload`` references
      artifact paths, or the job type commonly produces artifacts.

    This is a **pure function** — no Streamlit dependency.
    """
    chips: list[dict] = []
    detail = api_job or job_card
    job_id = detail.get("job_id") or detail.get("id") or ""
    job_type = detail.get("job_type", "")
    case_id = detail.get("case_id") or job_card.get("case_id") or ""
    status = detail.get("status", "unknown")

    # --- Retry chip ---
    if is_retry_eligible(detail):
        attempt = detail.get("attempt", 1) or 1
        max_retries = detail.get("max_retries", 0) or 0
        retries_remaining = (max_retries + 1) - attempt
        chips.append({
            "action": CHIP_RETRY,
            "label": "Retry",
            "description": f"Re-dispatch this failed job ({retries_remaining} attempt(s) remaining)",
            "enabled": True,
            "data": {
                "job_id": job_id,
                "job_type": job_type,
                "attempt": attempt,
                "max_retries": max_retries,
            },
        })

    # --- View structure chip ---
    linkback = derive_structure_linkback(job_card, api_job=api_job)
    if linkback:
        chips.append({
            "action": CHIP_VIEW_STRUCTURE,
            "label": linkback.get("label", "View structure"),
            "description": (
                f"Open structure job explorer for case {linkback.get('case_id', '?')}"
                + (f", structure {linkback['structure_job_id'][:8]}" if linkback.get("structure_job_id") else "")
            ),
            "enabled": True,
            "data": {
                "job_id": job_id,
                "case_id": linkback.get("case_id", case_id),
                "structure_job_id": linkback.get("structure_job_id"),
                "candidate_id": linkback.get("candidate_id"),
                "surface": linkback.get("surface", "structure_job_explorer"),
            },
        })

    # --- View report chip ---
    # Derivable when result has report_id, or payload references a report,
    # or the job is a completed pipeline run (which typically generates reports).
    result = detail.get("result") or {}
    payload = detail.get("payload") or {}
    report_id = (
        (result.get("report_id") if isinstance(result, dict) else None)
        or (payload.get("report_id") if isinstance(payload, dict) else None)
    )
    # Also check for report in nested result structures
    if not report_id and isinstance(result, dict):
        nested_report = result.get("report") or {}
        if isinstance(nested_report, dict):
            report_id = nested_report.get("id") or nested_report.get("report_id")

    # Completed pipeline runs often produce reports — make it discoverable
    has_likely_report = (
        report_id is not None
        or (status == "completed" and job_type in {"pipeline_run", "report_generation"})
        or (isinstance(result, dict) and result.get("report_url"))
    )

    if has_likely_report:
        chips.append({
            "action": CHIP_VIEW_REPORT,
            "label": "View report",
            "description": (
                f"Open report {report_id[:8]}" if report_id
                else f"Open latest report for case {case_id[:8] if case_id else '?'}"
            ),
            "enabled": True,
            "data": {
                "job_id": job_id,
                "case_id": case_id,
                "report_id": report_id,
                "job_type": job_type,
            },
        })

    # --- View artifacts chip ---
    # Derivable when result references artifact paths, or the job type
    # commonly produces artifacts (alphafold, pipeline, execution).
    artifact_paths: list[str] = []
    if isinstance(result, dict):
        for key in ("output_file", "artifact_path", "model_cif", "pdb_file"):
            val = result.get(key)
            if isinstance(val, str) and val:
                artifact_paths.append(val)
        # Nested execution result
        execution = result.get("execution") or {}
        if isinstance(execution, dict):
            for key in ("output_path", "log_path"):
                val = execution.get(key)
                if isinstance(val, str) and val:
                    artifact_paths.append(val)

    if isinstance(payload, dict):
        for key in ("output_path", "artifact_path"):
            val = payload.get(key)
            if isinstance(val, str) and val:
                artifact_paths.append(val)

    artifact_producing_types = {
        "pipeline_run",
        "alphafold_backend",
        "alphafold_structure",
        "shell_execution",
    }
    has_artifacts = (
        len(artifact_paths) > 0
        or (status == "completed" and job_type in artifact_producing_types)
    )

    if has_artifacts:
        chips.append({
            "action": CHIP_VIEW_ARTIFACTS,
            "label": "View artifacts",
            "description": (
                f"Browse {len(artifact_paths)} artifact(s)" if artifact_paths
                else f"Browse artifacts for case {case_id[:8] if case_id else '?'}"
            ),
            "enabled": True,
            "data": {
                "job_id": job_id,
                "case_id": case_id,
                "artifact_paths": artifact_paths,
                "job_type": job_type,
            },
        })

    # --- Macro focus chip ---
    # Available when the job has enough metadata to preselect at least
    # case + one additional dimension (report, structure, or artifacts).
    macro_bundle = derive_macro_focus_bundle(job_card, api_job=api_job)
    if macro_bundle and macro_bundle.get("dimensions", 0) >= 2:
        dim_labels: list[str] = ["case"]
        if macro_bundle.get("has_report"):
            dim_labels.append("report")
        if macro_bundle.get("has_structure"):
            dim_labels.append("structure")
        if macro_bundle.get("has_artifacts"):
            dim_labels.append("artifacts")
        chips.append({
            "action": CHIP_MACRO_FOCUS,
            "label": "Focus all",
            "description": (
                f"One-click focus: {' + '.join(dim_labels)} "
                f"for case {case_id[:8] if case_id else '?'}"
            ),
            "enabled": True,
            "data": macro_bundle,
        })

    return chips


def format_action_chips(chips: list[dict]) -> str:
    """Render action chips as a compact, operator-oriented text line.

    Pure function — no Streamlit dependency.

    Example output::

        ↻ Retry · 🔬 View structure · 📄 View report · 📦 View artifacts
    """
    if not chips:
        return "No actions available."

    icon_map = {
        CHIP_RETRY: "↻",
        CHIP_VIEW_STRUCTURE: "🔬",
        CHIP_VIEW_REPORT: "📄",
        CHIP_VIEW_ARTIFACTS: "📦",
        CHIP_MACRO_FOCUS: "🎯",
    }
    parts = []
    for chip in chips:
        icon = icon_map.get(chip["action"], "•")
        label = chip.get("label", chip["action"])
        enabled = chip.get("enabled", True)
        if enabled:
            parts.append(f"{icon} {label}")
        else:
            parts.append(f"{icon} {label} (unavailable)")
    return " · ".join(parts)


def format_action_chip_summary(chips: list[dict]) -> str:
    """Render a multi-line summary of action chips with descriptions.

    Pure function — no Streamlit dependency.

    Example::

        Available actions — 3 chip(s)
          [↻] Retry — Re-dispatch this failed job (2 attempt(s) remaining)
          [🔬] View structure — Open structure job explorer for case case-1, structure sj-1
          [📄] View report — Open report rep-1
    """
    if not chips:
        return "No actions available."

    lines = [f"Available actions — {len(chips)} chip(s)"]
    for chip in chips:
        action = chip.get("action", "?")
        label = chip.get("label", action)
        description = chip.get("description", "")
        enabled = chip.get("enabled", True)
        status_marker = "" if enabled else " (unavailable)"
        lines.append(f"  [{action}] {label}{status_marker} — {description}")
    return "\n".join(lines)