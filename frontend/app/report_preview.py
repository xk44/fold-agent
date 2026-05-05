from __future__ import annotations


def _section(title: str, lines: list[str]) -> str:
    body = "\n".join(line for line in lines if line)
    return f"{title}\n{body}" if body else title


def summarize_alphafold_diagnostics(backends_payload: dict) -> dict:
    payload = backends_payload or {}
    per_backend_summary = []
    unavailable_backends = []
    requires_gpu_backends = []
    external_upload_backends = []
    available_count = 0

    for backend_name, backend_payload in sorted(payload.items()):
        available = bool(backend_payload.get("available"))
        if available:
            available_count += 1
        else:
            unavailable_backends.append(backend_name)
        if backend_payload.get("requires_gpu"):
            requires_gpu_backends.append(backend_name)
        if backend_payload.get("requires_external_upload"):
            external_upload_backends.append(backend_name)
        per_backend_summary.append(
            {
                "backend_name": backend_name,
                "mode": backend_payload.get("mode") or "n/a",
                "available": available,
                "validation_ok": bool(backend_payload.get("validation_ok")),
                "requires_gpu": bool(backend_payload.get("requires_gpu")),
                "requires_external_upload": bool(backend_payload.get("requires_external_upload")),
                "supports_complexes": bool(backend_payload.get("supports_complexes")),
                "supports_rna_dna_ligands": bool(backend_payload.get("supports_rna_dna_ligands")),
            }
        )

    return {
        "total_backends": len(payload),
        "available_count": available_count,
        "unavailable_backends": unavailable_backends,
        "requires_gpu_backends": requires_gpu_backends,
        "external_upload_backends": external_upload_backends,
        "per_backend_summary": per_backend_summary,
    }


def format_alphafold_diagnostics_metrics(backends_payload: dict) -> list[dict]:
    summary = summarize_alphafold_diagnostics(backends_payload)
    return [
        {"label": "Total backends", "value": str(summary["total_backends"])},
        {"label": "Available backends", "value": str(summary["available_count"])},
        {
            "label": "GPU-required backends",
            "value": ", ".join(summary["requires_gpu_backends"]) or "none",
        },
        {
            "label": "External upload backends",
            "value": ", ".join(summary["external_upload_backends"]) or "none",
        },
    ]


def extract_backend_capability_table(backends_payload: dict) -> list[dict]:
    rows = []
    payload = backends_payload or {}
    ordered_keys = [
        "mode",
        "available",
        "validation_ok",
        "requires_gpu",
        "requires_external_upload",
        "supports_protein_only",
        "supports_complexes",
        "supports_rna_dna_ligands",
        "license_notes",
        "command",
        "path",
        "notes",
    ]
    for backend_name, backend_payload in sorted(payload.items()):
        for key in ordered_keys:
            rows.append(
                {
                    "backend": backend_name,
                    "capability": key,
                    "value": backend_payload.get(key),
                }
            )
        for key, value in sorted((backend_payload.get("diagnostics") or {}).items()):
            rows.append({"backend": backend_name, "capability": key, "value": value})
    return rows


def choose_default_alphafold_backend(backends_payload: dict) -> str | None:
    payload = backends_payload or {}
    if not payload:
        return None

    mode_priority = {"local": 3, "reference": 2, "cloud": 1}

    def score(item: tuple[str, dict]) -> tuple:
        backend_name, backend_payload = item
        return (
            1 if backend_payload.get("available") else 0,
            1 if backend_payload.get("validation_ok") else 0,
            0 if backend_payload.get("requires_external_upload") else 1,
            mode_priority.get(backend_payload.get("mode") or "", 0),
            1 if backend_payload.get("supports_rna_dna_ligands") else 0,
            1 if backend_payload.get("supports_complexes") else 0,
            1 if backend_payload.get("requires_gpu") else 0,
            backend_name,
        )

    return max(sorted(payload.items()), key=score)[0]


def format_alphafold_backend_option_label(backend_name: str, backend_payload: dict) -> str:
    payload = backend_payload or {}
    diagnostics = payload.get("diagnostics") or {}
    status_parts = []
    if not payload.get("available"):
        status_parts.append("🔴 unavailable")
    elif not payload.get("validation_ok"):
        status_parts.append("🟡 needs validation")
    else:
        status_parts.append("🟢 ready")
    if payload.get("requires_external_upload") or diagnostics.get("requires_external_upload_acknowledgement"):
        status_parts.append("ack required")
    mode = payload.get("mode") or "n/a"
    return f"{backend_name} [{mode}; {'; '.join(status_parts)}]"


def summarize_alphafold_recommended_backend(backends_payload: dict) -> dict:
    backend_name = choose_default_alphafold_backend(backends_payload)
    backend_payload = (backends_payload or {}).get(backend_name or "", {})
    if not backend_name:
        return {"backend_name": None, "label": "No recommended backend", "reason_lines": []}

    reason_lines = []
    if backend_payload.get("available"):
        reason_lines.append("Available on this system.")
    if backend_payload.get("validation_ok"):
        reason_lines.append("Validation currently OK.")
    if not backend_payload.get("requires_external_upload"):
        reason_lines.append("Does not require external upload by default.")
    if backend_payload.get("mode"):
        reason_lines.append(f"Mode={backend_payload.get('mode')}.")

    return {
        "backend_name": backend_name,
        "label": f"Recommended backend: {backend_name}",
        "reason_lines": reason_lines,
    }


def build_alphafold_backend_capability_chips(backend_name: str, backend_payload: dict) -> list[str]:
    payload = backend_payload or {}
    return [
        f"mode: {payload.get('mode') or 'n/a'}",
        f"gpu: {'yes' if payload.get('requires_gpu') else 'no'}",
        f"complexes: {'yes' if payload.get('supports_complexes') else 'no'}",
        f"rna/dna/ligands: {'yes' if payload.get('supports_rna_dna_ligands') else 'no'}",
    ]


def format_alphafold_troubleshooting_summary(backends_payload: dict) -> str:
    sections = ["AlphaFold validation troubleshooting"]
    for backend_name, payload in sorted((backends_payload or {}).items()):
        if payload.get("validation_ok", True):
            continue
        diagnostics = payload.get("diagnostics") or {}
        lines = [f"validation_reason={payload.get('validation_reason') or 'n/a'}"]
        if diagnostics.get("gpu_runtime_available") is False:
            lines.append("gpu_runtime_available=False")
        version_probe = diagnostics.get("version_probe") or {}
        if version_probe and not version_probe.get("probe_ok"):
            lines.append("version probe failed")
            if version_probe.get("probe_timed_out"):
                lines.append("version probe timed out")
        configured_paths = diagnostics.get("configured_paths") or {}
        for path_info in configured_paths.values():
            if path_info.get("configured") and path_info.get("exists") is False:
                lines.append(
                    f"missing configured path: {path_info.get('env_var')} -> {path_info.get('path')}"
                )
        sections.append(_section(f"Backend: {backend_name}", lines))
    return "\n\n".join(sections)


def format_alphafold_validation_error(error_payload: dict) -> str:
    payload = error_payload or {}
    return "\n\n".join(
        [
            "AlphaFold backend validation error",
            _section(
                "Summary",
                [
                    f"backend_name={payload.get('backend_name') or 'n/a'}",
                    f"validation_ok={payload.get('validation_ok')}",
                    f"validation_reason={payload.get('validation_reason') or 'n/a'}",
                    f"detail={payload.get('detail') or 'n/a'}",
                ],
            ),
        ]
    )


def build_alphafold_backend_form_state(backend_name: str, backend_payload: dict) -> dict:
    payload = backend_payload or {}
    diagnostics = payload.get("diagnostics") or {}

    if backend_name == "alphafold_db" or diagnostics.get("supports_accession_lookup"):
        input_mode = "accession"
        required_field = "accession"
    elif diagnostics.get("requires_json_input") or diagnostics.get("supports_remote_json_submission"):
        input_mode = "json"
        required_field = "json_path"
    else:
        input_mode = "sequence"
        required_field = "sequence"

    field_enabled = {
        "sequence": input_mode == "sequence",
        "json_path": input_mode == "json",
        "accession": input_mode == "accession",
    }
    disabled_field_reasons = {
        "sequence": [] if field_enabled["sequence"] else [f"Disabled: this backend expects {required_field} input instead."],
        "json_path": [] if field_enabled["json_path"] else [f"Disabled: this backend expects {required_field} input instead."],
        "accession": [] if field_enabled["accession"] else [f"Disabled: this backend expects {required_field} input instead."],
    }

    guidance_lines = [
        f"backend={backend_name}",
        f"mode={payload.get('mode') or 'n/a'}",
        f"required_field={required_field}",
    ]
    if input_mode == "sequence":
        guidance_lines.append("Submit a protein sequence here; JSON path and accession are not used.")
        if diagnostics.get("supports_a3m_input"):
            guidance_lines.append("A3M-style aligned input is supported by this backend family.")
        if diagnostics.get("supports_num_recycle"):
            guidance_lines.append("This backend supports recycle-count style tuning when exposed later.")
    elif input_mode == "json":
        guidance_lines.append("Submit a JSON input path here; sequence and accession are not used.")
        if diagnostics.get("supports_input_dir") or diagnostics.get("parses_output_directory"):
            guidance_lines.append("This backend can parse output directory artifacts after the run completes.")
    else:
        guidance_lines.append("Submit an AlphaFold DB accession here; local sequence/JSON inputs are not used.")

    warning_lines = []
    available = bool(payload.get("available"))
    validation_ok = bool(payload.get("validation_ok"))
    if not available:
        warning_lines.append("Backend is not currently available on this system.")
    if available and not validation_ok:
        warning_lines.append("Backend command exists but environment validation is not yet OK.")
    if payload.get("requires_external_upload") or diagnostics.get("requires_external_upload_acknowledgement"):
        warning_lines.append("This backend requires external upload acknowledgement before use.")
    if payload.get("requires_gpu"):
        warning_lines.append("This backend expects local GPU capacity.")
    if payload.get("license_notes"):
        warning_lines.append(f"License notes: {payload.get('license_notes')}")

    severity = "info"
    if not available:
        severity = "error"
    elif (
        not validation_ok
        or payload.get("requires_external_upload")
        or diagnostics.get("requires_external_upload_acknowledgement")
    ):
        severity = "warning"

    requires_acknowledgement = severity == "warning"
    acknowledgement_label = (
        "I understand this backend has extra requirements and want to continue."
        if requires_acknowledgement
        else ""
    )
    submit_block_reason = ""
    if severity == "error":
        submit_block_reason = "Selected backend is not currently runnable on this system."
    elif requires_acknowledgement:
        submit_block_reason = "Acknowledge the backend requirements before submitting this run."

    return {
        "backend_name": backend_name,
        "input_mode": input_mode,
        "required_field": required_field,
        "field_enabled": field_enabled,
        "disabled_field_reasons": disabled_field_reasons,
        "guidance_lines": guidance_lines,
        "warning_lines": warning_lines,
        "severity": severity,
        "available": available,
        "validation_ok": validation_ok,
        "requires_acknowledgement": requires_acknowledgement,
        "acknowledgement_label": acknowledgement_label,
        "submit_blocked": bool(submit_block_reason),
        "submit_block_reason": submit_block_reason,
    }


def format_alphafold_backend_form_guidance(form_state: dict) -> str:
    payload = form_state or {}
    return "\n\n".join(
        [
            "AlphaFold backend form guidance",
            _section(
                "Selected backend",
                [
                    f"backend={payload.get('backend_name') or 'n/a'}",
                    f"input_mode={payload.get('input_mode') or 'n/a'}",
                    f"required_field={payload.get('required_field') or 'n/a'}",
                    f"severity={payload.get('severity') or 'info'}",
                    f"submit_block_reason={payload.get('submit_block_reason') or 'none'}",
                ],
            ),
            _section("Guidance", [f"- {line}" for line in (payload.get('guidance_lines') or [])] or ["- none"]),
            _section("Warnings", [f"- {line}" for line in (payload.get('warning_lines') or [])] or ["- none"]),
        ]
    )


def build_alphafold_run_payload_preview(
    *,
    case_id: str,
    backend_name: str,
    form_state: dict,
    job_name: str,
    sequence: str,
    json_path: str,
    accession: str,
) -> dict:
    payload = {
        "case_id": case_id,
        "job_name": job_name,
        "backend_name": backend_name,
    }
    required_field = (form_state or {}).get("required_field")
    if required_field == "sequence":
        payload["sequence"] = sequence
    elif required_field == "json_path":
        payload.update({"input_kind": "json", "json_path": json_path})
    elif required_field == "accession":
        payload["accession"] = accession
    return payload


def format_alphafold_diagnostics_preview(backends_payload: dict) -> str:
    backend_sections = []
    for backend_name, payload in sorted((backends_payload or {}).items()):
        diagnostics = payload.get("diagnostics") or {}
        diagnostic_lines = [f"- {key}={value}" for key, value in diagnostics.items()] or ["- none"]
        backend_sections.append(
            "\n\n".join(
                [
                    f"Backend: {backend_name}",
                    _section(
                        "Shell status",
                        [
                            f"command={payload.get('command') or 'n/a'}",
                            f"mode={payload.get('mode') or 'n/a'}",
                            f"available={payload.get('available')}",
                            f"validation_ok={payload.get('validation_ok')}",
                            f"requires_gpu={payload.get('requires_gpu')}",
                            f"requires_external_upload={payload.get('requires_external_upload')}",
                            f"supports_protein_only={payload.get('supports_protein_only')}",
                            f"supports_complexes={payload.get('supports_complexes')}",
                            f"supports_rna_dna_ligands={payload.get('supports_rna_dna_ligands')}",
                            f"license_notes={payload.get('license_notes') or 'n/a'}",
                            f"path={payload.get('path') or 'n/a'}",
                            f"notes={payload.get('notes') or 'n/a'}",
                        ],
                    ),
                    _section("Diagnostics", diagnostic_lines),
                ]
            )
        )
    return "\n\n".join(["AlphaFold Backend Diagnostics", *backend_sections])


def format_bundle_preview(bundle_payload: dict) -> str:
    case = bundle_payload.get("case") or {}
    variants = bundle_payload.get("variants") or []
    reports = bundle_payload.get("reports") or []
    latest_pipeline = bundle_payload.get("latest_pipeline_run") or {}
    top_genes = sorted({variant.get("gene") for variant in variants if variant.get("gene")})
    return "\n\n".join(
        [
            f"Case Bundle\nCase: {case.get('id') or 'unknown'}",
            f"Species: {case.get('species') or 'n/a'}",
            f"Diagnosis summary: {case.get('diagnosis_summary') or 'n/a'}",
            _section(
                "Counts",
                [
                    f"samples={len(bundle_payload.get('samples') or [])}",
                    f"variants={len(variants)}",
                    f"candidates={len(bundle_payload.get('candidates') or [])}",
                    f"reports={len(reports)}",
                    f"audit_entries={len(bundle_payload.get('audit_log') or [])}",
                ],
            ),
            _section("Top genes", [f"- {gene}" for gene in top_genes] or ["- none"]),
            _section("Latest reports", [f"- {report.get('report_type') or 'unknown'}" for report in reports[:5]] or ["- none"]),
            _section(
                "Pipeline status",
                [
                    f"status={latest_pipeline.get('status') or 'none'}",
                    f"completed_steps={latest_pipeline.get('completed_steps') if latest_pipeline else 'n/a'}",
                    f"total_steps={latest_pipeline.get('total_steps') if latest_pipeline else 'n/a'}",
                ],
            ),
            _section("Safety label", [str(bundle_payload.get('safety_label') or 'n/a')]),
        ]
    )


def format_structure_job_preview(structure_job_payload: dict) -> str:
    metrics = structure_job_payload.get("confidence_metrics") or {}
    return "\n\n".join(
        [
            "Structure Job",
            _section(
                "Summary",
                [
                    f"id={structure_job_payload.get('id') or 'unknown'}",
                    f"backend={structure_job_payload.get('backend_used') or 'n/a'}",
                    f"status={structure_job_payload.get('status') or 'n/a'}",
                    f"output_path={structure_job_payload.get('output_path') or 'n/a'}",
                ],
            ),
            _section(
                "Confidence metrics",
                [
                    f"ranking_score={metrics.get('ranking_score') if metrics.get('ranking_score') is not None else 'n/a'}",
                    f"ptm={metrics.get('ptm') if metrics.get('ptm') is not None else 'n/a'}",
                    f"iptm={metrics.get('iptm') if metrics.get('iptm') is not None else 'n/a'}",
                    f"source_url={metrics.get('source_url') or 'n/a'}",
                    f"summary_confidences_json={metrics.get('summary_confidences_json') or 'n/a'}",
                    f"output_format={metrics.get('output_format') or 'n/a'}",
                ],
            ),
        ]
    )


def format_report_preview(report_payload: dict) -> str:
    report_type = report_payload.get("report_type") or "report"
    content = report_payload.get("content_json") or {}
    case_id = report_payload.get("case_id") or "unknown"

    if report_type == "candidate_review":
        rows = content.get("candidate_table") or []
        candidate_lines = [
            f"- {row.get('gene') or 'unknown'} | {row.get('protein_change') or 'n/a'} | bind={row.get('binding_rank')} | immunogenicity={row.get('immunogenicity')} | mhc={row.get('mhc_context') or 'n/a'}"
            for row in rows
        ] or ["- none"]
        return "\n\n".join(
            [
                f"Candidate Review\nCase: {case_id}",
                f"Summary: {content.get('summary') or 'n/a'}",
                f"Top candidate gene: {content.get('top_candidate_gene') or 'n/a'}",
                _section("Candidate antigens", candidate_lines),
                _section(
                    "Structure evidence",
                    [
                        f"backend={content.get('structure_backend') or 'n/a'}",
                        f"status={content.get('structure_status') or 'n/a'}",
                        f"ranking_score={content.get('ranking_score') if content.get('ranking_score') is not None else 'n/a'}",
                        f"ptm={content.get('ptm') if content.get('ptm') is not None else 'n/a'}",
                        f"iptm={content.get('iptm') if content.get('iptm') is not None else 'n/a'}",
                    ],
                ),
                _section("Missing data checklist", [f"- [ ] {item}" for item in (content.get('missing_data_checklist') or [])] or ["- [ ] none"]),
                _section("Tool versions", [f"- {k}: {v}" for k, v in (content.get('tool_versions') or {}).items()] or ["- none"]),
                _section("Safety labels", [f"- {item}" for item in (content.get('safety_labels') or [])] or ["- none"]),
            ]
        )

    if report_type == "ethics_package":
        consent_lines = [f"- {k}: {v}" for k, v in (content.get('consent_templates') or {}).items()] or ["- none"]
        privacy_lines = [f"- {item}" for item in (content.get('privacy_notices') or [])] or ["- none"]
        risk_lines = [f"- risk: {item}" for item in ((content.get('risk_benefit_summary') or {}).get('risks') or [])]
        benefit_lines = [f"- benefit: {item}" for item in ((content.get('risk_benefit_summary') or {}).get('benefits') or [])]
        oversight_lines = [f"- [ ] {item}" for item in (content.get('professional_oversight_checklist') or [])] or ["- [ ] none"]
        return "\n\n".join(
            [
                f"Ethics Package\nCase: {case_id}",
                f"Species: {content.get('species') or 'n/a'}",
                _section("Consent templates", consent_lines),
                _section("Privacy notices", privacy_lines),
                _section("Risk and benefit summary", (risk_lines + benefit_lines) or ["- none"]),
                _section("Professional oversight checklist", oversight_lines),
                _section("Jurisdiction warning", [str(content.get('jurisdiction_warning') or 'n/a')]),
            ]
        )

    return str(report_payload)
