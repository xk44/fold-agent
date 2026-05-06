"""Tests for Phase 4 data loading and validation endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_case(client: TestClient) -> str:
    resp = client.post("/cases", json={"species": "demo", "diagnosis_summary": "data loading test"})
    assert resp.status_code == 201
    return resp.json()["id"]


class TestSupportedFormats:
    def test_list_formats(self, client: TestClient) -> None:
        resp = client.get("/data/formats")
        assert resp.status_code == 200
        body = resp.json()
        assert "fastq" in body
        assert "bam" in body
        assert "vcf" in body
        assert "csv" in body


class TestFileValidation:
    def test_valid_fastq(self, client: TestClient) -> None:
        resp = client.post("/data/validate-file", json={"filename": "tumor_R1.fastq.gz"})
        assert resp.status_code == 200
        assert resp.json()["valid"] is True
        assert resp.json()["detected_format"] == "fastq"

    def test_valid_bam(self, client: TestClient) -> None:
        resp = client.post("/data/validate-file", json={"filename": "aligned.bam"})
        assert resp.json()["valid"] is True
        assert resp.json()["detected_format"] == "bam"

    def test_valid_vcf(self, client: TestClient) -> None:
        resp = client.post("/data/validate-file", json={"filename": "somatic.vcf.gz"})
        assert resp.json()["valid"] is True
        assert resp.json()["detected_format"] == "vcf"

    def test_invalid_format(self, client: TestClient) -> None:
        resp = client.post("/data/validate-file", json={"filename": "photo.jpg"})
        assert resp.json()["valid"] is False
        assert "Unrecognized" in resp.json()["error"]

    def test_format_mismatch(self, client: TestClient) -> None:
        resp = client.post(
            "/data/validate-file", json={"filename": "data.bam", "expected_format": "vcf"}
        )
        assert resp.json()["valid"] is False

    def test_validate_multiple_files(self, client: TestClient) -> None:
        resp = client.post(
            "/data/validate-files",
            json={"file_paths": {"tumor_r1": "tumor_R1.fastq.gz", "normal_bam": "normal.bam"}},
        )
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 2
        assert all(r["valid"] for r in results)


class TestSampleRoleDetection:
    def test_detect_tumor(self, client: TestClient) -> None:
        resp = client.post("/data/detect-role", json={"filename": "tumor_sample_R1.fastq.gz"})
        assert resp.json()["detected_role"] == "tumor"

    def test_detect_normal(self, client: TestClient) -> None:
        resp = client.post("/data/detect-role", json={"label": "matched_normal"})
        assert resp.json()["detected_role"] == "normal"

    def test_detect_rna(self, client: TestClient) -> None:
        resp = client.post("/data/detect-role", json={"filename": "rnaseq_expression.fastq.gz"})
        assert resp.json()["detected_role"] == "rna"

    def test_detect_unknown(self, client: TestClient) -> None:
        resp = client.post("/data/detect-role", json={"filename": "sample_001.bam"})
        assert resp.json()["detected_role"] == "other"


class TestMissingDataDetection:
    def test_empty_case_reports_issues(self, client: TestClient) -> None:
        case_id = _create_case(client)
        resp = client.get(f"/cases/{case_id}/data/missing")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data_completeness"] == "incomplete"
        assert len(body["issues"]) > 0
        assert body["sample_count"] == 0

    def test_case_with_tumor_no_normal(self, client: TestClient) -> None:
        case_id = _create_case(client)
        client.post(f"/cases/{case_id}/samples", json={"sample_type": "tumor"})
        resp = client.get(f"/cases/{case_id}/data/missing")
        body = resp.json()
        assert body["has_tumor"] is True
        assert body["has_normal"] is False
        assert any("matched-normal" in i for i in body["issues"])

    def test_case_with_tumor_and_normal(self, client: TestClient) -> None:
        case_id = _create_case(client)
        client.post(f"/cases/{case_id}/samples", json={"sample_type": "tumor"})
        client.post(f"/cases/{case_id}/samples", json={"sample_type": "normal"})
        resp = client.get(f"/cases/{case_id}/data/missing")
        body = resp.json()
        assert body["has_tumor"] is True
        assert body["has_normal"] is True
        assert not any("matched-normal" in i for i in body["issues"])


class TestDataChecklist:
    def test_empty_case_checklist(self, client: TestClient) -> None:
        case_id = _create_case(client)
        resp = client.get(f"/cases/{case_id}/data/checklist")
        assert resp.status_code == 200
        checklist = resp.json()
        assert len(checklist) >= 5
        assert not checklist[0]["done"]  # tumor sample not registered

    def test_checklist_reflects_progress(self, client: TestClient) -> None:
        case_id = _create_case(client)
        client.post(f"/cases/{case_id}/samples", json={"sample_type": "tumor"})
        checklist = client.get(f"/cases/{case_id}/data/checklist").json()
        tumor_item = next(c for c in checklist if "tumor" in c["item"].lower())
        assert tumor_item["done"] is True
