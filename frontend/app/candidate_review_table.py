from __future__ import annotations

from typing import Any

_CANDIDATE_COLUMN_PRESETS: dict[str, list[str]] = {
    "review": [
        "mhc_context",
        "peptide_sequence",
        "binding_rank",
        "immunogenicity",
        "ranking_score",
        "review_status",
    ],
    "structure": [
        "mhc_context",
        "structure_backend",
        "structure_status",
        "ranking_score",
        "ptm",
        "iptm",
        "model_cif",
    ],
}

_REPORT_TYPE_PRIORITY = {
    "candidate_review": 0,
    "ethics_package": 1,
}


def _candidate_numeric_value(candidate: dict, sort_key: str) -> float | None:
    structure = candidate.get("structure_evidence") or {}
    prediction_scores = candidate.get("prediction_scores") or {}
    if sort_key == "ranking_score":
        value = structure.get("ranking_score")
        if value is None:
            value = prediction_scores.get("binding_rank")
        return None if value is None else float(value)
    if sort_key == "binding_rank":
        value = prediction_scores.get("binding_rank")
        return None if value is None else float(value)
    return None


def build_candidate_column_presets() -> dict[str, list[str]]:
    return {name: list(columns) for name, columns in _CANDIDATE_COLUMN_PRESETS.items()}


def filter_candidates(
    candidates: list[dict] | None,
    *,
    review_status: str = "all",
    mhc_context: str = "all",
    ranking_score_min: float | None = None,
    binding_rank_max: float | None = None,
) -> list[dict]:
    filtered = list(candidates or [])
    if review_status != "all":
        filtered = [
            candidate
            for candidate in filtered
            if str(candidate.get("review_status") or "") == review_status
        ]
    if mhc_context != "all":
        filtered = [
            candidate
            for candidate in filtered
            if str(candidate.get("mhc_context") or "") == mhc_context
        ]
    if ranking_score_min is not None:
        filtered = [
            candidate
            for candidate in filtered
            if (score := _candidate_numeric_value(candidate, "ranking_score")) is not None
            and score >= float(ranking_score_min)
        ]
    if binding_rank_max is not None:
        filtered = [
            candidate
            for candidate in filtered
            if (score := _candidate_numeric_value(candidate, "binding_rank")) is not None
            and score <= float(binding_rank_max)
        ]
    return filtered


def sort_candidates(
    candidates: list[dict] | None,
    *,
    sort_key: str = "ranking_score",
    reverse: bool = True,
) -> list[dict]:
    ordered = list(candidates or [])
    if sort_key in {"ranking_score", "binding_rank"}:
        present = [
            candidate
            for candidate in ordered
            if _candidate_numeric_value(candidate, sort_key) is not None
        ]
        missing = [
            candidate
            for candidate in ordered
            if _candidate_numeric_value(candidate, sort_key) is None
        ]
        present = sorted(
            present,
            key=lambda candidate: float(_candidate_numeric_value(candidate, sort_key) or 0.0),
            reverse=reverse,
        )
        return present + missing
    return sorted(
        ordered, key=lambda candidate: str(candidate.get(sort_key) or "").lower(), reverse=reverse
    )


def apply_candidate_column_preset(
    rows: list[dict[str, Any]] | None, preset: str
) -> list[dict[str, Any]]:
    columns = _CANDIDATE_COLUMN_PRESETS.get(preset)
    if not columns:
        return list(rows or [])
    trimmed: list[dict[str, Any]] = []
    for row in rows or []:
        trimmed.append({column: row.get(column) for column in columns})
    return trimmed


def build_candidate_detail(candidate: dict | None) -> dict[str, Any]:
    if not candidate:
        return {}
    peptide_metadata = candidate.get("peptide_metadata") or {}
    prediction_scores = candidate.get("prediction_scores") or {}
    expression_evidence = candidate.get("expression_evidence") or {}
    structure_evidence = candidate.get("structure_evidence") or {}
    uncertainty_flags = candidate.get("uncertainty_flags") or {}
    detail = {
        "id": candidate.get("id"),
        "case_id": candidate.get("case_id"),
        "variant_id": candidate.get("variant_id"),
        "mhc_context": candidate.get("mhc_context"),
        "review_status": candidate.get("review_status"),
        "expert_review_notes": candidate.get("expert_review_notes"),
        "last_parsed_execution_id": candidate.get("last_parsed_execution_id"),
        "created_at": candidate.get("created_at"),
        "peptide_sequence": peptide_metadata.get("sequence"),
        "peptide_length": peptide_metadata.get("length"),
        "binding_rank": prediction_scores.get("binding_rank"),
        "immunogenicity": prediction_scores.get("immunogenicity"),
        "expression_tpm": expression_evidence.get("tpm"),
        "structure_backend": structure_evidence.get("backend"),
        "structure_status": structure_evidence.get("alphafold_status"),
        "structure_ranking_score": structure_evidence.get("ranking_score"),
        "structure_ptm": structure_evidence.get("ptm"),
        "structure_iptm": structure_evidence.get("iptm"),
        "structure_source_url": structure_evidence.get("source_url"),
        "structure_model_path": structure_evidence.get("model_cif")
        or structure_evidence.get("pdb_file"),
    }
    for key, value in uncertainty_flags.items():
        detail[f"uncertainty_{key}"] = value
    return detail


def build_candidate_review_summary(candidates: list[dict] | None) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    ranking_scores: list[float] = []
    for candidate in candidates or []:
        status = str(candidate.get("review_status") or "unreviewed")
        by_status[status] = by_status.get(status, 0) + 1
        ranking_score = (candidate.get("structure_evidence") or {}).get("ranking_score")
        if ranking_score is not None:
            ranking_scores.append(float(ranking_score))
    return {
        "total": len(candidates or []),
        "by_status": by_status,
        "has_accepted": by_status.get("expert_accepted_for_further_research", 0) > 0,
        "best_ranking_score": max(ranking_scores) if ranking_scores else "n/a",
    }


def _report_sort_key(report: dict) -> tuple[int, str]:
    report_type = str(report.get("report_type") or "")
    generated_at = str(report.get("generated_at") or "")
    return (_REPORT_TYPE_PRIORITY.get(report_type, 99), generated_at)


def _structure_job_sort_key(job: dict) -> str:
    return str(job.get("created_at") or "")


def build_candidate_linkout_targets(
    candidate: dict | None,
    *,
    reports: list[dict] | None = None,
    artifacts: list[dict] | None = None,
    structure_jobs: list[dict] | None = None,
) -> dict[str, Any]:
    if not candidate:
        return {}
    structure_evidence = candidate.get("structure_evidence") or {}
    preferred_artifact = structure_evidence.get("model_cif") or structure_evidence.get("pdb_file")
    candidate_id = candidate.get("id")

    matching_structure_jobs = [
        job for job in (structure_jobs or []) if job.get("candidate_id") == candidate_id
    ]
    matching_structure_jobs = sorted(
        matching_structure_jobs, key=_structure_job_sort_key, reverse=True
    )
    structure_job_id = matching_structure_jobs[0].get("id") if matching_structure_jobs else None

    sorted_reports = sorted(reports or [], key=_report_sort_key)
    sorted_reports.reverse()
    candidate_review_reports = [
        report for report in sorted_reports if report.get("report_type") == "candidate_review"
    ]
    report_id = None
    if candidate_review_reports:
        report_id = candidate_review_reports[0].get("id")
    elif sorted_reports:
        report_id = sorted_reports[0].get("id")

    artifact_path = next(
        (
            artifact.get("path")
            for artifact in artifacts or []
            if artifact.get("path") == preferred_artifact
        ),
        None,
    )
    if artifact_path is None and report_id is not None:
        artifact_path = next(
            (
                artifact.get("path")
                for artifact in artifacts or []
                if artifact.get("report_id") == report_id
            ),
            None,
        )
    if artifact_path is None:
        artifact_path = preferred_artifact
    if artifact_path is None and artifacts:
        artifact_path = next(
            (artifact.get("path") for artifact in artifacts if artifact.get("path")), None
        )

    return {
        "candidate_id": candidate_id,
        "case_id": candidate.get("case_id"),
        "structure_job_id": structure_job_id,
        "report_id": report_id,
        "artifact_path": artifact_path,
    }


def format_candidate_option(candidate: dict) -> str:
    candidate_id = str(candidate.get("id") or "unknown")
    mhc_context = candidate.get("mhc_context") or "candidate"
    review_status = candidate.get("review_status") or "unreviewed"
    return f"{mhc_context} · {review_status} · {candidate_id[:8]}"
