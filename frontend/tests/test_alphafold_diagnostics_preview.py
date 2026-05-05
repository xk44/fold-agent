from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.report_preview import (
    build_alphafold_backend_capability_chips,
    build_alphafold_backend_form_state,
    build_alphafold_run_payload_preview,
    choose_default_alphafold_backend,
    extract_backend_capability_table,
    format_alphafold_backend_form_guidance,
    format_alphafold_backend_option_label,
    format_alphafold_diagnostics_metrics,
    format_alphafold_diagnostics_preview,
    format_alphafold_troubleshooting_summary,
    format_alphafold_validation_error,
    summarize_alphafold_diagnostics,
    summarize_alphafold_recommended_backend,
)


def _sample_alphafold_backends() -> dict:
    return {
        "colabfold": {
            "name": "colabfold",
            "version": "colabfold-shell",
            "mode": "local",
            "requires_gpu": True,
            "requires_external_upload": False,
            "supports_protein_only": True,
            "supports_complexes": True,
            "supports_rna_dna_ligands": False,
            "license_notes": "ColabFold CLI wrapper",
            "command": "colabfold_batch",
            "available": True,
            "path": "/usr/bin/colabfold_batch",
            "validation_ok": True,
            "notes": "ColabFold shell stub.",
            "diagnostics": {
                "command_on_path": True,
                "command_name": "colabfold_batch",
                "host_url_supported": True,
                "supports_a3m_input": True,
                "supports_num_recycle": True,
            },
        },
        "alphafold3_local": {
            "name": "alphafold3_local",
            "version": "alphafold3-shell",
            "mode": "local",
            "requires_gpu": True,
            "requires_external_upload": False,
            "supports_protein_only": False,
            "supports_complexes": True,
            "supports_rna_dna_ligands": True,
            "license_notes": "AlphaFold 3 local shell wrapper",
            "command": "alphafold",
            "available": True,
            "path": "/usr/bin/alphafold",
            "validation_ok": True,
            "notes": "AlphaFold 3 local shell stub.",
            "diagnostics": {
                "command_on_path": True,
                "command_name": "alphafold",
                "requires_json_input": True,
                "supports_input_dir": True,
                "parses_output_directory": True,
            },
        },
        "alphafold_db": {
            "name": "alphafold_db",
            "version": "alphafold-db-reference",
            "mode": "reference",
            "requires_gpu": False,
            "requires_external_upload": False,
            "supports_protein_only": True,
            "supports_complexes": False,
            "supports_rna_dna_ligands": False,
            "license_notes": "Reference lookup only",
            "command": "builtin",
            "available": True,
            "path": "builtin",
            "validation_ok": True,
            "notes": "AlphaFold DB lookup backend.",
            "diagnostics": {
                "command_on_path": True,
                "command_name": "builtin",
                "supports_accession_lookup": True,
            },
        },
        "alphafold_server": {
            "name": "alphafold_server",
            "version": "alphafold-server-remote",
            "mode": "cloud",
            "requires_gpu": False,
            "requires_external_upload": True,
            "supports_protein_only": False,
            "supports_complexes": True,
            "supports_rna_dna_ligands": True,
            "license_notes": "Remote upload required",
            "command": "alphafold_server_submit",
            "available": False,
            "path": None,
            "validation_ok": False,
            "validation_reason": "Remote descriptor only; local executable validation is not available.",
            "notes": "Remote AlphaFold Server descriptor.",
            "diagnostics": {
                "command_on_path": False,
                "command_name": "alphafold_server_submit",
                "requires_external_upload_acknowledgement": True,
                "supports_remote_json_submission": True,
            },
        },
    }


def test_format_alphafold_diagnostics_preview_surfaces_capabilities() -> None:
    preview = format_alphafold_diagnostics_preview(
        {
            "colabfold": {
                "name": "colabfold",
                "command": "colabfold_batch",
                "available": True,
                "path": "/usr/bin/colabfold_batch",
                "validation_ok": True,
                "notes": "ColabFold shell stub.",
                "diagnostics": {
                    "command_on_path": True,
                    "command_name": "colabfold_batch",
                    "host_url_supported": True,
                    "supports_a3m_input": True,
                    "supports_num_recycle": True,
                },
            }
        }
    )

    assert "AlphaFold Backend Diagnostics" in preview
    assert "Backend: colabfold" in preview
    assert "command=colabfold_batch" in preview
    assert "command_on_path=True" in preview
    assert "supports_a3m_input=True" in preview
    assert "path=/usr/bin/colabfold_batch" in preview


def test_format_alphafold_diagnostics_preview_handles_missing_diagnostics() -> None:
    preview = format_alphafold_diagnostics_preview(
        {
            "mock": {
                "name": "mock",
                "command": "builtin",
                "available": True,
                "path": None,
                "validation_ok": True,
                "notes": "Mock backend",
            }
        }
    )

    assert "Backend: mock" in preview
    assert "Diagnostics" in preview
    assert "- none" in preview


def test_summarize_alphafold_diagnostics_counts_total_and_available() -> None:
    summary = summarize_alphafold_diagnostics(_sample_alphafold_backends())

    assert summary["total_backends"] == 4
    assert summary["available_count"] == 3
    assert summary["unavailable_backends"] == ["alphafold_server"]


def test_summarize_alphafold_diagnostics_flags_gpu_and_external_upload() -> None:
    summary = summarize_alphafold_diagnostics(_sample_alphafold_backends())

    assert summary["requires_gpu_backends"] == ["alphafold3_local", "colabfold"]
    assert summary["external_upload_backends"] == ["alphafold_server"]


def test_summarize_alphafold_diagnostics_per_backend_summary() -> None:
    summary = summarize_alphafold_diagnostics(_sample_alphafold_backends())

    colabfold_entry = next(
        entry for entry in summary["per_backend_summary"] if entry["backend_name"] == "colabfold"
    )
    assert colabfold_entry["mode"] == "local"
    assert colabfold_entry["available"] is True
    assert colabfold_entry["requires_gpu"] is True
    assert colabfold_entry["supports_complexes"] is True
    assert colabfold_entry["supports_rna_dna_ligands"] is False


def test_format_alphafold_diagnostics_metrics_provides_summary_rows() -> None:
    metrics = format_alphafold_diagnostics_metrics(_sample_alphafold_backends())

    assert [metric["label"] for metric in metrics] == [
        "Total backends",
        "Available backends",
        "GPU-required backends",
        "External upload backends",
    ]
    assert metrics[0]["value"] == "4"
    assert metrics[1]["value"] == "3"
    assert metrics[2]["value"] == "alphafold3_local, colabfold"
    assert metrics[3]["value"] == "alphafold_server"


def test_extract_backend_capability_table_provides_flat_rows() -> None:
    rows = extract_backend_capability_table(_sample_alphafold_backends())

    assert rows
    assert {row["backend"] for row in rows} == {
        "alphafold3_local",
        "alphafold_db",
        "alphafold_server",
        "colabfold",
    }
    capability_rows = [row for row in rows if row["backend"] == "colabfold"]
    assert {row["capability"] for row in capability_rows} >= {
        "available",
        "mode",
        "requires_gpu",
        "supports_a3m_input",
        "supports_complexes",
    }


def test_format_alphafold_diagnostics_preview_includes_backend_metadata() -> None:
    preview = format_alphafold_diagnostics_preview(_sample_alphafold_backends())

    assert "mode=local" in preview
    assert "requires_gpu=True" in preview
    assert "supports_complexes=True" in preview
    assert "supports_rna_dna_ligands=False" in preview
    assert "requires_external_upload=True" in preview
    assert "license_notes=Remote upload required" in preview


def test_build_alphafold_backend_form_state_for_sequence_backend() -> None:
    state = build_alphafold_backend_form_state("colabfold", _sample_alphafold_backends()["colabfold"])

    assert state["input_mode"] == "sequence"
    assert state["required_field"] == "sequence"
    assert state["field_enabled"] == {"sequence": True, "json_path": False, "accession": False}
    assert any("A3M" in line for line in state["guidance_lines"])


def test_build_alphafold_backend_form_state_for_json_backend() -> None:
    state = build_alphafold_backend_form_state(
        "alphafold3_local", _sample_alphafold_backends()["alphafold3_local"]
    )

    assert state["input_mode"] == "json"
    assert state["required_field"] == "json_path"
    assert state["field_enabled"] == {"sequence": False, "json_path": True, "accession": False}
    assert any("output directory" in line.lower() for line in state["guidance_lines"])


def test_build_alphafold_backend_form_state_for_accession_backend() -> None:
    state = build_alphafold_backend_form_state("alphafold_db", _sample_alphafold_backends()["alphafold_db"])

    assert state["input_mode"] == "accession"
    assert state["required_field"] == "accession"
    assert state["field_enabled"] == {"sequence": False, "json_path": False, "accession": True}
    assert any("accession" in line.lower() for line in state["guidance_lines"])


def test_build_alphafold_backend_form_state_surfaces_external_upload_warning() -> None:
    state = build_alphafold_backend_form_state(
        "alphafold_server", _sample_alphafold_backends()["alphafold_server"]
    )

    assert state["input_mode"] == "json"
    assert state["severity"] == "error"
    assert any("external upload" in line.lower() for line in state["warning_lines"])


def test_format_alphafold_backend_form_guidance_renders_sections() -> None:
    guidance = format_alphafold_backend_form_guidance(
        build_alphafold_backend_form_state("colabfold", _sample_alphafold_backends()["colabfold"])
    )

    assert "AlphaFold backend form guidance" in guidance
    assert "required_field=sequence" in guidance
    assert "Guidance" in guidance
    assert "Warnings" in guidance


def test_choose_default_alphafold_backend_prefers_safest_runnable_backend() -> None:
    assert choose_default_alphafold_backend(_sample_alphafold_backends()) == "alphafold3_local"


def test_format_alphafold_backend_option_label_marks_unavailable_backend() -> None:
    label = format_alphafold_backend_option_label(
        "alphafold_server", _sample_alphafold_backends()["alphafold_server"]
    )

    assert "alphafold_server" in label
    assert "unavailable" in label.lower()
    assert "ack" in label.lower()


def test_build_alphafold_backend_form_state_includes_disabled_field_reasons() -> None:
    state = build_alphafold_backend_form_state("alphafold_db", _sample_alphafold_backends()["alphafold_db"])

    assert state["disabled_field_reasons"]["sequence"]
    assert any("accession" in reason.lower() for reason in state["disabled_field_reasons"]["sequence"])
    assert state["disabled_field_reasons"]["json_path"]


def test_build_alphafold_backend_form_state_requires_ack_for_warning_backend() -> None:
    warning_backend = dict(_sample_alphafold_backends()["alphafold3_local"])
    warning_backend["validation_ok"] = False
    state = build_alphafold_backend_form_state("alphafold3_local", warning_backend)

    assert state["severity"] == "warning"
    assert state["requires_acknowledgement"] is True
    assert "acknowledgement_label" in state


def test_diagnostics_level_ack_flag_requires_warning_and_label_marker() -> None:
    backend = dict(_sample_alphafold_backends()["alphafold3_local"])
    backend["requires_external_upload"] = False
    backend["diagnostics"] = dict(backend["diagnostics"])
    backend["diagnostics"]["requires_external_upload_acknowledgement"] = True

    state = build_alphafold_backend_form_state("alphafold3_local", backend)
    label = format_alphafold_backend_option_label("alphafold3_local", backend)

    assert state["severity"] == "warning"
    assert state["requires_acknowledgement"] is True
    assert "ack required" in label.lower()


def test_build_alphafold_backend_form_state_sets_submit_block_reason_for_error_backend() -> None:
    state = build_alphafold_backend_form_state("alphafold_server", _sample_alphafold_backends()["alphafold_server"])

    assert state["submit_blocked"] is True
    assert "not currently runnable" in state["submit_block_reason"].lower()


def test_build_alphafold_backend_form_state_sets_submit_block_reason_for_missing_ack() -> None:
    warning_backend = dict(_sample_alphafold_backends()["alphafold3_local"])
    warning_backend["validation_ok"] = False
    state = build_alphafold_backend_form_state("alphafold3_local", warning_backend)

    assert state["submit_blocked"] is True
    assert "acknowledge" in state["submit_block_reason"].lower()


def test_summarize_alphafold_recommended_backend_mentions_default_and_reason() -> None:
    summary = summarize_alphafold_recommended_backend(_sample_alphafold_backends())

    assert summary["backend_name"] == "alphafold3_local"
    assert "recommended" in summary["label"].lower()
    assert any("available" in line.lower() or "validated" in line.lower() for line in summary["reason_lines"])


def test_build_alphafold_run_payload_preview_matches_json_backend() -> None:
    form_state = build_alphafold_backend_form_state(
        "alphafold3_local", _sample_alphafold_backends()["alphafold3_local"]
    )
    payload = build_alphafold_run_payload_preview(
        case_id="case-123",
        backend_name="alphafold3_local",
        form_state=form_state,
        job_name="job-json",
        sequence="SEQUENCE_UNUSED",
        json_path="/tmp/input.json",
        accession="P04637",
    )

    assert payload == {
        "case_id": "case-123",
        "job_name": "job-json",
        "backend_name": "alphafold3_local",
        "input_kind": "json",
        "json_path": "/tmp/input.json",
    }


def test_build_alphafold_backend_capability_chips_summarizes_core_flags() -> None:
    chips = build_alphafold_backend_capability_chips(
        "alphafold3_local", _sample_alphafold_backends()["alphafold3_local"]
    )

    assert chips == [
        "mode: local",
        "gpu: yes",
        "complexes: yes",
        "rna/dna/ligands: yes",
    ]


def test_build_alphafold_backend_capability_chips_handles_reference_backend() -> None:
    chips = build_alphafold_backend_capability_chips(
        "alphafold_db", _sample_alphafold_backends()["alphafold_db"]
    )

    assert chips == [
        "mode: reference",
        "gpu: no",
        "complexes: no",
        "rna/dna/ligands: no",
    ]


def test_format_alphafold_troubleshooting_summary_surfaces_invalid_backend_reason() -> None:
    payload = _sample_alphafold_backends()
    payload["alphafold3_local"]["validation_ok"] = False
    payload["alphafold3_local"]["validation_reason"] = "Command probe succeeded but GPU runtime was not detected."
    payload["alphafold3_local"]["diagnostics"] = {
        **payload["alphafold3_local"]["diagnostics"],
        "gpu_runtime_available": False,
        "configured_paths": {
            "alphafold3_model_dir": {
                "env_var": "NEOVAX_ALPHAFOLD3_MODEL_DIR",
                "configured": True,
                "path": "/missing/model_dir",
                "exists": False,
            }
        },
        "version_probe": {
            "probe_ok": False,
            "version_first_line": None,
            "probe_timed_out": False,
        },
    }

    summary = format_alphafold_troubleshooting_summary(payload)

    assert "AlphaFold validation troubleshooting" in summary
    assert "alphafold3_local" in summary
    assert "GPU runtime was not detected" in summary
    assert "NEOVAX_ALPHAFOLD3_MODEL_DIR" in summary
    assert "version probe failed" in summary.lower()


def test_format_alphafold_validation_error_renders_structured_fields() -> None:
    formatted = format_alphafold_validation_error(
        {
            "detail": "AlphaFold backend 'colabfold' failed environment validation: Command 'colabfold_batch' not found on PATH.",
            "backend_name": "colabfold",
            "validation_ok": False,
            "validation_reason": "Command 'colabfold_batch' not found on PATH.",
        }
    )

    assert "AlphaFold backend validation error" in formatted
    assert "backend_name=colabfold" in formatted
    assert "validation_ok=False" in formatted
    assert "validation_reason=Command 'colabfold_batch' not found on PATH." in formatted
