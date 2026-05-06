from fastapi.testclient import TestClient


def test_mock_variant_and_candidate_endpoints_return_dashboard_ready_data(
    client: TestClient,
) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Candidate table case"},
    )
    case_id = create_case.json()["id"]

    variants_response = client.get(f"/cases/{case_id}/variants")
    assert variants_response.status_code == 200
    variants = variants_response.json()
    assert len(variants) >= 1
    assert variants[0]["case_id"] == case_id
    assert variants[0]["gene"]
    assert variants[0]["review_status"] == "unreviewed"

    candidates_response = client.get(f"/cases/{case_id}/candidates")
    assert candidates_response.status_code == 200
    candidates = candidates_response.json()
    assert len(candidates) >= 1
    assert candidates[0]["case_id"] == case_id
    assert candidates[0]["variant_id"] == variants[0]["id"]
    assert candidates[0]["mhc_context"]
    assert candidates[0]["prediction_scores"]
    assert candidates[0]["review_status"] == "unreviewed"


def test_candidate_report_reflects_mock_candidate_summary(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Candidate report enrichment case"},
    )
    case_id = create_case.json()["id"]

    report_response = client.post(f"/cases/{case_id}/reports/candidate-review")
    assert report_response.status_code == 201
    report = report_response.json()

    assert report["content_json"]["candidate_count"] >= 1
    assert report["content_json"]["top_candidate_gene"]
    assert "top candidate" in report["content_text"].lower()


def test_variant_and_candidate_review_updates_are_persisted(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Review workflow case"},
    )
    case_id = create_case.json()["id"]

    variant = client.get(f"/cases/{case_id}/variants").json()[0]
    candidate = client.get(f"/cases/{case_id}/candidates").json()[0]

    variant_update = client.patch(
        f"/variants/{variant['id']}/review",
        json={"review_status": "needs_data", "expert_review_notes": "Need RNA validation"},
    )
    assert variant_update.status_code == 200
    assert variant_update.json()["review_status"] == "needs_data"
    assert variant_update.json()["expert_review_notes"] == "Need RNA validation"

    candidate_update = client.patch(
        f"/candidates/{candidate['id']}/review",
        json={
            "review_status": "expert_accepted_for_further_research",
            "expert_review_notes": "Promising mock candidate",
        },
    )
    assert candidate_update.status_code == 200
    assert candidate_update.json()["review_status"] == "expert_accepted_for_further_research"

    refreshed_variant = client.get(f"/cases/{case_id}/variants").json()[0]
    refreshed_candidate = client.get(f"/cases/{case_id}/candidates").json()[0]
    assert refreshed_variant["review_status"] == "needs_data"
    assert refreshed_candidate["review_status"] == "expert_accepted_for_further_research"
    assert refreshed_candidate["expert_review_notes"] == "Promising mock candidate"


def test_missing_case_variant_and_candidate_requests_return_404(client: TestClient) -> None:
    variants_response = client.get("/cases/missing-case/variants")
    candidates_response = client.get("/cases/missing-case/candidates")

    assert variants_response.status_code == 404
    assert candidates_response.status_code == 404
