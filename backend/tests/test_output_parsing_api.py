import json

from fastapi.testclient import TestClient

from backend.app.pipeline.shells import ShellExecution


def test_vep_shell_output_parsing_updates_variant_and_report_summary(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "VEP parsed case"},
    )
    case_id = create_case.json()["id"]

    def fake_execute_pipeline_adapter(adapter_name: str, payload: dict) -> ShellExecution:
        assert adapter_name == "vep"
        return ShellExecution(
            adapter="vep",
            mode="execute",
            command=["vep", "--input_file", payload["input_vcf"]],
            available=True,
            validation_ok=True,
            notes="simulated",
            status="completed",
            stdout=json.dumps(
                {
                    "variant": {
                        "gene": "BRAF",
                        "protein_change": "p.V600E",
                        "genomic_coordinates": "chr7:140453136 A>T",
                        "annotation_source": "vep_shell",
                    }
                }
            ),
            stderr="",
            timed_out=False,
            return_code=0,
            output_path="/tmp/mock.vep.json",
        )

    monkeypatch.setattr("backend.app.main.execute_pipeline_adapter", fake_execute_pipeline_adapter)

    run_response = client.post(
        "/pipeline/adapters/vep/run",
        json={"case_id": case_id, "input_vcf": "/tmp/mock.vcf", "output_path": "/tmp/mock.vep.json"},
    )
    assert run_response.status_code == 200

    variants = client.get(f"/cases/{case_id}/variants").json()
    assert variants[0]["gene"] == "BRAF"
    assert variants[0]["protein_change"] == "p.V600E"
    assert variants[0]["annotation_source"] == "vep_shell"
    executions = client.get(f"/cases/{case_id}/executions").json()
    vep_execution = next(item for item in executions if item["runner_name"] == "vep")
    assert variants[0]["last_parsed_execution_id"] == vep_execution["id"]

    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    assert report["content_json"]["top_candidate_gene"] == "BRAF"


def test_pvactools_shell_output_parsing_updates_candidate_scores(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "pVAC parsed case"},
    )
    case_id = create_case.json()["id"]

    def fake_execute_pipeline_adapter(adapter_name: str, payload: dict) -> ShellExecution:
        assert adapter_name == "pvactools"
        return ShellExecution(
            adapter="pvactools",
            mode="execute",
            command=["pvacseq", payload["input_vcf"], payload["sample_name"]],
            available=True,
            validation_ok=True,
            notes="simulated",
            status="completed",
            stdout=json.dumps(
                {
                    "candidate": {
                        "mhc_context": "HLA-A*02:01",
                        "peptide_sequence": "GLYTESTAA",
                        "binding_rank": 0.12,
                        "immunogenicity": 0.89,
                    }
                }
            ),
            stderr="",
            timed_out=False,
            return_code=0,
            output_path="/tmp/mock.pvac.json",
        )

    monkeypatch.setattr("backend.app.main.execute_pipeline_adapter", fake_execute_pipeline_adapter)

    run_response = client.post(
        "/pipeline/adapters/pvactools/run",
        json={
            "case_id": case_id,
            "input_vcf": "/tmp/mock.vcf",
            "sample_name": "demo-sample",
            "output_path": "/tmp/mock.pvac.json",
        },
    )
    assert run_response.status_code == 200

    candidates = client.get(f"/cases/{case_id}/candidates").json()
    assert candidates[0]["mhc_context"] == "HLA-A*02:01"
    assert candidates[0]["prediction_scores"]["binding_rank"] == 0.12
    assert candidates[0]["prediction_scores"]["immunogenicity"] == 0.89
    assert candidates[0]["peptide_metadata"]["sequence"] == "GLYTESTAA"
    executions = client.get(f"/cases/{case_id}/executions").json()
    pvac_execution = next(item for item in executions if item["runner_name"] == "pvactools")
    assert candidates[0]["last_parsed_execution_id"] == pvac_execution["id"]
