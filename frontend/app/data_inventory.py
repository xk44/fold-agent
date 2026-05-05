from __future__ import annotations


def build_case_inventory_summary(
    *,
    subjects: list[dict] | None = None,
    samples: list[dict] | None = None,
    variants: list[dict] | None = None,
    candidates: list[dict] | None = None,
    reports: list[dict] | None = None,
    structure_jobs: list[dict] | None = None,
    artifacts: list[dict] | None = None,
    executions: list[dict] | None = None,
    audit_entries: list[dict] | None = None,
) -> dict:
    summary = {
        "subjects": len(subjects or []),
        "samples": len(samples or []),
        "variants": len(variants or []),
        "candidates": len(candidates or []),
        "reports": len(reports or []),
        "structure_jobs": len(structure_jobs or []),
        "artifacts": len(artifacts or []),
        "executions": len(executions or []),
        "audit_entries": len(audit_entries or []),
    }
    summary["total_records"] = sum(summary.values())
    return summary


def _inventory_timestamp(item: dict) -> str | None:
    return item.get("saved_at") or item.get("started_at") or item.get("generated_at") or item.get("created_at")


def build_inventory_rows(
    *,
    subjects: list[dict] | None = None,
    samples: list[dict] | None = None,
    variants: list[dict] | None = None,
    candidates: list[dict] | None = None,
    reports: list[dict] | None = None,
    structure_jobs: list[dict] | None = None,
    artifacts: list[dict] | None = None,
    executions: list[dict] | None = None,
) -> list[dict]:
    rows: list[dict] = []

    for subject in subjects or []:
        privacy_flags = subject.get("privacy_flags") or {}
        rows.append(
            {
                "entity_type": "subject",
                "id": subject.get("id"),
                "label": subject.get("anonymized_display_name") or subject.get("id"),
                "status": "redacted" if privacy_flags.get("redacted") else "standard",
                "timestamp": _inventory_timestamp(subject),
            }
        )

    for sample in samples or []:
        rows.append(
            {
                "entity_type": "sample",
                "id": sample.get("id"),
                "label": " · ".join(part for part in [sample.get("sample_type"), sample.get("source_lab")] if part) or sample.get("id"),
                "status": sample.get("sample_type"),
                "timestamp": _inventory_timestamp(sample),
            }
        )

    for variant in variants or []:
        rows.append(
            {
                "entity_type": "variant",
                "id": variant.get("id"),
                "label": " · ".join(part for part in [variant.get("gene"), variant.get("protein_change")] if part) or variant.get("genomic_coordinates") or variant.get("id"),
                "status": variant.get("review_status"),
                "timestamp": _inventory_timestamp(variant),
            }
        )

    for candidate in candidates or []:
        rows.append(
            {
                "entity_type": "candidate",
                "id": candidate.get("id"),
                "label": candidate.get("mhc_context") or candidate.get("id"),
                "status": candidate.get("review_status"),
                "timestamp": _inventory_timestamp(candidate),
            }
        )

    for report in reports or []:
        rows.append(
            {
                "entity_type": "report",
                "id": report.get("id"),
                "label": report.get("report_type") or report.get("id"),
                "status": report.get("safety_label"),
                "timestamp": _inventory_timestamp(report),
            }
        )

    for structure_job in structure_jobs or []:
        rows.append(
            {
                "entity_type": "structure_job",
                "id": structure_job.get("id"),
                "label": structure_job.get("backend_used") or structure_job.get("id"),
                "status": structure_job.get("status"),
                "timestamp": _inventory_timestamp(structure_job),
            }
        )

    for artifact in artifacts or []:
        rows.append(
            {
                "entity_type": "artifact",
                "id": artifact.get("id") or artifact.get("path"),
                "label": " · ".join(part for part in [artifact.get("artifact_type"), artifact.get("filename")] if part) or artifact.get("path"),
                "status": artifact.get("format") or artifact.get("artifact_type"),
                "timestamp": _inventory_timestamp(artifact),
            }
        )

    for execution in executions or []:
        rows.append(
            {
                "entity_type": "execution",
                "id": execution.get("id"),
                "label": execution.get("adapter_name") or execution.get("backend_name") or execution.get("id"),
                "status": execution.get("status"),
                "timestamp": _inventory_timestamp(execution),
            }
        )

    return sorted(rows, key=lambda row: (row.get("timestamp") or "", row.get("entity_type") or "", row.get("id") or ""), reverse=True)
