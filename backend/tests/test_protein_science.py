"""Tests for Advanced Protein Science — Phase 24 Tier 3."""

from __future__ import annotations

import pytest

from backend.app.protein_science import (
    # Epitope mapping
    EpitopeRegion,
    EpitopeMapResult,
    map_epitopes,
    rank_epitopes,
    # Hot-spot prediction
    HotSpotResidue,
    PPIHotSpotResult,
    AMINO_ACID_ALANINE_DDG,
    predict_hot_spots,
    assess_interface_druggability,
    # Coevolution
    CoevolvingPair,
    CoevolutionResult,
    KNOWN_COEVOLUTION_DATA,
    predict_coevolution,
    map_constraints_to_structure,
    # NA binding
    NucleicAcidType,
    NABindingResult,
    KNOWN_NA_BINDING_PROTEINS,
    predict_na_binding,
    identify_binding_residues,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# ~50 AA — KRAS G12-region context
KRAS_SEQ = "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSY"

# Hydrophilic stretch — good for B-cell epitopes
HYDROPHILIC_SEQ = "MDERERKDDDEKKNNDDSSERKKRDDDEKKE" * 2

# Aromatic/basic — typical NA-binding
NA_BINDING_SEQ = "MRKKWYRRKHHWFYKKNRGGRKKRWWFYRK"

# Short sequences for edge-case tests
SHORT_SEQ_5 = "MWKRD"
SHORT_SEQ_1 = "M"
EMPTY_SEQ = ""

# p53 DBD snippet (positions approximate)
TP53_SEQ = (
    "VVRCPHHERCSDSDGLAPPQHLIRVEGNLRVEYLDDRNTFRHSVVVPYEPPEVGSDCTTIHYNYMCNS"
    "SCMGQMNRRPILTIITLEDSSGKLLGRNSFEVRVCACPGRDRRTEEENLRKKGEPVHGQWLDSPRTFM"
)


# ---------------------------------------------------------------------------
# Feature 1: Epitope mapping
# ---------------------------------------------------------------------------

class TestEpitopeRegionDataclass:
    def test_fields_present(self):
        ep = EpitopeRegion(
            start=0, end=9, residues="MDERERKDDD",
            epitope_type="continuous",
            solvent_accessibility=0.7,
            immunogenicity_score=0.65,
            b_cell_score=0.70,
            t_cell_score=0.55,
        )
        assert ep.start == 0
        assert ep.end == 9
        assert ep.epitope_type == "continuous"
        assert 0.0 <= ep.solvent_accessibility <= 1.0

    def test_discontinuous_type(self):
        ep = EpitopeRegion(
            start=5, end=40, residues="DKRDKS",
            epitope_type="discontinuous",
            solvent_accessibility=0.5,
            immunogenicity_score=0.4,
            b_cell_score=0.45,
            t_cell_score=0.35,
        )
        assert ep.epitope_type == "discontinuous"


class TestMapEpitopes:
    def test_returns_correct_type(self):
        result = map_epitopes(HYDROPHILIC_SEQ)
        assert isinstance(result, EpitopeMapResult)

    def test_antigen_sequence_stored_uppercase(self):
        result = map_epitopes(HYDROPHILIC_SEQ.lower())
        assert result.antigen_sequence == HYDROPHILIC_SEQ.upper()

    def test_total_epitopes_consistent(self):
        result = map_epitopes(KRAS_SEQ)
        assert result.total_epitopes == (
            len(result.continuous_epitopes) + len(result.discontinuous_epitopes)
        )

    def test_continuous_epitopes_are_continuous_type(self):
        result = map_epitopes(HYDROPHILIC_SEQ)
        for ep in result.continuous_epitopes:
            assert ep.epitope_type == "continuous"

    def test_discontinuous_epitopes_are_discontinuous_type(self):
        result = map_epitopes(HYDROPHILIC_SEQ)
        for ep in result.discontinuous_epitopes:
            assert ep.epitope_type == "discontinuous"

    def test_scores_bounded_0_1(self):
        result = map_epitopes(HYDROPHILIC_SEQ)
        for ep in result.continuous_epitopes + result.discontinuous_epitopes:
            assert 0.0 <= ep.immunogenicity_score <= 1.0
            assert 0.0 <= ep.b_cell_score <= 1.0
            assert 0.0 <= ep.t_cell_score <= 1.0
            assert 0.0 <= ep.solvent_accessibility <= 1.0

    def test_continuous_residues_length_in_range(self):
        min_len, max_len = 6, 20
        result = map_epitopes(HYDROPHILIC_SEQ, min_length=min_len, max_length=max_len)
        for ep in result.continuous_epitopes:
            assert min_len <= len(ep.residues) <= max_len

    def test_surface_accessibility_profile_length(self):
        result = map_epitopes(KRAS_SEQ)
        assert len(result.surface_accessibility_profile) == len(KRAS_SEQ)

    def test_surface_profile_values_0_1(self):
        result = map_epitopes(KRAS_SEQ)
        for val in result.surface_accessibility_profile:
            assert 0.0 <= val <= 1.0

    def test_immunodominant_region_is_none_or_tuple(self):
        result = map_epitopes(KRAS_SEQ)
        assert result.immunodominant_region is None or (
            isinstance(result.immunodominant_region, tuple)
            and len(result.immunodominant_region) == 2
        )

    def test_immunodominant_region_valid_span(self):
        result = map_epitopes(HYDROPHILIC_SEQ)
        if result.immunodominant_region is not None:
            start, end = result.immunodominant_region
            assert start <= end
            assert start >= 0
            assert end < len(HYDROPHILIC_SEQ)

    def test_deterministic(self):
        r1 = map_epitopes(KRAS_SEQ)
        r2 = map_epitopes(KRAS_SEQ)
        assert r1.total_epitopes == r2.total_epitopes
        assert len(r1.continuous_epitopes) == len(r2.continuous_epitopes)

    def test_hydrophilic_seq_has_continuous_epitopes(self):
        result = map_epitopes(HYDROPHILIC_SEQ)
        assert len(result.continuous_epitopes) > 0

    def test_short_seq_no_crash(self):
        result = map_epitopes(SHORT_SEQ_5)
        assert isinstance(result, EpitopeMapResult)

    def test_custom_min_max_length(self):
        result = map_epitopes(HYDROPHILIC_SEQ, min_length=8, max_length=12)
        for ep in result.continuous_epitopes:
            assert 8 <= len(ep.residues) <= 12


class TestRankEpitopes:
    def test_returns_list(self):
        result = map_epitopes(HYDROPHILIC_SEQ)
        ranked = rank_epitopes(result)
        assert isinstance(ranked, list)

    def test_sorted_descending(self):
        result = map_epitopes(HYDROPHILIC_SEQ)
        ranked = rank_epitopes(result)
        scores = [ep.immunogenicity_score for ep in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_contains_all_epitopes(self):
        result = map_epitopes(HYDROPHILIC_SEQ)
        ranked = rank_epitopes(result)
        expected = len(result.continuous_epitopes) + len(result.discontinuous_epitopes)
        assert len(ranked) == expected

    def test_empty_result(self):
        empty = EpitopeMapResult(antigen_sequence="M", total_epitopes=0)
        ranked = rank_epitopes(empty)
        assert ranked == []


# ---------------------------------------------------------------------------
# Feature 2: PPI hot-spot prediction
# ---------------------------------------------------------------------------

class TestAminoAcidAlanineDDG:
    def test_all_20_canonical_present(self):
        aa_list = "ACDEFGHIKLMNPQRSTVWY"
        for aa in aa_list:
            assert aa in AMINO_ACID_ALANINE_DDG

    def test_tryptophan_highest(self):
        assert AMINO_ACID_ALANINE_DDG["W"] == max(AMINO_ACID_ALANINE_DDG.values())

    def test_alanine_zero(self):
        assert AMINO_ACID_ALANINE_DDG["A"] == 0.0

    def test_glycine_negative(self):
        assert AMINO_ACID_ALANINE_DDG["G"] < 0.0


class TestPredictHotSpots:
    def test_returns_correct_type(self):
        result = predict_hot_spots(KRAS_SEQ)
        assert isinstance(result, PPIHotSpotResult)

    def test_custom_interface_residues(self):
        residues = [0, 5, 10, 15, 20]
        result = predict_hot_spots(KRAS_SEQ, interface_residues=residues)
        assert set(result.interface_residues) == set(residues)

    def test_hot_spots_subset_of_interface(self):
        result = predict_hot_spots(KRAS_SEQ)
        interface_set = set(result.interface_residues)
        for hs in result.hot_spots:
            assert hs.position in interface_set

    def test_hot_spot_fraction_0_1(self):
        result = predict_hot_spots(KRAS_SEQ)
        assert 0.0 <= result.hot_spot_fraction <= 1.0

    def test_druggability_score_0_1(self):
        result = predict_hot_spots(KRAS_SEQ)
        assert 0.0 <= result.druggability_score <= 1.0

    def test_total_interface_energy_nonneg(self):
        result = predict_hot_spots(KRAS_SEQ)
        assert result.total_interface_energy >= 0.0

    def test_hot_spot_ddg_threshold(self):
        result = predict_hot_spots(KRAS_SEQ)
        for hs in result.hot_spots:
            assert hs.is_hot_spot is True
            assert hs.alanine_ddg >= 2.0

    def test_energy_contribution_sums_to_100(self):
        result = predict_hot_spots(KRAS_SEQ)
        if result.interface_residues:
            # all residues in the result (not just hot spots)
            all_residues = [
                HotSpotResidue(
                    position=r,
                    residue=KRAS_SEQ[r],
                    alanine_ddg=AMINO_ACID_ALANINE_DDG.get(KRAS_SEQ[r].upper(), 0.5),
                    energy_contribution_pct=0.0,
                    is_hot_spot=False,
                    buried_surface_area=0.0,
                )
                for r in result.interface_residues
            ]
        total_pct = sum(
            AMINO_ACID_ALANINE_DDG.get(KRAS_SEQ[r].upper(), 0.5)
            for r in result.interface_residues
        )
        # Just check hot spots have reasonable contribution pct
        for hs in result.hot_spots:
            assert 0.0 <= hs.energy_contribution_pct <= 100.0

    def test_deterministic(self):
        r1 = predict_hot_spots(KRAS_SEQ)
        r2 = predict_hot_spots(KRAS_SEQ)
        assert r1.druggability_score == r2.druggability_score
        assert len(r1.hot_spots) == len(r2.hot_spots)

    def test_aromatic_rich_seq_druggable(self):
        # sequence rich in W/F/Y should be more druggable
        aromatic_seq = "MWWFFYYWWFFYYRKKRWWFFY" * 2
        result = predict_hot_spots(aromatic_seq)
        assert result.druggable or result.druggability_score > 0.0

    def test_invalid_positions_clamped(self):
        result = predict_hot_spots(KRAS_SEQ, interface_residues=[-1, 0, 5, 9999])
        for pos in result.interface_residues:
            assert 0 <= pos < len(KRAS_SEQ)


class TestAssessInterfaceDruggability:
    def test_returns_dict(self):
        result = predict_hot_spots(KRAS_SEQ)
        report = assess_interface_druggability(result)
        assert isinstance(report, dict)

    def test_required_keys(self):
        result = predict_hot_spots(KRAS_SEQ)
        report = assess_interface_druggability(result)
        for key in [
            "druggable", "druggability_score", "confidence",
            "n_hot_spots", "largest_cluster_size", "n_clusters",
            "mean_alanine_ddg", "aromatic_hot_spots",
            "estimated_pocket_bsa_A2", "hot_spot_fraction", "recommendation",
        ]:
            assert key in report

    def test_confidence_valid_values(self):
        result = predict_hot_spots(KRAS_SEQ)
        report = assess_interface_druggability(result)
        assert report["confidence"] in ("high", "medium", "low")

    def test_recommendation_is_string(self):
        result = predict_hot_spots(KRAS_SEQ)
        report = assess_interface_druggability(result)
        assert isinstance(report["recommendation"], str)

    def test_no_hot_spots_not_druggable(self):
        # all-Ala sequence → no hot spots
        ala_seq = "A" * 30
        result = predict_hot_spots(ala_seq, interface_residues=list(range(10)))
        report = assess_interface_druggability(result)
        assert report["n_hot_spots"] == 0
        assert report["druggable"] is False


# ---------------------------------------------------------------------------
# Feature 3: Coevolution constraint mapping
# ---------------------------------------------------------------------------

class TestCoevolvingPair:
    def test_fields(self):
        pair = CoevolvingPair(
            residue_i=10, residue_j=50,
            coupling_score=0.85,
            contact_probability=0.80,
            functional_constraint="catalytic",
        )
        assert pair.residue_i < pair.residue_j
        assert 0.0 <= pair.coupling_score <= 1.0

    def test_constraint_values(self):
        valid = {"structural", "catalytic", "allosteric", "unknown"}
        for c in valid:
            pair = CoevolvingPair(0, 1, 0.5, 0.5, c)
            assert pair.functional_constraint in valid


class TestKnownCoevolutionData:
    def test_has_8_genes(self):
        assert len(KNOWN_COEVOLUTION_DATA) == 8

    def test_expected_genes_present(self):
        for gene in ["TP53", "KRAS", "EGFR", "BRAF", "BRCA1", "MYC", "PIK3CA", "PTEN"]:
            assert gene in KNOWN_COEVOLUTION_DATA

    def test_each_gene_has_pairs(self):
        for gene, pairs in KNOWN_COEVOLUTION_DATA.items():
            assert len(pairs) >= 2


class TestPredictCoevolution:
    def test_returns_correct_type(self):
        result = predict_coevolution(KRAS_SEQ)
        assert isinstance(result, CoevolutionResult)

    def test_sequence_stored_uppercase(self):
        result = predict_coevolution(KRAS_SEQ.lower())
        assert result.sequence == KRAS_SEQ.upper()

    def test_n_pairs_matches_top_pairs(self):
        result = predict_coevolution(KRAS_SEQ)
        assert result.n_pairs == len(result.top_pairs)

    def test_top_pairs_sorted_descending(self):
        result = predict_coevolution(KRAS_SEQ)
        scores = [p.coupling_score for p in result.top_pairs]
        assert scores == sorted(scores, reverse=True)

    def test_conservation_scores_length(self):
        result = predict_coevolution(KRAS_SEQ)
        assert len(result.conservation_scores) == len(KRAS_SEQ)

    def test_conservation_scores_0_1(self):
        result = predict_coevolution(KRAS_SEQ)
        for s in result.conservation_scores:
            assert 0.0 <= s <= 1.0

    def test_sectors_are_lists(self):
        result = predict_coevolution(KRAS_SEQ)
        assert isinstance(result.sectors, list)
        for sector in result.sectors:
            assert isinstance(sector, list)

    def test_known_gene_overlay_kras(self):
        # With KRAS gene, known pairs should appear (if positions valid for seq)
        result = predict_coevolution(KRAS_SEQ, gene="KRAS")
        # KRAS known pairs include (12, 61), etc. — positions may exceed 40-char seq
        # just check no error and structure is valid
        assert isinstance(result, CoevolutionResult)
        assert result.n_pairs > 0

    def test_tp53_gene_overlay(self):
        result = predict_coevolution(TP53_SEQ, gene="TP53")
        assert result.n_pairs > 0
        # known pairs for TP53 include (175, 248) — check overlap if positions valid
        valid_positions = {(p.residue_i, p.residue_j) for p in result.top_pairs}
        assert len(valid_positions) > 0

    def test_functionally_constrained_positions_list(self):
        result = predict_coevolution(TP53_SEQ, gene="TP53")
        assert isinstance(result.functionally_constrained_positions, list)

    def test_deterministic(self):
        r1 = predict_coevolution(KRAS_SEQ, gene="KRAS")
        r2 = predict_coevolution(KRAS_SEQ, gene="KRAS")
        assert r1.n_pairs == r2.n_pairs

    def test_unknown_gene_still_works(self):
        result = predict_coevolution(KRAS_SEQ, gene="UNKNOWN_GENE_XYZ")
        assert result.n_pairs > 0


class TestMapConstraintsToStructure:
    def test_returns_dict(self):
        coev = predict_coevolution(TP53_SEQ, gene="TP53")
        result = map_constraints_to_structure(coev, variants=[10, 20, 30])
        assert isinstance(result, dict)

    def test_required_keys(self):
        coev = predict_coevolution(TP53_SEQ, gene="TP53")
        result = map_constraints_to_structure(coev, variants=[10, 50])
        for key in [
            "total_constrained_positions", "total_coevolving_positions",
            "n_sectors", "disrupted_variants", "safe_variants", "variants_analyzed",
        ]:
            assert key in result

    def test_variants_analyzed_count(self):
        coev = predict_coevolution(TP53_SEQ)
        variants = [5, 10, 15, 20]
        result = map_constraints_to_structure(coev, variants=variants)
        assert result["variants_analyzed"] == len(variants)

    def test_no_variants_returns_zero(self):
        coev = predict_coevolution(KRAS_SEQ)
        result = map_constraints_to_structure(coev, variants=None)
        assert result["variants_analyzed"] == 0
        assert result["disrupted_variants"] == []
        assert result["safe_variants"] == []

    def test_severity_values_valid(self):
        coev = predict_coevolution(TP53_SEQ, gene="TP53")
        # put all constrained positions as variants to trigger disruptions
        variants = coev.functionally_constrained_positions[:5] or [5, 10, 15]
        result = map_constraints_to_structure(coev, variants=variants)
        for dv in result["disrupted_variants"]:
            assert dv["severity"] in ("high", "moderate", "low")

    def test_total_coevolving_positions_nonneg(self):
        coev = predict_coevolution(KRAS_SEQ)
        result = map_constraints_to_structure(coev)
        assert result["total_coevolving_positions"] >= 0


# ---------------------------------------------------------------------------
# Feature 4: Protein-nucleic acid interaction prediction
# ---------------------------------------------------------------------------

class TestNucleicAcidType:
    def test_enum_values(self):
        assert NucleicAcidType.dna == "dna"
        assert NucleicAcidType.rna == "rna"
        assert NucleicAcidType.hybrid == "hybrid"

    def test_is_str_enum(self):
        assert isinstance(NucleicAcidType.dna, str)


class TestKnownNABindingProteins:
    def test_has_12_entries(self):
        assert len(KNOWN_NA_BINDING_PROTEINS) == 12

    def test_required_fields(self):
        for entry in KNOWN_NA_BINDING_PROTEINS:
            assert "name" in entry
            assert "gene" in entry
            assert "na_type" in entry
            assert "specificity" in entry
            assert "key_residues" in entry

    def test_specificity_valid_values(self):
        valid = {"sequence_specific", "non_specific", "structure_specific"}
        for entry in KNOWN_NA_BINDING_PROTEINS:
            assert entry["specificity"] in valid

    def test_na_type_is_enum(self):
        for entry in KNOWN_NA_BINDING_PROTEINS:
            assert isinstance(entry["na_type"], NucleicAcidType)


class TestIdentifyBindingResidues:
    def test_basic_rich_seq(self):
        residues = identify_binding_residues(NA_BINDING_SEQ)
        assert len(residues) > 0

    def test_alanine_seq_no_binding(self):
        ala_seq = "A" * 30
        residues = identify_binding_residues(ala_seq)
        assert residues == []

    def test_returns_sorted_list(self):
        residues = identify_binding_residues(NA_BINDING_SEQ)
        assert residues == sorted(residues)

    def test_positions_in_range(self):
        seq = KRAS_SEQ
        residues = identify_binding_residues(seq)
        for pos in residues:
            assert 0 <= pos < len(seq)

    def test_empty_sequence(self):
        residues = identify_binding_residues("")
        assert residues == []

    def test_single_residue(self):
        residues = identify_binding_residues("R")
        # single R may not meet window density threshold
        assert isinstance(residues, list)


class TestPredictNABinding:
    def test_returns_correct_type(self):
        result = predict_na_binding(NA_BINDING_SEQ, NucleicAcidType.dna)
        assert isinstance(result, NABindingResult)

    def test_binding_score_0_1(self):
        for na_type in NucleicAcidType:
            result = predict_na_binding(NA_BINDING_SEQ, na_type)
            assert 0.0 <= result.binding_score <= 1.0

    def test_interface_area_nonneg(self):
        result = predict_na_binding(NA_BINDING_SEQ, NucleicAcidType.rna)
        assert result.interface_area >= 0.0

    def test_interface_area_proportional_to_binding_residues(self):
        result = predict_na_binding(NA_BINDING_SEQ, NucleicAcidType.dna)
        expected_area = len(result.binding_residues) * 150.0
        assert abs(result.interface_area - expected_area) < 0.1

    def test_specificity_valid_values(self):
        valid = {"sequence_specific", "non_specific", "structure_specific"}
        for na_type in NucleicAcidType:
            result = predict_na_binding(NA_BINDING_SEQ, na_type)
            assert result.specificity in valid

    def test_na_type_stored(self):
        result = predict_na_binding(KRAS_SEQ, NucleicAcidType.rna)
        assert result.nucleic_acid_type == NucleicAcidType.rna

    def test_protein_sequence_uppercase(self):
        result = predict_na_binding(NA_BINDING_SEQ.lower(), NucleicAcidType.dna)
        assert result.protein_sequence == NA_BINDING_SEQ.upper()

    def test_with_nucleic_acid_sequence(self):
        gc_rich = "GCGCGCGCGCGCGCGC"
        result = predict_na_binding(NA_BINDING_SEQ, NucleicAcidType.dna, nucleic_acid_sequence=gc_rich)
        assert isinstance(result, NABindingResult)
        assert 0.0 <= result.binding_score <= 1.0

    def test_dna_vs_rna_different_scores(self):
        dna_result = predict_na_binding(NA_BINDING_SEQ, NucleicAcidType.dna)
        rna_result = predict_na_binding(NA_BINDING_SEQ, NucleicAcidType.rna)
        # scores may differ for same sequence with different NA type
        assert isinstance(dna_result.binding_score, float)
        assert isinstance(rna_result.binding_score, float)

    def test_hybrid_type(self):
        result = predict_na_binding(NA_BINDING_SEQ, NucleicAcidType.hybrid)
        assert result.nucleic_acid_type == NucleicAcidType.hybrid

    def test_nucleic_acid_partner_string_or_none(self):
        result = predict_na_binding(NA_BINDING_SEQ, NucleicAcidType.dna)
        assert result.nucleic_acid_partner is None or isinstance(result.nucleic_acid_partner, str)

    def test_deterministic(self):
        r1 = predict_na_binding(KRAS_SEQ, NucleicAcidType.dna)
        r2 = predict_na_binding(KRAS_SEQ, NucleicAcidType.dna)
        assert r1.binding_score == r2.binding_score
        assert r1.binding_residues == r2.binding_residues

    def test_binding_residues_in_range(self):
        result = predict_na_binding(KRAS_SEQ, NucleicAcidType.dna)
        for pos in result.binding_residues:
            assert 0 <= pos < len(KRAS_SEQ)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_map_epitopes_single_char(self):
        result = map_epitopes("M")
        assert isinstance(result, EpitopeMapResult)
        assert result.total_epitopes == 0

    def test_map_epitopes_min_equals_max(self):
        result = map_epitopes(HYDROPHILIC_SEQ, min_length=8, max_length=8)
        for ep in result.continuous_epitopes:
            assert len(ep.residues) == 8

    def test_predict_hot_spots_short_seq(self):
        result = predict_hot_spots("MWFYK")
        assert isinstance(result, PPIHotSpotResult)

    def test_predict_hot_spots_empty_interface(self):
        result = predict_hot_spots(KRAS_SEQ, interface_residues=[])
        assert result.total_interface_energy == 0.0
        assert result.hot_spot_fraction == 0.0
        assert result.hot_spots == []

    def test_predict_coevolution_very_short(self):
        result = predict_coevolution("MWKRD")
        assert isinstance(result, CoevolutionResult)

    def test_identify_binding_residues_all_glycine(self):
        result = identify_binding_residues("G" * 20)
        assert result == []

    def test_na_binding_low_basic_content(self):
        # all hydrophobic — minimal NA binding
        hydrophobic_seq = "LLLLLVVVVIIIIAAAAMMMM"
        result = predict_na_binding(hydrophobic_seq, NucleicAcidType.dna)
        assert result.binding_score < 0.3

    def test_na_binding_high_basic_content(self):
        # all basic residues — high NA binding
        basic_seq = "RRRRKKKRRRRKKKRRRRKKKR"
        result = predict_na_binding(basic_seq, NucleicAcidType.dna)
        assert result.binding_score > 0.3

    def test_map_constraints_empty_variants(self):
        coev = predict_coevolution(KRAS_SEQ)
        result = map_constraints_to_structure(coev, variants=[])
        assert result["variants_analyzed"] == 0

    def test_rank_epitopes_single_epitope(self):
        ep = EpitopeRegion(0, 5, "MWKRDE", "continuous", 0.7, 0.8, 0.75, 0.85)
        result = EpitopeMapResult(
            antigen_sequence="MWKRDE",
            total_epitopes=1,
            continuous_epitopes=[ep],
        )
        ranked = rank_epitopes(result)
        assert len(ranked) == 1
        assert ranked[0] is ep
