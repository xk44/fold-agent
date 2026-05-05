import json

from fastapi.testclient import TestClient

from backend.app.alphafold.shells import AlphaFoldExecution
from backend.app.pipeline.shells import ShellExecution


def test_pipeline_execution_records_parsed_ok_status(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "parse ok case"},
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
            stdout=json.dumps({"variant": {"gene": "BRAF"}}),
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

    executions = client.get(f"/cases/{case_id}/executions").json()
    execution = next(item for item in executions if item["runner_name"] == "vep")
    assert execution["parse_status"] == "parsed_ok"
    assert execution["parse_error"] is None


def test_pipeline_execution_records_parse_failure_details(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "parse fail case"},
    )
    case_id = create_case.json()["id"]

    def fake_execute_pipeline_adapter(adapter_name: str, payload: dict) -> ShellExecution:
        return ShellExecution(
            adapter=adapter_name,
            mode="execute",
            command=[adapter_name, payload["input_vcf"]],
            available=True,
            validation_ok=True,
            notes="simulated",
            status="completed",
            stdout='{"unexpected": true}',
            stderr="",
            timed_out=False,
            return_code=0,
            output_path="/tmp/mock.output.json",
        )

    monkeypatch.setattr("backend.app.main.execute_pipeline_adapter", fake_execute_pipeline_adapter)

    run_response = client.post(
        "/pipeline/adapters/vep/run",
        json={"case_id": case_id, "input_vcf": "/tmp/mock.vcf", "output_path": "/tmp/mock.output.json"},
    )
    assert run_response.status_code == 200

    executions = client.get(f"/cases/{case_id}/executions").json()
    execution = next(item for item in executions if item["runner_name"] == "vep")
    assert execution["parse_status"] == "parse_failed"
    assert "variant" in execution["parse_error"]


def test_pipeline_execution_records_skipped_parse_for_non_completed_runs(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "parse skipped case"},
    )
    case_id = create_case.json()["id"]

    def fake_execute_pipeline_adapter(adapter_name: str, payload: dict) -> ShellExecution:
        return ShellExecution(
            adapter=adapter_name,
            mode="execute",
            command=[adapter_name, payload["input_vcf"]],
            available=True,
            validation_ok=True,
            notes="simulated",
            status="failed",
            stdout="not-json",
            stderr="adapter failed",
            timed_out=False,
            return_code=2,
            output_path=None,
        )

    monkeypatch.setattr("backend.app.main.execute_pipeline_adapter", fake_execute_pipeline_adapter)

    run_response = client.post(
        "/pipeline/adapters/vep/run",
        json={"case_id": case_id, "input_vcf": "/tmp/mock.vcf"},
    )
    assert run_response.status_code == 200

    executions = client.get(f"/cases/{case_id}/executions").json()
    execution = next(item for item in executions if item["runner_name"] == "vep")
    assert execution["parse_status"] == "skipped_not_completed"
    assert "failed" in execution["parse_error"]


def test_alphafold_execution_records_parse_failure_details(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "alphafold parse fail case"},
    )
    case_id = create_case.json()["id"]

    def fake_execute_alphafold_backend(backend_name: str, payload: dict) -> AlphaFoldExecution:
        return AlphaFoldExecution(
            backend=backend_name,
            mode="execute",
            command=["colabfold_batch", "/tmp/demo.fa", "/tmp/demo_out"],
            available=True,
            validation_ok=True,
            notes="simulated",
            status="completed",
            stdout=json.dumps({"unexpected": True}),
            stderr="",
            timed_out=False,
            return_code=0,
        )

    monkeypatch.setattr("backend.app.main.execute_alphafold_backend", fake_execute_alphafold_backend)

    run_response = client.post(
        "/alphafold/backends/colabfold/run",
        json={
            "case_id": case_id,
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
            "job_name": "demo-job",
        },
    )
    assert run_response.status_code == 200

    executions = client.get(f"/cases/{case_id}/executions").json()
    execution = next(item for item in executions if item["runner_name"] == "colabfold")
    assert execution["parse_status"] == "parse_failed"
    assert "structure" in execution["parse_error"]
