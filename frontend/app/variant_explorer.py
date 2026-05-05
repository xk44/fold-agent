from __future__ import annotations

from typing import Any

from frontend.app.candidate_review_table import build_candidate_linkout_targets


_REVIEW_STATUS_OPTIONS = [
    "unreviewed",
    "needs_data",
    "expert_rejected",
    "expert_accepted_for_further_research",
]

_VARIANT_COLUMN_PRESETS: dict[str, list[str]] = {
    "review": [
        "gene",
        "protein_change",
        "review_status",
        "quality_vaf",
        "quality_parsed_from",
        "created_at",
    ],
    "traceability": [
        "genomic_coordinates",
        "caller_source",
        "annotation_source",
        "last_parsed_execution_id",
        "quality_parsed_from",
    ],
}

_REVIEW_STATUS_PRIORITY = {
    "expert_accepted_for_further_research": 0,
    "needs_data": 1,
    "unreviewed": 2,
    "expert_rejected": 3,
}


def build_variant_review_status_options() -> list[str]:
    return list(_REVIEW_STATUS_OPTIONS)


def build_variant_column_presets() -> dict[str, list[str]]:
    return {name: list(columns) for name, columns in _VARIANT_COLUMN_PRESETS.items()}


def flatten_variant_rows(variants: list[dict] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for variant in variants or []:
        quality_metrics = variant.get("quality_metrics") or {}
        rows.append(
            {
                "id": variant.get("id"),
                "case_id": variant.get("case_id"),
                "sample_id": variant.get("sample_id"),
                "genomic_coordinates": variant.get("genomic_coordinates"),
                "gene": variant.get("gene"),
                "transcript": variant.get("transcript"),
                "protein_change": variant.get("protein_change"),
                "caller_source": variant.get("caller_source"),
                "annotation_source": variant.get("annotation_source"),
                "review_status": variant.get("review_status"),
                "last_parsed_execution_id": variant.get("last_parsed_execution_id"),
                "created_at": variant.get("created_at"),
                "quality_parsed_from": quality_metrics.get("parsed_from"),
                "quality_vaf": quality_metrics.get("vaf"),
                "quality_depth": quality_metrics.get("depth"),
            }
        )
    return rows


def _variant_vaf(variant: dict) -> float | None:
    quality_metrics = variant.get("quality_metrics") or {}
    value = quality_metrics.get("vaf")
    if value is None:
        return None
    return float(value)


def filter_variants(
    variants: list[dict] | None,
    *,
    review_status: str = "all",
    gene_query: str = "",
    vaf_min: float | None = None,
    vaf_max: float | None = None,
) -> list[dict]:
    filtered = list(variants or [])
    if review_status != "all":
        filtered = [variant for variant in filtered if str(variant.get("review_status") or "") == review_status]
    if gene_query.strip():
        gene_query_lower = gene_query.strip().lower()
        filtered = [
            variant
            for variant in filtered
            if gene_query_lower in str(variant.get("gene") or "").lower()
        ]
    if vaf_min is not None:
        narrowed: list[dict] = []
        for variant in filtered:
            vaf_value = _variant_vaf(variant)
            if vaf_value is not None and vaf_value >= float(vaf_min):
                narrowed.append(variant)
        filtered = narrowed
    if vaf_max is not None:
        narrowed = []
        for variant in filtered:
            vaf_value = _variant_vaf(variant)
            if vaf_value is not None and vaf_value <= float(vaf_max):
                narrowed.append(variant)
        filtered = narrowed
    return filtered


def _variant_sort_value(variant: dict, key: str) -> tuple[int, str]:
    raw_value = variant.get(key)
    if raw_value is None:
        return (1, "")
    return (0, str(raw_value).lower())


def sort_variants(
    variants: list[dict] | None,
    *,
    key: str = "created_at",
    reverse: bool = False,
) -> list[dict]:
    ordered = list(variants or [])
    if key == "created_at":
        present = [variant for variant in ordered if variant.get("created_at") is not None]
        missing = [variant for variant in ordered if variant.get("created_at") is None]
        present = sorted(present, key=lambda variant: str(variant.get("created_at") or ""), reverse=reverse)
        return present + missing
    return sorted(ordered, key=lambda variant: _variant_sort_value(variant, key), reverse=reverse)


def apply_variant_column_preset(rows: list[dict[str, Any]] | None, preset: str) -> list[dict[str, Any]]:
    columns = _VARIANT_COLUMN_PRESETS.get(preset)
    if not columns:
        return list(rows or [])
    trimmed: list[dict[str, Any]] = []
    for row in rows or []:
        trimmed.append({column: row.get(column) for column in columns})
    return trimmed


def build_variant_detail(variant: dict | None) -> dict[str, Any]:
    if not variant:
        return {}
    quality_metrics = variant.get("quality_metrics") or {}
    return {
        "id": variant.get("id"),
        "case_id": variant.get("case_id"),
        "sample_id": variant.get("sample_id"),
        "genomic_coordinates": variant.get("genomic_coordinates"),
        "gene": variant.get("gene"),
        "transcript": variant.get("transcript"),
        "protein_change": variant.get("protein_change"),
        "caller_source": variant.get("caller_source"),
        "annotation_source": variant.get("annotation_source"),
        "review_status": variant.get("review_status"),
        "expert_review_notes": variant.get("expert_review_notes"),
        "last_parsed_execution_id": variant.get("last_parsed_execution_id"),
        "created_at": variant.get("created_at"),
        "quality_parsed_from": quality_metrics.get("parsed_from"),
        "quality_vaf": quality_metrics.get("vaf"),
        "quality_depth": quality_metrics.get("depth"),
        "quality_filters": quality_metrics.get("filters"),
    }


def _candidate_rank(candidate: dict) -> tuple[float, int, str]:
    structure = candidate.get("structure_evidence") or {}
    ranking_score = structure.get("ranking_score")
    normalized_score = float(ranking_score) if ranking_score is not None else -1.0
    review_status = str(candidate.get("review_status") or "unreviewed")
    created_at = str(candidate.get("created_at") or "")
    return (
        normalized_score,
        -_REVIEW_STATUS_PRIORITY.get(review_status, 99),
        created_at,
    )


def build_variant_linkout_targets(
    variant: dict | None,
    *,
    candidates: list[dict] | None = None,
    reports: list[dict] | None = None,
    artifacts: list[dict] | None = None,
    structure_jobs: list[dict] | None = None,
) -> dict[str, Any]:
    if not variant:
        return {}
    related_candidates = [
        candidate for candidate in (candidates or []) if candidate.get("variant_id") == variant.get("id")
    ]
    if not related_candidates:
        return {"case_id": variant.get("case_id")}
    best_candidate = sorted(related_candidates, key=_candidate_rank, reverse=True)[0]
    candidate_linkouts = build_candidate_linkout_targets(
        best_candidate,
        reports=reports,
        artifacts=artifacts,
        structure_jobs=structure_jobs,
    )
    return {
        "case_id": variant.get("case_id"),
        "candidate_id": best_candidate.get("id"),
        "structure_job_id": candidate_linkouts.get("structure_job_id"),
        "report_id": candidate_linkouts.get("report_id"),
        "artifact_path": candidate_linkouts.get("artifact_path"),
    }


def format_variant_option(variant: dict) -> str:
    variant_id = str(variant.get("id") or "unknown")
    gene = variant.get("gene") or "unknown"
    protein_change = variant.get("protein_change") or variant_id[:8]
    return f"{gene} · {protein_change}"


def render_variant_explorer(
    api_base: str,
    case_id: str | None,
    http_get: Any,
    st: Any,
) -> None:
    """Render the Variant & Candidate Explorer page."""
    st.header("Variant & Candidate Explorer")

    if case_id is None:
        st.info("Select a case to explore variants and candidates.")
        return

    try:
        candidates_raw = http_get(f"{api_base}/cases/{case_id}/candidates").json()
    except Exception as exc:
        st.error(f"Failed to fetch candidates: {exc}")
        return

    candidates: list[dict] = (
        candidates_raw if isinstance(candidates_raw, list)
        else candidates_raw.get("candidates", [])
    )

    # --- Summary metrics row ---
    total = len(candidates)
    genes = {c.get("gene") for c in candidates if c.get("gene")}
    affinities = [
        c["binding_affinity"]
        for c in candidates
        if c.get("binding_affinity") is not None
    ]
    mean_affinity = (sum(affinities) / len(affinities)) if affinities else None

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Candidates", total)
    m2.metric("Unique Genes", len(genes))
    if mean_affinity is not None:
        m3.metric("Mean Binding Affinity", f"{mean_affinity:.2f}")
    else:
        m3.metric("Mean Binding Affinity", "N/A")

    # --- Optional: evidence level ---
    evidence_level: str | None = None
    try:
        ev_data = http_get(f"{api_base}/cases/{case_id}/evidence").json()
        evidence_level = ev_data.get("evidence_level") or ev_data.get("level")
    except Exception:
        pass

    # --- Optional: false-positive risk ---
    fp_risk: str | None = None
    try:
        fp_data = http_get(f"{api_base}/cases/{case_id}/false-positive-risk").json()
        fp_risk = fp_data.get("risk") or fp_data.get("false_positive_risk")
    except Exception:
        pass

    if evidence_level or fp_risk:
        badge_cols = st.columns(2)
        if evidence_level:
            badge_cols[0].info(f"Evidence level: **{evidence_level}**")
        if fp_risk:
            badge_cols[1].warning(f"False-positive risk: **{fp_risk}**")

    # --- Filter controls ---
    with st.expander("Filters"):
        min_affinity = st.slider(
            "Min binding affinity",
            min_value=0.0,
            max_value=1000.0,
            value=0.0,
            step=1.0,
            key="ve_min_affinity",
        )
        gene_filter = st.text_input(
            "Gene name filter (partial match)",
            value="",
            key="ve_gene_filter",
        )

    # --- Apply filters ---
    filtered = candidates
    if gene_filter:
        filtered = [
            c for c in filtered
            if gene_filter.lower() in (c.get("gene") or "").lower()
        ]
    if min_affinity > 0 and affinities:
        filtered = [
            c for c in filtered
            if (c.get("binding_affinity") or 0) >= min_affinity
        ]

    if not filtered:
        st.info("No candidates match the current filters.")
        return

    st.write(f"Showing **{len(filtered)}** of **{total}** candidates")

    # --- Per-candidate cards ---
    for candidate in filtered:
        cid = candidate.get("id", candidate.get("candidate_id", ""))
        gene = candidate.get("gene", "—")
        mutation = candidate.get("mutation", "—")
        rank = candidate.get("rank")
        label = f"**{gene}** — {mutation}"
        if rank is not None:
            label = f"#{rank} {label}"

        with st.expander(label):
            cols = st.columns(3)
            cols[0].write(f"**Gene:** {gene}")
            cols[1].write(f"**Mutation:** {mutation}")
            if rank is not None:
                cols[2].write(f"**Rank:** {rank}")

            peptide = candidate.get("peptide_sequence")
            if peptide:
                st.write(f"**Peptide sequence:** `{peptide}`")

            detail_cols = st.columns(2)
            ba = candidate.get("binding_affinity")
            if ba is not None:
                detail_cols[0].metric("Binding Affinity", f"{ba:.2f}")
            el = candidate.get("expression_level")
            if el is not None:
                detail_cols[1].metric("Expression Level", f"{el:.2f}")

            if cid:
                st.caption(f"ID: `{cid}`")
