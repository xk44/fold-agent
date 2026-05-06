from fastapi.testclient import TestClient


def test_manual_variant_creation_with_sample_linkage(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Variant sample linkage case"},
    )
    case_id = create_case.json()["id"]

    sample = client.post(
        f"/cases/{case_id}/samples",
        json={"sample_type": "tumor", "checksum": "variant123"},
    ).json()

    variant_response = client.post(
        f"/cases/{case_id}/variants",
        json={
            "sample_id": sample["id"],
            "genomic_coordinates": "chr1:12345 A>G",
            "gene": "EGFR",
            "protein_change": "p.L858R",
            "annotation_source": "manual_entry",
        },
    )
    assert variant_response.status_code == 201
    variant = variant_response.json()
    assert variant["case_id"] == case_id
    assert variant["sample_id"] == sample["id"]

    variants = client.get(f"/cases/{case_id}/variants").json()
    assert variants[0]["sample_id"] == sample["id"]


def test_variant_creation_rejects_sample_from_other_case(client: TestClient) -> None:
    case_a = client.post("/cases", json={"species": "demo", "diagnosis_summary": "case a"}).json()[
        "id"
    ]
    case_b = client.post("/cases", json={"species": "demo", "diagnosis_summary": "case b"}).json()[
        "id"
    ]

    sample = client.post(
        f"/cases/{case_a}/samples",
        json={"sample_type": "tumor"},
    ).json()

    response = client.post(
        f"/cases/{case_b}/variants",
        json={
            "sample_id": sample["id"],
            "genomic_coordinates": "chr1:12345 A>G",
        },
    )

    assert response.status_code == 404
