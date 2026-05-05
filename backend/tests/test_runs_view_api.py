from fastapi.testclient import TestClient


def test_unified_runs_view_lists_pipeline_execution_and_report_events(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Unified runs case"},
    )
    case_id = create_case.json()["id"]

    client.post(f"/cases/{case_id}/pipeline/run")
    client.post(
        "/pipeline/adapters/vep/run",
        json={
            "case_id": case_id,
            "input_vcf": "/tmp/mock.vcf",
            "output_path": "/tmp/mock.vep.json",
        },
    )
    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()

    response = client.get(f"/cases/{case_id}/runs")
    assert response.status_code == 200
    runs = response.json()

    assert len(runs) == 3
    run_kinds = {item["run_kind"] for item in runs}
    assert run_kinds == {"pipeline_run", "execution_run", "report"}
    assert all(item["case_id"] == case_id for item in runs)
    assert any(item["name"] == report["report_type"] for item in runs)
    timestamps = [item["created_at"] for item in runs]
    assert timestamps == sorted(timestamps, reverse=True)
    execution_runs = [item for item in runs if item["run_kind"] == "execution_run"]
    assert execution_runs
    assert execution_runs[0]["artifacts"]


def test_unified_runs_view_for_missing_case_returns_404(client: TestClient) -> None:
    response = client.get("/cases/missing-case/runs")

    assert response.status_code == 404
