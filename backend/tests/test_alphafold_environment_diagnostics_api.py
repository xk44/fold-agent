import subprocess

from fastapi.testclient import TestClient

from backend.app.alphafold import shells
from backend.app.schemas import AlphaFoldValidationErrorResponse


def test_alphafold_status_exposes_colabfold_and_af3_diagnostics(client: TestClient) -> None:
    response = client.get("/alphafold/backends")
    assert response.status_code == 200
    payload = response.json()

    colabfold = payload["colabfold"]
    assert "diagnostics" in colabfold
    assert colabfold["diagnostics"]["host_url_supported"] is True
    assert colabfold["diagnostics"]["supports_a3m_input"] is True
    assert colabfold["diagnostics"]["supports_multimer_fasta_colon_syntax"] is True
    assert "validation_reason" in colabfold
    assert "version_probe" in colabfold["diagnostics"]

    af3 = payload["alphafold3_local"]
    assert "diagnostics" in af3
    assert af3["diagnostics"]["requires_json_input"] is True
    assert af3["diagnostics"]["supports_input_dir"] is True
    assert af3["diagnostics"]["parses_output_directory"] is True
    assert af3["diagnostics"]["harvests_model_cif_artifacts"] is True
    assert "validation_reason" in af3
    assert "gpu_runtime_available" in af3["diagnostics"]


def test_list_alphafold_shell_statuses_marks_probe_failure_as_not_valid(monkeypatch) -> None:
    def fake_which(command: str) -> str | None:
        mapping = {
            "colabfold_batch": "/usr/bin/colabfold_batch",
            "run_alphafold": "/usr/bin/run_alphafold",
            "alphafold": "/usr/bin/alphafold",
            "nvidia-smi": "/usr/bin/nvidia-smi",
        }
        return mapping.get(command)

    def fake_run(command: list[str], capture_output: bool, text: bool, timeout: int, check: bool):
        if command[0] == "alphafold":
            return subprocess.CompletedProcess(command, 2, stdout="", stderr="boom")
        return subprocess.CompletedProcess(command, 0, stdout="ok version\n", stderr="")

    monkeypatch.setattr(shells, "which", fake_which)
    monkeypatch.setattr(shells.subprocess, "run", fake_run)

    payload = shells.list_alphafold_shell_statuses()
    af3 = payload["alphafold3_local"]
    assert af3["available"] is True
    assert af3["validation_ok"] is False
    assert af3["diagnostics"]["version_probe"]["probe_ok"] is False
    assert "probe" in af3["validation_reason"].lower()


def test_list_alphafold_shell_statuses_surfaces_probe_timeout(monkeypatch) -> None:
    def fake_which(command: str) -> str | None:
        mapping = {
            "colabfold_batch": "/usr/bin/colabfold_batch",
            "run_alphafold": "/usr/bin/run_alphafold",
            "alphafold": "/usr/bin/alphafold",
            "nvidia-smi": "/usr/bin/nvidia-smi",
        }
        return mapping.get(command)

    def fake_run(command: list[str], capture_output: bool, text: bool, timeout: int, check: bool):
        if command[0] == "colabfold_batch":
            raise subprocess.TimeoutExpired(command, timeout)
        return subprocess.CompletedProcess(command, 0, stdout="ok version\n", stderr="")

    monkeypatch.setattr(shells, "which", fake_which)
    monkeypatch.setattr(shells.subprocess, "run", fake_run)

    payload = shells.list_alphafold_shell_statuses()
    colabfold = payload["colabfold"]
    assert colabfold["validation_ok"] is False
    assert colabfold["diagnostics"]["version_probe"]["probe_timed_out"] is True


def test_alphafold_run_rejects_backend_when_validation_not_ok(
    client: TestClient, monkeypatch
) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "validation gate case"},
    )
    case_id = create_case.json()["id"]

    monkeypatch.setattr(
        "backend.app.main.get_shell_backend_status",
        lambda backend_name: shells.AlphaFoldShellStatus(
            name=backend_name,
            command="colabfold_batch",
            available=True,
            path="/usr/bin/colabfold_batch",
            validation_ok=False,
            notes="simulated invalid backend",
            validation_reason="Executable probe failed during validation.",
            version_string=None,
            version_probe_ok=False,
            probe_timed_out=False,
        ),
    )

    response = client.post(
        "/alphafold/backends/colabfold/run",
        json={
            "case_id": case_id,
            "job_name": "blocked-colabfold",
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
        },
    )

    assert response.status_code == 409
    payload = response.json()
    parsed = AlphaFoldValidationErrorResponse.model_validate(payload)
    assert parsed.backend_name == "colabfold"
    assert parsed.validation_ok is False
    assert parsed.validation_reason == "Executable probe failed during validation."
    assert "Executable probe failed during validation." in parsed.detail
