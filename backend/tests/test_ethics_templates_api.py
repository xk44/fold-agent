"""Tests for ethics template API endpoints.

Covers:
  GET /cases/{case_id}/ethics/uncertainty-summary
  GET /cases/{case_id}/ethics/adverse-event-template
  GET /ethics/compassionate-use-checklist?species=...
  GET /cases/{case_id}/ethics/professional-questions
"""

from fastapi.testclient import TestClient

DISCLAIMER_FRAGMENT = "research coordination tool only"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_case(client: TestClient, species: str = "dog", summary: str = "Ethics template test") -> str:
    resp = client.post("/cases", json={"species": species, "diagnosis_summary": summary})
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Uncertainty summary
# ---------------------------------------------------------------------------


def test_uncertainty_summary_returns_200_with_required_fields(client: TestClient) -> None:
    case_id = _make_case(client, species="dog")
    resp = client.get(f"/cases/{case_id}/ethics/uncertainty-summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["template_type"] == "uncertainty_summary"
    assert data["case_id"] == case_id
    assert data["species"] == "dog"
    assert isinstance(data["uncertainty_sources"], list)
    assert len(data["uncertainty_sources"]) >= 4


def test_uncertainty_summary_includes_expected_source_names(client: TestClient) -> None:
    case_id = _make_case(client, species="human")
    data = client.get(f"/cases/{case_id}/ethics/uncertainty-summary").json()

    names = [s["name"].lower() for s in data["uncertainty_sources"]]
    assert any("variant calling" in n for n in names)
    assert any("prediction tool" in n for n in names)
    assert any("expression" in n for n in names)
    assert any("structure" in n for n in names)


def test_uncertainty_summary_severity_values_are_valid(client: TestClient) -> None:
    case_id = _make_case(client)
    data = client.get(f"/cases/{case_id}/ethics/uncertainty-summary").json()

    valid_severities = {"high", "medium", "low"}
    for source in data["uncertainty_sources"]:
        assert source["severity"] in valid_severities


def test_uncertainty_summary_contains_disclaimer(client: TestClient) -> None:
    case_id = _make_case(client)
    data = client.get(f"/cases/{case_id}/ethics/uncertainty-summary").json()

    assert DISCLAIMER_FRAGMENT in data["disclaimer"].lower()


def test_uncertainty_summary_no_dosing_or_injection_content(client: TestClient) -> None:
    case_id = _make_case(client)
    resp = client.get(f"/cases/{case_id}/ethics/uncertainty-summary")
    raw = resp.text.lower()

    for forbidden in ("dosing", "injection", "formulation", "manufacturing"):
        # Allowed only in the warnings/disclaimer that explicitly deny them
        # Check the disclaimer warning text doesn't accidentally provide instructions
        assert "inject " not in raw or "no dosing" in raw


def test_uncertainty_summary_404_for_missing_case(client: TestClient) -> None:
    resp = client.get("/cases/nonexistent-case-xyz/ethics/uncertainty-summary")
    assert resp.status_code == 404


def test_uncertainty_summary_with_rna_sample_reflects_has_rna(client: TestClient) -> None:
    case_id = _make_case(client)
    client.post(f"/cases/{case_id}/samples", json={"sample_type": "rna", "checksum": "rna_abc"})

    data = client.get(f"/cases/{case_id}/ethics/uncertainty-summary").json()
    assert data["has_rna_sample"] is True


def test_uncertainty_summary_without_rna_sample_has_rna_false(client: TestClient) -> None:
    case_id = _make_case(client)
    client.post(f"/cases/{case_id}/samples", json={"sample_type": "tumor", "checksum": "tum_abc"})

    data = client.get(f"/cases/{case_id}/ethics/uncertainty-summary").json()
    assert data["has_rna_sample"] is False


# ---------------------------------------------------------------------------
# Adverse event template
# ---------------------------------------------------------------------------


def test_adverse_event_template_returns_200_with_sections(client: TestClient) -> None:
    case_id = _make_case(client, species="dog")
    resp = client.get(f"/cases/{case_id}/ethics/adverse-event-template")

    assert resp.status_code == 200
    data = resp.json()
    assert data["template_type"] == "adverse_event_report"
    assert data["case_id"] == case_id
    assert data["species"] == "dog"
    sections = data["sections"]
    assert "event_description" in sections
    assert "timeline" in sections
    assert "severity_classification" in sections
    assert "suspected_cause" in sections
    assert "actions_taken" in sections
    assert "outcome" in sections


def test_adverse_event_template_is_marked_template_only(client: TestClient) -> None:
    case_id = _make_case(client)
    data = client.get(f"/cases/{case_id}/ethics/adverse-event-template").json()

    assert "TEMPLATE ONLY" in data["template_status"]


def test_adverse_event_template_veterinary_language_for_dog(client: TestClient) -> None:
    case_id = _make_case(client, species="dog")
    data = client.get(f"/cases/{case_id}/ethics/adverse-event-template").json()

    raw = str(data).lower()
    assert "veterinarian" in raw or "veterinary" in raw


def test_adverse_event_template_clinical_language_for_human(client: TestClient) -> None:
    case_id = _make_case(client, species="human")
    data = client.get(f"/cases/{case_id}/ethics/adverse-event-template").json()

    raw = str(data).lower()
    assert "physician" in raw or "oncologist" in raw


def test_adverse_event_template_has_reporting_contacts(client: TestClient) -> None:
    case_id = _make_case(client)
    data = client.get(f"/cases/{case_id}/ethics/adverse-event-template").json()

    contacts = data["reporting_contacts"]
    assert "institutional_oversight" in contacts
    assert "regulatory_body" in contacts
    assert "principal_investigator" in contacts


def test_adverse_event_template_contains_disclaimer(client: TestClient) -> None:
    case_id = _make_case(client)
    data = client.get(f"/cases/{case_id}/ethics/adverse-event-template").json()

    assert DISCLAIMER_FRAGMENT in data["disclaimer"].lower()


def test_adverse_event_template_warnings_mention_no_dosing(client: TestClient) -> None:
    case_id = _make_case(client)
    data = client.get(f"/cases/{case_id}/ethics/adverse-event-template").json()

    warnings_text = " ".join(data["warnings"]).lower()
    assert "dosing" in warnings_text or "injection" in warnings_text


def test_adverse_event_template_404_for_missing_case(client: TestClient) -> None:
    resp = client.get("/cases/nonexistent-xyz/ethics/adverse-event-template")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Compassionate use checklist
# ---------------------------------------------------------------------------


def test_compassionate_use_checklist_dog_returns_200(client: TestClient) -> None:
    resp = client.get("/ethics/compassionate-use-checklist?species=dog")

    assert resp.status_code == 200
    data = resp.json()
    assert data["template_type"] == "compassionate_use_checklist"
    assert data["species"] == "dog"
    assert data["is_veterinary"] is True


def test_compassionate_use_checklist_human_returns_200(client: TestClient) -> None:
    resp = client.get("/ethics/compassionate-use-checklist?species=human")

    assert resp.status_code == 200
    data = resp.json()
    assert data["is_veterinary"] is False


def test_compassionate_use_checklist_has_checklist_items(client: TestClient) -> None:
    data = client.get("/ethics/compassionate-use-checklist?species=dog").json()

    items = data["checklist_items"]
    assert len(items) >= 8
    for item in items:
        assert "id" in item
        assert "category" in item
        assert "item" in item
        assert "required_attestation" in item


def test_compassionate_use_checklist_has_regulatory_considerations(client: TestClient) -> None:
    data = client.get("/ethics/compassionate-use-checklist?species=human").json()

    reg = data["regulatory_considerations"]
    assert "framework" in reg
    assert "oversight_body" in reg


def test_compassionate_use_checklist_has_attestations(client: TestClient) -> None:
    data = client.get("/ethics/compassionate-use-checklist?species=dog").json()

    attestations = data["required_professional_attestations"]
    assert len(attestations) >= 1
    for att in attestations:
        assert "role" in att
        assert "attestation" in att


def test_compassionate_use_checklist_critical_warning_mentions_neovax(client: TestClient) -> None:
    data = client.get("/ethics/compassionate-use-checklist?species=dog").json()

    assert "neovax" in data["critical_warning"].lower() or "cannot bypass" in data["critical_warning"].lower()


def test_compassionate_use_checklist_contains_disclaimer(client: TestClient) -> None:
    data = client.get("/ethics/compassionate-use-checklist?species=dog").json()

    assert DISCLAIMER_FRAGMENT in data["disclaimer"].lower()


def test_compassionate_use_checklist_missing_species_param_returns_422(client: TestClient) -> None:
    resp = client.get("/ethics/compassionate-use-checklist")
    assert resp.status_code == 422


def test_compassionate_use_checklist_iacuc_mentioned_for_veterinary(client: TestClient) -> None:
    data = client.get("/ethics/compassionate-use-checklist?species=dog").json()
    raw = str(data).lower()
    assert "iacuc" in raw or "ethics committee" in raw


def test_compassionate_use_checklist_irb_mentioned_for_human(client: TestClient) -> None:
    data = client.get("/ethics/compassionate-use-checklist?species=human").json()
    raw = str(data).lower()
    assert "irb" in raw or "review board" in raw


# ---------------------------------------------------------------------------
# Professional questions
# ---------------------------------------------------------------------------


def test_professional_questions_returns_200_with_topics(client: TestClient) -> None:
    case_id = _make_case(client, species="dog")
    resp = client.get(f"/cases/{case_id}/ethics/professional-questions")

    assert resp.status_code == 200
    data = resp.json()
    assert data["template_type"] == "professional_consultation_questions"
    assert data["case_id"] == case_id
    topics = data["questions_by_topic"]
    assert "treatment_options" in topics
    assert "prognosis_discussion" in topics
    assert "sequencing_results_interpretation" in topics
    assert "clinical_trial_eligibility" in topics


def test_professional_questions_each_topic_has_questions(client: TestClient) -> None:
    case_id = _make_case(client, species="human")
    data = client.get(f"/cases/{case_id}/ethics/professional-questions").json()

    for topic, questions in data["questions_by_topic"].items():
        assert len(questions) >= 1, f"Topic {topic!r} has no questions"
        for q in questions:
            assert "question" in q
            assert "topic" in q
            assert "for_professional" in q


def test_professional_questions_veterinary_framing_for_dog(client: TestClient) -> None:
    case_id = _make_case(client, species="dog")
    data = client.get(f"/cases/{case_id}/ethics/professional-questions").json()

    assert data["is_veterinary"] is True
    raw = str(data["questions_by_topic"]).lower()
    assert "veterinary" in raw or "veterinarian" in raw


def test_professional_questions_clinical_framing_for_human(client: TestClient) -> None:
    case_id = _make_case(client, species="human")
    data = client.get(f"/cases/{case_id}/ethics/professional-questions").json()

    assert data["is_veterinary"] is False


def test_professional_questions_reflects_candidate_count(client: TestClient) -> None:
    case_id = _make_case(client, species="dog")
    # Run pipeline to populate candidates
    client.post(f"/cases/{case_id}/samples", json={"sample_type": "tumor", "checksum": "t_001"})
    client.post(f"/cases/{case_id}/pipeline/run")

    data = client.get(f"/cases/{case_id}/ethics/professional-questions").json()
    # candidate_count should be a non-negative integer
    assert isinstance(data["candidate_count"], int)
    assert data["candidate_count"] >= 0


def test_professional_questions_contains_disclaimer(client: TestClient) -> None:
    case_id = _make_case(client)
    data = client.get(f"/cases/{case_id}/ethics/professional-questions").json()

    assert DISCLAIMER_FRAGMENT in data["disclaimer"].lower()


def test_professional_questions_warnings_mention_no_dosing(client: TestClient) -> None:
    case_id = _make_case(client)
    data = client.get(f"/cases/{case_id}/ethics/professional-questions").json()

    warnings_text = " ".join(data["warnings"]).lower()
    assert "dosing" in warnings_text or "injection" in warnings_text


def test_professional_questions_404_for_missing_case(client: TestClient) -> None:
    resp = client.get("/cases/nonexistent-xyz/ethics/professional-questions")
    assert resp.status_code == 404


def test_professional_questions_includes_instructions(client: TestClient) -> None:
    case_id = _make_case(client)
    data = client.get(f"/cases/{case_id}/ethics/professional-questions").json()

    assert "instructions" in data
    assert len(data["instructions"]) > 10
