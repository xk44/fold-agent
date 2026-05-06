"""Tests for Safety Report Enhancements (Phase 7).

Covers:
  - EvidenceLevel / EvidenceAssessment logic (all levels)
  - FalsePositiveRisk / FPAssessment logic
  - Citation generation
  - Attestation recording and retrieval
  - All 6 API endpoints
  - Edge cases: empty case, case with full data
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.safety_reports import (
    AttestationType,
    EvidenceLevel,
    FalsePositiveRisk,
    ProfessionalAttestation,
    assess_evidence_level,
    assess_false_positive_risk,
    build_report_citations,
    check_attestation_required,
    get_attestation,
    record_attestation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_case(
    client: TestClient, species: str = "demo", summary: str = "Safety report test"
) -> str:
    resp = client.post("/cases", json={"species": species, "diagnosis_summary": summary})
    assert resp.status_code == 201
    return resp.json()["id"]


def _make_case_with_candidates(client: TestClient, species: str = "demo") -> tuple[str, list[str]]:
    """Create a case with samples, variants, and candidates. Returns (case_id, candidate_ids)."""
    case_id = _make_case(client, species=species)

    # Register samples
    tumor_resp = client.post(
        f"/cases/{case_id}/samples",
        json={"sample_type": "tumor", "file_paths": {"bam": "/tmp/tumor.bam"}},
    )
    assert tumor_resp.status_code == 201
    normal_resp = client.post(
        f"/cases/{case_id}/samples",
        json={"sample_type": "normal", "file_paths": {"bam": "/tmp/normal.bam"}},
    )
    assert normal_resp.status_code == 201
    rna_resp = client.post(
        f"/cases/{case_id}/samples",
        json={"sample_type": "rna", "file_paths": {"fastq": "/tmp/rna.fastq"}},
    )
    assert rna_resp.status_code == 201

    # Register variants
    variant_ids = []
    for i in range(3):
        v_resp = client.post(
            f"/cases/{case_id}/variants",
            json={
                "genomic_coordinates": f"chr1:100{i}:A>T",
                "gene": f"GENE{i}",
                "caller_source": "mutect2",
                "annotation_source": "ensembl_vep",
            },
        )
        assert v_resp.status_code == 201
        variant_ids.append(v_resp.json()["id"])

    # Register candidates
    candidate_ids = []
    for vid in variant_ids:
        c_resp = client.post(
            f"/cases/{case_id}/candidates",
            json={
                "variant_id": vid,
                "prediction_scores": {
                    "tool": "netmhcpan",
                    "binding_affinity": 50.0,
                    "rank": 0.5,
                },
                "expression_evidence": {"tpm": 12.5},
            },
        )
        assert c_resp.status_code == 201
        candidate_ids.append(c_resp.json()["id"])

    return case_id, candidate_ids


# ---------------------------------------------------------------------------
# Unit-level: EvidenceAssessment
# ---------------------------------------------------------------------------


def test_evidence_insufficient_on_empty_case(client: TestClient) -> None:
    """Empty case (no samples, no candidates) → insufficient."""
    from backend.app.db import SessionLocal

    case_id = _make_case(client)
    with SessionLocal() as db:
        assessment = assess_evidence_level(case_id, db)

    assert assessment.level == EvidenceLevel.insufficient
    assert any("No candidate antigens" in f for f in assessment.flags)
    assert any("No samples" in f for f in assessment.flags)


def test_evidence_weak_with_few_candidates(client: TestClient) -> None:
    """Case with < 3 candidates but samples present → weak or moderate."""
    from backend.app.db import SessionLocal

    case_id = _make_case(client)
    # Add samples
    client.post(f"/cases/{case_id}/samples", json={"sample_type": "tumor"})
    client.post(f"/cases/{case_id}/samples", json={"sample_type": "normal"})
    # Add 1 variant + candidate
    v_resp = client.post(
        f"/cases/{case_id}/variants",
        json={"genomic_coordinates": "chr1:500:G>A", "gene": "TP53"},
    )
    vid = v_resp.json()["id"]
    client.post(f"/cases/{case_id}/candidates", json={"variant_id": vid})

    with SessionLocal() as db:
        assessment = assess_evidence_level(case_id, db)

    assert assessment.level in (EvidenceLevel.weak, EvidenceLevel.moderate)
    assert any("Fewer than 3" in f for f in assessment.flags)


def test_evidence_strong_with_full_data(client: TestClient) -> None:
    """Fully populated case → strong evidence."""
    from backend.app.db import SessionLocal

    case_id, _ = _make_case_with_candidates(client)

    with SessionLocal() as db:
        assessment = assess_evidence_level(case_id, db)

    # With all samples + 3 candidates with binding + expression, should be strong or moderate
    assert assessment.level in (EvidenceLevel.strong, EvidenceLevel.moderate)


def test_evidence_flags_missing_rna(client: TestClient) -> None:
    """Case without RNA sample gets flagged."""
    from backend.app.db import SessionLocal

    case_id = _make_case(client)
    client.post(f"/cases/{case_id}/samples", json={"sample_type": "tumor"})
    client.post(f"/cases/{case_id}/samples", json={"sample_type": "normal"})
    v_resp = client.post(
        f"/cases/{case_id}/variants",
        json={"genomic_coordinates": "chr2:200:C>T"},
    )
    vid = v_resp.json()["id"]
    for _ in range(3):
        client.post(f"/cases/{case_id}/candidates", json={"variant_id": vid})

    with SessionLocal() as db:
        assessment = assess_evidence_level(case_id, db)

    assert any("RNA" in f for f in assessment.flags)


def test_evidence_flags_missing_binding_predictions(client: TestClient) -> None:
    """Candidates without prediction_scores → binding flag."""
    from backend.app.db import SessionLocal

    case_id = _make_case(client)
    client.post(f"/cases/{case_id}/samples", json={"sample_type": "tumor"})
    client.post(f"/cases/{case_id}/samples", json={"sample_type": "normal"})
    client.post(f"/cases/{case_id}/samples", json={"sample_type": "rna"})
    v_resp = client.post(
        f"/cases/{case_id}/variants",
        json={"genomic_coordinates": "chr3:300:G>C"},
    )
    vid = v_resp.json()["id"]
    for _ in range(3):
        # No prediction_scores
        client.post(f"/cases/{case_id}/candidates", json={"variant_id": vid})

    with SessionLocal() as db:
        assessment = assess_evidence_level(case_id, db)

    assert any("binding affinity" in f.lower() or "binding" in f.lower() for f in assessment.flags)


# ---------------------------------------------------------------------------
# Unit-level: FPAssessment
# ---------------------------------------------------------------------------


def test_fp_risk_low_on_empty_candidates(client: TestClient) -> None:
    from backend.app.db import SessionLocal

    with SessionLocal() as db:
        fp = assess_false_positive_risk([], db)

    assert fp.risk == FalsePositiveRisk.low


def test_fp_risk_moderate_with_missing_expression(client: TestClient) -> None:
    from backend.app.db import SessionLocal
    from backend.app.models import CandidateAntigen

    case_id = _make_case(client)
    v_resp = client.post(
        f"/cases/{case_id}/variants",
        json={"genomic_coordinates": "chr4:400:A>G"},
    )
    vid = v_resp.json()["id"]
    # Add candidates without expression_evidence
    cand_ids = []
    for _ in range(3):
        c_resp = client.post(
            f"/cases/{case_id}/candidates",
            json={"variant_id": vid, "prediction_scores": {"binding_affinity": 200}},
        )
        cand_ids.append(c_resp.json()["id"])

    with SessionLocal() as db:
        candidates = db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case_id).all()
        fp = assess_false_positive_risk(candidates, db)

    assert fp.risk in (FalsePositiveRisk.moderate, FalsePositiveRisk.high)
    assert any(w.warnings for w in fp.per_candidate)


def test_fp_risk_warns_on_high_affinity(client: TestClient) -> None:
    from backend.app.db import SessionLocal
    from backend.app.models import CandidateAntigen

    case_id = _make_case(client)
    v_resp = client.post(
        f"/cases/{case_id}/variants",
        json={"genomic_coordinates": "chr5:500:T>C"},
    )
    vid = v_resp.json()["id"]
    client.post(
        f"/cases/{case_id}/candidates",
        json={
            "variant_id": vid,
            "prediction_scores": {"binding_affinity": 1000.0},
            "expression_evidence": {"tpm": 5.0},
        },
    )

    with SessionLocal() as db:
        candidates = db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case_id).all()
        fp = assess_false_positive_risk(candidates, db)

    all_warnings = [w for c in fp.per_candidate for w in c.warnings]
    assert any("500 nM" in w or "weak binder" in w.lower() for w in all_warnings)


def test_fp_per_candidate_details_populated(client: TestClient) -> None:
    from backend.app.db import SessionLocal
    from backend.app.models import CandidateAntigen

    case_id, candidate_ids = _make_case_with_candidates(client)

    with SessionLocal() as db:
        candidates = db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case_id).all()
        fp = assess_false_positive_risk(candidates, db)

    assert isinstance(fp.per_candidate, list)
    assert isinstance(fp.overall_warnings, list)


# ---------------------------------------------------------------------------
# Unit-level: Citations
# ---------------------------------------------------------------------------


def test_citations_fallback_to_mock_for_empty_case(client: TestClient) -> None:
    from backend.app.db import SessionLocal

    case_id = _make_case(client)
    with SessionLocal() as db:
        citations = build_report_citations(case_id, db)

    assert len(citations) >= 1
    sources = [c.source for c in citations]
    assert any("Mock" in s or "FoldAgent" in s for s in sources)


def test_citations_include_caller_and_annotation(client: TestClient) -> None:
    from backend.app.db import SessionLocal

    case_id = _make_case(client, species="human")
    v_resp = client.post(
        f"/cases/{case_id}/variants",
        json={
            "genomic_coordinates": "chr1:100:A>T",
            "caller_source": "mutect2",
            "annotation_source": "ensembl_vep",
        },
    )
    assert v_resp.status_code == 201

    with SessionLocal() as db:
        citations = build_report_citations(case_id, db)

    sources = [c.source.lower() for c in citations]
    assert any("mutect" in s for s in sources)
    assert any("vep" in s or "ensembl" in s for s in sources)


def test_citations_include_binding_tool(client: TestClient) -> None:
    from backend.app.db import SessionLocal

    case_id = _make_case(client)
    v_resp = client.post(
        f"/cases/{case_id}/variants",
        json={"genomic_coordinates": "chr1:100:A>T"},
    )
    vid = v_resp.json()["id"]
    client.post(
        f"/cases/{case_id}/candidates",
        json={"variant_id": vid, "prediction_scores": {"tool": "netmhcpan"}},
    )

    with SessionLocal() as db:
        citations = build_report_citations(case_id, db)

    sources = [c.source.lower() for c in citations]
    assert any("netmhc" in s for s in sources)


def test_citations_include_reference_genome_for_human(client: TestClient) -> None:
    from backend.app.db import SessionLocal

    case_id = _make_case(client, species="human")
    with SessionLocal() as db:
        citations = build_report_citations(case_id, db)

    sources = [c.source.lower() for c in citations]
    assert any("grch" in s or "hg38" in s for s in sources)


def test_citations_include_reference_genome_for_dog(client: TestClient) -> None:
    from backend.app.db import SessionLocal

    case_id = _make_case(client, species="dog")
    with SessionLocal() as db:
        citations = build_report_citations(case_id, db)

    sources = [c.source.lower() for c in citations]
    assert any("canfam" in s for s in sources)


def test_citations_have_accessed_date(client: TestClient) -> None:
    from backend.app.db import SessionLocal

    case_id = _make_case(client)
    with SessionLocal() as db:
        citations = build_report_citations(case_id, db)

    for cit in citations:
        assert isinstance(cit.accessed_date, str)
        assert len(cit.accessed_date) == 10  # YYYY-MM-DD


# ---------------------------------------------------------------------------
# Unit-level: Attestation
# ---------------------------------------------------------------------------


def test_attestation_not_required_for_insufficient_evidence(client: TestClient) -> None:
    from backend.app.db import SessionLocal

    case_id = _make_case(client)  # empty case → insufficient evidence
    with SessionLocal() as db:
        required = check_attestation_required(case_id, db)

    assert required is False


def test_attestation_record_and_retrieve(client: TestClient) -> None:
    from backend.app.db import SessionLocal
    from backend.app.safety_reports import _attestation_store

    # Clear store to avoid cross-test pollution
    _attestation_store.clear()

    case_id = _make_case(client)
    attestation = ProfessionalAttestation(
        type=AttestationType.research_only,
        attester_name="Dr. Jane Smith",
        credentials="DVM, PhD",
        attestation_text="I confirm these outputs are research coordination artifacts only.",
    )

    with SessionLocal() as db:
        result = record_attestation(case_id, attestation, db)

    assert result["status"] == "recorded"
    assert result["case_id"] == case_id
    assert result["attestation"]["attester_name"] == "Dr. Jane Smith"

    retrieved = get_attestation(case_id)
    assert retrieved is not None
    assert retrieved["type"] == "research_only"


def test_attestation_none_when_not_recorded(client: TestClient) -> None:
    from backend.app.safety_reports import _attestation_store

    _attestation_store.clear()
    result = get_attestation("nonexistent-case")
    assert result is None


# ---------------------------------------------------------------------------
# API: GET /cases/{case_id}/evidence
# ---------------------------------------------------------------------------


def test_api_evidence_404_unknown_case(client: TestClient) -> None:
    resp = client.get("/cases/does-not-exist/evidence")
    assert resp.status_code == 404


def test_api_evidence_empty_case_returns_insufficient(client: TestClient) -> None:
    case_id = _make_case(client)
    resp = client.get(f"/cases/{case_id}/evidence")
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == case_id
    assert data["level"] == "insufficient"
    assert isinstance(data["flags"], list)
    assert isinstance(data["recommendations"], list)
    assert len(data["flags"]) > 0


def test_api_evidence_full_case_returns_non_insufficient(client: TestClient) -> None:
    case_id, _ = _make_case_with_candidates(client)
    resp = client.get(f"/cases/{case_id}/evidence")
    assert resp.status_code == 200
    data = resp.json()
    assert data["level"] != "insufficient"


# ---------------------------------------------------------------------------
# API: GET /cases/{case_id}/false-positive-risk
# ---------------------------------------------------------------------------


def test_api_fp_risk_404_unknown_case(client: TestClient) -> None:
    resp = client.get("/cases/missing/false-positive-risk")
    assert resp.status_code == 404


def test_api_fp_risk_empty_case_returns_low(client: TestClient) -> None:
    case_id = _make_case(client)
    resp = client.get(f"/cases/{case_id}/false-positive-risk")
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == case_id
    assert data["risk"] == "low"
    assert isinstance(data["per_candidate"], list)
    assert isinstance(data["overall_warnings"], list)


def test_api_fp_risk_case_with_candidates(client: TestClient) -> None:
    case_id, _ = _make_case_with_candidates(client)
    resp = client.get(f"/cases/{case_id}/false-positive-risk")
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk"] in ("low", "moderate", "high")


# ---------------------------------------------------------------------------
# API: GET /cases/{case_id}/report/citations
# ---------------------------------------------------------------------------


def test_api_citations_404_unknown_case(client: TestClient) -> None:
    resp = client.get("/cases/nope/report/citations")
    assert resp.status_code == 404


def test_api_citations_returns_list(client: TestClient) -> None:
    case_id = _make_case(client)
    resp = client.get(f"/cases/{case_id}/report/citations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == case_id
    assert isinstance(data["citations"], list)
    assert len(data["citations"]) >= 1


def test_api_citations_each_has_required_fields(client: TestClient) -> None:
    case_id = _make_case(client)
    resp = client.get(f"/cases/{case_id}/report/citations")
    assert resp.status_code == 200
    for cit in resp.json()["citations"]:
        assert "source" in cit
        assert "description" in cit
        assert "accessed_date" in cit
        # url may be None but key must be present
        assert "url" in cit


def test_api_citations_with_variants_includes_tools(client: TestClient) -> None:
    case_id, _ = _make_case_with_candidates(client, species="human")
    resp = client.get(f"/cases/{case_id}/report/citations")
    assert resp.status_code == 200
    sources = [c["source"].lower() for c in resp.json()["citations"]]
    assert any("mutect" in s for s in sources)
    assert any("vep" in s or "ensembl" in s for s in sources)
    assert any("netmhc" in s for s in sources)


# ---------------------------------------------------------------------------
# API: POST /cases/{case_id}/attestation
# ---------------------------------------------------------------------------


def test_api_attestation_post_404_unknown_case(client: TestClient) -> None:
    resp = client.post(
        "/cases/nope/attestation",
        json={
            "type": "research_only",
            "attester_name": "Dr. X",
            "credentials": "PhD",
            "attestation_text": "Confirmed.",
        },
    )
    assert resp.status_code == 404


def test_api_attestation_post_missing_attester_name(client: TestClient) -> None:
    case_id = _make_case(client)
    resp = client.post(
        f"/cases/{case_id}/attestation",
        json={"type": "research_only", "attestation_text": "Confirmed."},
    )
    assert resp.status_code == 422


def test_api_attestation_post_missing_attestation_text(client: TestClient) -> None:
    case_id = _make_case(client)
    resp = client.post(
        f"/cases/{case_id}/attestation",
        json={"type": "research_only", "attester_name": "Dr. X"},
    )
    assert resp.status_code == 422


def test_api_attestation_post_invalid_type(client: TestClient) -> None:
    case_id = _make_case(client)
    resp = client.post(
        f"/cases/{case_id}/attestation",
        json={
            "type": "not_a_real_type",
            "attester_name": "Dr. X",
            "attestation_text": "Confirmed.",
        },
    )
    assert resp.status_code == 422


def test_api_attestation_post_success(client: TestClient) -> None:
    from backend.app.safety_reports import _attestation_store

    _attestation_store.clear()
    case_id = _make_case(client)
    resp = client.post(
        f"/cases/{case_id}/attestation",
        json={
            "type": "veterinary_review",
            "attester_name": "Dr. Alice Vet",
            "credentials": "DVM, DACVIM",
            "attestation_text": "I have reviewed these research outputs under veterinary professional supervision.",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "recorded"
    assert data["case_id"] == case_id
    assert data["attestation"]["attester_name"] == "Dr. Alice Vet"
    assert data["attestation"]["type"] == "veterinary_review"


def test_api_attestation_all_types_accepted(client: TestClient) -> None:
    from backend.app.safety_reports import _attestation_store

    for att_type in ("veterinary_review", "medical_review", "research_only"):
        _attestation_store.clear()
        case_id = _make_case(client)
        resp = client.post(
            f"/cases/{case_id}/attestation",
            json={
                "type": att_type,
                "attester_name": "Dr. Test",
                "attestation_text": "Confirmed.",
            },
        )
        assert resp.status_code == 201, f"Failed for type {att_type}: {resp.text}"


# ---------------------------------------------------------------------------
# API: GET /cases/{case_id}/attestation
# ---------------------------------------------------------------------------


def test_api_get_attestation_404_unknown_case(client: TestClient) -> None:
    resp = client.get("/cases/nope/attestation")
    assert resp.status_code == 404


def test_api_get_attestation_not_recorded(client: TestClient) -> None:
    from backend.app.safety_reports import _attestation_store

    _attestation_store.clear()
    case_id = _make_case(client)
    resp = client.get(f"/cases/{case_id}/attestation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == case_id
    assert data["attestation_recorded"] is False
    assert data["attestation"] is None
    assert "attestation_required" in data


def test_api_get_attestation_after_recording(client: TestClient) -> None:
    from backend.app.safety_reports import _attestation_store

    _attestation_store.clear()
    case_id = _make_case(client)
    client.post(
        f"/cases/{case_id}/attestation",
        json={
            "type": "research_only",
            "attester_name": "Dr. Bob",
            "attestation_text": "Verified.",
        },
    )
    resp = client.get(f"/cases/{case_id}/attestation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["attestation_recorded"] is True
    assert data["attestation"]["attester_name"] == "Dr. Bob"


# ---------------------------------------------------------------------------
# API: GET /cases/{case_id}/report/enhanced
# ---------------------------------------------------------------------------


def test_api_enhanced_report_404_unknown_case(client: TestClient) -> None:
    resp = client.get("/cases/ghost/report/enhanced")
    assert resp.status_code == 404


def test_api_enhanced_report_structure_empty_case(client: TestClient) -> None:
    from backend.app.safety_reports import _attestation_store

    _attestation_store.clear()
    case_id = _make_case(client)
    resp = client.get(f"/cases/{case_id}/report/enhanced")
    assert resp.status_code == 200
    data = resp.json()

    assert data["case_id"] == case_id
    assert "safety_label" in data
    assert "disclaimer" in data
    assert "evidence_assessment" in data
    assert "false_positive_risk" in data
    assert "citations" in data
    assert "attestation" in data

    assert data["evidence_assessment"]["level"] == "insufficient"
    assert data["false_positive_risk"]["risk"] == "low"


def test_api_enhanced_report_structure_full_case(client: TestClient) -> None:
    from backend.app.safety_reports import _attestation_store

    _attestation_store.clear()
    case_id, _ = _make_case_with_candidates(client, species="human")
    resp = client.get(f"/cases/{case_id}/report/enhanced")
    assert resp.status_code == 200
    data = resp.json()

    assert data["evidence_assessment"]["level"] != "insufficient"
    assert len(data["citations"]) >= 1
    assert isinstance(data["false_positive_risk"]["per_candidate"], list)
    assert data["attestation"]["recorded"] is False  # none posted yet


def test_api_enhanced_report_includes_attestation_when_recorded(client: TestClient) -> None:
    from backend.app.safety_reports import _attestation_store

    _attestation_store.clear()
    case_id, _ = _make_case_with_candidates(client)
    client.post(
        f"/cases/{case_id}/attestation",
        json={
            "type": "medical_review",
            "attester_name": "Dr. Carol",
            "credentials": "MD, PhD",
            "attestation_text": "Research outputs reviewed.",
        },
    )
    resp = client.get(f"/cases/{case_id}/report/enhanced")
    assert resp.status_code == 200
    data = resp.json()
    assert data["attestation"]["recorded"] is True
    assert data["attestation"]["details"]["attester_name"] == "Dr. Carol"


def test_api_enhanced_report_safety_label_present(client: TestClient) -> None:
    case_id = _make_case(client)
    resp = client.get(f"/cases/{case_id}/report/enhanced")
    assert resp.status_code == 200
    data = resp.json()
    assert "not administerable" in data["safety_label"].lower()
    assert "research coordination" in data["disclaimer"].lower()


def test_api_enhanced_report_audit_action_logged(client: TestClient) -> None:
    case_id = _make_case(client)
    client.get(f"/cases/{case_id}/report/enhanced")
    audit_resp = client.get(f"/audit/{case_id}")
    assert audit_resp.status_code == 200
    actions = [e["action"] for e in audit_resp.json()]
    assert "report.enhanced.generated" in actions
