"""Advanced Protein Science Extensions — Phase 24 Tier 3

Membrane protein handling, metal coordination, glycoprotein modeling.
RESEARCH USE ONLY.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Feature 1: Membrane protein handling
# ---------------------------------------------------------------------------


@dataclass
class TMHelix:
    start: int
    end: int
    orientation: str  # "in_to_out" | "out_to_in"
    hydrophobicity_score: float


@dataclass
class MembraneProteinResult:
    sequence: str
    is_membrane_protein: bool
    tm_helices: list[TMHelix]
    topology: str  # "type_I" | "type_II" | "multi_pass" | "peripheral" | "none"
    n_tm_helices: int
    extracellular_regions: list[tuple[int, int]]
    intracellular_regions: list[tuple[int, int]]
    membrane_insertion_energy: float


@dataclass
class LipidEnvironment:
    membrane_type: str  # "plasma" | "er" | "mitochondrial" | "nuclear"
    lipid_composition: dict[str, float]
    thickness_nm: float
    tilt_angle_deg: float


# Kyte-Doolittle hydrophobicity scale
KYTE_DOOLITTLE: dict[str, float] = {
    "A": 1.8,
    "R": -4.5,
    "N": -3.5,
    "D": -3.5,
    "C": 2.5,
    "Q": -3.5,
    "E": -3.5,
    "G": -0.4,
    "H": -3.2,
    "I": 4.5,
    "L": 3.8,
    "K": -3.9,
    "M": 1.9,
    "F": 2.8,
    "P": -1.6,
    "S": -0.8,
    "T": -0.7,
    "W": -0.9,
    "Y": -1.3,
    "V": 4.2,
}


def predict_tm_helices(sequence: str) -> list[TMHelix]:
    """Sliding window Kyte-Doolittle scan for TM helices."""
    seq = sequence.upper()
    n = len(seq)
    helices: list[TMHelix] = []
    in_helix = False
    helix_start = 0
    helix_scores: list[float] = []

    window_size = 19

    scores: list[float] = []
    for i in range(n - window_size + 1):
        window = seq[i : i + window_size]
        score = sum(KYTE_DOOLITTLE.get(aa, 0.0) for aa in window) / window_size
        scores.append(score)

    THRESHOLD = 1.6
    i = 0
    while i < len(scores):
        if scores[i] >= THRESHOLD:
            if not in_helix:
                in_helix = True
                helix_start = i
                helix_scores = [scores[i]]
            else:
                helix_scores.append(scores[i])
        else:
            if in_helix:
                in_helix = False
                helix_end = helix_start + window_size + len(helix_scores) - 2
                avg_score = sum(helix_scores) / len(helix_scores)
                orientation = "in_to_out" if len(helices) % 2 == 0 else "out_to_in"
                helices.append(
                    TMHelix(
                        start=helix_start,
                        end=min(helix_end, n - 1),
                        orientation=orientation,
                        hydrophobicity_score=round(avg_score, 3),
                    )
                )
                helix_scores = []
        i += 1

    # Close open helix at end
    if in_helix and helix_scores:
        helix_end = helix_start + window_size + len(helix_scores) - 2
        avg_score = sum(helix_scores) / len(helix_scores)
        orientation = "in_to_out" if len(helices) % 2 == 0 else "out_to_in"
        helices.append(
            TMHelix(
                start=helix_start,
                end=min(helix_end, n - 1),
                orientation=orientation,
                hydrophobicity_score=round(avg_score, 3),
            )
        )

    return helices


def analyze_membrane_protein(sequence: str) -> MembraneProteinResult:
    """Full TM helix prediction, topology assignment, region classification."""
    helices = predict_tm_helices(sequence)
    n = len(sequence)
    n_tm = len(helices)
    is_membrane = n_tm >= 1

    # Topology assignment
    if n_tm == 0:
        topology = "none"
    elif n_tm == 1:
        # Type I: N-term extracellular, single-pass
        # Type II: N-term intracellular, single-pass
        topology = "type_I" if helices[0].orientation == "in_to_out" else "type_II"
    elif n_tm >= 2:
        topology = "multi_pass"

    # Check peripheral: very low insertion energy (no true TM, but membrane-associated)
    # Treat proteins with borderline hydrophobicity without confirmed TM helices
    if not is_membrane:
        # Check if protein has surface hydrophobic patch (peripheral)
        total_hydro = sum(KYTE_DOOLITTLE.get(aa, 0.0) for aa in sequence.upper())
        avg_hydro = total_hydro / max(len(sequence), 1)
        if avg_hydro > 0.3:
            topology = "peripheral"
            is_membrane = True

    # Region classification: between TM helices alternate extracellular/intracellular
    extracellular: list[tuple[int, int]] = []
    intracellular: list[tuple[int, int]] = []

    if n_tm == 0:
        intracellular.append((0, n - 1))
    else:
        # N-terminal region
        if helices[0].start > 0:
            region = (0, helices[0].start - 1)
            if topology == "type_I":
                extracellular.append(region)
            else:
                intracellular.append(region)

        for idx, helix in enumerate(helices):
            if idx < len(helices) - 1:
                next_helix = helices[idx + 1]
                gap_start = helix.end + 1
                gap_end = next_helix.start - 1
                if gap_start <= gap_end:
                    region = (gap_start, gap_end)
                    # Alternate: after even-indexed helix → extracellular if type_I
                    if (idx % 2 == 0 and topology == "type_I") or (
                        idx % 2 == 1 and topology != "type_I"
                    ):
                        intracellular.append(region)
                    else:
                        extracellular.append(region)

        # C-terminal region
        if helices[-1].end < n - 1:
            region = (helices[-1].end + 1, n - 1)
            if n_tm % 2 == 0:
                if topology == "type_I":
                    extracellular.append(region)
                else:
                    intracellular.append(region)
            else:
                if topology == "type_I":
                    intracellular.append(region)
                else:
                    extracellular.append(region)

    # Membrane insertion energy: rough estimate from TM helix hydrophobicity
    if helices:
        insertion_energy = -1.5 * sum(h.hydrophobicity_score for h in helices)
    else:
        insertion_energy = 0.0

    return MembraneProteinResult(
        sequence=sequence,
        is_membrane_protein=is_membrane,
        tm_helices=helices,
        topology=topology,
        n_tm_helices=n_tm,
        extracellular_regions=extracellular,
        intracellular_regions=intracellular,
        membrane_insertion_energy=round(insertion_energy, 3),
    )


def assign_lipid_environment(result: MembraneProteinResult) -> LipidEnvironment:
    """Assign lipid environment based on topology and TM count."""
    n_tm = result.n_tm_helices
    topology = result.topology

    if topology == "none" or not result.is_membrane_protein:
        # Peripheral / non-membrane — default plasma
        return LipidEnvironment(
            membrane_type="plasma",
            lipid_composition={"POPC": 0.4, "POPE": 0.3, "cholesterol": 0.3},
            thickness_nm=3.5,
            tilt_angle_deg=0.0,
        )

    if n_tm >= 7:
        # GPCR-like → plasma membrane
        return LipidEnvironment(
            membrane_type="plasma",
            lipid_composition={
                "POPC": 0.35,
                "POPE": 0.25,
                "cholesterol": 0.30,
                "sphingomyelin": 0.10,
            },
            thickness_nm=4.0,
            tilt_angle_deg=5.0,
        )
    elif n_tm >= 4:
        # Multi-pass, ER-like
        return LipidEnvironment(
            membrane_type="er",
            lipid_composition={"POPC": 0.55, "POPE": 0.30, "cholesterol": 0.10, "PI": 0.05},
            thickness_nm=3.8,
            tilt_angle_deg=8.0,
        )
    elif n_tm >= 2:
        # Mitochondrial
        return LipidEnvironment(
            membrane_type="mitochondrial",
            lipid_composition={
                "POPC": 0.40,
                "POPE": 0.35,
                "cardiolipin": 0.20,
                "cholesterol": 0.05,
            },
            thickness_nm=3.6,
            tilt_angle_deg=12.0,
        )
    else:
        # Single-pass → plasma
        return LipidEnvironment(
            membrane_type="plasma",
            lipid_composition={"POPC": 0.40, "POPE": 0.30, "cholesterol": 0.30},
            thickness_nm=3.5,
            tilt_angle_deg=3.0,
        )


def calculate_cavity_accessibility(
    result: MembraneProteinResult, residue_positions: list[int]
) -> dict:
    """Report accessibility of residue positions from extracellular vs intracellular face."""
    extracellular_set: set[int] = set()
    for start, end in result.extracellular_regions:
        extracellular_set.update(range(start, end + 1))

    intracellular_set: set[int] = set()
    for start, end in result.intracellular_regions:
        intracellular_set.update(range(start, end + 1))

    tm_set: set[int] = set()
    for helix in result.tm_helices:
        tm_set.update(range(helix.start, helix.end + 1))

    accessibility: dict[int, str] = {}
    for pos in residue_positions:
        if pos in extracellular_set:
            accessibility[pos] = "extracellular"
        elif pos in intracellular_set:
            accessibility[pos] = "intracellular"
        elif pos in tm_set:
            accessibility[pos] = "transmembrane"
        else:
            accessibility[pos] = "unknown"

    return {
        "residue_accessibility": accessibility,
        "extracellular_count": sum(1 for v in accessibility.values() if v == "extracellular"),
        "intracellular_count": sum(1 for v in accessibility.values() if v == "intracellular"),
        "transmembrane_count": sum(1 for v in accessibility.values() if v == "transmembrane"),
    }


# ---------------------------------------------------------------------------
# Feature 2: Metal coordination site prediction
# ---------------------------------------------------------------------------


class MetalIon(str, Enum):
    zinc = "zinc"
    iron = "iron"
    calcium = "calcium"
    magnesium = "magnesium"
    copper = "copper"
    manganese = "manganese"
    cobalt = "cobalt"
    nickel = "nickel"


@dataclass
class MetalSite:
    metal: MetalIon
    coordinating_residues: list[int]
    coordination_number: int
    geometry: str  # "tetrahedral" | "octahedral" | "square_planar" | "trigonal_bipyramidal"
    confidence: float
    site_type: str  # "catalytic" | "structural" | "regulatory"
    druggable: bool


@dataclass
class MetalSiteResult:
    sequence: str
    sites: list[MetalSite]
    total_sites: int
    catalytic_sites: int
    structural_sites: int


# Metal binding motifs (regex patterns)
METAL_BINDING_MOTIFS: dict[str, str] = {
    "zinc_finger": r"C.{2,4}C.{12,14}H.{3,5}H",
    "ef_hand": r"D.{1}[DNS].{1}[DENSTG].{1}[DE]",
    "iron_sulfur": r"C.{2}C.{2}C.{3}C",
    "rubredoxin": r"C.{2}C.{16,18}C.{2}C",
    "zinc_mononuclear": r"H.{2}H.{10,20}[DE]",
    "calcium_binding": r"[DE].{1}[DNS].{2}[DEST]",
    "copper_type1": r"H.{3,5}C.{2}H",
    "manganese_sod": r"H.{1}[DE].{2}H",
    "nickel_binding": r"H.{2}[DE].{1}H.{2}H",
    "cobalt_corrins": r"H.{4}[HCE].{4,6}H",
}

# Known metalloprotein reference DB (15 entries)
KNOWN_METALLOPROTEIN_DB: list[dict] = [
    {
        "name": "carbonic_anhydrase",
        "gene": "CA2",
        "metal": MetalIon.zinc,
        "motif": "ZINC_FINGER",
        "function": "catalytic",
        "keywords": ["CA2", "carbonic", "anhydrase"],
    },
    {
        "name": "hemoglobin_alpha",
        "gene": "HBA1",
        "metal": MetalIon.iron,
        "motif": "HEME",
        "function": "oxygen_transport",
        "keywords": ["HBA1", "hemoglobin", "globin"],
    },
    {
        "name": "hemoglobin_beta",
        "gene": "HBB",
        "metal": MetalIon.iron,
        "motif": "HEME",
        "function": "oxygen_transport",
        "keywords": ["HBB", "hemoglobin"],
    },
    {
        "name": "calmodulin",
        "gene": "CALM1",
        "metal": MetalIon.calcium,
        "motif": "EF_HAND",
        "function": "signaling",
        "keywords": ["CALM1", "calmodulin"],
    },
    {
        "name": "superoxide_dismutase_cu",
        "gene": "SOD1",
        "metal": MetalIon.copper,
        "motif": "COPPER_TYPE1",
        "function": "catalytic",
        "keywords": ["SOD1", "superoxide", "dismutase"],
    },
    {
        "name": "superoxide_dismutase_zn",
        "gene": "SOD1",
        "metal": MetalIon.zinc,
        "motif": "ZINC_MONONUCLEAR",
        "function": "structural",
        "keywords": ["SOD1", "superoxide"],
    },
    {
        "name": "ferritin",
        "gene": "FTH1",
        "metal": MetalIon.iron,
        "motif": "IRON_STORAGE",
        "function": "storage",
        "keywords": ["FTH1", "ferritin"],
    },
    {
        "name": "matrix_metalloprotease",
        "gene": "MMP2",
        "metal": MetalIon.zinc,
        "motif": "ZINC_MONONUCLEAR",
        "function": "catalytic",
        "keywords": ["MMP2", "metalloprotease", "MMP"],
    },
    {
        "name": "alcohol_dehydrogenase",
        "gene": "ADH1",
        "metal": MetalIon.zinc,
        "motif": "ZINC_FINGER",
        "function": "catalytic",
        "keywords": ["ADH1", "alcohol", "dehydrogenase"],
    },
    {
        "name": "myoglobin",
        "gene": "MB",
        "metal": MetalIon.iron,
        "motif": "HEME",
        "function": "oxygen_storage",
        "keywords": ["MB", "myoglobin"],
    },
    {
        "name": "lactoferrin",
        "gene": "LTF",
        "metal": MetalIon.iron,
        "motif": "TRANSFERRIN",
        "function": "transport",
        "keywords": ["LTF", "lactoferrin", "transferrin"],
    },
    {
        "name": "manganese_sod",
        "gene": "SOD2",
        "metal": MetalIon.manganese,
        "motif": "MANGANESE_SOD",
        "function": "catalytic",
        "keywords": ["SOD2", "manganese"],
    },
    {
        "name": "nitrogenase",
        "gene": "NIFH",
        "metal": MetalIon.iron,
        "motif": "IRON_SULFUR",
        "function": "catalytic",
        "keywords": ["NIFH", "nitrogenase"],
    },
    {
        "name": "cytochrome_c",
        "gene": "CYCS",
        "metal": MetalIon.iron,
        "motif": "HEME",
        "function": "electron_transfer",
        "keywords": ["CYCS", "cytochrome"],
    },
    {
        "name": "cobalt_corrinoid",
        "gene": "MMUT",
        "metal": MetalIon.cobalt,
        "motif": "COBALT_CORRINS",
        "function": "catalytic",
        "keywords": ["MMUT", "cobalamin", "methylmalonyl"],
    },
]


def _infer_metal_from_residues(coordinating: list[str]) -> MetalIon:
    """Infer metal type from coordinating residue types."""
    c_count = coordinating.count("C")
    h_count = coordinating.count("H")
    de_count = sum(1 for r in coordinating if r in ("D", "E"))

    if c_count >= 2 and h_count >= 2:
        return MetalIon.zinc
    if c_count >= 3:
        return MetalIon.iron  # iron-sulfur
    if h_count >= 2 and de_count >= 1:
        return MetalIon.zinc
    if de_count >= 2 and c_count == 0:
        return MetalIon.calcium
    if de_count >= 1 and h_count >= 2:
        return MetalIon.magnesium
    return MetalIon.zinc


def _geometry_from_cn(coordination_number: int) -> str:
    if coordination_number == 4:
        return "tetrahedral"
    elif coordination_number == 6:
        return "octahedral"
    elif coordination_number == 5:
        return "trigonal_bipyramidal"
    else:
        return "square_planar"


def predict_metal_sites(sequence: str) -> MetalSiteResult:
    """Scan for metal binding motifs + CHH/CCH/CCC/HHH clusters."""
    seq = sequence.upper()
    sites: list[MetalSite] = []

    # Pattern-based scan
    for motif_name, pattern in METAL_BINDING_MOTIFS.items():
        for m in re.finditer(pattern, seq):
            start = m.start()
            matched = m.group()
            # Extract coordinating residues (C, H, D, E)
            coord_residues_letters = [aa for aa in matched if aa in ("C", "H", "D", "E")]
            coord_positions = []
            for i, aa in enumerate(matched):
                if aa in ("C", "H", "D", "E"):
                    coord_positions.append(start + i)

            if not coord_positions:
                continue

            metal = _infer_metal_from_residues(coord_residues_letters)
            cn = min(len(coord_positions), 6)
            geometry = _geometry_from_cn(cn)

            # Site type heuristics
            if (
                "zinc_finger" in motif_name
                or "rubredoxin" in motif_name
                or "iron_sulfur" in motif_name
            ):
                site_type = "structural"
            elif "ef_hand" in motif_name or "calcium" in motif_name:
                site_type = "regulatory"
            else:
                site_type = "catalytic"

            confidence = 0.75 if motif_name in ("zinc_finger", "ef_hand", "iron_sulfur") else 0.60
            druggable = site_type == "catalytic"

            sites.append(
                MetalSite(
                    metal=metal,
                    coordinating_residues=coord_positions,
                    coordination_number=cn,
                    geometry=geometry,
                    confidence=confidence,
                    site_type=site_type,
                    druggable=druggable,
                )
            )

    # CHH / CCH / CCC / HHH cluster scan (short-range, within 10 residues)
    cluster_patterns = [
        (r"C.{1,3}C.{1,3}C", MetalIon.iron, "structural"),
        (r"H.{1,3}H.{1,3}H", MetalIon.zinc, "catalytic"),
        (r"C.{1,3}C.{1,3}H", MetalIon.zinc, "catalytic"),
        (r"C.{1,3}H.{1,3}H", MetalIon.zinc, "catalytic"),
    ]
    for pattern, metal, site_type in cluster_patterns:
        for m in re.finditer(pattern, seq):
            start = m.start()
            matched = m.group()
            coord_positions = [
                start + i for i, aa in enumerate(matched) if aa in ("C", "H", "D", "E")
            ]
            if not coord_positions:
                continue
            # Avoid duplicate sites (check overlap with existing)
            overlap = any(
                any(p in existing.coordinating_residues for p in coord_positions)
                for existing in sites
            )
            if overlap:
                continue
            cn = min(len(coord_positions), 4)
            sites.append(
                MetalSite(
                    metal=metal,
                    coordinating_residues=coord_positions,
                    coordination_number=cn,
                    geometry=_geometry_from_cn(cn),
                    confidence=0.55,
                    site_type=site_type,
                    druggable=(site_type == "catalytic"),
                )
            )

    catalytic = sum(1 for s in sites if s.site_type == "catalytic")
    structural = sum(1 for s in sites if s.site_type == "structural")

    return MetalSiteResult(
        sequence=sequence,
        sites=sites,
        total_sites=len(sites),
        catalytic_sites=catalytic,
        structural_sites=structural,
    )


def cross_validate_metal(sequence: str, gene: str = "") -> dict:
    """Cross-validate predicted metal sites against KNOWN_METALLOPROTEIN_DB."""
    predicted = predict_metal_sites(sequence)
    gene_upper = gene.upper()

    db_matches: list[dict] = []
    for entry in KNOWN_METALLOPROTEIN_DB:
        match = False
        if gene_upper and any(
            kw.upper() in gene_upper or gene_upper in kw.upper() for kw in entry["keywords"]
        ):
            match = True
        if match:
            db_matches.append(
                {
                    "db_name": entry["name"],
                    "gene": entry["gene"],
                    "expected_metal": entry["metal"].value,
                    "function": entry["function"],
                }
            )

    predicted_metals = list({s.metal.value for s in predicted.sites})
    validated = []
    for match in db_matches:
        if match["expected_metal"] in predicted_metals:
            validated.append({**match, "validated": True})
        else:
            validated.append(
                {**match, "validated": False, "note": "metal not predicted from sequence"}
            )

    return {
        "gene": gene,
        "predicted_sites": predicted.total_sites,
        "predicted_metals": predicted_metals,
        "db_matches": db_matches,
        "cross_validated": validated,
        "validation_source": "KNOWN_METALLOPROTEIN_DB",
        "confidence": "high" if validated and all(v.get("validated") for v in validated) else "low",
    }


# ---------------------------------------------------------------------------
# Feature 3: Glycoprotein modeling
# ---------------------------------------------------------------------------


@dataclass
class GlycosylationSite:
    position: int
    type: str  # "n_linked" | "o_linked" | "c_mannosylation"
    motif: str
    occupancy_probability: float
    glycan_type: str | None


@dataclass
class GlycanShieldResult:
    sequence: str
    sites: list[GlycosylationSite]
    n_linked_count: int
    o_linked_count: int
    shield_coverage_pct: float
    shielded_residues: list[int]
    exposed_residues: list[int]
    epitope_accessibility_impact: dict


N_GLYCOSYLATION_MOTIF = r"N[^P][ST]"

# Common glycan types (8)
COMMON_GLYCAN_TYPES: dict[str, dict] = {
    "high_mannose": {
        "molecular_weight_da": 1500,
        "size_angstrom": 25.0,
        "description": "Man5-9GlcNAc2, ER-processed",
    },
    "complex_biantennary": {
        "molecular_weight_da": 2200,
        "size_angstrom": 35.0,
        "description": "Gal2GlcNAc2Man3GlcNAc2, fully processed",
    },
    "complex_triantennary": {
        "molecular_weight_da": 2800,
        "size_angstrom": 40.0,
        "description": "Three-antennae complex type",
    },
    "hybrid": {
        "molecular_weight_da": 1900,
        "size_angstrom": 30.0,
        "description": "Half-processed, one arm complex one high-mannose",
    },
    "sialylated": {
        "molecular_weight_da": 2500,
        "size_angstrom": 38.0,
        "description": "Complex type with terminal sialic acid",
    },
    "fucosylated": {
        "molecular_weight_da": 2100,
        "size_angstrom": 33.0,
        "description": "Core-fucosylated biantennary",
    },
    "o_glcnac": {
        "molecular_weight_da": 220,
        "size_angstrom": 8.0,
        "description": "Simple O-GlcNAc monosaccharide, nuclear/cytoplasmic",
    },
    "mucin_type_o": {
        "molecular_weight_da": 600,
        "size_angstrom": 15.0,
        "description": "Core 1/2 O-linked mucin-type",
    },
}


def predict_glycosylation_sites(sequence: str) -> list[GlycosylationSite]:
    """Predict N-linked, O-linked, and C-mannosylation sites."""
    seq = sequence.upper()
    sites: list[GlycosylationSite] = []

    # N-linked: NXS/T where X != P
    for m in re.finditer(N_GLYCOSYLATION_MOTIF, seq):
        pos = m.start()
        motif_str = m.group()
        # Occupancy varies with sequon context; simple heuristic
        occupancy = 0.7 if motif_str[2] == "T" else 0.55
        # Assign glycan type based on position (deterministic)
        glycan_types_list = list(COMMON_GLYCAN_TYPES.keys())
        glycan = glycan_types_list[pos % len(glycan_types_list)]
        sites.append(
            GlycosylationSite(
                position=pos,
                type="n_linked",
                motif=motif_str,
                occupancy_probability=occupancy,
                glycan_type=glycan,
            )
        )

    # O-linked: S or T in Pro-rich regions (P within 3 residues)
    for i, aa in enumerate(seq):
        if aa in ("S", "T"):
            # Check for Pro in window [-3, +3]
            window_start = max(0, i - 3)
            window_end = min(len(seq), i + 4)
            window = seq[window_start:window_end]
            if "P" in window:
                # Avoid overlapping with N-linked sites at same position
                if not any(s.position == i for s in sites):
                    sites.append(
                        GlycosylationSite(
                            position=i,
                            type="o_linked",
                            motif=aa,
                            occupancy_probability=0.35,
                            glycan_type="mucin_type_o",
                        )
                    )

    # C-mannosylation: WXXW motif
    for m in re.finditer(r"W.{2}W", seq):
        pos = m.start()
        sites.append(
            GlycosylationSite(
                position=pos,
                type="c_mannosylation",
                motif=m.group(),
                occupancy_probability=0.45,
                glycan_type="high_mannose",
            )
        )

    return sites


def analyze_glycan_shield(sequence: str) -> GlycanShieldResult:
    """Predict glycosylation sites and estimate glycan shield coverage."""
    seq = sequence.upper()
    n = len(seq)
    sites = predict_glycosylation_sites(seq)

    n_linked = [s for s in sites if s.type == "n_linked"]
    o_linked = [s for s in sites if s.type == "o_linked"]

    # Each N-linked glycan shields ~20 surrounding residues
    shielded_set: set[int] = set()
    for site in n_linked:
        shield_start = max(0, site.position - 10)
        shield_end = min(n - 1, site.position + 10)
        shielded_set.update(range(shield_start, shield_end + 1))

    # O-linked glycans shield ~5 surrounding residues
    for site in o_linked:
        shield_start = max(0, site.position - 2)
        shield_end = min(n - 1, site.position + 2)
        shielded_set.update(range(shield_start, shield_end + 1))

    exposed_set = set(range(n)) - shielded_set
    shield_pct = round(100.0 * len(shielded_set) / max(n, 1), 2)

    # Epitope accessibility impact: basic classification
    epitope_impact: dict = {
        "shielded_fraction": round(len(shielded_set) / max(n, 1), 3),
        "n_linked_sites": len(n_linked),
        "o_linked_sites": len(o_linked),
        "estimated_shielded_residues": len(shielded_set),
        "vaccine_design_note": (
            "High glycan shield — epitope selection should focus on exposed regions"
            if shield_pct > 30
            else "Moderate glycan shield — targeted glycan engineering may improve immunogenicity"
        ),
    }

    return GlycanShieldResult(
        sequence=sequence,
        sites=sites,
        n_linked_count=len(n_linked),
        o_linked_count=len(o_linked),
        shield_coverage_pct=shield_pct,
        shielded_residues=sorted(shielded_set),
        exposed_residues=sorted(exposed_set),
        epitope_accessibility_impact=epitope_impact,
    )


def assess_epitope_accessibility(shield: GlycanShieldResult, epitope_positions: list[int]) -> dict:
    """For each epitope position, report whether it's shielded by glycans."""
    shielded_set = set(shield.shielded_residues)
    results: dict[int, dict] = {}

    for pos in epitope_positions:
        is_shielded = pos in shielded_set
        # Find nearest glycan site
        nearest_site = None
        nearest_dist = None
        for site in shield.sites:
            dist = abs(site.position - pos)
            if nearest_dist is None or dist < nearest_dist:
                nearest_dist = dist
                nearest_site = site

        results[pos] = {
            "position": pos,
            "shielded": is_shielded,
            "accessibility": "low" if is_shielded else "high",
            "nearest_glycan_position": nearest_site.position if nearest_site else None,
            "nearest_glycan_distance": nearest_dist,
            "nearest_glycan_type": nearest_site.type if nearest_site else None,
            "vaccine_relevance": "poor_target" if is_shielded else "good_target",
        }

    shielded_count = sum(1 for v in results.values() if v["shielded"])
    exposed_count = len(epitope_positions) - shielded_count

    return {
        "epitope_results": results,
        "total_epitopes": len(epitope_positions),
        "shielded_epitopes": shielded_count,
        "exposed_epitopes": exposed_count,
        "accessibility_score": round(exposed_count / max(len(epitope_positions), 1), 3),
        "recommendation": (
            "Select exposed epitopes for vaccine design"
            if exposed_count > 0
            else "All epitopes shielded — consider glycan deletion mutants"
        ),
    }
