"""Tests for Advanced Protein Science Extensions — Phase 24 Tier 3."""

from __future__ import annotations

import pytest

from backend.app.protein_science_ext import (
    # Feature 1
    TMHelix,
    MembraneProteinResult,
    LipidEnvironment,
    KYTE_DOOLITTLE,
    predict_tm_helices,
    analyze_membrane_protein,
    assign_lipid_environment,
    calculate_cavity_accessibility,
    # Feature 2
    MetalIon,
    MetalSite,
    MetalSiteResult,
    METAL_BINDING_MOTIFS,
    KNOWN_METALLOPROTEIN_DB,
    predict_metal_sites,
    cross_validate_metal,
    # Feature 3
    GlycosylationSite,
    GlycanShieldResult,
    N_GLYCOSYLATION_MOTIF,
    COMMON_GLYCAN_TYPES,
    predict_glycosylation_sites,
    analyze_glycan_shield,
    assess_epitope_accessibility,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

# 23 hydrophobic AA stretch (TM-like)
TM_STRETCH = "AILVLLILVLLAILVLLIILVLL"  # pure hydrophobic
# Non-membrane short soluble protein
SOLUBLE_SEQ = "MKVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSHGSAQVKGHGKKVADALTNAVAHVDDMPNALSALSDLHAHKLRVDPVNFKLLSHCLLVTLAAHLPAEFTPAVHASLDKFLASVSTVLTSKYR"

# Glycoprotein spike-like fragment with NXS/NXT motifs
GLYCO_SEQ = "MNITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFKCYGVSPTKLNDLCFTNVYADSFVIRGDEVRQIAPGQTGKIADYNYKLPDDFTGCVIAWNSNNLDSKVGGNYNYLYRLFRKSNLKPFERDISTEIYQAGSTPCNGVEGFNCYFPLQSYGFQPTNGVGYQPYRVVVLSFELLHAPATVCGPKKSTNLVKNKCVNFNFNGLTGTGVLTESNKKFLPFQQFGRDIADTTDAVRDPQTLEILDITPCSFGGVSVITPGTNTSNQVAVLYQDVNCTEVPVAIHADQLTPTWRVYSTGSNVFQTRAGCLIGAEHVNNSYECDIPIGAGICASYQTQTNSPRRARSVASQSIIAYTMSLGAENSVAYSNNSIAIPTNFTISVTTEILPVSMTKTSVDCTMYICGDSTECSNLLLQYGSFCTQLNRALTGIAVEQDKNTQEVFAQVKQIYKTPPIKDFGGFNFSQILPDPSKPSKRSFIEDLLFNKVTLADAGFIKQYGDCLGDIAARDLICAQKFNGLTVLPPLLTDEMIAQYTSALLAGTITSGWTFGAGAALQIPFAMQMAYRFNGIGVTQNVLYENQKLIANQFNSAIGKIQDSLSSTASALGKLQDVVNQNAQALNTLVKQLSSNFGAISSVLNDILSRLDKVEAEVQIDRLITGRLQSLQTYVTQQLIRAAEIRASANLAATKMSECVLGQSKRVDFCGKGYHLMSFPQSAPHGVVFLHVTYVPAQEKNFTTAPAICHDGKAHFPREGVFVSNGTHWFVTQRNFYEPQIITTDNTFVSGNCDVVIGIVNNTVYDPLQPELDSFKEELDKYFKNHTSPDVDLGDISGINASVVNIQKEIDRLNEVAKNLNESLIDLQELGKYEQYIKWPWYIWLGFIAGLIAIVMVTIMLCCMTSCCSCLKGCCSCGSCCKFDEDDSEPVLKGVKLHYT"

# Zinc finger-like sequence
ZF_SEQ = "MALGCGGCAAAAAHFFFHAAAA"  # C..C..............H...H

# Metal-free short sequence
NO_METAL_SEQ = "MKVLSPADKTNVKAAWGKVGAHAG"


# ---------------------------------------------------------------------------
# Feature 1: TM Helix prediction
# ---------------------------------------------------------------------------

class TestKyteDoolittle:
    def test_all_20_aa_present(self):
        assert len(KYTE_DOOLITTLE) == 20

    def test_isoleucine_most_hydrophobic(self):
        assert KYTE_DOOLITTLE["I"] == 4.5

    def test_arginine_most_hydrophilic(self):
        assert KYTE_DOOLITTLE["R"] == -4.5

    def test_values_in_range(self):
        for aa, val in KYTE_DOOLITTLE.items():
            assert -5.0 <= val <= 5.0, f"{aa} out of range: {val}"


class TestPredictTMHelices:
    def test_returns_list(self):
        result = predict_tm_helices(TM_STRETCH)
        assert isinstance(result, list)

    def test_tm_helix_dataclass_fields(self):
        helices = predict_tm_helices(TM_STRETCH)
        if helices:
            h = helices[0]
            assert hasattr(h, "start")
            assert hasattr(h, "end")
            assert hasattr(h, "orientation")
            assert hasattr(h, "hydrophobicity_score")

    def test_hydrophobic_stretch_detected(self):
        helices = predict_tm_helices(TM_STRETCH)
        assert len(helices) >= 1

    def test_soluble_protein_no_tm_helices(self):
        helices = predict_tm_helices("MKVLSPADKTNVKAAEDKSTRVN")
        assert len(helices) == 0

    def test_helix_start_less_than_end(self):
        helices = predict_tm_helices(TM_STRETCH)
        for h in helices:
            assert h.start <= h.end

    def test_helix_orientation_valid(self):
        helices = predict_tm_helices(TM_STRETCH)
        for h in helices:
            assert h.orientation in ("in_to_out", "out_to_in")

    def test_helix_hydrophobicity_above_threshold(self):
        helices = predict_tm_helices(TM_STRETCH)
        for h in helices:
            assert h.hydrophobicity_score > 1.6

    def test_empty_sequence_returns_empty(self):
        assert predict_tm_helices("") == []

    def test_short_sequence_no_crash(self):
        result = predict_tm_helices("MKVL")
        assert isinstance(result, list)


class TestAnalyzeMembraneProtein:
    def test_returns_membrane_protein_result(self):
        result = analyze_membrane_protein(TM_STRETCH)
        assert isinstance(result, MembraneProteinResult)

    def test_is_membrane_protein_for_tm_stretch(self):
        result = analyze_membrane_protein(TM_STRETCH)
        assert result.is_membrane_protein is True

    def test_soluble_protein_not_membrane(self):
        result = analyze_membrane_protein("MKVLSPADKTNEDDSRRVNEDST")
        assert result.is_membrane_protein is False or result.topology == "none"

    def test_topology_assigned(self):
        result = analyze_membrane_protein(TM_STRETCH)
        assert result.topology in ("type_I", "type_II", "multi_pass", "peripheral", "none")

    def test_n_tm_helices_consistent(self):
        result = analyze_membrane_protein(TM_STRETCH)
        assert result.n_tm_helices == len(result.tm_helices)

    def test_sequence_preserved(self):
        seq = TM_STRETCH
        result = analyze_membrane_protein(seq)
        assert result.sequence == seq

    def test_regions_are_tuples(self):
        result = analyze_membrane_protein(TM_STRETCH)
        for region in result.extracellular_regions + result.intracellular_regions:
            assert isinstance(region, tuple)
            assert len(region) == 2

    def test_insertion_energy_negative_for_membrane(self):
        result = analyze_membrane_protein(TM_STRETCH)
        if result.is_membrane_protein and result.n_tm_helices > 0:
            assert result.membrane_insertion_energy <= 0.0

    def test_multi_pass_topology_for_long_hydrophobic(self):
        # Build a sequence with multiple TM stretches
        tm = "AILVLLILVLLAILVLLIILVLL"
        loop = "KRDEEDDRK"
        multi = tm + loop + tm + loop + tm
        result = analyze_membrane_protein(multi)
        if result.n_tm_helices >= 2:
            assert result.topology == "multi_pass"


class TestAssignLipidEnvironment:
    def test_returns_lipid_environment(self):
        result = analyze_membrane_protein(TM_STRETCH)
        env = assign_lipid_environment(result)
        assert isinstance(env, LipidEnvironment)

    def test_membrane_type_valid(self):
        result = analyze_membrane_protein(TM_STRETCH)
        env = assign_lipid_environment(result)
        assert env.membrane_type in ("plasma", "er", "mitochondrial", "nuclear")

    def test_lipid_composition_sums_to_one(self):
        result = analyze_membrane_protein(TM_STRETCH)
        env = assign_lipid_environment(result)
        total = sum(env.lipid_composition.values())
        assert abs(total - 1.0) < 0.01

    def test_thickness_positive(self):
        result = analyze_membrane_protein(TM_STRETCH)
        env = assign_lipid_environment(result)
        assert env.thickness_nm > 0

    def test_non_membrane_assigns_plasma(self):
        result = analyze_membrane_protein("MKVLSPADKTNEDDSRRVNEDST")
        env = assign_lipid_environment(result)
        assert env.membrane_type == "plasma"


class TestCalculateCavityAccessibility:
    def test_returns_dict(self):
        result = analyze_membrane_protein(TM_STRETCH)
        out = calculate_cavity_accessibility(result, [0, 5, 10])
        assert isinstance(out, dict)

    def test_residue_accessibility_keys(self):
        result = analyze_membrane_protein(TM_STRETCH)
        out = calculate_cavity_accessibility(result, [0, 1, 2])
        assert "residue_accessibility" in out

    def test_accessibility_values_valid(self):
        result = analyze_membrane_protein(TM_STRETCH)
        out = calculate_cavity_accessibility(result, list(range(5)))
        valid = {"extracellular", "intracellular", "transmembrane", "unknown"}
        for v in out["residue_accessibility"].values():
            assert v in valid

    def test_empty_positions(self):
        result = analyze_membrane_protein(TM_STRETCH)
        out = calculate_cavity_accessibility(result, [])
        assert out["extracellular_count"] == 0


# ---------------------------------------------------------------------------
# Feature 2: Metal coordination
# ---------------------------------------------------------------------------

class TestMetalBindingMotifs:
    def test_ten_motifs_present(self):
        assert len(METAL_BINDING_MOTIFS) == 10

    def test_zinc_finger_present(self):
        assert "zinc_finger" in METAL_BINDING_MOTIFS

    def test_ef_hand_present(self):
        assert "ef_hand" in METAL_BINDING_MOTIFS

    def test_iron_sulfur_present(self):
        assert "iron_sulfur" in METAL_BINDING_MOTIFS


class TestKnownMetalloproteinDB:
    def test_fifteen_entries(self):
        assert len(KNOWN_METALLOPROTEIN_DB) == 15

    def test_all_entries_have_metal(self):
        for entry in KNOWN_METALLOPROTEIN_DB:
            assert "metal" in entry
            assert isinstance(entry["metal"], MetalIon)

    def test_all_entries_have_gene(self):
        for entry in KNOWN_METALLOPROTEIN_DB:
            assert "gene" in entry and entry["gene"]


class TestPredictMetalSites:
    def test_returns_metal_site_result(self):
        result = predict_metal_sites(ZF_SEQ)
        assert isinstance(result, MetalSiteResult)

    def test_total_sites_consistent(self):
        result = predict_metal_sites(ZF_SEQ)
        assert result.total_sites == len(result.sites)

    def test_no_sites_for_no_metal_seq(self):
        result = predict_metal_sites(NO_METAL_SEQ)
        assert result.total_sites == 0

    def test_metal_site_fields(self):
        result = predict_metal_sites(ZF_SEQ)
        if result.sites:
            site = result.sites[0]
            assert hasattr(site, "metal")
            assert hasattr(site, "coordinating_residues")
            assert hasattr(site, "coordination_number")
            assert hasattr(site, "geometry")
            assert hasattr(site, "confidence")
            assert hasattr(site, "site_type")
            assert hasattr(site, "druggable")

    def test_confidence_in_range(self):
        result = predict_metal_sites(ZF_SEQ)
        for site in result.sites:
            assert 0.0 <= site.confidence <= 1.0

    def test_geometry_valid(self):
        result = predict_metal_sites(ZF_SEQ)
        valid = {"tetrahedral", "octahedral", "square_planar", "trigonal_bipyramidal"}
        for site in result.sites:
            assert site.geometry in valid

    def test_site_type_valid(self):
        result = predict_metal_sites(ZF_SEQ)
        valid = {"catalytic", "structural", "regulatory"}
        for site in result.sites:
            assert site.site_type in valid

    def test_catalytic_plus_structural_le_total(self):
        result = predict_metal_sites(ZF_SEQ)
        assert result.catalytic_sites + result.structural_sites <= result.total_sites

    def test_metal_ion_enum_values(self):
        values = {m.value for m in MetalIon}
        expected = {"zinc", "iron", "calcium", "magnesium", "copper", "manganese", "cobalt", "nickel"}
        assert values == expected


class TestCrossValidateMetal:
    def test_returns_dict(self):
        result = cross_validate_metal(ZF_SEQ, "CA2")
        assert isinstance(result, dict)

    def test_keys_present(self):
        result = cross_validate_metal(ZF_SEQ, "CA2")
        assert "predicted_sites" in result
        assert "db_matches" in result
        assert "cross_validated" in result

    def test_unknown_gene_no_db_matches(self):
        result = cross_validate_metal(NO_METAL_SEQ, "FAKEGENE99")
        assert result["db_matches"] == []

    def test_known_gene_produces_match(self):
        result = cross_validate_metal(ZF_SEQ, "SOD1")
        assert len(result["db_matches"]) > 0

    def test_confidence_field_present(self):
        result = cross_validate_metal(ZF_SEQ, "CA2")
        assert "confidence" in result
        assert result["confidence"] in ("high", "low")


# ---------------------------------------------------------------------------
# Feature 3: Glycoprotein modeling
# ---------------------------------------------------------------------------

class TestCommonGlycanTypes:
    def test_eight_types_present(self):
        assert len(COMMON_GLYCAN_TYPES) == 8

    def test_high_mannose_present(self):
        assert "high_mannose" in COMMON_GLYCAN_TYPES

    def test_each_has_molecular_weight(self):
        for name, info in COMMON_GLYCAN_TYPES.items():
            assert "molecular_weight_da" in info, f"{name} missing molecular_weight_da"

    def test_each_has_size(self):
        for name, info in COMMON_GLYCAN_TYPES.items():
            assert "size_angstrom" in info


class TestPredictGlycosylationSites:
    def test_returns_list(self):
        result = predict_glycosylation_sites(GLYCO_SEQ)
        assert isinstance(result, list)

    def test_n_linked_detected(self):
        # GLYCO_SEQ has NXT/NXS motifs
        sites = predict_glycosylation_sites(GLYCO_SEQ)
        n_linked = [s for s in sites if s.type == "n_linked"]
        assert len(n_linked) > 0

    def test_nxt_motif_occupancy_higher(self):
        # NXT > NXS occupancy probability
        seq = "MANTSMANSS"  # NTS (NXT) and NSS (NXS)
        sites = predict_glycosylation_sites(seq)
        nxt = [s for s in sites if s.type == "n_linked" and s.motif[2] == "T"]
        nxs = [s for s in sites if s.type == "n_linked" and s.motif[2] == "S"]
        if nxt and nxs:
            assert nxt[0].occupancy_probability >= nxs[0].occupancy_probability

    def test_o_linked_detected_with_proline(self):
        seq = "MAPTSPTSAPA"  # S/T with Pro nearby
        sites = predict_glycosylation_sites(seq)
        o_linked = [s for s in sites if s.type == "o_linked"]
        assert len(o_linked) > 0

    def test_c_mannosylation_detected(self):
        seq = "MWXXWAAAA".replace("X", "A")  # WAAW
        sites = predict_glycosylation_sites(seq)
        c_man = [s for s in sites if s.type == "c_mannosylation"]
        assert len(c_man) > 0

    def test_no_sites_plain_sequence(self):
        # No N, no S/T, no W
        seq = "MAAKLLRREEGGGAAAKKRRMM"
        sites = predict_glycosylation_sites(seq)
        n_linked = [s for s in sites if s.type == "n_linked"]
        assert len(n_linked) == 0

    def test_site_fields(self):
        sites = predict_glycosylation_sites(GLYCO_SEQ)
        if sites:
            s = sites[0]
            assert hasattr(s, "position")
            assert hasattr(s, "type")
            assert hasattr(s, "motif")
            assert hasattr(s, "occupancy_probability")
            assert hasattr(s, "glycan_type")

    def test_np_not_detected(self):
        # NPS should not be N-glycosylated (X == P)
        seq = "AANPSAAA"
        sites = predict_glycosylation_sites(seq)
        n_linked = [s for s in sites if s.type == "n_linked"]
        assert len(n_linked) == 0

    def test_occupancy_in_range(self):
        sites = predict_glycosylation_sites(GLYCO_SEQ)
        for s in sites:
            assert 0.0 <= s.occupancy_probability <= 1.0


class TestAnalyzeGlycanShield:
    def test_returns_glycan_shield_result(self):
        result = analyze_glycan_shield(GLYCO_SEQ)
        assert isinstance(result, GlycanShieldResult)

    def test_n_linked_count_correct(self):
        result = analyze_glycan_shield(GLYCO_SEQ)
        n_linked = [s for s in result.sites if s.type == "n_linked"]
        assert result.n_linked_count == len(n_linked)

    def test_o_linked_count_correct(self):
        result = analyze_glycan_shield(GLYCO_SEQ)
        o_linked = [s for s in result.sites if s.type == "o_linked"]
        assert result.o_linked_count == len(o_linked)

    def test_shield_coverage_in_range(self):
        result = analyze_glycan_shield(GLYCO_SEQ)
        assert 0.0 <= result.shield_coverage_pct <= 100.0

    def test_shielded_plus_exposed_eq_sequence_length(self):
        result = analyze_glycan_shield(GLYCO_SEQ)
        total = len(result.shielded_residues) + len(result.exposed_residues)
        assert total == len(GLYCO_SEQ)

    def test_no_glycan_shield_for_unglycoable_seq(self):
        seq = "MAAKLLRREEGGGAAAKKRRMM"
        result = analyze_glycan_shield(seq)
        assert result.shield_coverage_pct == 0.0 or result.n_linked_count == 0

    def test_epitope_accessibility_impact_present(self):
        result = analyze_glycan_shield(GLYCO_SEQ)
        assert isinstance(result.epitope_accessibility_impact, dict)

    def test_shielded_residues_sorted(self):
        result = analyze_glycan_shield(GLYCO_SEQ)
        assert result.shielded_residues == sorted(result.shielded_residues)

    def test_exposed_residues_sorted(self):
        result = analyze_glycan_shield(GLYCO_SEQ)
        assert result.exposed_residues == sorted(result.exposed_residues)


class TestAssessEpitopeAccessibility:
    def test_returns_dict(self):
        shield = analyze_glycan_shield(GLYCO_SEQ)
        result = assess_epitope_accessibility(shield, [10, 50, 100])
        assert isinstance(result, dict)

    def test_total_epitopes_correct(self):
        shield = analyze_glycan_shield(GLYCO_SEQ)
        positions = [10, 50, 100]
        result = assess_epitope_accessibility(shield, positions)
        assert result["total_epitopes"] == 3

    def test_shielded_plus_exposed_eq_total(self):
        shield = analyze_glycan_shield(GLYCO_SEQ)
        positions = [10, 50, 100, 200]
        result = assess_epitope_accessibility(shield, positions)
        assert result["shielded_epitopes"] + result["exposed_epitopes"] == result["total_epitopes"]

    def test_accessibility_score_in_range(self):
        shield = analyze_glycan_shield(GLYCO_SEQ)
        result = assess_epitope_accessibility(shield, [10, 50, 100])
        assert 0.0 <= result["accessibility_score"] <= 1.0

    def test_epitope_results_has_all_positions(self):
        shield = analyze_glycan_shield(GLYCO_SEQ)
        positions = [10, 50, 100]
        result = assess_epitope_accessibility(shield, positions)
        for pos in positions:
            assert pos in result["epitope_results"]

    def test_vaccine_relevance_field(self):
        shield = analyze_glycan_shield(GLYCO_SEQ)
        result = assess_epitope_accessibility(shield, [10, 50])
        for pos_data in result["epitope_results"].values():
            assert pos_data["vaccine_relevance"] in ("good_target", "poor_target")

    def test_empty_epitope_list(self):
        shield = analyze_glycan_shield(GLYCO_SEQ)
        result = assess_epitope_accessibility(shield, [])
        assert result["total_epitopes"] == 0
        assert result["accessibility_score"] == 0.0

    def test_recommendation_present(self):
        shield = analyze_glycan_shield(GLYCO_SEQ)
        result = assess_epitope_accessibility(shield, [10])
        assert "recommendation" in result
