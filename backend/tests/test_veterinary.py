"""Tests for backend.app.veterinary — Phase 24 Tier 3 (unit tests, no API endpoints)."""

import pytest

from backend.app.veterinary import (
    # Feature 3
    AVMA_GUIDELINES,
    MHC_ALLELE_DATABASE,
    # Feature 2
    ORTHOLOG_DATABASE,
    USDA_REQUIREMENTS_BY_SPECIES,
    # Feature 1
    CalibrationWarning,
    CompassionateUseDocument,
    MHCAllele,
    OrthologComparison,
    Species,
    VetAttestationRequirements,
    check_variant_conservation,
    compare_orthologs,
    find_cross_species_equivalent,
    generate_compassionate_use_doc,
    generate_owner_consent_form,
    get_alleles_for_species,
    get_attestation_requirements,
    get_calibration_warning,
    rank_animal_models,
)

# ============================================================================
# Feature 1: Species-specific MHC allele database
# ============================================================================


class TestMHCAlleleDatabase:
    def test_database_has_50_plus_entries(self):
        assert len(MHC_ALLELE_DATABASE) >= 50

    def test_all_entries_are_mhc_allele_instances(self):
        for entry in MHC_ALLELE_DATABASE:
            assert isinstance(entry, MHCAllele)

    def test_locus_values_valid(self):
        valid_loci = {"MHC-I", "MHC-II"}
        for allele in MHC_ALLELE_DATABASE:
            assert allele.locus in valid_loci, f"{allele.allele_name} has invalid locus"

    def test_species_enum_values(self):
        species_values = {s.value for s in Species}
        assert "human" in species_values
        assert "canine" in species_values
        assert "feline" in species_values
        assert "equine" in species_values
        assert "murine" in species_values
        assert "porcine" in species_values

    def test_human_alleles_count(self):
        human = get_alleles_for_species(Species.human)
        assert len(human) >= 15

    def test_canine_alleles_count(self):
        canine = get_alleles_for_species(Species.canine)
        assert len(canine) >= 12

    def test_feline_alleles_count(self):
        feline = get_alleles_for_species(Species.feline)
        assert len(feline) >= 8

    def test_equine_alleles_count(self):
        equine = get_alleles_for_species(Species.equine)
        assert len(equine) >= 6

    def test_murine_alleles_count(self):
        murine = get_alleles_for_species(Species.murine)
        assert len(murine) >= 8

    def test_porcine_alleles_exist(self):
        porcine = get_alleles_for_species(Species.porcine)
        assert len(porcine) > 0

    def test_get_alleles_returns_correct_species(self):
        for sp in Species:
            alleles = get_alleles_for_species(sp)
            for a in alleles:
                assert a.species == sp

    def test_human_known_alleles_present(self):
        human = get_alleles_for_species(Species.human)
        names = {a.allele_name for a in human}
        assert "HLA-A*02:01" in names
        assert "HLA-B*07:02" in names
        assert "HLA-DRB1*01:01" in names

    def test_canine_known_alleles_present(self):
        canine = get_alleles_for_species(Species.canine)
        names = {a.allele_name for a in canine}
        assert "DLA-88*001:01" in names
        assert "DLA-DRB1*001:01" in names

    def test_murine_h2_alleles_present(self):
        murine = get_alleles_for_species(Species.murine)
        names = {a.allele_name for a in murine}
        assert "H-2Kb" in names
        assert "H-2Db" in names
        assert "H-2IAb" in names

    def test_source_db_populated(self):
        for allele in MHC_ALLELE_DATABASE:
            assert allele.source_db, f"{allele.allele_name} missing source_db"

    def test_binding_data_available_is_bool(self):
        for allele in MHC_ALLELE_DATABASE:
            assert isinstance(allele.binding_data_available, bool)


class TestCrossSpeciesEquivalents:
    def test_hla_a0201_has_equivalents(self):
        result = find_cross_species_equivalent("HLA-A*02:01")
        assert len(result) > 0

    def test_dla88_001_has_human_equivalent(self):
        result = find_cross_species_equivalent("DLA-88*001:01")
        species_set = {a.species for a in result}
        assert Species.human in species_set

    def test_returns_list_of_mhc_alleles(self):
        result = find_cross_species_equivalent("HLA-A*02:01")
        for item in result:
            assert isinstance(item, MHCAllele)

    def test_unknown_allele_returns_empty(self):
        result = find_cross_species_equivalent("UNKNOWN-ALLELE")
        assert result == []

    def test_h2kb_has_human_equivalent(self):
        result = find_cross_species_equivalent("H-2Kb")
        assert len(result) > 0

    def test_no_self_in_equivalents(self):
        """The returned list should not contain the queried allele itself."""
        result = find_cross_species_equivalent("HLA-A*02:01")
        names = [a.allele_name for a in result]
        assert "HLA-A*02:01" not in names


class TestCalibrationWarnings:
    def test_same_species_returns_low_warning(self):
        warn = get_calibration_warning("HLA-A*02:01", Species.human)
        assert warn.warning_level == "low"

    def test_human_to_murine_is_medium(self):
        warn = get_calibration_warning("HLA-A*02:01", Species.murine)
        assert warn.warning_level == "medium"

    def test_human_to_feline_is_high(self):
        warn = get_calibration_warning("HLA-A*02:01", Species.feline)
        assert warn.warning_level == "high"

    def test_human_to_porcine_is_low(self):
        warn = get_calibration_warning("HLA-A*02:01", Species.porcine)
        assert warn.warning_level == "low"

    def test_unknown_allele_returns_high_warning(self):
        warn = get_calibration_warning("UNKNOWN-123", Species.canine)
        assert warn.warning_level == "high"

    def test_returns_calibration_warning_dataclass(self):
        warn = get_calibration_warning("H-2Kb", Species.human)
        assert isinstance(warn, CalibrationWarning)

    def test_warning_has_message(self):
        warn = get_calibration_warning("HLA-A*02:01", Species.equine)
        assert warn.message
        assert len(warn.message) > 10

    def test_warning_has_recommended_action(self):
        warn = get_calibration_warning("HLA-A*02:01", Species.equine)
        assert warn.recommended_action
        assert len(warn.recommended_action) > 10

    def test_source_allele_stored_correctly(self):
        warn = get_calibration_warning("HLA-B*07:02", Species.canine)
        assert warn.source_allele == "HLA-B*07:02"

    def test_target_species_stored_correctly(self):
        warn = get_calibration_warning("HLA-A*02:01", Species.equine)
        assert warn.target_species == Species.equine


# ============================================================================
# Feature 2: Cross-species ortholog comparison
# ============================================================================


class TestOrthologDatabase:
    def test_has_20_entries(self):
        assert len(ORTHOLOG_DATABASE) >= 20

    def test_known_genes_present(self):
        for gene in ["TP53", "KRAS", "BRAF", "EGFR", "BRCA1"]:
            assert gene in ORTHOLOG_DATABASE

    def test_identity_pct_structure(self):
        for gene, data in ORTHOLOG_DATABASE.items():
            assert "identity_pct" in data
            assert isinstance(data["identity_pct"], dict)


class TestCompareOrthologs:
    def test_tp53_canine(self):
        result = compare_orthologs("TP53", "canine")
        assert isinstance(result, OrthologComparison)
        assert result.gene == "TP53"
        assert result.species_pair == ("human", "canine")
        assert result.sequence_identity_pct > 0

    def test_kras_murine_high_identity(self):
        result = compare_orthologs("KRAS", "murine")
        assert result.sequence_identity_pct > 95

    def test_brca1_murine_lower_identity(self):
        result = compare_orthologs("BRCA1", "murine")
        assert result.sequence_identity_pct < 70

    def test_structural_conservation_range(self):
        result = compare_orthologs("TP53", "canine")
        assert 0.0 <= result.structural_conservation <= 1.0

    def test_model_quality_score_range(self):
        result = compare_orthologs("BRAF", "feline")
        assert 0.0 <= result.model_quality_score <= 1.0

    def test_recommendation_non_empty(self):
        result = compare_orthologs("EGFR", "equine")
        assert result.recommendation
        assert len(result.recommendation) > 10

    def test_unknown_gene_returns_zero_scores(self):
        result = compare_orthologs("UNKNOWN_GENE_XYZ", "canine")
        assert result.sequence_identity_pct == 0.0
        assert result.structural_conservation == 0.0
        assert result.model_quality_score == 0.0

    def test_alias_dog_resolves_to_canine(self):
        result = compare_orthologs("KRAS", "dog")
        assert result.species_pair == ("human", "canine")

    def test_alias_mouse_resolves_to_murine(self):
        result = compare_orthologs("KRAS", "mouse")
        assert result.species_pair == ("human", "murine")


class TestRankAnimalModels:
    def test_returns_list(self):
        result = rank_animal_models("KRAS")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_sorted_by_structural_conservation_desc(self):
        result = rank_animal_models("TP53")
        scores = [r.structural_conservation for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_no_human_in_ranked_models(self):
        result = rank_animal_models("TP53")
        for r in result:
            assert "human" not in r.species_pair[1]

    def test_all_are_ortholog_comparisons(self):
        result = rank_animal_models("BRAF")
        for r in result:
            assert isinstance(r, OrthologComparison)

    def test_unknown_gene_still_returns_list(self):
        result = rank_animal_models("FAKE_GENE_999")
        assert isinstance(result, list)
        for r in result:
            assert r.model_quality_score == 0.0

    def test_variant_param_accepted(self):
        result = rank_animal_models("KRAS", variant="G12D")
        assert isinstance(result, list)


class TestCheckVariantConservation:
    def test_returns_dict(self):
        result = check_variant_conservation("TP53", 248, "canine")
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        result = check_variant_conservation("TP53", 248, "canine")
        for key in ["gene", "position", "target_species", "conserved", "confidence", "notes"]:
            assert key in result

    def test_gene_stored(self):
        result = check_variant_conservation("KRAS", 12, "murine")
        assert result["gene"] == "KRAS"

    def test_position_stored(self):
        result = check_variant_conservation("KRAS", 12, "murine")
        assert result["position"] == 12

    def test_confidence_range(self):
        result = check_variant_conservation("TP53", 175, "feline")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_unknown_gene_returns_none_conserved(self):
        result = check_variant_conservation("FAKE_GENE", 100, "canine")
        assert result["conserved"] is None
        assert result["confidence"] == 0.0

    def test_deterministic(self):
        r1 = check_variant_conservation("TP53", 248, "canine")
        r2 = check_variant_conservation("TP53", 248, "canine")
        assert r1 == r2

    def test_different_positions_may_differ(self):
        r1 = check_variant_conservation("TP53", 248, "canine")
        r2 = check_variant_conservation("TP53", 175, "canine")
        # Not guaranteed to differ, but at least both valid
        assert isinstance(r1["conserved"], (bool, type(None)))
        assert isinstance(r2["conserved"], (bool, type(None)))


# ============================================================================
# Feature 3: Veterinary compassionate use documentation
# ============================================================================


class TestAttestationRequirements:
    def test_canine_requirements(self):
        req = get_attestation_requirements("canine")
        assert isinstance(req, VetAttestationRequirements)
        assert req.dvm_license_required is True
        assert req.owner_consent_required is True
        assert req.usda_notification is True
        assert req.adverse_event_reporting is True

    def test_feline_requirements(self):
        req = get_attestation_requirements("feline")
        assert req.dvm_license_required is True
        assert req.owner_consent_required is True

    def test_murine_no_owner_consent(self):
        req = get_attestation_requirements("murine")
        assert req.owner_consent_required is False

    def test_murine_institutional_approval(self):
        req = get_attestation_requirements("murine")
        assert req.institutional_approval is True

    def test_equine_usda_notification(self):
        req = get_attestation_requirements("equine")
        assert req.usda_notification is True

    def test_equine_has_state_requirements(self):
        req = get_attestation_requirements("equine")
        assert len(req.state_specific_requirements) > 0

    def test_unknown_species_returns_requirements(self):
        req = get_attestation_requirements("alpaca")
        assert isinstance(req, VetAttestationRequirements)
        assert req.dvm_license_required is True

    def test_adverse_event_always_true(self):
        for sp in ["canine", "feline", "equine", "murine", "porcine"]:
            req = get_attestation_requirements(sp)
            assert req.adverse_event_reporting is True


class TestOwnerConsentForm:
    def test_returns_string(self):
        form = generate_owner_consent_form("canine", "lymphoma", "mRNA neoantigen vaccine")
        assert isinstance(form, str)

    def test_contains_species(self):
        form = generate_owner_consent_form("feline", "sarcoma", "experimental immunotherapy")
        assert "Feline" in form or "feline" in form

    def test_contains_condition(self):
        form = generate_owner_consent_form("canine", "osteosarcoma", "tumor vaccine")
        assert "osteosarcoma" in form

    def test_contains_treatment_summary(self):
        form = generate_owner_consent_form("equine", "melanoma", "dendritic cell therapy")
        assert "dendritic cell therapy" in form

    def test_contains_avma_reference(self):
        form = generate_owner_consent_form("canine", "lymphoma", "mRNA vaccine")
        assert "AVMA" in form

    def test_contains_research_disclaimer(self):
        form = generate_owner_consent_form("canine", "lymphoma", "mRNA vaccine")
        assert "RESEARCH USE ONLY" in form

    def test_contains_signature_line(self):
        form = generate_owner_consent_form("canine", "lymphoma", "mRNA vaccine")
        assert "Signature" in form or "signature" in form


class TestGenerateCompassionateUseDoc:
    @pytest.fixture
    def sample_doc(self) -> CompassionateUseDocument:
        return generate_compassionate_use_doc(
            species="canine",
            condition="osteosarcoma",
            treatment_summary="Personalized mRNA neoantigen vaccine (FoldAgent platform)",
            vet_name="Dr. Jane Smith",
            vet_license="DVM-CA-12345",
            owner_name="John Doe",
            animal_id="DOG-2024-001",
        )

    def test_returns_document_instance(self, sample_doc):
        assert isinstance(sample_doc, CompassionateUseDocument)

    def test_document_type(self, sample_doc):
        assert "Compassionate Use" in sample_doc.document_type

    def test_species_stored(self, sample_doc):
        assert sample_doc.species.lower() == "canine"

    def test_condition_stored(self, sample_doc):
        assert sample_doc.condition == "osteosarcoma"

    def test_treatment_summary_stored(self, sample_doc):
        assert "mRNA" in sample_doc.proposed_treatment_summary

    def test_vet_name_in_attestation(self, sample_doc):
        assert "Dr. Jane Smith" in sample_doc.attending_vet_attestation

    def test_vet_license_in_attestation(self, sample_doc):
        assert "DVM-CA-12345" in sample_doc.attending_vet_attestation

    def test_animal_id_in_attestation(self, sample_doc):
        assert "DOG-2024-001" in sample_doc.attending_vet_attestation

    def test_owner_consent_text_non_empty(self, sample_doc):
        assert len(sample_doc.owner_consent_text) > 50

    def test_regulatory_notices_non_empty(self, sample_doc):
        assert len(sample_doc.regulatory_notices) > 0

    def test_avma_guidelines_ref_non_empty(self, sample_doc):
        assert len(sample_doc.avma_guidelines_ref) > 10

    def test_usda_requirements_non_empty(self, sample_doc):
        assert len(sample_doc.usda_requirements) > 0

    def test_document_text_contains_species(self, sample_doc):
        assert "Canine" in sample_doc.document_text or "canine" in sample_doc.document_text

    def test_document_text_contains_disclaimer(self, sample_doc):
        assert "RESEARCH USE ONLY" in sample_doc.document_text

    def test_generated_at_iso_format(self, sample_doc):
        from datetime import datetime

        # Should parse without error
        datetime.fromisoformat(sample_doc.generated_at)

    def test_feline_doc_generation(self):
        doc = generate_compassionate_use_doc(
            species="feline",
            condition="injection-site sarcoma",
            treatment_summary="Neoantigen peptide vaccine trial",
            vet_name="Dr. Bob Lee",
            vet_license="DVM-TX-99999",
            owner_name="Alice Green",
            animal_id="CAT-2024-002",
        )
        assert isinstance(doc, CompassionateUseDocument)
        assert "feline" in doc.species.lower() or "Feline" in doc.species

    def test_equine_doc_has_usda_requirements(self):
        doc = generate_compassionate_use_doc(
            species="equine",
            condition="melanoma",
            treatment_summary="DNA vaccine trial",
            vet_name="Dr. Mary Clark",
            vet_license="DVM-KY-55555",
            owner_name="Mark Johnson",
            animal_id="HORSE-2024-003",
        )
        assert len(doc.usda_requirements) > 0
        # Equine should have more USDA requirements than feline
        feline_doc = generate_compassionate_use_doc(
            species="feline",
            condition="sarcoma",
            treatment_summary="vaccine",
            vet_name="Dr. X",
            vet_license="DVM-00000",
            owner_name="Owner",
            animal_id="CAT-001",
        )
        assert len(doc.usda_requirements) >= len(feline_doc.usda_requirements)

    def test_regulatory_notices_contain_research_disclaimer(self, sample_doc):
        combined = " ".join(sample_doc.regulatory_notices)
        assert "RESEARCH USE ONLY" in combined


class TestAVMAGuidelines:
    def test_avma_guidelines_dict_non_empty(self):
        assert len(AVMA_GUIDELINES) > 0

    def test_compassionate_use_key_present(self):
        assert "compassionate_use" in AVMA_GUIDELINES

    def test_informed_consent_key_present(self):
        assert "informed_consent" in AVMA_GUIDELINES

    def test_all_values_non_empty_strings(self):
        for key, val in AVMA_GUIDELINES.items():
            assert isinstance(val, str)
            assert len(val) > 0


class TestUSDARequirements:
    def test_canine_requirements_present(self):
        assert "canine" in USDA_REQUIREMENTS_BY_SPECIES
        assert len(USDA_REQUIREMENTS_BY_SPECIES["canine"]) > 0

    def test_equine_requirements_present(self):
        assert "equine" in USDA_REQUIREMENTS_BY_SPECIES
        assert len(USDA_REQUIREMENTS_BY_SPECIES["equine"]) > 0

    def test_murine_requirements_present(self):
        assert "murine" in USDA_REQUIREMENTS_BY_SPECIES

    def test_default_fallback_present(self):
        assert "default" in USDA_REQUIREMENTS_BY_SPECIES
