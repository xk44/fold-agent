"""PPI Mapping Mode — Protein-Protein Interaction Analysis Pipeline.

Provides:
  - PPI prediction (AF-Multimer stub)
  - PPI interface druggability assessment
  - Signaling pathway mapping
  - Host-pathogen interaction prediction
  - Combination therapy target suggestions
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# PPI prediction
# ---------------------------------------------------------------------------


@dataclass
class PPIResult:
    protein_a: str
    protein_b: str
    confidence_score: float
    interface_residues_a: list[int]
    interface_residues_b: list[int]
    interaction_type: str  # direct / indirect / predicted
    biological_context: str


KNOWN_CANCER_PPIS: dict[str, dict] = {
    "TP53-MDM2": {
        "protein_a": "TP53",
        "protein_b": "MDM2",
        "confidence_score": 0.98,
        "interface_residues_a": [19, 22, 26],
        "interface_residues_b": [54, 58, 67, 72, 75],
        "interaction_type": "direct",
        "biological_context": "MDM2 ubiquitinates TP53 for proteasomal degradation; p53 transactivation domain binds MDM2 hydrophobic cleft",
    },
    "KRAS-RAF1": {
        "protein_a": "KRAS",
        "protein_b": "RAF1",
        "confidence_score": 0.95,
        "interface_residues_a": [32, 35, 36, 40],
        "interface_residues_b": [68, 71, 84, 89],
        "interaction_type": "direct",
        "biological_context": "RAS effector interaction; GTP-bound KRAS recruits RAF1 RBD to activate MAPK cascade",
    },
    "EGFR-GRB2": {
        "protein_a": "EGFR",
        "protein_b": "GRB2",
        "confidence_score": 0.92,
        "interface_residues_a": [1068, 1086, 1148, 1173],
        "interface_residues_b": [99, 102, 165, 207],
        "interaction_type": "direct",
        "biological_context": "pY1068/pY1086 EGFR recruits GRB2 SH2 domain; links receptor activation to RAS-MAPK and PI3K pathways",
    },
    "MYC-MAX": {
        "protein_a": "MYC",
        "protein_b": "MAX",
        "confidence_score": 0.96,
        "interface_residues_a": [355, 361, 368, 374, 381],
        "interface_residues_b": [22, 28, 35, 41, 48],
        "interaction_type": "direct",
        "biological_context": "bHLH-LZ heterodimerization required for MYC transcriptional activity at E-box elements",
    },
    "BRCA1-BARD1": {
        "protein_a": "BRCA1",
        "protein_b": "BARD1",
        "confidence_score": 0.97,
        "interface_residues_a": [1, 22, 62, 64],
        "interface_residues_b": [29, 45, 99, 127],
        "interaction_type": "direct",
        "biological_context": "RING domain heterodimer; BRCA1-BARD1 E3 ubiquitin ligase essential for DNA double-strand break repair",
    },
    "PDCD1-CD274": {
        "protein_a": "PDCD1",
        "protein_b": "CD274",
        "confidence_score": 0.94,
        "interface_residues_a": [62, 66, 115, 121, 126],
        "interface_residues_b": [54, 56, 68, 115, 122, 125],
        "interaction_type": "direct",
        "biological_context": "PD-1/PD-L1 immune checkpoint axis; suppresses T-cell activation in tumor microenvironment",
    },
    "BCL2-BAX": {
        "protein_a": "BCL2",
        "protein_b": "BAX",
        "confidence_score": 0.95,
        "interface_residues_a": [92, 96, 100, 104, 136, 140, 143],
        "interface_residues_b": [68, 72, 76, 80, 146, 150],
        "interaction_type": "direct",
        "biological_context": "BCL2 BH3-binding groove sequesters BAX BH3 domain; anti-apoptotic interaction controlling MOMP",
    },
    "CDK4-CCND1": {
        "protein_a": "CDK4",
        "protein_b": "CCND1",
        "confidence_score": 0.93,
        "interface_residues_a": [14, 15, 18, 31, 145],
        "interface_residues_b": [156, 160, 164, 231, 249],
        "interaction_type": "direct",
        "biological_context": "Cyclin D1 activates CDK4; complex phosphorylates RB1 driving G1/S cell cycle progression",
    },
    "RB1-E2F1": {
        "protein_a": "RB1",
        "protein_b": "E2F1",
        "confidence_score": 0.91,
        "interface_residues_a": [378, 394, 462, 567, 651],
        "interface_residues_b": [409, 412, 415, 423, 426],
        "interaction_type": "direct",
        "biological_context": "Hypophosphorylated RB1 represses E2F1 transcriptional targets; CDK4/6 phosphorylation releases E2F1",
    },
    "AKT1-MTOR": {
        "protein_a": "AKT1",
        "protein_b": "MTOR",
        "confidence_score": 0.88,
        "interface_residues_a": [308, 450],
        "interface_residues_b": [2448, 2481],
        "interaction_type": "indirect",
        "biological_context": "AKT phosphorylates TSC2 to activate mTORC1; AKT also directly phosphorylates mTOR S2448",
    },
    "EGFR-SRC": {
        "protein_a": "EGFR",
        "protein_b": "SRC",
        "confidence_score": 0.87,
        "interface_residues_a": [845, 1045, 1068],
        "interface_residues_b": [416, 527, 534],
        "interaction_type": "direct",
        "biological_context": "SRC kinase transactivates EGFR and is recruited to activated receptor; co-operative oncogenic signaling",
    },
    "VHL-HIF1A": {
        "protein_a": "VHL",
        "protein_b": "HIF1A",
        "confidence_score": 0.93,
        "interface_residues_a": [67, 69, 78, 83, 111, 115],
        "interface_residues_b": [561, 564, 567, 571],
        "interaction_type": "direct",
        "biological_context": "VHL E3 ligase targets hydroxylated HIF1A for proteasomal degradation under normoxia",
    },
    "PIK3CA-PIK3R1": {
        "protein_a": "PIK3CA",
        "protein_b": "PIK3R1",
        "confidence_score": 0.94,
        "interface_residues_a": [108, 113, 163, 261],
        "interface_residues_b": [435, 472, 621, 657],
        "interaction_type": "direct",
        "biological_context": "p110α catalytic subunit constitutively bound to p85α regulatory subunit; p85 SH2 domains bind pY-containing receptors",
    },
    "BRAF-RAF1": {
        "protein_a": "BRAF",
        "protein_b": "RAF1",
        "confidence_score": 0.89,
        "interface_residues_a": [457, 461, 467, 470],
        "interface_residues_b": [257, 261, 267, 270],
        "interaction_type": "direct",
        "biological_context": "BRAF-CRAF heterodimerization; critical for paradoxical MAPK activation by first-gen BRAF inhibitors",
    },
    "STAT3-JAK2": {
        "protein_a": "STAT3",
        "protein_b": "JAK2",
        "confidence_score": 0.90,
        "interface_residues_a": [664, 705, 727],
        "interface_residues_b": [1007, 1008, 1028],
        "interaction_type": "direct",
        "biological_context": "JAK2 phosphorylates STAT3 Y705; activated STAT3 dimerizes and drives oncogenic transcription",
    },
    "NOTCH1-DLL4": {
        "protein_a": "NOTCH1",
        "protein_b": "DLL4",
        "confidence_score": 0.86,
        "interface_residues_a": [210, 250, 312, 345],
        "interface_residues_b": [178, 195, 208, 225],
        "interaction_type": "direct",
        "biological_context": "Delta-like ligand 4 activates NOTCH1 signaling; critical in tumor angiogenesis and cancer stem cell maintenance",
    },
    "CTNNB1-APC": {
        "protein_a": "CTNNB1",
        "protein_b": "APC",
        "confidence_score": 0.94,
        "interface_residues_a": [130, 134, 174, 178, 222],
        "interface_residues_b": [1014, 1020, 1062, 1068],
        "interaction_type": "direct",
        "biological_context": "APC in destruction complex promotes β-catenin phosphorylation and ubiquitination; Wnt pathway regulation",
    },
    "ERBB2-ERBB3": {
        "protein_a": "ERBB2",
        "protein_b": "ERBB3",
        "confidence_score": 0.92,
        "interface_residues_a": [267, 270, 573, 577],
        "interface_residues_b": [245, 248, 551, 555],
        "interaction_type": "direct",
        "biological_context": "HER2-HER3 heterodimer is the most potent ERBB signaling complex; strong PI3K-AKT activation",
    },
    "MDM2-MDM4": {
        "protein_a": "MDM2",
        "protein_b": "MDM4",
        "confidence_score": 0.88,
        "interface_residues_a": [464, 472, 476, 480],
        "interface_residues_b": [454, 462, 466, 470],
        "interaction_type": "direct",
        "biological_context": "MDM2-MDMX RING domain heterodimerization required for efficient TP53 ubiquitination",
    },
    "SMAD2-SMAD4": {
        "protein_a": "SMAD2",
        "protein_b": "SMAD4",
        "confidence_score": 0.91,
        "interface_residues_a": [264, 275, 330, 338],
        "interface_residues_b": [263, 274, 329, 337],
        "interaction_type": "direct",
        "biological_context": "TGF-β induced SMAD2/3 phosphorylation enables complex formation with SMAD4 for nuclear transcription",
    },
}


def predict_ppi(gene_a: str, gene_b: str) -> PPIResult:
    """Stub PPI prediction (AF-Multimer style). Returns known data or mock scores."""
    a = gene_a.upper()
    b = gene_b.upper()
    key_ab = f"{a}-{b}"
    key_ba = f"{b}-{a}"
    entry = KNOWN_CANCER_PPIS.get(key_ab) or KNOWN_CANCER_PPIS.get(key_ba)
    if entry:
        if KNOWN_CANCER_PPIS.get(key_ba) and not KNOWN_CANCER_PPIS.get(key_ab):
            # swap so protein_a/b match the lookup order
            return PPIResult(
                protein_a=b,
                protein_b=a,
                confidence_score=entry["confidence_score"],
                interface_residues_a=entry["interface_residues_a"],
                interface_residues_b=entry["interface_residues_b"],
                interaction_type=entry["interaction_type"],
                biological_context=entry["biological_context"],
            )
        return PPIResult(
            protein_a=a,
            protein_b=b,
            confidence_score=entry["confidence_score"],
            interface_residues_a=entry["interface_residues_a"],
            interface_residues_b=entry["interface_residues_b"],
            interaction_type=entry["interaction_type"],
            biological_context=entry["biological_context"],
        )
    # Mock prediction for unknown pairs
    mock_score = 0.45 + (hash(key_ab) % 40) / 100.0
    mock_score = max(0.0, min(1.0, mock_score))
    return PPIResult(
        protein_a=a,
        protein_b=b,
        confidence_score=round(mock_score, 3),
        interface_residues_a=[10, 25, 40],
        interface_residues_b=[15, 30, 45],
        interaction_type="predicted",
        biological_context="Computationally predicted interaction — experimental validation required",
    )


# ---------------------------------------------------------------------------
# Druggability assessment
# ---------------------------------------------------------------------------


@dataclass
class DruggabilityScore:
    ppi_pair: str
    interface_area_a2: float
    hot_spots: list[int]
    druggability: str  # high / moderate / low / undruggable
    known_inhibitors: list[str]


_DRUGGABILITY_DB: dict[str, dict] = {
    "TP53-MDM2": {
        "interface_area_a2": 1050.0,
        "hot_spots": [19, 22, 26],
        "druggability": "high",
        "known_inhibitors": ["Nutlin-3a", "RG7112", "AMG232", "Idasanutlin", "APG-115"],
    },
    "BCL2-BAX": {
        "interface_area_a2": 1300.0,
        "hot_spots": [92, 96, 100, 104],
        "druggability": "high",
        "known_inhibitors": ["Venetoclax", "Navitoclax", "Obatoclax"],
    },
    "PDCD1-CD274": {
        "interface_area_a2": 1970.0,
        "hot_spots": [62, 66, 115, 121],
        "druggability": "high",
        "known_inhibitors": ["Pembrolizumab", "Nivolumab", "Atezolizumab", "BMS-1166", "CA-170"],
    },
    "MYC-MAX": {
        "interface_area_a2": 3200.0,
        "hot_spots": [355, 368, 374],
        "druggability": "low",
        "known_inhibitors": ["10058-F4", "JQ1 (indirect)", "MYCi361", "Omomyc"],
    },
    "KRAS-RAF1": {
        "interface_area_a2": 1650.0,
        "hot_spots": [32, 35, 40],
        "druggability": "moderate",
        "known_inhibitors": ["BI-3406", "BAY-293", "Rigosertib"],
    },
    "CDK4-CCND1": {
        "interface_area_a2": 2400.0,
        "hot_spots": [14, 15],
        "druggability": "low",
        "known_inhibitors": ["Palbociclib (CDK4 ATP site)", "Ribociclib", "Abemaciclib"],
    },
    "BRCA1-BARD1": {
        "interface_area_a2": 2100.0,
        "hot_spots": [1, 22, 62],
        "druggability": "low",
        "known_inhibitors": [],
    },
    "EGFR-GRB2": {
        "interface_area_a2": 890.0,
        "hot_spots": [1068, 1086],
        "druggability": "moderate",
        "known_inhibitors": ["SH2 domain inhibitors (preclinical)"],
    },
    "VHL-HIF1A": {
        "interface_area_a2": 780.0,
        "hot_spots": [561, 564, 567],
        "druggability": "moderate",
        "known_inhibitors": ["PT2977/Belzutifan (indirect)", "VH032 PROTAC warhead"],
    },
    "CTNNB1-APC": {
        "interface_area_a2": 4500.0,
        "hot_spots": [174, 178],
        "druggability": "undruggable",
        "known_inhibitors": [],
    },
    "AKT1-MTOR": {
        "interface_area_a2": 1200.0,
        "hot_spots": [308],
        "druggability": "moderate",
        "known_inhibitors": ["Rapamycin (mTOR)", "Temsirolimus", "Everolimus"],
    },
    "RB1-E2F1": {
        "interface_area_a2": 2800.0,
        "hot_spots": [409, 412],
        "druggability": "low",
        "known_inhibitors": [],
    },
}


def assess_interface_druggability(gene_a: str, gene_b: str) -> DruggabilityScore:
    """Return druggability score for the PPI interface."""
    a = gene_a.upper()
    b = gene_b.upper()
    key_ab = f"{a}-{b}"
    key_ba = f"{b}-{a}"
    entry = _DRUGGABILITY_DB.get(key_ab) or _DRUGGABILITY_DB.get(key_ba)
    if entry:
        pair = key_ab if _DRUGGABILITY_DB.get(key_ab) else key_ba
        return DruggabilityScore(
            ppi_pair=pair,
            interface_area_a2=entry["interface_area_a2"],
            hot_spots=entry["hot_spots"],
            druggability=entry["druggability"],
            known_inhibitors=entry["known_inhibitors"],
        )
    # Default for unknown pairs
    return DruggabilityScore(
        ppi_pair=key_ab,
        interface_area_a2=1500.0,
        hot_spots=[],
        druggability="low",
        known_inhibitors=[],
    )


# ---------------------------------------------------------------------------
# Signaling pathway mapping
# ---------------------------------------------------------------------------


@dataclass
class PathwayNode:
    gene: str
    role: str  # oncogene / tumor_suppressor / kinase / receptor / transcription_factor
    pathway: str


SIGNALING_PATHWAYS: dict[str, dict] = {
    "RAS-MAPK": {
        "description": "RAS-RAF-MEK-ERK proliferation and survival signaling",
        "genes": [
            "EGFR",
            "HRAS",
            "KRAS",
            "NRAS",
            "RAF1",
            "BRAF",
            "MAP2K1",
            "MAP2K2",
            "MAPK1",
            "MAPK3",
            "GRB2",
            "SOS1",
        ],
        "nodes": {
            "EGFR": "receptor",
            "HRAS": "oncogene",
            "KRAS": "oncogene",
            "NRAS": "oncogene",
            "RAF1": "kinase",
            "BRAF": "kinase",
            "MAP2K1": "kinase",
            "MAP2K2": "kinase",
            "MAPK1": "kinase",
            "MAPK3": "kinase",
            "GRB2": "adaptor",
            "SOS1": "adaptor",
        },
    },
    "PI3K-AKT-mTOR": {
        "description": "PI3K-AKT-mTOR survival, growth, and metabolism axis",
        "genes": [
            "EGFR",
            "PIK3CA",
            "PIK3R1",
            "PTEN",
            "AKT1",
            "AKT2",
            "PDPK1",
            "TSC1",
            "TSC2",
            "MTOR",
            "RPS6KB1",
            "EIF4EBP1",
        ],
        "nodes": {
            "EGFR": "receptor",
            "PIK3CA": "kinase",
            "PIK3R1": "adaptor",
            "PTEN": "tumor_suppressor",
            "AKT1": "kinase",
            "AKT2": "kinase",
            "PDPK1": "kinase",
            "TSC1": "tumor_suppressor",
            "TSC2": "tumor_suppressor",
            "MTOR": "kinase",
            "RPS6KB1": "kinase",
            "EIF4EBP1": "translational_regulator",
        },
    },
    "p53": {
        "description": "TP53 tumor suppressor and DNA damage response",
        "genes": [
            "TP53",
            "MDM2",
            "MDM4",
            "ATM",
            "ATR",
            "CHEK1",
            "CHEK2",
            "CDKN1A",
            "BBC3",
            "BAX",
            "PUMA",
        ],
        "nodes": {
            "TP53": "tumor_suppressor",
            "MDM2": "oncogene",
            "MDM4": "oncogene",
            "ATM": "kinase",
            "ATR": "kinase",
            "CHEK1": "kinase",
            "CHEK2": "kinase",
            "CDKN1A": "tumor_suppressor",
            "BBC3": "tumor_suppressor",
            "BAX": "tumor_suppressor",
            "PUMA": "tumor_suppressor",
        },
    },
    "Wnt-beta-catenin": {
        "description": "Wnt/β-catenin developmental and oncogenic signaling",
        "genes": [
            "WNT1",
            "FZD1",
            "LRP5",
            "LRP6",
            "DVL1",
            "APC",
            "AXIN1",
            "GSK3B",
            "CTNNB1",
            "TCF7L2",
            "MYC",
            "CCND1",
        ],
        "nodes": {
            "WNT1": "ligand",
            "FZD1": "receptor",
            "LRP5": "receptor",
            "LRP6": "receptor",
            "DVL1": "adaptor",
            "APC": "tumor_suppressor",
            "AXIN1": "tumor_suppressor",
            "GSK3B": "kinase",
            "CTNNB1": "oncogene",
            "TCF7L2": "transcription_factor",
            "MYC": "transcription_factor",
            "CCND1": "oncogene",
        },
    },
    "JAK-STAT": {
        "description": "Janus kinase – signal transducer and activator of transcription",
        "genes": [
            "IL6",
            "IL6R",
            "JAK1",
            "JAK2",
            "TYK2",
            "STAT1",
            "STAT3",
            "STAT5A",
            "SOCS1",
            "SOCS3",
        ],
        "nodes": {
            "IL6": "cytokine",
            "IL6R": "receptor",
            "JAK1": "kinase",
            "JAK2": "kinase",
            "TYK2": "kinase",
            "STAT1": "transcription_factor",
            "STAT3": "transcription_factor",
            "STAT5A": "transcription_factor",
            "SOCS1": "tumor_suppressor",
            "SOCS3": "tumor_suppressor",
        },
    },
    "Notch": {
        "description": "Notch developmental signaling and cancer stem cell maintenance",
        "genes": [
            "DLL4",
            "JAG1",
            "NOTCH1",
            "NOTCH2",
            "NOTCH3",
            "ADAM10",
            "PSEN1",
            "RBPJ",
            "HES1",
            "HEY1",
            "MAML1",
        ],
        "nodes": {
            "DLL4": "ligand",
            "JAG1": "ligand",
            "NOTCH1": "receptor",
            "NOTCH2": "receptor",
            "NOTCH3": "receptor",
            "ADAM10": "protease",
            "PSEN1": "protease",
            "RBPJ": "transcription_factor",
            "HES1": "transcription_factor",
            "HEY1": "transcription_factor",
            "MAML1": "transcription_factor",
        },
    },
}


def map_to_pathway(genes: list[str]) -> dict:
    """Return which signaling pathways are hit and the position of each gene."""
    upper_genes = [g.upper() for g in genes]
    result: dict[str, dict] = {}
    for pathway_name, pathway_data in SIGNALING_PATHWAYS.items():
        hits = []
        for g in upper_genes:
            if g in pathway_data["genes"]:
                hits.append(
                    {
                        "gene": g,
                        "role": pathway_data["nodes"].get(g, "unknown"),
                        "position_in_pathway": pathway_data["genes"].index(g),
                    }
                )
        if hits:
            result[pathway_name] = {
                "description": pathway_data["description"],
                "hit_count": len(hits),
                "hits": hits,
            }
    return result


# ---------------------------------------------------------------------------
# Host-pathogen interaction
# ---------------------------------------------------------------------------


@dataclass
class HostPathogenPPI:
    host_protein: str
    pathogen_protein: str
    pathogen_name: str
    interaction_type: str
    therapeutic_target: bool


KNOWN_HOST_PATHOGEN_PPIS: dict[str, dict] = {
    "ACE2-Spike": {
        "host_protein": "ACE2",
        "pathogen_protein": "Spike",
        "pathogen_name": "SARS-CoV-2",
        "interaction_type": "receptor_binding",
        "therapeutic_target": True,
    },
    "CD4-gp120": {
        "host_protein": "CD4",
        "pathogen_protein": "gp120",
        "pathogen_name": "HIV-1",
        "interaction_type": "receptor_binding",
        "therapeutic_target": True,
    },
    "TMPRSS2-Spike": {
        "host_protein": "TMPRSS2",
        "pathogen_protein": "Spike",
        "pathogen_name": "SARS-CoV-2",
        "interaction_type": "proteolytic_priming",
        "therapeutic_target": True,
    },
    "IFITM3-HA": {
        "host_protein": "IFITM3",
        "pathogen_protein": "HA",
        "pathogen_name": "Influenza A",
        "interaction_type": "restriction_factor",
        "therapeutic_target": False,
    },
    "BST2-GAG": {
        "host_protein": "BST2",
        "pathogen_protein": "GAG",
        "pathogen_name": "HIV-1",
        "interaction_type": "restriction_factor",
        "therapeutic_target": False,
    },
    "TP53-E6": {
        "host_protein": "TP53",
        "pathogen_protein": "E6",
        "pathogen_name": "HPV-16",
        "interaction_type": "oncoviral_degradation",
        "therapeutic_target": True,
    },
    "RB1-E7": {
        "host_protein": "RB1",
        "pathogen_protein": "E7",
        "pathogen_name": "HPV-16",
        "interaction_type": "oncoviral_inactivation",
        "therapeutic_target": True,
    },
    "EGFR-LMP1": {
        "host_protein": "EGFR",
        "pathogen_protein": "LMP1",
        "pathogen_name": "EBV",
        "interaction_type": "receptor_mimicry",
        "therapeutic_target": True,
    },
    "STAT3-NSP3": {
        "host_protein": "STAT3",
        "pathogen_protein": "NSP3",
        "pathogen_name": "SARS-CoV-2",
        "interaction_type": "immune_evasion",
        "therapeutic_target": True,
    },
    "MAVS-NS3": {
        "host_protein": "MAVS",
        "pathogen_protein": "NS3",
        "pathogen_name": "HCV",
        "interaction_type": "innate_immune_evasion",
        "therapeutic_target": True,
    },
}


def predict_host_pathogen_ppi(host_gene: str, pathogen_protein: str) -> HostPathogenPPI | None:
    """Return known host-pathogen PPI or None if not in database."""
    h = host_gene.upper()
    p = pathogen_protein
    for key, entry in KNOWN_HOST_PATHOGEN_PPIS.items():
        if entry["host_protein"] == h and entry["pathogen_protein"] == p:
            return HostPathogenPPI(
                host_protein=entry["host_protein"],
                pathogen_protein=entry["pathogen_protein"],
                pathogen_name=entry["pathogen_name"],
                interaction_type=entry["interaction_type"],
                therapeutic_target=entry["therapeutic_target"],
            )
    return None


# ---------------------------------------------------------------------------
# Combination therapy targets
# ---------------------------------------------------------------------------


@dataclass
class CombinationTarget:
    target_a: str
    target_b: str
    rationale: str
    synergy_score: float
    known_combinations: list[str]


_COMBINATION_DB: list[dict] = [
    {
        "trigger_genes": {"EGFR", "KRAS", "BRAF", "MAP2K1"},
        "target_a": "BRAF",
        "target_b": "MAP2K1",
        "rationale": "Vertical MAPK pathway inhibition prevents adaptive resistance to single-agent BRAF or MEK blockade",
        "synergy_score": 0.87,
        "known_combinations": [
            "Dabrafenib+Trametinib",
            "Vemurafenib+Cobimetinib",
            "Encorafenib+Binimetinib",
        ],
    },
    {
        "trigger_genes": {"EGFR", "PIK3CA", "AKT1", "PTEN"},
        "target_a": "EGFR",
        "target_b": "PIK3CA",
        "rationale": "PI3K pathway bypass is a major mechanism of EGFR TKI resistance; co-inhibition extends responses",
        "synergy_score": 0.79,
        "known_combinations": ["Erlotinib+Alpelisib", "Osimertinib+Copanlisib"],
    },
    {
        "trigger_genes": {"CDK4", "RB1", "CCND1", "CDKN2A"},
        "target_a": "CDK4",
        "target_b": "MTOR",
        "rationale": "mTOR drives cyclin D translation; dual CDK4/6 + mTOR blockade has additive antiproliferative effects",
        "synergy_score": 0.72,
        "known_combinations": ["Palbociclib+Everolimus", "Ribociclib+Temsirolimus"],
    },
    {
        "trigger_genes": {"BCL2", "BAX", "MCL1", "BCL2L1"},
        "target_a": "BCL2",
        "target_b": "MCL1",
        "rationale": "MCL1 upregulation mediates venetoclax resistance; co-targeting BCL2 + MCL1 prevents escape",
        "synergy_score": 0.84,
        "known_combinations": ["Venetoclax+AMG176", "Venetoclax+AZD5991"],
    },
    {
        "trigger_genes": {"TP53", "MDM2", "MDM4"},
        "target_a": "MDM2",
        "target_b": "MDM4",
        "rationale": "MDM2+MDMX heterodimerization required for efficient p53 ubiquitination; dual inhibition needed for full p53 reactivation",
        "synergy_score": 0.76,
        "known_combinations": ["RG7112+ATSP-7041", "Idasanutlin+MDMX peptide"],
    },
    {
        "trigger_genes": {"AKT1", "MTOR", "PIK3CA", "TSC1", "TSC2"},
        "target_a": "AKT1",
        "target_b": "MTOR",
        "rationale": "Feedback reactivation of AKT occurs with mTOR-only inhibition; co-targeting suppresses feedback loop",
        "synergy_score": 0.81,
        "known_combinations": ["MK-2206+Everolimus", "Ipatasertib+Temsirolimus"],
    },
    {
        "trigger_genes": {"BRCA1", "BRCA2", "ATM", "CHEK2"},
        "target_a": "PARP1",
        "target_b": "ATR",
        "rationale": "Synthetic lethality: HR-deficient tumors rely on PARP and ATR for replication stress survival",
        "synergy_score": 0.88,
        "known_combinations": ["Olaparib+Ceralasertib", "Niraparib+M6620"],
    },
    {
        "trigger_genes": {"PDCD1", "CD274", "CTLA4"},
        "target_a": "PDCD1",
        "target_b": "CTLA4",
        "rationale": "PD-1 and CTLA-4 act at distinct checkpoints; dual blockade has synergistic anti-tumor immunity",
        "synergy_score": 0.91,
        "known_combinations": ["Nivolumab+Ipilimumab", "Pembrolizumab+Ipilimumab"],
    },
]


def suggest_combinations(mutated_genes: list[str]) -> list[CombinationTarget]:
    """Suggest combination therapy targets based on mutated gene list."""
    upper = {g.upper() for g in mutated_genes}
    results: list[CombinationTarget] = []
    seen: set[tuple[str, str]] = set()
    for entry in _COMBINATION_DB:
        if upper & entry["trigger_genes"]:
            key = (entry["target_a"], entry["target_b"])
            if key not in seen:
                seen.add(key)
                results.append(
                    CombinationTarget(
                        target_a=entry["target_a"],
                        target_b=entry["target_b"],
                        rationale=entry["rationale"],
                        synergy_score=entry["synergy_score"],
                        known_combinations=entry["known_combinations"],
                    )
                )
    results.sort(key=lambda c: c.synergy_score, reverse=True)
    return results
