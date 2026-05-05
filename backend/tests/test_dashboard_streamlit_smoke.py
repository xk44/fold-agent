from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from collections.abc import Generator, Sequence
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_http(url: str, *, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=1.0)
            if response.status_code < 500:
                return
            last_error = f"status={response.status_code} body={response.text[:200]}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(0.2)
    raise AssertionError(f"Timed out waiting for {url}: {last_error}")


class _LiveApiServer:
    def __init__(self, *, database_url: str) -> None:
        self.database_url = database_url
        self.port = _find_free_port()
        self.process: subprocess.Popen[str] | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> str:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        env["NEOVAX_DATABASE_URL"] = self.database_url
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            _wait_for_http(f"{self.base_url}/health")
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self.base_url

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.process = None


@pytest.fixture
def live_api_url(tmp_path: Path) -> Generator[str, None, None]:
    database_path = tmp_path / "dashboard-smoke.db"
    with _LiveApiServer(database_url=f"sqlite:///{database_path}") as base_url:
        yield base_url


def _run_dashboard(*, base_url: str, home_dir: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.setenv("NEOVAX_API_URL", base_url)
    monkeypatch.setenv("HOME", str(home_dir))
    at = AppTest.from_file(PROJECT_ROOT / "frontend/app/dashboard.py", default_timeout=10)
    return at.run(timeout=30)


def _find_widget_by_label(widgets: Sequence[object], label: str):
    return next(widget for widget in widgets if getattr(widget, "label", None) == label)


def _json_payloads(at: AppTest) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for widget in at.json:
        try:
            payloads.append(json.loads(widget.value))
        except json.JSONDecodeError:
            continue
    return payloads


def _drop_sqlite_schema(database_path: Path) -> None:
    with sqlite3.connect(database_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        conn.execute("PRAGMA foreign_keys=OFF")
        for (table_name,) in rows:
            conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        conn.commit()


def _seed_linkback_case(live_api_url: str) -> dict[str, object]:
    case = httpx.post(
        f"{live_api_url}/cases",
        json={
            "species": "demo",
            "diagnosis_summary": "variant candidate review controls",
            "supervising_professional": "Dr. AppTest",
        },
        timeout=10.0,
    ).json()
    target_variant = httpx.post(
        f"{live_api_url}/cases/{case['id']}/variants",
        json={
            "genomic_coordinates": "7:140453136A>T",
            "gene": "KIT",
            "transcript": "NM_000222.3",
            "protein_change": "p.V600E",
            "caller_source": "mock",
            "quality_metrics": {"parsed_from": "vcf", "vaf": 0.42},
            "annotation_source": "vep",
        },
        timeout=10.0,
    ).json()
    other_variant = httpx.post(
        f"{live_api_url}/cases/{case['id']}/variants",
        json={
            "genomic_coordinates": "12:25398284C>T",
            "gene": "KRAS",
            "transcript": "NM_004985.5",
            "protein_change": "p.G12D",
            "caller_source": "mock",
            "quality_metrics": {"parsed_from": "vcf", "vaf": 0.18},
            "annotation_source": "vep",
        },
        timeout=10.0,
    ).json()
    target_candidate = httpx.post(
        f"{live_api_url}/cases/{case['id']}/candidates",
        json={
            "variant_id": target_variant["id"],
            "mhc_context": "HLA-A*02:01",
            "peptide_metadata": {"sequence": "SIINFEKL", "length": 8},
            "prediction_scores": {"binding_rank": 0.04, "immunogenicity": 0.8},
            "expression_evidence": {"tpm": 12.5},
            "structure_evidence": {
                "backend": "alphafold3_local",
                "alphafold_status": "completed",
                "ranking_score": 0.93,
                "ptm": 0.82,
                "iptm": 0.74,
            },
        },
        timeout=10.0,
    ).json()
    other_candidate = httpx.post(
        f"{live_api_url}/cases/{case['id']}/candidates",
        json={
            "variant_id": other_variant["id"],
            "mhc_context": "HLA-B*07:02",
            "peptide_metadata": {"sequence": "GADGVGKSA", "length": 9},
            "prediction_scores": {"binding_rank": 0.22, "immunogenicity": 0.31},
            "expression_evidence": {"tpm": 6.2},
            "structure_evidence": {
                "backend": "alphafold3_local",
                "alphafold_status": "completed",
                "ranking_score": 0.51,
                "ptm": 0.55,
                "iptm": 0.44,
            },
        },
        timeout=10.0,
    ).json()
    target_structure = httpx.post(
        f"{live_api_url}/cases/{case['id']}/structure-jobs",
        json={
            "candidate_id": target_candidate["id"],
            "backend_used": "alphafold3_local",
            "output_path": "/tmp/target-model.cif",
            "status": "completed",
        },
        timeout=10.0,
    ).json()
    candidate_review_report = httpx.post(
        f"{live_api_url}/cases/{case['id']}/reports/candidate-review",
        timeout=10.0,
    ).json()
    target_artifact = httpx.post(
        f"{live_api_url}/reports/{candidate_review_report['id']}/save",
        params={"format": "markdown"},
        timeout=10.0,
    ).json()
    ethics_report = httpx.post(
        f"{live_api_url}/cases/{case['id']}/reports/ethics-package",
        timeout=10.0,
    ).json()
    other_artifact = httpx.post(
        f"{live_api_url}/cases/{case['id']}/bundle/save",
        params={"format": "markdown"},
        timeout=10.0,
    ).json()
    other_structure = httpx.post(
        f"{live_api_url}/cases/{case['id']}/structure-jobs",
        json={
            "candidate_id": other_candidate["id"],
            "backend_used": "alphafold3_local",
            "output_path": "/tmp/other-model.cif",
            "status": "completed",
        },
        timeout=10.0,
    ).json()
    return {
        "case": case,
        "target_variant": target_variant,
        "other_variant": other_variant,
        "target_candidate": target_candidate,
        "other_candidate": other_candidate,
        "target_structure": target_structure,
        "other_structure": other_structure,
        "candidate_review_report": candidate_review_report,
        "ethics_report": ethics_report,
        "target_artifact": target_artifact,
        "other_artifact": other_artifact,
    }


def test_dashboard_streamlit_smoke_renders_degraded_health_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "dashboard-degraded-health.db"
    with _LiveApiServer(database_url=f"sqlite:///{database_path}") as base_url:
        _drop_sqlite_schema(database_path)
        health_response = httpx.get(f"{base_url}/health", timeout=10.0)
        assert health_response.status_code == 503
        assert health_response.json()["status"] == "degraded"

        at = _run_dashboard(base_url=base_url, home_dir=tmp_path / "home", monkeypatch=monkeypatch)

    assert not at.exception, at.exception[0].value
    assert any(widget.value == "API health" for widget in at.subheader)
    assert any(
        "API degraded" in str(widget.value) and "missing:" in str(widget.value)
        for widget in at.warning
    )
    assert any(payload.get("status") == "degraded" for payload in _json_payloads(at))


def test_dashboard_streamlit_smoke_renders_live_case_without_exception(
    live_api_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = httpx.post(
        f"{live_api_url}/cases",
        json={
            "species": "demo",
            "diagnosis_summary": "Streamlit smoke case",
            "supervising_professional": "Dr. AppTest",
        },
        timeout=10.0,
    )
    response.raise_for_status()
    created_case = response.json()

    at = _run_dashboard(base_url=live_api_url, home_dir=tmp_path / "home", monkeypatch=monkeypatch)

    assert not at.exception, at.exception[0].value
    assert at.title[0].value == "NeoVax-Agent"
    assert any(widget.value == "API health" for widget in at.subheader)
    assert any(widget.value == "Safety preflight" for widget in at.subheader)
    assert any(
        payload.get("status") == "ok" and payload.get("version") == "0.1.0-alpha"
        for payload in _json_payloads(at)
    )
    case_selector = _find_widget_by_label(at.selectbox, "Select case")
    assert any(
        created_case["diagnosis_summary"] in option and created_case["id"][:8] in option
        for option in case_selector.options
    )


def test_dashboard_streamlit_smoke_variant_candidate_review_controls_render(
    live_api_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_linkback_case(live_api_url)

    at = _run_dashboard(base_url=live_api_url, home_dir=tmp_path / "home", monkeypatch=monkeypatch)

    assert not at.exception, at.exception[0].value
    selectbox_labels = [widget.label for widget in at.selectbox]
    assert "Variant filter status" in selectbox_labels
    assert "Variant sort" in selectbox_labels
    assert "Variant columns" in selectbox_labels
    assert "Candidate filter status" in selectbox_labels
    assert "Candidate MHC filter" in selectbox_labels
    assert "Candidate sort" in selectbox_labels
    assert "Candidate columns" in selectbox_labels
    number_input_labels = [widget.label for widget in at.number_input]
    assert "Variant VAF min" in number_input_labels
    assert "Variant VAF max" in number_input_labels
    assert "Candidate ranking min" in number_input_labels
    assert "Candidate binding max" in number_input_labels
    button_labels = [widget.label for widget in at.button]
    assert "Focus related candidate" in button_labels
    assert "Focus related structure job" in button_labels
    assert "Focus related report" in button_labels
    assert "Focus candidate review report" in button_labels
    assert "Focus candidate artifact" in button_labels
    assert "Focus structure job" in button_labels


def test_dashboard_streamlit_smoke_variant_focus_buttons_drive_selectors(
    live_api_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded = _seed_linkback_case(live_api_url)

    at = _run_dashboard(base_url=live_api_url, home_dir=tmp_path / "home", monkeypatch=monkeypatch)
    assert not at.exception, at.exception[0].value

    _find_widget_by_label(at.button, "Load case bundle").click()
    at.run(timeout=30)
    assert not at.exception, at.exception[0].value

    _find_widget_by_label(at.selectbox, "Candidate review target").set_value(seeded["other_candidate"]["id"])
    _find_widget_by_label(at.selectbox, "Candidate MHC filter").set_value("HLA-B*07:02")
    _find_widget_by_label(at.selectbox, "Variant review target").set_value(seeded["target_variant"]["id"])
    _find_widget_by_label(at.selectbox, "Structure job detail").set_value(seeded["other_structure"]["id"])
    _find_widget_by_label(at.selectbox, "Report detail/export").set_value(seeded["ethics_report"]["id"])
    at.run(timeout=30)

    _find_widget_by_label(at.button, "Focus related candidate").click()
    at.run(timeout=30)
    assert _find_widget_by_label(at.selectbox, "Candidate review target").value == seeded["target_candidate"]["id"]
    assert _find_widget_by_label(at.selectbox, "Candidate MHC filter").value == "all"

    _find_widget_by_label(at.selectbox, "Structure job detail").set_value(seeded["other_structure"]["id"])
    at.run(timeout=30)
    _find_widget_by_label(at.button, "Focus related structure job").click()
    at.run(timeout=30)
    assert _find_widget_by_label(at.selectbox, "Structure job detail").value == seeded["target_structure"]["id"]

    _find_widget_by_label(at.selectbox, "Report detail/export").set_value(seeded["ethics_report"]["id"])
    at.run(timeout=30)
    _find_widget_by_label(at.button, "Focus related report").click()
    at.run(timeout=30)
    assert _find_widget_by_label(at.selectbox, "Report detail/export").value == seeded["candidate_review_report"]["id"]



def test_dashboard_streamlit_smoke_candidate_focus_buttons_drive_selectors(
    live_api_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded = _seed_linkback_case(live_api_url)

    at = _run_dashboard(base_url=live_api_url, home_dir=tmp_path / "home", monkeypatch=monkeypatch)
    assert not at.exception, at.exception[0].value

    _find_widget_by_label(at.button, "Load case bundle").click()
    at.run(timeout=30)
    assert not at.exception, at.exception[0].value

    _find_widget_by_label(at.selectbox, "Candidate review target").set_value(seeded["target_candidate"]["id"])
    _find_widget_by_label(at.selectbox, "Structure job detail").set_value(seeded["other_structure"]["id"])
    _find_widget_by_label(at.selectbox, "Report detail/export").set_value(seeded["ethics_report"]["id"])
    _find_widget_by_label(at.selectbox, "Artifact download target").set_value(seeded["other_artifact"])
    at.run(timeout=30)

    _find_widget_by_label(at.button, "Focus structure job").click()
    at.run(timeout=30)
    assert _find_widget_by_label(at.selectbox, "Structure job detail").value == seeded["target_structure"]["id"]

    _find_widget_by_label(at.selectbox, "Report detail/export").set_value(seeded["ethics_report"]["id"])
    at.run(timeout=30)
    _find_widget_by_label(at.button, "Focus candidate review report").click()
    at.run(timeout=60)
    assert _find_widget_by_label(at.selectbox, "Report detail/export").value == seeded["candidate_review_report"]["id"]

    _find_widget_by_label(at.selectbox, "Artifact download target").set_value(seeded["other_artifact"])
    at.run(timeout=30)
    _find_widget_by_label(at.button, "Focus candidate artifact").click()
    at.run(timeout=30)
    assert _find_widget_by_label(at.selectbox, "Artifact download target").value["path"] == seeded["target_artifact"]["path"]

def test_dashboard_streamlit_smoke_can_create_case_and_block_preflight(
    live_api_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = _run_dashboard(base_url=live_api_url, home_dir=tmp_path / "home", monkeypatch=monkeypatch)

    assert not at.exception, at.exception[0].value

    _find_widget_by_label(at.text_area, "Diagnosis summary").input("Created from AppTest")
    _find_widget_by_label(at.text_input, "Supervising professional").input("Dr. Streamlit")
    _find_widget_by_label(at.button, "Create case").click()
    at.run(timeout=30)

    assert not at.exception, at.exception[0].value

    cases_response = httpx.get(f"{live_api_url}/cases", timeout=10.0)
    cases_response.raise_for_status()
    created_case = next(
        case for case in cases_response.json() if case["diagnosis_summary"] == "Created from AppTest"
    )
    case_selector = _find_widget_by_label(at.selectbox, "Select case")
    assert any(
        created_case["diagnosis_summary"] in option and created_case["id"][:8] in option
        for option in case_selector.options
    )

    _find_widget_by_label(at.text_area, "Content to scan").input(
        "This includes an injection instruction and dosing schedule."
    )
    _find_widget_by_label(at.button, "Run preflight").click()
    at.run(timeout=30)

    assert not at.exception, at.exception[0].value
    assert any(
        payload.get("status") == "block" and payload.get("allowed") is False
        for payload in _json_payloads(at)
    )
