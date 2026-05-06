"""Small shared helpers extracted from dashboard.py.

Pure-logic utilities with no Streamlit dependency.  The dashboard and the
extracted panel modules all import from here so that behaviour stays
identical while dashboard.py gets shorter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

HealthStatusLevel = Literal["ok", "degraded", "unreachable"]


def classify_health_status(
    payload: dict[str, Any] | None, error: str | None = None
) -> HealthStatusLevel:
    """Classify a health payload for operator-facing dashboard rendering."""
    if error or not payload:
        return "unreachable"
    status = str(payload.get("status") or "").lower()
    db_status = str(payload.get("db_status") or "").lower()
    if status == "degraded" or db_status == "degraded" or payload.get("missing_tables"):
        return "degraded"
    return "ok"


def format_health_status_summary(payload: dict[str, Any] | None, error: str | None = None) -> str:
    """Build a compact, actionable health summary for the operator dashboard."""
    level = classify_health_status(payload, error)
    if level == "unreachable":
        return f"API unreachable: {error or 'no health payload returned'}"

    payload = payload or {}
    status = str(payload.get("status") or level)
    db_status = str(payload.get("db_status") or "unknown")
    tables_present = payload.get("tables_present", "?")
    tables_expected = payload.get("tables_expected", "?")
    missing_tables = [str(item) for item in payload.get("missing_tables") or []]
    table_summary = f"{tables_present} / {tables_expected} tables present"

    parts = [f"API {status}", f"DB {db_status}", table_summary]
    if missing_tables:
        parts.append(f"missing: {', '.join(missing_tables)}")
    if payload.get("db_init_mode"):
        parts.append(f"db_init_mode: {payload['db_init_mode']}")
    if payload.get("database_url"):
        parts.append(f"database: {payload['database_url']}")
    if payload.get("error"):
        parts.append(f"error: {payload['error']}")
    return " — ".join(parts)


def parse_due_date(value: str | None):
    """Parse an ISO-8601 due-date string (trailing ``Z`` accepted)."""
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def is_task_overdue(task: dict[str, Any], now: datetime | None = None) -> bool:
    """Return True when a task is overdue and not already done."""
    due = parse_due_date(task.get("due_date"))
    if due is None:
        return False
    current_time = now or datetime.now(UTC)
    return bool(due < current_time and task.get("status") not in {"done"})


def task_sort_key(task: dict):
    """Sort key that orders tasks by due-date, then title."""
    due = parse_due_date(task.get("due_date"))
    return (due is None, due or datetime.max.replace(tzinfo=UTC), task.get("title") or "")


def build_provenance_summary(
    variants: list[dict] | None, candidates: list[dict] | None
) -> dict[str, Any]:
    """Collect provenance/source metrics used by the case inspection view."""
    variant_sources = sorted(
        {
            (variant.get("quality_metrics") or {}).get("parsed_from")
            for variant in (variants or [])
            if (variant.get("quality_metrics") or {}).get("parsed_from")
        }
    )
    candidate_sources = sorted(
        {
            (candidate.get("prediction_scores") or {}).get("parsed_from")
            for candidate in (candidates or [])
            if (candidate.get("prediction_scores") or {}).get("parsed_from")
        }
    )
    structure_backends = sorted(
        {
            (candidate.get("structure_evidence") or {}).get("backend")
            for candidate in (candidates or [])
            if (candidate.get("structure_evidence") or {}).get("backend")
        }
    )
    structure_statuses = sorted(
        {
            (candidate.get("structure_evidence") or {}).get("alphafold_status")
            for candidate in (candidates or [])
            if (candidate.get("structure_evidence") or {}).get("alphafold_status")
        }
    )
    variant_execution_ids = [
        variant.get("last_parsed_execution_id")
        for variant in (variants or [])
        if variant.get("last_parsed_execution_id")
    ]
    candidate_execution_ids = [
        candidate.get("last_parsed_execution_id")
        for candidate in (candidates or [])
        if candidate.get("last_parsed_execution_id")
    ]
    structure_scores = [
        candidate.get("structure_evidence") or {}
        for candidate in (candidates or [])
        if candidate.get("structure_evidence")
    ]
    combined_execution_ids: list[str] = []
    for execution_id in variant_execution_ids + candidate_execution_ids:
        if execution_id not in combined_execution_ids:
            combined_execution_ids.append(execution_id)
    return {
        "variant_sources": variant_sources,
        "candidate_sources": candidate_sources,
        "structure_backends": structure_backends,
        "structure_statuses": structure_statuses,
        "variant_execution_ids": variant_execution_ids,
        "candidate_execution_ids": candidate_execution_ids,
        "best_ranking_score": max(
            (
                item.get("ranking_score")
                for item in structure_scores
                if item.get("ranking_score") is not None
            ),
            default="n/a",
        ),
        "best_ptm": max(
            (item.get("ptm") for item in structure_scores if item.get("ptm") is not None),
            default="n/a",
        ),
        "best_iptm": max(
            (item.get("iptm") for item in structure_scores if item.get("iptm") is not None),
            default="n/a",
        ),
        "combined_execution_ids": combined_execution_ids,
    }


def build_case_governance_summary(
    case_detail: dict[str, Any] | None,
    subjects: list[dict] | None = None,
    samples: list[dict] | None = None,
) -> dict[str, Any]:
    """Summarize case-level governance and subject linkage state for the operator UI."""
    case_detail = case_detail or {}
    subjects = subjects or []
    samples = samples or []
    subject_ids = {subject.get("id") for subject in subjects if subject.get("id")}
    linked_sample_count = sum(1 for sample in samples if sample.get("subject_id") in subject_ids)
    redacted_subject_count = sum(
        1
        for subject in subjects
        if (subject.get("privacy_flags") or {}).get("redacted")
        or str(subject.get("redaction_level") or "full") in {"deidentify", "anonymous", "deleted"}
    )
    return {
        "species": str(case_detail.get("species") or "n/a"),
        "consent_status": str(case_detail.get("consent_status") or "unknown"),
        "review_status": str(case_detail.get("review_status") or "unknown"),
        "redaction_level": str(case_detail.get("redaction_level") or "full"),
        "subject_count": len(subjects),
        "linked_sample_count": linked_sample_count,
        "redacted_subject_count": redacted_subject_count,
        "supervising_professional": case_detail.get("supervising_professional") or "",
        "diagnosis_summary": case_detail.get("diagnosis_summary") or "",
    }


def build_subject_governance_rows(
    subjects: list[dict] | None,
    samples: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """Build richer per-subject governance rows for privacy/detail drilldown."""
    sample_buckets: dict[str, list[str]] = {}
    for sample in samples or []:
        subject_id = sample.get("subject_id")
        if not subject_id:
            continue
        sample_buckets.setdefault(subject_id, [])
        sample_type = sample.get("sample_type")
        if sample_type:
            sample_buckets[subject_id].append(str(sample_type))

    rows: list[dict[str, Any]] = []
    for subject in subjects or []:
        metadata = subject.get("metadata_json") or {}
        privacy_flags = subject.get("privacy_flags") or {}
        subject_sample_types = sorted(
            {item for item in sample_buckets.get(subject.get("id"), []) if item}
        )
        rows.append(
            {
                "id": subject.get("id"),
                "display_name": subject.get("anonymized_display_name")
                or subject.get("id")
                or "unknown",
                "privacy_mode": (
                    str(subject.get("redaction_level"))
                    if str(subject.get("redaction_level") or "full")
                    in {"deidentify", "anonymous", "deleted"}
                    else ("redacted" if privacy_flags.get("redacted") else "standard")
                ),
                "species": metadata.get("species") or "",
                "intake_notes": metadata.get("intake_notes") or "",
                "linked_samples": len(sample_buckets.get(subject.get("id"), [])),
                "sample_types": ", ".join(subject_sample_types) or "",
                "created_at": subject.get("created_at") or "",
            }
        )
    return rows


def flatten_candidate_rows(candidates: list[dict] | None) -> list[dict]:
    """Flatten nested candidate dicts into flat rows for a dataframe."""
    rows = []
    for candidate in candidates or []:
        structure = candidate.get("structure_evidence") or {}
        prediction_scores = candidate.get("prediction_scores") or {}
        peptide_metadata = candidate.get("peptide_metadata") or {}
        rows.append(
            {
                "id": candidate.get("id"),
                "variant_id": candidate.get("variant_id"),
                "mhc_context": candidate.get("mhc_context"),
                "peptide_sequence": peptide_metadata.get("sequence"),
                "binding_rank": prediction_scores.get("binding_rank"),
                "immunogenicity": prediction_scores.get("immunogenicity"),
                "structure_backend": structure.get("backend"),
                "structure_status": structure.get("alphafold_status"),
                "ranking_score": structure.get("ranking_score"),
                "ptm": structure.get("ptm"),
                "iptm": structure.get("iptm"),
                "model_cif": structure.get("model_cif") or structure.get("pdb_file"),
                "source_url": structure.get("source_url"),
                "review_status": candidate.get("review_status"),
                "last_parsed_execution_id": candidate.get("last_parsed_execution_id"),
            }
        )
    return rows


def normalize_table_rows(rows: list[dict] | None) -> list[dict[str, str]]:
    """Normalize heterogeneous row payloads for safer Streamlit dataframe rendering."""
    normalized: list[dict[str, str]] = []
    for row in rows or []:
        normalized_row: dict[str, str] = {}
        for key, value in (row or {}).items():
            if value is None:
                normalized_row[key] = ""
            elif isinstance(value, bool):
                normalized_row[key] = "true" if value else "false"
            else:
                normalized_row[key] = str(value)
        normalized.append(normalized_row)
    return normalized
