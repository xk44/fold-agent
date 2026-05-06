"""Drug Discovery Mode — Computational Drug Discovery Pipeline.

Provides:
  - Binding site prediction (20 known oncology targets)
  - Virtual screening against approved drug library
  - Covalent compound screening
  - Drug repurposing candidate finder
  - Allosteric site prediction
  - Comprehensive drug discovery report builder
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Known drug targets
# ---------------------------------------------------------------------------

KNOWN_DRUG_TARGETS: dict[str, dict] = {
    "EGFR": {
        "full_name": "Epidermal Growth Factor Receptor",
        "target_class": "receptor_tyrosine_kinase",
        "cancer_relevance": ["NSCLC", "glioblastoma", "colorectal"],
        "approved_drugs": ["Gefitinib", "Erlotinib", "Afatinib", "Osimertinib"],
    },
    "BRAF": {
        "full_name": "B-Raf Proto-Oncogene",
        "target_class": "serine_threonine_kinase",
        "cancer_relevance": ["melanoma", "colorectal", "thyroid"],
        "approved_drugs": ["Vemurafenib", "Dabrafenib", "Encorafenib"],
    },
    "ABL1": {
        "full_name": "ABL Proto-Oncogene 1",
        "target_class": "tyrosine_kinase",
        "cancer_relevance": ["CML", "ALL"],
        "approved_drugs": ["Imatinib", "Dasatinib", "Nilotinib", "Ponatinib"],
    },
    "HER2": {
        "full_name": "Human Epidermal Growth Factor Receptor 2",
        "target_class": "receptor_tyrosine_kinase",
        "cancer_relevance": ["breast", "gastric", "lung"],
        "approved_drugs": ["Trastuzumab", "Pertuzumab", "Lapatinib", "Tucatinib"],
    },
    "VEGFR": {
        "full_name": "Vascular Endothelial Growth Factor Receptor",
        "target_class": "receptor_tyrosine_kinase",
        "cancer_relevance": ["renal", "hepatocellular", "thyroid"],
        "approved_drugs": ["Sunitinib", "Sorafenib", "Pazopanib", "Axitinib"],
    },
    "ALK": {
        "full_name": "Anaplastic Lymphoma Kinase",
        "target_class": "receptor_tyrosine_kinase",
        "cancer_relevance": ["NSCLC", "neuroblastoma", "ALCL"],
        "approved_drugs": ["Crizotinib", "Ceritinib", "Alectinib", "Brigatinib"],
    },
    "KRAS": {
        "full_name": "KRAS Proto-Oncogene",
        "target_class": "small_GTPase",
        "cancer_relevance": ["NSCLC", "colorectal", "pancreatic"],
        "approved_drugs": ["Sotorasib", "Adagrasib"],
    },
    "TP53": {
        "full_name": "Tumor Protein P53",
        "target_class": "transcription_factor",
        "cancer_relevance": ["pan-cancer"],
        "approved_drugs": [],
    },
    "PIK3CA": {
        "full_name": "Phosphatidylinositol-4,5-Bisphosphate 3-Kinase Catalytic Subunit Alpha",
        "target_class": "lipid_kinase",
        "cancer_relevance": ["breast", "colorectal", "endometrial"],
        "approved_drugs": ["Alpelisib"],
    },
    "PTEN": {
        "full_name": "Phosphatase And Tensin Homolog",
        "target_class": "phosphatase",
        "cancer_relevance": ["glioblastoma", "prostate", "breast"],
        "approved_drugs": [],
    },
    "CDK4": {
        "full_name": "Cyclin Dependent Kinase 4",
        "target_class": "serine_threonine_kinase",
        "cancer_relevance": ["breast", "liposarcoma", "melanoma"],
        "approved_drugs": ["Palbociclib", "Ribociclib", "Abemaciclib"],
    },
    "MET": {
        "full_name": "MET Proto-Oncogene",
        "target_class": "receptor_tyrosine_kinase",
        "cancer_relevance": ["NSCLC", "gastric", "renal"],
        "approved_drugs": ["Crizotinib", "Capmatinib", "Tepotinib"],
    },
    "RET": {
        "full_name": "Ret Proto-Oncogene",
        "target_class": "receptor_tyrosine_kinase",
        "cancer_relevance": ["thyroid", "NSCLC"],
        "approved_drugs": ["Selpercatinib", "Pralsetinib"],
    },
    "FLT3": {
        "full_name": "FMS Related Receptor Tyrosine Kinase 3",
        "target_class": "receptor_tyrosine_kinase",
        "cancer_relevance": ["AML"],
        "approved_drugs": ["Midostaurin", "Gilteritinib", "Quizartinib"],
    },
    "JAK2": {
        "full_name": "Janus Kinase 2",
        "target_class": "non_receptor_tyrosine_kinase",
        "cancer_relevance": ["MPN", "AML", "DLBCL"],
        "approved_drugs": ["Ruxolitinib", "Fedratinib", "Pacritinib"],
    },
    "BTK": {
        "full_name": "Bruton Tyrosine Kinase",
        "target_class": "non_receptor_tyrosine_kinase",
        "cancer_relevance": ["CLL", "MCL", "WM"],
        "approved_drugs": ["Ibrutinib", "Acalabrutinib", "Zanubrutinib"],
    },
    "BCL2": {
        "full_name": "BCL2 Apoptosis Regulator",
        "target_class": "anti_apoptotic_protein",
        "cancer_relevance": ["CLL", "AML", "follicular_lymphoma"],
        "approved_drugs": ["Venetoclax"],
    },
    "IDH1": {
        "full_name": "Isocitrate Dehydrogenase 1",
        "target_class": "metabolic_enzyme",
        "cancer_relevance": ["AML", "glioma", "cholangiocarcinoma"],
        "approved_drugs": ["Ivosidenib", "Olutasidenib"],
    },
    "FGFR": {
        "full_name": "Fibroblast Growth Factor Receptor",
        "target_class": "receptor_tyrosine_kinase",
        "cancer_relevance": ["bladder", "cholangiocarcinoma", "myeloma"],
        "approved_drugs": ["Erdafitinib", "Pemigatinib", "Infigratinib"],
    },
    "MDM2": {
        "full_name": "MDM2 Proto-Oncogene",
        "target_class": "E3_ubiquitin_ligase",
        "cancer_relevance": ["liposarcoma", "AML", "pan-cancer"],
        "approved_drugs": [],
    },
}


# ---------------------------------------------------------------------------
# Approved drug library
# ---------------------------------------------------------------------------

APPROVED_DRUG_LIBRARY: list[dict] = [
    {
        "name": "Imatinib",
        "primary_target": "ABL1",
        "targets": ["ABL1", "KIT", "PDGFR"],
        "indication": "CML, GIST",
        "mechanism": "ATP-competitive kinase inhibitor",
        "approval_year": 2001,
        "drug_class": "small_molecule",
    },
    {
        "name": "Gefitinib",
        "primary_target": "EGFR",
        "targets": ["EGFR"],
        "indication": "NSCLC (EGFR-mutant)",
        "mechanism": "EGFR TKI (first generation)",
        "approval_year": 2003,
        "drug_class": "small_molecule",
    },
    {
        "name": "Erlotinib",
        "primary_target": "EGFR",
        "targets": ["EGFR"],
        "indication": "NSCLC, pancreatic cancer",
        "mechanism": "EGFR TKI (first generation)",
        "approval_year": 2004,
        "drug_class": "small_molecule",
    },
    {
        "name": "Sorafenib",
        "primary_target": "VEGFR",
        "targets": ["VEGFR", "BRAF", "PDGFR", "KIT"],
        "indication": "Renal cell carcinoma, HCC",
        "mechanism": "Multi-kinase inhibitor",
        "approval_year": 2005,
        "drug_class": "small_molecule",
    },
    {
        "name": "Sunitinib",
        "primary_target": "VEGFR",
        "targets": ["VEGFR", "PDGFR", "KIT", "FLT3"],
        "indication": "Renal cell carcinoma, GIST",
        "mechanism": "Multi-kinase inhibitor",
        "approval_year": 2006,
        "drug_class": "small_molecule",
    },
    {
        "name": "Lapatinib",
        "primary_target": "HER2",
        "targets": ["HER2", "EGFR"],
        "indication": "HER2-positive breast cancer",
        "mechanism": "Dual EGFR/HER2 TKI",
        "approval_year": 2007,
        "drug_class": "small_molecule",
    },
    {
        "name": "Dasatinib",
        "primary_target": "ABL1",
        "targets": ["ABL1", "SRC", "BCR-ABL"],
        "indication": "CML, ALL",
        "mechanism": "BCR-ABL/Src kinase inhibitor",
        "approval_year": 2006,
        "drug_class": "small_molecule",
    },
    {
        "name": "Nilotinib",
        "primary_target": "ABL1",
        "targets": ["ABL1", "KIT", "PDGFR"],
        "indication": "CML",
        "mechanism": "BCR-ABL kinase inhibitor (second gen)",
        "approval_year": 2007,
        "drug_class": "small_molecule",
    },
    {
        "name": "Vemurafenib",
        "primary_target": "BRAF",
        "targets": ["BRAF"],
        "indication": "BRAF V600E melanoma",
        "mechanism": "BRAF V600E inhibitor",
        "approval_year": 2011,
        "drug_class": "small_molecule",
    },
    {
        "name": "Trastuzumab",
        "primary_target": "HER2",
        "targets": ["HER2"],
        "indication": "HER2-positive breast/gastric cancer",
        "mechanism": "Anti-HER2 monoclonal antibody",
        "approval_year": 1998,
        "drug_class": "monoclonal_antibody",
    },
    {
        "name": "Crizotinib",
        "primary_target": "ALK",
        "targets": ["ALK", "MET", "ROS1"],
        "indication": "ALK+ or ROS1+ NSCLC",
        "mechanism": "ALK/MET/ROS1 inhibitor",
        "approval_year": 2011,
        "drug_class": "small_molecule",
    },
    {
        "name": "Palbociclib",
        "primary_target": "CDK4",
        "targets": ["CDK4", "CDK6"],
        "indication": "HR+/HER2- breast cancer",
        "mechanism": "CDK4/6 inhibitor",
        "approval_year": 2015,
        "drug_class": "small_molecule",
    },
    {
        "name": "Ribociclib",
        "primary_target": "CDK4",
        "targets": ["CDK4", "CDK6"],
        "indication": "HR+/HER2- breast cancer",
        "mechanism": "CDK4/6 inhibitor",
        "approval_year": 2017,
        "drug_class": "small_molecule",
    },
    {
        "name": "Venetoclax",
        "primary_target": "BCL2",
        "targets": ["BCL2"],
        "indication": "CLL, AML",
        "mechanism": "BCL-2 BH3 mimetic",
        "approval_year": 2016,
        "drug_class": "small_molecule",
    },
    {
        "name": "Ibrutinib",
        "primary_target": "BTK",
        "targets": ["BTK"],
        "indication": "CLL, MCL, WM",
        "mechanism": "BTK covalent inhibitor (C481)",
        "approval_year": 2013,
        "drug_class": "small_molecule",
    },
    {
        "name": "Ruxolitinib",
        "primary_target": "JAK2",
        "targets": ["JAK1", "JAK2"],
        "indication": "Myelofibrosis, PV",
        "mechanism": "JAK1/2 inhibitor",
        "approval_year": 2011,
        "drug_class": "small_molecule",
    },
    {
        "name": "Osimertinib",
        "primary_target": "EGFR",
        "targets": ["EGFR"],
        "indication": "EGFR T790M NSCLC",
        "mechanism": "Third-gen EGFR TKI (covalent C797)",
        "approval_year": 2015,
        "drug_class": "small_molecule",
    },
    {
        "name": "Sotorasib",
        "primary_target": "KRAS",
        "targets": ["KRAS"],
        "indication": "KRAS G12C NSCLC",
        "mechanism": "KRAS G12C covalent inhibitor",
        "approval_year": 2021,
        "drug_class": "small_molecule",
    },
    {
        "name": "Adagrasib",
        "primary_target": "KRAS",
        "targets": ["KRAS"],
        "indication": "KRAS G12C NSCLC/CRC",
        "mechanism": "KRAS G12C covalent inhibitor",
        "approval_year": 2022,
        "drug_class": "small_molecule",
    },
    {
        "name": "Alpelisib",
        "primary_target": "PIK3CA",
        "targets": ["PIK3CA"],
        "indication": "HR+/HER2- PIK3CA-mutant breast cancer",
        "mechanism": "PI3K-alpha inhibitor",
        "approval_year": 2019,
        "drug_class": "small_molecule",
    },
    {
        "name": "Ivosidenib",
        "primary_target": "IDH1",
        "targets": ["IDH1"],
        "indication": "IDH1-mutant AML",
        "mechanism": "IDH1 mutant inhibitor",
        "approval_year": 2018,
        "drug_class": "small_molecule",
    },
    {
        "name": "Midostaurin",
        "primary_target": "FLT3",
        "targets": ["FLT3", "KIT", "PDGFR"],
        "indication": "FLT3-mutant AML",
        "mechanism": "Multi-kinase inhibitor",
        "approval_year": 2017,
        "drug_class": "small_molecule",
    },
    {
        "name": "Gilteritinib",
        "primary_target": "FLT3",
        "targets": ["FLT3", "AXL"],
        "indication": "Relapsed/refractory FLT3+ AML",
        "mechanism": "FLT3/AXL inhibitor",
        "approval_year": 2018,
        "drug_class": "small_molecule",
    },
    {
        "name": "Selpercatinib",
        "primary_target": "RET",
        "targets": ["RET"],
        "indication": "RET fusion+ NSCLC, thyroid",
        "mechanism": "Selective RET inhibitor",
        "approval_year": 2020,
        "drug_class": "small_molecule",
    },
    {
        "name": "Capmatinib",
        "primary_target": "MET",
        "targets": ["MET"],
        "indication": "METex14-skipping NSCLC",
        "mechanism": "Selective MET inhibitor",
        "approval_year": 2020,
        "drug_class": "small_molecule",
    },
    {
        "name": "Dabrafenib",
        "primary_target": "BRAF",
        "targets": ["BRAF"],
        "indication": "BRAF V600E/K melanoma, NSCLC, thyroid",
        "mechanism": "BRAF V600 inhibitor",
        "approval_year": 2013,
        "drug_class": "small_molecule",
    },
    {
        "name": "Abemaciclib",
        "primary_target": "CDK4",
        "targets": ["CDK4", "CDK6"],
        "indication": "HR+/HER2- breast cancer",
        "mechanism": "CDK4/6 inhibitor",
        "approval_year": 2017,
        "drug_class": "small_molecule",
    },
    {
        "name": "Zanubrutinib",
        "primary_target": "BTK",
        "targets": ["BTK"],
        "indication": "MCL, CLL, WM",
        "mechanism": "Next-gen BTK covalent inhibitor",
        "approval_year": 2019,
        "drug_class": "small_molecule",
    },
    {
        "name": "Acalabrutinib",
        "primary_target": "BTK",
        "targets": ["BTK"],
        "indication": "CLL, MCL",
        "mechanism": "Second-gen BTK covalent inhibitor",
        "approval_year": 2017,
        "drug_class": "small_molecule",
    },
    {
        "name": "Erdafitinib",
        "primary_target": "FGFR",
        "targets": ["FGFR1", "FGFR2", "FGFR3", "FGFR4"],
        "indication": "FGFR-altered bladder cancer",
        "mechanism": "Pan-FGFR inhibitor",
        "approval_year": 2019,
        "drug_class": "small_molecule",
    },
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BindingSite:
    site_id: str
    gene: str
    residues: list[int]
    center_coords: tuple[float, float, float]
    volume: float  # Angstrom^3
    druggability_score: float  # 0-1
    pocket_type: str  # "orthosteric" | "allosteric" | "covalent" | "cryptic"
    description: str


@dataclass
class CompoundHit:
    compound_name: str
    target_gene: str
    docking_score: float  # kcal/mol, more negative = better
    binding_affinity_ki: float  # nM
    selectivity_index: float
    passes_lipinski: bool
    library: str
    mechanism: str


@dataclass
class CovalentHit:
    compound_name: str
    target_gene: str
    reactive_residue: str  # e.g. "C797"
    warhead_type: str  # e.g. "acrylamide", "vinyl_sulfone"
    irreversibility: str  # "irreversible" | "reversible_covalent"
    target_engagement_ic50: float  # nM
    selectivity_panel: dict[str, float]


@dataclass
class RepurposingCandidate:
    drug_name: str
    original_indication: str
    repurposing_target: str
    rationale: str
    target_similarity_score: float  # 0-1
    evidence_level: str  # "preclinical" | "phase1" | "phase2" | "approved"
    related_targets: list[str]


@dataclass
class AllostericSite:
    site_id: str
    gene: str
    residues: list[int]
    site_type: str  # "allosteric_activator" | "allosteric_inhibitor" | "conformational"
    regulatory_mechanism: str
    druggability_score: float
    known_ligands: list[str]


# ---------------------------------------------------------------------------
# Binding site prediction
# ---------------------------------------------------------------------------

_BINDING_SITES: dict[str, list[BindingSite]] = {
    "EGFR": [
        BindingSite(
            site_id="EGFR_ATP",
            gene="EGFR",
            residues=[718, 719, 745, 766, 790, 858],
            center_coords=(22.4, -8.1, 14.7),
            volume=842.0,
            druggability_score=0.95,
            pocket_type="orthosteric",
            description="ATP-binding cleft of the EGFR kinase domain",
        ),
        BindingSite(
            site_id="EGFR_C797",
            gene="EGFR",
            residues=[797, 800, 801],
            center_coords=(20.1, -6.4, 12.9),
            volume=310.0,
            druggability_score=0.87,
            pocket_type="covalent",
            description="C797 covalent warhead site for third-gen inhibitors",
        ),
    ],
    "BRAF": [
        BindingSite(
            site_id="BRAF_ATP",
            gene="BRAF",
            residues=[464, 529, 530, 594, 596, 600],
            center_coords=(3.5, 12.2, -4.8),
            volume=920.0,
            druggability_score=0.93,
            pocket_type="orthosteric",
            description="ATP-binding site; V600E creates an extended hydrophobic pocket",
        ),
    ],
    "ABL1": [
        BindingSite(
            site_id="ABL1_ATP",
            gene="ABL1",
            residues=[253, 255, 315, 317, 381],
            center_coords=(8.7, 2.3, -11.4),
            volume=780.0,
            druggability_score=0.97,
            pocket_type="orthosteric",
            description="ATP-binding cleft targeted by Imatinib/Dasatinib",
        ),
        BindingSite(
            site_id="ABL1_DFG",
            gene="ABL1",
            residues=[381, 382, 383, 386],
            center_coords=(9.1, 3.0, -10.2),
            volume=450.0,
            druggability_score=0.88,
            pocket_type="allosteric",
            description="DFG-out inactive conformation pocket",
        ),
    ],
    "HER2": [
        BindingSite(
            site_id="HER2_ATP",
            gene="HER2",
            residues=[726, 728, 745, 766, 878],
            center_coords=(15.3, -4.7, 8.2),
            volume=870.0,
            druggability_score=0.91,
            pocket_type="orthosteric",
            description="Kinase domain ATP-binding pocket",
        ),
    ],
    "VEGFR": [
        BindingSite(
            site_id="VEGFR_ATP",
            gene="VEGFR",
            residues=[815, 816, 861, 882, 916],
            center_coords=(5.9, 18.4, -7.6),
            volume=760.0,
            druggability_score=0.89,
            pocket_type="orthosteric",
            description="VEGFR2 kinase ATP pocket; highly flexible hinge region",
        ),
    ],
    "ALK": [
        BindingSite(
            site_id="ALK_ATP",
            gene="ALK",
            residues=[1122, 1123, 1151, 1174, 1196],
            center_coords=(-2.4, 7.8, 19.3),
            volume=810.0,
            druggability_score=0.92,
            pocket_type="orthosteric",
            description="ALK kinase domain ATP-binding site",
        ),
    ],
    "KRAS": [
        BindingSite(
            site_id="KRAS_GDP",
            gene="KRAS",
            residues=[10, 11, 12, 13, 15, 16, 57, 59, 116],
            center_coords=(-1.2, 4.5, -3.8),
            volume=520.0,
            druggability_score=0.62,
            pocket_type="orthosteric",
            description="GDP/GTP nucleotide-binding site; historically undruggable",
        ),
        BindingSite(
            site_id="KRAS_G12C_switch2",
            gene="KRAS",
            residues=[12, 61, 95, 96, 99],
            center_coords=(0.8, 6.1, -2.3),
            volume=380.0,
            druggability_score=0.78,
            pocket_type="covalent",
            description="Switch II pocket exposed in G12C mutant; targeted by Sotorasib",
        ),
    ],
    "TP53": [
        BindingSite(
            site_id="TP53_DNA",
            gene="TP53",
            residues=[175, 245, 248, 249, 273, 282],
            center_coords=(12.0, -14.3, 2.1),
            volume=650.0,
            druggability_score=0.42,
            pocket_type="orthosteric",
            description="DNA-binding domain; mutations destabilize fold",
        ),
    ],
    "PIK3CA": [
        BindingSite(
            site_id="PIK3CA_ATP",
            gene="PIK3CA",
            residues=[800, 836, 859, 911, 1047],
            center_coords=(24.7, 6.2, -8.9),
            volume=890.0,
            druggability_score=0.86,
            pocket_type="orthosteric",
            description="PI3K catalytic domain ATP/lipid substrate pocket",
        ),
    ],
    "PTEN": [
        BindingSite(
            site_id="PTEN_PHOSPHATASE",
            gene="PTEN",
            residues=[92, 130, 131, 173, 174],
            center_coords=(-5.3, 9.8, 1.4),
            volume=420.0,
            druggability_score=0.38,
            pocket_type="orthosteric",
            description="Phosphatase active site; C2 domain interface",
        ),
    ],
    "CDK4": [
        BindingSite(
            site_id="CDK4_ATP",
            gene="CDK4",
            residues=[13, 14, 89, 95, 145, 160],
            center_coords=(7.4, -3.6, 12.8),
            volume=740.0,
            druggability_score=0.91,
            pocket_type="orthosteric",
            description="CDK4 ATP-binding cleft; cyclin D-dependent activation",
        ),
    ],
    "MET": [
        BindingSite(
            site_id="MET_ATP",
            gene="MET",
            residues=[1158, 1165, 1199, 1222, 1230, 1253],
            center_coords=(18.2, 1.7, -15.4),
            volume=800.0,
            druggability_score=0.88,
            pocket_type="orthosteric",
            description="MET kinase domain ATP site; Y1253 gatekeeper",
        ),
    ],
    "RET": [
        BindingSite(
            site_id="RET_ATP",
            gene="RET",
            residues=[730, 732, 770, 804, 918],
            center_coords=(4.1, 22.6, -9.3),
            volume=770.0,
            druggability_score=0.90,
            pocket_type="orthosteric",
            description="RET kinase ATP-binding pocket",
        ),
    ],
    "FLT3": [
        BindingSite(
            site_id="FLT3_ATP",
            gene="FLT3",
            residues=[591, 636, 680, 691, 835],
            center_coords=(-8.6, 5.4, 17.2),
            volume=790.0,
            druggability_score=0.90,
            pocket_type="orthosteric",
            description="FLT3 kinase ATP site; JM-domain mutations cause activation",
        ),
    ],
    "JAK2": [
        BindingSite(
            site_id="JAK2_ATP",
            gene="JAK2",
            residues=[617, 617, 867, 932, 934],
            center_coords=(11.5, -7.2, 3.6),
            volume=810.0,
            druggability_score=0.89,
            pocket_type="orthosteric",
            description="JAK2 JH1 kinase domain ATP binding site",
        ),
    ],
    "BTK": [
        BindingSite(
            site_id="BTK_ATP",
            gene="BTK",
            residues=[408, 430, 481, 483, 484],
            center_coords=(2.8, -12.4, 7.9),
            volume=730.0,
            druggability_score=0.94,
            pocket_type="covalent",
            description="BTK ATP site with C481 covalent hot spot for Ibrutinib",
        ),
    ],
    "BCL2": [
        BindingSite(
            site_id="BCL2_BH3",
            gene="BCL2",
            residues=[101, 104, 108, 111, 146, 150],
            center_coords=(-14.3, 3.9, -6.1),
            volume=560.0,
            druggability_score=0.82,
            pocket_type="orthosteric",
            description="BH3-binding hydrophobic groove targeted by Venetoclax",
        ),
    ],
    "IDH1": [
        BindingSite(
            site_id="IDH1_ACTIVE",
            gene="IDH1",
            residues=[100, 119, 130, 132, 270, 271],
            center_coords=(6.5, -9.1, 4.4),
            volume=640.0,
            druggability_score=0.80,
            pocket_type="orthosteric",
            description="IDH1 active site isocitrate pocket; R132 mutation creates neomorphic activity",
        ),
        BindingSite(
            site_id="IDH1_ALLOSTERIC",
            gene="IDH1",
            residues=[130, 200, 201, 212],
            center_coords=(8.2, -7.4, 5.8),
            volume=320.0,
            druggability_score=0.74,
            pocket_type="allosteric",
            description="Allosteric dimer interface site in mutant IDH1",
        ),
    ],
    "FGFR": [
        BindingSite(
            site_id="FGFR_ATP",
            gene="FGFR",
            residues=[471, 492, 563, 563, 628, 653],
            center_coords=(9.4, 16.7, -11.2),
            volume=850.0,
            druggability_score=0.88,
            pocket_type="orthosteric",
            description="FGFR kinase domain ATP cleft; gatekeeper V561 in FGFR1",
        ),
    ],
    "MDM2": [
        BindingSite(
            site_id="MDM2_P53",
            gene="MDM2",
            residues=[50, 54, 58, 62, 67, 72, 94],
            center_coords=(-7.8, 1.3, 9.7),
            volume=490.0,
            druggability_score=0.76,
            pocket_type="orthosteric",
            description="MDM2 p53-binding cleft; deep hydrophobic pocket (F19/W23/L26 triad)",
        ),
    ],
}


def predict_binding_sites(gene: str) -> list[BindingSite]:
    """Return predicted binding sites for a target gene.

    Uses a curated table of known oncology drug target binding sites.
    Returns an empty list for genes not in the knowledge base.
    """
    return list(_BINDING_SITES.get(gene.upper(), []))


# ---------------------------------------------------------------------------
# Virtual screening
# ---------------------------------------------------------------------------


def screen_compound_library(
    target_gene: str,
    library: str = "approved_drugs",
) -> list[CompoundHit]:
    """Virtual screen a compound library against a target gene.

    Returns mock docking hits with estimated binding affinities.
    Hits are only returned for compounds whose target list includes target_gene.
    """
    gene = target_gene.upper()
    hits: list[CompoundHit] = []

    # Score mapping: primary target hits harder
    _docking_base: dict[str, float] = {
        "EGFR": -9.2,
        "BRAF": -9.5,
        "ABL1": -10.1,
        "HER2": -8.7,
        "VEGFR": -8.9,
        "ALK": -9.4,
        "KRAS": -7.8,
        "TP53": -6.1,
        "PIK3CA": -8.5,
        "PTEN": -5.9,
        "CDK4": -9.0,
        "MET": -8.8,
        "RET": -9.3,
        "FLT3": -9.1,
        "JAK2": -8.6,
        "BTK": -9.7,
        "BCL2": -8.4,
        "IDH1": -8.2,
        "FGFR": -8.9,
        "MDM2": -7.6,
    }
    base_score = _docking_base.get(gene, -7.0)

    for drug in APPROVED_DRUG_LIBRARY:
        drug_targets_upper = [t.upper() for t in drug["targets"]]
        if gene not in drug_targets_upper:
            continue
        is_primary = drug["primary_target"].upper() == gene
        score_adj = 0.0 if is_primary else 1.2  # off-targets score worse
        ki = (10 ** ((base_score + score_adj + 1.4) / -1.36)) * 1e9  # rough Ki nM
        hits.append(
            CompoundHit(
                compound_name=drug["name"],
                target_gene=gene,
                docking_score=round(base_score - score_adj, 2),
                binding_affinity_ki=round(max(ki, 0.1), 2),
                selectivity_index=round(4.5 if is_primary else 1.8, 1),
                passes_lipinski=drug["drug_class"] == "small_molecule",
                library=library,
                mechanism=drug["mechanism"],
            )
        )

    # Sort by docking score (most negative first)
    hits.sort(key=lambda h: h.docking_score)
    return hits


# ---------------------------------------------------------------------------
# Covalent screening
# ---------------------------------------------------------------------------

# Known covalent inhibitor data: (gene, residue) -> drug info
_COVALENT_COMPOUNDS: dict[tuple[str, str], dict] = {
    ("EGFR", "C797"): {
        "compound_name": "Osimertinib",
        "warhead_type": "acrylamide",
        "irreversibility": "irreversible",
        "target_engagement_ic50": 0.18,
        "selectivity_panel": {"EGFR_T790M": 0.18, "EGFR_WT": 184.0, "HER2": 67.0},
    },
    ("EGFR", "C805"): {
        "compound_name": "Afatinib",
        "warhead_type": "acrylamide",
        "irreversibility": "irreversible",
        "target_engagement_ic50": 0.5,
        "selectivity_panel": {"EGFR": 0.5, "HER2": 14.0, "ERBB4": 1.0},
    },
    ("KRAS", "C12"): {
        "compound_name": "Sotorasib",
        "warhead_type": "acrylamide",
        "irreversibility": "irreversible",
        "target_engagement_ic50": 0.09,
        "selectivity_panel": {"KRAS_G12C": 0.09, "KRAS_WT": ">10000"},
    },
    ("KRAS", "C12_adagrasib"): {
        "compound_name": "Adagrasib",
        "warhead_type": "acrylamide",
        "irreversibility": "irreversible",
        "target_engagement_ic50": 0.14,
        "selectivity_panel": {"KRAS_G12C": 0.14, "KRAS_WT": ">10000"},
    },
    ("BTK", "C481"): {
        "compound_name": "Ibrutinib",
        "warhead_type": "acrylamide",
        "irreversibility": "irreversible",
        "target_engagement_ic50": 0.5,
        "selectivity_panel": {"BTK": 0.5, "ITK": 10.8, "TEC": 7.6},
    },
    ("BTK", "C481_acala"): {
        "compound_name": "Acalabrutinib",
        "warhead_type": "acrylamide",
        "irreversibility": "irreversible",
        "target_engagement_ic50": 3.0,
        "selectivity_panel": {"BTK": 3.0, "ITK": ">1000", "TEC": 845.0},
    },
    ("BTK", "C481_zanu"): {
        "compound_name": "Zanubrutinib",
        "warhead_type": "acrylamide",
        "irreversibility": "irreversible",
        "target_engagement_ic50": 0.52,
        "selectivity_panel": {"BTK": 0.52, "ITK": ">1000"},
    },
}


def screen_covalent_candidates(
    target_gene: str,
    reactive_cysteines: list[str],
) -> list[CovalentHit]:
    """Screen for covalent inhibitor candidates against specified reactive cysteines.

    reactive_cysteines: list of residue strings, e.g. ["C797", "C805"]
    Returns known covalent compounds for (gene, cysteine) pairs found in the
    knowledge base. Also includes generic warhead scaffolds for unlisted cysteines.
    """
    gene = target_gene.upper()
    hits: list[CovalentHit] = []
    seen_compounds: set[str] = set()

    for cys in reactive_cysteines:
        cys_upper = cys.upper()
        # Try exact match first
        for (kg, kc), data in _COVALENT_COMPOUNDS.items():
            if kg != gene:
                continue
            # Match residue prefix (C797 matches C797 and C797_*)
            if not (kc.upper() == cys_upper or kc.upper().startswith(cys_upper + "_")):
                continue
            cname = data["compound_name"]
            if cname in seen_compounds:
                continue
            seen_compounds.add(cname)

            selectivity = {
                k: (v if isinstance(v, float) else 9999.0)
                for k, v in data["selectivity_panel"].items()
            }
            hits.append(
                CovalentHit(
                    compound_name=cname,
                    target_gene=gene,
                    reactive_residue=cys,
                    warhead_type=data["warhead_type"],
                    irreversibility=data["irreversibility"],
                    target_engagement_ic50=data["target_engagement_ic50"],
                    selectivity_panel=selectivity,
                )
            )

    return hits


# ---------------------------------------------------------------------------
# Drug repurposing
# ---------------------------------------------------------------------------

# Target similarity graph: which targets share mechanisms / structural homology
_TARGET_SIMILARITY: dict[str, list[tuple[str, float, str]]] = {
    "EGFR": [
        ("HER2", 0.78, "ErbB family kinase domain homology"),
        ("ALK", 0.55, "RTK class III shared structural features"),
        ("MET", 0.52, "RTK activation loop conservation"),
    ],
    "BRAF": [
        ("VEGFR", 0.60, "RAF/VEGFR shared DFG-out pocket"),
        ("ABL1", 0.55, "Type II inhibitor binding mode"),
    ],
    "ABL1": [
        ("BRAF", 0.55, "Type II inhibitor binding mode"),
        ("KIT", 0.72, "PDGFR-family conserved pocket"),
        ("FLT3", 0.68, "RTK type III class homology"),
    ],
    "HER2": [
        ("EGFR", 0.78, "ErbB family"),
        ("FGFR", 0.51, "RTK extracellular domain features"),
    ],
    "ALK": [
        ("EGFR", 0.55, "Shared gatekeeper residue architecture"),
        ("MET", 0.65, "ALK/MET co-target profile (Crizotinib)"),
        ("RET", 0.58, "RTK activation loop similarity"),
    ],
    "KRAS": [
        ("TP53", 0.40, "Tumor suppressor pathway interaction"),
        ("PIK3CA", 0.45, "RAS-PI3K signaling axis"),
    ],
    "CDK4": [
        ("CDK6", 0.95, "Highly homologous CDK family"),
        ("CDK2", 0.70, "CDK family ATP-site conservation"),
    ],
    "BTK": [
        ("ITK", 0.75, "TEC kinase family C481 homolog"),
        ("JAK2", 0.50, "Covalent-binding NHEJ overlap"),
    ],
    "BCL2": [
        ("BCL-XL", 0.82, "BCL-2 family BH3 groove"),
        ("MCL1", 0.65, "Anti-apoptotic BH3 mimetic overlap"),
    ],
    "IDH1": [
        ("IDH2", 0.73, "IDH isozyme family"),
    ],
    "FLT3": [
        ("ABL1", 0.68, "Type III RTK homology"),
        ("KIT", 0.72, "Co-targeted by multi-kinase inhibitors"),
    ],
    "JAK2": [
        ("JAK1", 0.80, "JAK family pseudokinase domain"),
        ("BTK", 0.50, "Cross-kinome off-target observed"),
    ],
    "MET": [
        ("ALK", 0.65, "ALK/MET co-target (Crizotinib)"),
        ("RET", 0.55, "RTK gatekeeper residue homology"),
    ],
    "RET": [
        ("ALK", 0.58, "RTK activation loop similarity"),
        ("MET", 0.55, "RTK gatekeeper residue homology"),
        ("FGFR", 0.52, "RTK extracellular domain features"),
    ],
    "MDM2": [
        ("MDMX", 0.70, "MDM2/MDMX p53-binding groove similarity"),
        ("BCL2", 0.30, "Shared hydrophobic cleft drugging strategy"),
    ],
}

# Drug → original target for repurposing cross-reference
_DRUG_TARGET_MAP: dict[str, str] = {d["name"]: d["primary_target"] for d in APPROVED_DRUG_LIBRARY}


def find_repurposing_candidates(target_gene: str) -> list[RepurposingCandidate]:
    """Find drug repurposing candidates for a target gene.

    Cross-references the approved drug library against known target similarity
    to identify drugs approved for related targets that may show activity.
    """
    gene = target_gene.upper()
    candidates: list[RepurposingCandidate] = []

    similar_targets = _TARGET_SIMILARITY.get(gene, [])
    for sim_target, similarity, rationale in similar_targets:
        sim_upper = sim_target.upper()
        for drug in APPROVED_DRUG_LIBRARY:
            drug_targets_upper = [t.upper() for t in drug["targets"]]
            if sim_upper not in drug_targets_upper:
                continue
            evidence = "approved" if drug["primary_target"].upper() == sim_upper else "preclinical"
            candidates.append(
                RepurposingCandidate(
                    drug_name=drug["name"],
                    original_indication=drug["indication"],
                    repurposing_target=gene,
                    rationale=f"{rationale} (similarity to {sim_target})",
                    target_similarity_score=similarity,
                    evidence_level=evidence,
                    related_targets=[sim_target],
                )
            )

    # Deduplicate by drug name, keep highest similarity
    seen: dict[str, RepurposingCandidate] = {}
    for c in candidates:
        if (
            c.drug_name not in seen
            or c.target_similarity_score > seen[c.drug_name].target_similarity_score
        ):
            seen[c.drug_name] = c

    result = sorted(seen.values(), key=lambda c: -c.target_similarity_score)
    return result


# ---------------------------------------------------------------------------
# Allosteric sites
# ---------------------------------------------------------------------------

_ALLOSTERIC_SITES: dict[str, list[AllostericSite]] = {
    "EGFR": [
        AllostericSite(
            site_id="EGFR_ALLOSTERIC_DIMER",
            gene="EGFR",
            residues=[973, 974, 976, 977, 979],
            site_type="allosteric_activator",
            regulatory_mechanism="Asymmetric kinase domain dimerization activator lobe",
            druggability_score=0.65,
            known_ligands=["EAI045"],
        ),
    ],
    "ABL1": [
        AllostericSite(
            site_id="ABL1_MYRISTOYL",
            gene="ABL1",
            residues=[69, 70, 72, 75, 78, 81],
            site_type="allosteric_inhibitor",
            regulatory_mechanism="N-terminal myristoyl cap clamps kinase in inactive state",
            druggability_score=0.72,
            known_ligands=["GNF-2", "GNF-5", "Asciminib"],
        ),
    ],
    "KRAS": [
        AllostericSite(
            site_id="KRAS_SWITCH_I",
            gene="KRAS",
            residues=[25, 26, 27, 28, 32, 35],
            site_type="conformational",
            regulatory_mechanism="Switch I effector-binding surface",
            druggability_score=0.45,
            known_ligands=["BI-2852"],
        ),
        AllostericSite(
            site_id="KRAS_SWITCH_II",
            gene="KRAS",
            residues=[58, 59, 60, 61, 92, 95, 96],
            site_type="allosteric_inhibitor",
            regulatory_mechanism="Switch II pocket (SII-P) accessible in GDP-bound state",
            druggability_score=0.68,
            known_ligands=["AMG-510 analog", "MRTX849 analog"],
        ),
    ],
    "BRAF": [
        AllostericSite(
            site_id="BRAF_DIMER_FACE",
            gene="BRAF",
            residues=[504, 508, 509, 514, 547, 549],
            site_type="allosteric_inhibitor",
            regulatory_mechanism="BRAF kinase dimer interface; paradoxical activation mechanism",
            druggability_score=0.58,
            known_ligands=["PLX8394"],
        ),
    ],
    "MDM2": [
        AllostericSite(
            site_id="MDM2_LID",
            gene="MDM2",
            residues=[17, 18, 19, 22, 26, 289],
            site_type="allosteric_inhibitor",
            regulatory_mechanism="N-terminal lid region modulates p53-binding cleft accessibility",
            druggability_score=0.52,
            known_ligands=["stapled peptides"],
        ),
    ],
    "BCL2": [
        AllostericSite(
            site_id="BCL2_P2",
            gene="BCL2",
            residues=[67, 68, 72, 104, 108],
            site_type="allosteric_inhibitor",
            regulatory_mechanism="Secondary binding site; modulates BH3-groove dynamics",
            druggability_score=0.55,
            known_ligands=["WEHI-539 analog"],
        ),
    ],
    "IDH1": [
        AllostericSite(
            site_id="IDH1_DIMER_INTERFACE",
            gene="IDH1",
            residues=[130, 150, 200, 201, 212, 219],
            site_type="allosteric_inhibitor",
            regulatory_mechanism="Homodimer interface; mutant R132H creates neomorphic allosteric pocket",
            druggability_score=0.74,
            known_ligands=["Ivosidenib", "Olutasidenib", "AG-881"],
        ),
    ],
    "PIK3CA": [
        AllostericSite(
            site_id="PIK3CA_ABD",
            gene="PIK3CA",
            residues=[144, 155, 206, 207, 214],
            site_type="allosteric_activator",
            regulatory_mechanism="Adapter-binding domain; RAS-interaction surface",
            druggability_score=0.48,
            known_ligands=["experimental compounds"],
        ),
    ],
    "TP53": [
        AllostericSite(
            site_id="TP53_Y220C_CAVITY",
            gene="TP53",
            residues=[220, 221, 224, 225, 313, 314],
            site_type="conformational",
            regulatory_mechanism="Y220C mutant creates extended cavity allowing small-molecule rescue",
            druggability_score=0.63,
            known_ligands=["PC14586", "APR-246 (PRIMA-1Met)"],
        ),
    ],
}


def predict_allosteric_sites(gene: str) -> list[AllostericSite]:
    """Return predicted allosteric sites for a target gene.

    Returns from a curated table of known oncology target allosteric sites.
    Returns an empty list for genes not in the knowledge base.
    """
    return list(_ALLOSTERIC_SITES.get(gene.upper(), []))


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_drug_discovery_report(
    case_id: str,
    target_genes: list[str],
    db,
) -> dict:
    """Aggregate a full drug discovery report for a case.

    Combines binding site prediction, virtual screening, covalent screening,
    repurposing candidates, and allosteric sites for each target gene.
    Returns a structured report dict.
    """
    from backend.app.models import Case  # late import to avoid circular

    case = db.query(Case).filter(Case.id == case_id).first()
    if case is None:
        return {"error": "case_not_found", "case_id": case_id}

    per_target: list[dict] = []
    total_binding_sites = 0
    total_screen_hits = 0
    total_covalent_hits = 0
    total_repurposing = 0
    total_allosteric = 0

    for gene in target_genes:
        gene_upper = gene.upper()
        target_info = KNOWN_DRUG_TARGETS.get(gene_upper, {})

        binding_sites = predict_binding_sites(gene_upper)
        screen_hits = screen_compound_library(gene_upper)
        cov_hits = screen_covalent_candidates(
            gene_upper,
            _get_reactive_cysteines_for_gene(gene_upper),
        )
        repurposing = find_repurposing_candidates(gene_upper)
        allosteric = predict_allosteric_sites(gene_upper)

        total_binding_sites += len(binding_sites)
        total_screen_hits += len(screen_hits)
        total_covalent_hits += len(cov_hits)
        total_repurposing += len(repurposing)
        total_allosteric += len(allosteric)

        per_target.append(
            {
                "gene": gene_upper,
                "target_info": target_info,
                "binding_sites": [
                    {
                        "site_id": s.site_id,
                        "residues": s.residues,
                        "center_coords": s.center_coords,
                        "volume": s.volume,
                        "druggability_score": s.druggability_score,
                        "pocket_type": s.pocket_type,
                        "description": s.description,
                    }
                    for s in binding_sites
                ],
                "virtual_screen_hits": [
                    {
                        "compound_name": h.compound_name,
                        "docking_score": h.docking_score,
                        "binding_affinity_ki_nM": h.binding_affinity_ki,
                        "selectivity_index": h.selectivity_index,
                        "passes_lipinski": h.passes_lipinski,
                        "mechanism": h.mechanism,
                    }
                    for h in screen_hits
                ],
                "covalent_hits": [
                    {
                        "compound_name": h.compound_name,
                        "reactive_residue": h.reactive_residue,
                        "warhead_type": h.warhead_type,
                        "irreversibility": h.irreversibility,
                        "target_engagement_ic50_nM": h.target_engagement_ic50,
                        "selectivity_panel": h.selectivity_panel,
                    }
                    for h in cov_hits
                ],
                "repurposing_candidates": [
                    {
                        "drug_name": r.drug_name,
                        "original_indication": r.original_indication,
                        "rationale": r.rationale,
                        "target_similarity_score": r.target_similarity_score,
                        "evidence_level": r.evidence_level,
                        "related_targets": r.related_targets,
                    }
                    for r in repurposing
                ],
                "allosteric_sites": [
                    {
                        "site_id": a.site_id,
                        "residues": a.residues,
                        "site_type": a.site_type,
                        "regulatory_mechanism": a.regulatory_mechanism,
                        "druggability_score": a.druggability_score,
                        "known_ligands": a.known_ligands,
                    }
                    for a in allosteric
                ],
            }
        )

    return {
        "case_id": case_id,
        "target_genes": target_genes,
        "summary": {
            "total_targets_analyzed": len(target_genes),
            "total_binding_sites": total_binding_sites,
            "total_screen_hits": total_screen_hits,
            "total_covalent_hits": total_covalent_hits,
            "total_repurposing_candidates": total_repurposing,
            "total_allosteric_sites": total_allosteric,
        },
        "targets": per_target,
        "safety_label": "Research candidate only — not administerable",
    }


def _get_reactive_cysteines_for_gene(gene: str) -> list[str]:
    """Return known reactive cysteines for well-characterized covalent targets."""
    _GENE_CYSTEINES: dict[str, list[str]] = {
        "EGFR": ["C797", "C805"],
        "KRAS": ["C12"],
        "BTK": ["C481"],
    }
    return _GENE_CYSTEINES.get(gene, [])


# ---------------------------------------------------------------------------
# AF3 Protein–Small Molecule Co-folding  (Phase 23)
# RESEARCH ONLY — stub implementation using hash-based deterministic mock scores
# ---------------------------------------------------------------------------

import hashlib  # noqa: E402 (stdlib, already available)


@dataclass
class CoFoldingResult:
    """Result of AlphaFold 3 protein–ligand co-folding prediction.

    AF3 can jointly predict protein and small-molecule poses, enabling
    structure-based drug design without a pre-existing apo structure.
    """

    target_gene: str
    ligand_smiles: str
    predicted_binding_pose: str  # PDB-format coordinate block
    binding_energy_kcal: float  # negative = favorable; range −3 to −12
    contact_residues: list[int]
    confidence: float  # 0–1 (iPTM-like score)


def predict_cofold(target_gene: str, ligand_smiles: str) -> CoFoldingResult:
    """Predict protein–ligand binding pose via AF3 co-folding (deterministic stub).

    Uses a hash of (target_gene, ligand_smiles) to produce reproducible mock
    scores in a biologically plausible range.  Real integration would call the
    AF3 inference pipeline with the ligand CCD dictionary.

    RESEARCH ONLY — not for clinical or therapeutic decision-making.
    """
    gene_upper = target_gene.upper()
    key = f"{gene_upper}:{ligand_smiles}"
    h = int(hashlib.sha256(key.encode()).hexdigest(), 16)

    # Binding energy: −3 to −12 kcal/mol
    frac = (h & 0xFFFF) / 0xFFFF  # 0.0–1.0
    binding_energy = -(3.0 + frac * 9.0)

    # Confidence: higher for known targets
    known = gene_upper in KNOWN_DRUG_TARGETS
    conf_base = 0.65 if known else 0.35
    confidence = round(conf_base + ((h >> 16) & 0xFF) / 0xFF * 0.30, 3)

    # Contact residues: deterministic set of 4–8 residue numbers
    n_contacts = 4 + (h & 0x3)
    contact_residues = sorted({((h >> (i * 8)) & 0xFF) % 350 + 1 for i in range(n_contacts + 4)})[
        :n_contacts
    ]

    # Mock PDB coordinate block
    pdb_snippet = (
        "REMARK  AF3 Co-folding stub — RESEARCH ONLY\n"
        f"REMARK  Target: {gene_upper}  Ligand: {ligand_smiles[:40]}\n"
        "ATOM      1  CA  ALA A   1      10.000  10.000  10.000  1.00 50.00           C\n"
        "HETATM    2  C1  LIG B   1      12.500  11.200   9.800  1.00 60.00           C\n"
        "END\n"
    )

    return CoFoldingResult(
        target_gene=gene_upper,
        ligand_smiles=ligand_smiles,
        predicted_binding_pose=pdb_snippet,
        binding_energy_kcal=round(binding_energy, 3),
        contact_residues=contact_residues,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# ADMET Property Prediction  (Phase 23)
# RESEARCH ONLY — placeholder for future integration with real ADMET tools
# ---------------------------------------------------------------------------


@dataclass
class ADMETProfile:
    """ADMET (Absorption, Distribution, Metabolism, Excretion, Toxicity) profile.

    Placeholder implementation.  Future versions will integrate with tools
    such as SwissADME, pkCSM, or in-house QSAR models.

    RESEARCH ONLY — not for clinical or regulatory decision-making.
    """

    compound_name: str
    absorption: float  # 0–1 (fraction absorbed)
    distribution_vd: float  # L/kg (volume of distribution)
    metabolism_cyp_risk: str  # "low" | "medium" | "high"
    excretion_half_life_hours: float
    toxicity_ld50_estimate: str  # e.g. "500 mg/kg (rat, oral)"
    lipinski_violations: int  # 0–5
    drug_likeness_score: float  # 0–1


def predict_admet(compound_name: str, smiles: str) -> ADMETProfile:
    """Predict ADMET properties for a small molecule (deterministic stub).

    Uses a hash of (compound_name, smiles) for reproducible mock values.
    Applies a SMILES-length heuristic for Lipinski rule-of-five violations:
      – MW proxy: len(smiles)
      – logP proxy: count of carbon-heavy tokens
      – HBD/HBA proxy: O/N character count

    RESEARCH ONLY — not for clinical or regulatory decision-making.
    """
    key = f"{compound_name}:{smiles}"
    h = int(hashlib.sha256(key.encode()).hexdigest(), 16)

    # --- Lipinski heuristics ---
    violations = 0
    # MW proxy: SMILES > 60 chars ≈ MW > 500
    if len(smiles) > 60:
        violations += 1
    # logP proxy: >5 carbons relative to heteroatoms
    carbon_count = smiles.count("C") + smiles.count("c")
    hetero_count = smiles.count("N") + smiles.count("n") + smiles.count("O") + smiles.count("o")
    if carbon_count > 0 and hetero_count > 0 and (carbon_count / hetero_count) > 4:
        violations += 1
    # HBD proxy: NH or OH groups approximated by H-bearing N/O
    hbd = smiles.count("[NH]") + smiles.count("[OH]") + smiles.count("N") // 2
    if hbd > 5:
        violations += 1
    # HBA proxy: N + O count
    if (smiles.count("N") + smiles.count("n") + smiles.count("O") + smiles.count("o")) > 10:
        violations += 1
    violations = min(violations, 5)

    # Hash-derived continuous properties
    frac = lambda bits, shift: ((h >> shift) & ((1 << bits) - 1)) / ((1 << bits) - 1)  # noqa: E731

    absorption = round(0.3 + frac(8, 0) * 0.65, 3)
    distribution_vd = round(0.3 + frac(10, 8) * 4.7, 2)
    half_life = round(1.0 + frac(12, 18) * 47.0, 1)
    drug_likeness = round(max(0.0, 1.0 - violations * 0.18 - frac(6, 30) * 0.15), 3)

    cyp_levels = ["low", "medium", "high"]
    cyp_risk = cyp_levels[(h >> 36) % 3]

    ld50_values = [
        "50 mg/kg (rat, oral)",
        "200 mg/kg (rat, oral)",
        "500 mg/kg (rat, oral)",
        "1000 mg/kg (rat, oral)",
        "2000 mg/kg (rat, oral)",
    ]
    ld50 = ld50_values[(h >> 40) % len(ld50_values)]

    return ADMETProfile(
        compound_name=compound_name,
        absorption=absorption,
        distribution_vd=distribution_vd,
        metabolism_cyp_risk=cyp_risk,
        excretion_half_life_hours=half_life,
        toxicity_ld50_estimate=ld50,
        lipinski_violations=violations,
        drug_likeness_score=drug_likeness,
    )
