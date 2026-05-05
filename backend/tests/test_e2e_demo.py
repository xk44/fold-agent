"""End-to-end integration tests for the FoldAgent demo pipeline (Phase 21).

Exercises the full demo flow via the FastAPI test client:
  - Case creation through the demo endpoint
  - Data completeness and checklist checks
  - Pipeline steps listing and dry-run
  - Candidate retrieval
  - Evidence assessment, FP risk, citations
  - HTML and Markdown report generation, report version
  - Privacy summary, structure jobs, ethics uncertainty summary
  - Source validation (hallucination guard)
  - Security audit chain
  - Synthetic dataset creation
  - Demo reset/cleanup

All data is synthetic. NOT FOR CLINICAL USE.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.e2e


class TestEndToEndDemo:
    def test_full_pipeline(self, client: TestClient) -> None:
        # 1. Create demo case
        resp = client.post("/demo/create-case")
        assert resp.status_code == 201
        body = resp.json()
        case_id = body["case_id"]
        assert case_id is not None

        # 2. Check data completeness
        resp = client.get(f"/cases/{case_id}/data/missing")
        assert resp.status_code == 200

        # 3. Check data checklist
        resp = client.get(f"/cases/{case_id}/data/checklist")
        assert resp.status_code == 200

        # 4. Get pipeline steps
        resp = client.get("/pipeline/steps")
        assert resp.status_code == 200
        steps = resp.json()
        assert len(steps) > 0

        # 5. Dry-run pipeline
        resp = client.post("/pipeline/dry-run", json={"steps": [s["name"] for s in steps[:3]]})
        assert resp.status_code == 200
        dry_run = resp.json()
        assert "valid" in dry_run
        assert "ok" in dry_run

        # 6. Get candidates
        resp = client.get(f"/cases/{case_id}/candidates")
        assert resp.status_code == 200
        candidates = resp.json()
        assert len(candidates) >= 1

        # 7. Get evidence assessment
        resp = client.get(f"/cases/{case_id}/evidence")
        assert resp.status_code == 200

        # 8. Get FP risk
        resp = client.get(f"/cases/{case_id}/false-positive-risk")
        assert resp.status_code == 200

        # 9. Get citations
        resp = client.get(f"/cases/{case_id}/report/citations")
        assert resp.status_code == 200

        # 10. Get HTML report
        resp = client.get(f"/cases/{case_id}/report/html")
        assert resp.status_code == 200
        assert "html" in resp.text.lower()

        # 11. Get Markdown report
        resp = client.get(f"/cases/{case_id}/report/markdown")
        assert resp.status_code == 200

        # 12. Get report version
        resp = client.get(f"/cases/{case_id}/report/version")
        assert resp.status_code == 200

        # 13. Get privacy summary
        resp = client.get(f"/cases/{case_id}/privacy")
        assert resp.status_code == 200

        # 14. Get structure jobs
        resp = client.get(f"/cases/{case_id}/structure-jobs")
        assert resp.status_code == 200

        # 15. Get ethics uncertainty summary
        resp = client.get(f"/cases/{case_id}/ethics/uncertainty-summary")
        assert resp.status_code == 200

        # 16. Validate sources
        resp = client.post(
            "/validate/sources",
            json={"text": "Data from Ensembl VEP and NetMHCpan."},
        )
        assert resp.status_code == 200

        # 17. Check audit chain
        resp = client.get(f"/security/audit-chain/{case_id}")
        assert resp.status_code == 200

        # 18. Cleanup
        resp = client.post("/demo/reset")
        assert resp.status_code == 200

    def test_synthetic_dataset(self, client: TestClient) -> None:
        resp = client.post("/demo/create-dataset?n_cases=2")
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["cases"]) == 2
        # Cleanup
        client.post("/demo/reset")
