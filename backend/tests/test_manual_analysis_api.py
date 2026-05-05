from fastapi.testclient import TestClient


def test_manual_variant_and_candidate_creation_flow(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Manual analysis case"},
    )
    case_id = create_case.json()["id"]

    variant_response = client.post(
        f"/cases/{case_id}/variants",
        json={
            "genomic_coordinates": "chr1:12345 A>G",
            "gene": "EGFR",
            "transcript": "NM_005228.5",
            "protein_change": "p.L858R",
            "caller_source": "manual_import",
            "annotation_source": "manual_entry",
        },
    )
    assert variant_response.status_code == 201
    variant = variant_response.json()
    assert variant["case_id"] == case_id
    assert variant["gene"] == "EGFR"
    assert variant["review_status"] == "unreviewed"

    candidate_response = client.post(
        f"/cases/{case_id}/candidates",
        json={
            "variant_id": variant["id"],
            "peptide_metadata": {"sequence": "EGFRL858R", "length": 9},
            "mhc_context": "HLA-A*02:01",
            "prediction_scores": {"binding_rank": 0.03},
        },
    )
    assert candidate_response.status_code == 201
    candidate = candidate_response.json()
    assert candidate["case_id"] == case_id
    assert candidate["variant_id"] == variant["id"]
    assert candidate["mhc_context"] == "HLA-A*02:01"
    assert candidate["review_status"] == "unreviewed"


def test_manual_candidate_creation_rejects_unknown_variant(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Manual analysis case"},
    )
    case_id = create_case.json()["id"]

    response = client.post(
        f"/cases/{case_id}/candidates",
        json={
            "variant_id": "missing-variant",
            "mhc_context": "HLA-A*02:01",
        },
    )

    assert response.status_code == 404
