"""Enzyme Engineering Mode — Therapeutic Enzyme Design Pipeline.

Provides:
  - Enzyme-substrate modeling (AF3 stub)
  - Rational mutagenesis suggestions
  - Enzyme replacement therapy (ERT) design
  - Prodrug activation systems
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Enzyme-substrate modeling
# ---------------------------------------------------------------------------

@dataclass
class EnzymeSubstrate:
    enzyme_gene: str
    substrate_name: str
    active_site_residues: list[int]
    binding_mode: str
    kcat_estimate: float
    km_estimate_um: float


KNOWN_THERAPEUTIC_ENZYMES: dict[str, dict] = {
    "GBA": {
        "full_name": "Glucocerebrosidase (acid β-glucosidase)",
        "disease": "Gaucher disease",
        "substrate": "glucocerebroside",
        "active_site_residues": [228, 340, 368, 439, 443],
        "binding_mode": "substrate_assisted_hydrolysis",
        "kcat_estimate": 4.2,
        "km_estimate_um": 0.085,
        "ert_product": "Imiglucerase (Cerezyme)",
    },
    "GLA": {
        "full_name": "Alpha-galactosidase A",
        "disease": "Fabry disease",
        "substrate": "globotriaosylceramide",
        "active_site_residues": [170, 203, 231, 259],
        "binding_mode": "retaining_glycosidase",
        "kcat_estimate": 2.8,
        "km_estimate_um": 0.12,
        "ert_product": "Agalsidase alfa (Replagal) / Agalsidase beta (Fabrazyme)",
    },
    "GAA": {
        "full_name": "Acid alpha-glucosidase",
        "disease": "Pompe disease",
        "substrate": "glycogen",
        "active_site_residues": [401, 516, 518, 616, 674],
        "binding_mode": "retaining_alpha_glucosidase",
        "kcat_estimate": 3.5,
        "km_estimate_um": 0.22,
        "ert_product": "Alglucosidase alfa (Myozyme/Lumizyme)",
    },
    "IDUA": {
        "full_name": "Alpha-L-iduronidase",
        "disease": "Hurler syndrome (MPS I)",
        "substrate": "heparan sulfate / dermatan sulfate",
        "active_site_residues": [182, 246, 349, 513, 514],
        "binding_mode": "inverting_glycosidase",
        "kcat_estimate": 1.9,
        "km_estimate_um": 0.18,
        "ert_product": "Laronidase (Aldurazyme)",
    },
    "SMPD1": {
        "full_name": "Sphingomyelin phosphodiesterase 1 (acid sphingomyelinase)",
        "disease": "Niemann-Pick disease type A/B",
        "substrate": "sphingomyelin",
        "active_site_residues": [314, 421, 422, 461, 462],
        "binding_mode": "phosphodiesterase_hydrolysis",
        "kcat_estimate": 1.4,
        "km_estimate_um": 0.35,
        "ert_product": "Olipudase alfa (Xenpozyme)",
    },
    "GALC": {
        "full_name": "Galactocerebrosidase",
        "disease": "Krabbe disease",
        "substrate": "galactocerebroside",
        "active_site_residues": [150, 258, 300, 380, 534],
        "binding_mode": "retaining_glycosidase",
        "kcat_estimate": 2.1,
        "km_estimate_um": 0.28,
        "ert_product": "No approved ERT; gene therapy under investigation",
    },
    "HEXA": {
        "full_name": "Hexosaminidase A (alpha subunit)",
        "disease": "Tay-Sachs disease",
        "substrate": "GM2 ganglioside",
        "active_site_residues": [303, 323, 435, 524, 529],
        "binding_mode": "substrate_assisted_hydrolysis",
        "kcat_estimate": 3.3,
        "km_estimate_um": 0.19,
        "ert_product": "No approved ERT; substrate reduction therapy (Miglustat)",
    },
    "ADA": {
        "full_name": "Adenosine deaminase",
        "disease": "ADA-SCID",
        "substrate": "adenosine / deoxyadenosine",
        "active_site_residues": [14, 17, 136, 141, 295, 296],
        "binding_mode": "zinc_metalloenzyme_hydrolysis",
        "kcat_estimate": 280.0,
        "km_estimate_um": 35.0,
        "ert_product": "Pegademase (Adagen) / Elapegademase (Revcovi)",
    },
    "ARSA": {
        "full_name": "Arylsulfatase A",
        "disease": "Metachromatic leukodystrophy",
        "substrate": "cerebroside-3-sulfate",
        "active_site_residues": [72, 73, 150, 282, 303],
        "binding_mode": "formylglycine_sulfatase",
        "kcat_estimate": 0.8,
        "km_estimate_um": 0.41,
        "ert_product": "Arylsulfatase A (gene therapy; atidarsagene autotemcel)",
    },
    "NAGLU": {
        "full_name": "N-acetyl-alpha-glucosaminidase",
        "disease": "Sanfilippo syndrome B (MPS IIIB)",
        "substrate": "heparan sulfate",
        "active_site_residues": [234, 412, 532, 594],
        "binding_mode": "inverting_glycosidase",
        "kcat_estimate": 1.2,
        "km_estimate_um": 0.55,
        "ert_product": "No approved ERT; tralesinidase alfa (investigational)",
    },
}


def model_enzyme_substrate(enzyme_gene: str, substrate: str) -> EnzymeSubstrate:
    """Stub enzyme-substrate modeling (AF3 style). Returns known data or mock values."""
    g = enzyme_gene.upper()
    entry = KNOWN_THERAPEUTIC_ENZYMES.get(g)
    if entry and (not substrate or substrate.lower() == entry["substrate"].lower() or substrate == ""):
        return EnzymeSubstrate(
            enzyme_gene=g,
            substrate_name=entry["substrate"],
            active_site_residues=entry["active_site_residues"],
            binding_mode=entry["binding_mode"],
            kcat_estimate=entry["kcat_estimate"],
            km_estimate_um=entry["km_estimate_um"],
        )
    # Mock for unknown enzyme/substrate combination
    mock_kcat = 1.0 + (hash(g + substrate) % 50) / 10.0
    mock_km = 0.1 + (hash(substrate + g) % 100) / 100.0
    return EnzymeSubstrate(
        enzyme_gene=g,
        substrate_name=substrate,
        active_site_residues=[150, 250, 350],
        binding_mode="predicted_hydrolysis",
        kcat_estimate=round(mock_kcat, 3),
        km_estimate_um=round(mock_km, 3),
    )


# ---------------------------------------------------------------------------
# Rational mutagenesis
# ---------------------------------------------------------------------------

@dataclass
class MutationSuggestion:
    position: int
    original_aa: str
    suggested_aa: str
    rationale: str
    predicted_effect: str  # activity / stability / specificity / half_life / immunogenicity
    confidence: float


_MUTATION_DB: dict[str, dict[str, list[dict]]] = {
    "GBA": {
        "activity": [
            {"position": 228, "original_aa": "E", "suggested_aa": "D", "rationale": "Conservative substitution maintains nucleophile geometry while reducing steric clash with bulkier substrates", "confidence": 0.72},
            {"position": 443, "original_aa": "H", "suggested_aa": "R", "rationale": "Increased hydrogen bonding network with glucoside C6 hydroxyl improves kcat", "confidence": 0.65},
        ],
        "stability": [
            {"position": 126, "original_aa": "N", "suggested_aa": "Q", "rationale": "Removal of glycosylation site at N126 associated with misfolding; Q improves ER folding", "confidence": 0.78},
            {"position": 370, "original_aa": "L", "suggested_aa": "V", "rationale": "Reduces hydrophobic core packing stress; improves thermostability by +3°C", "confidence": 0.68},
        ],
        "immunogenicity": [
            {"position": 495, "original_aa": "R", "suggested_aa": "A", "rationale": "Ablates predicted MHC-II epitope without affecting catalytic core", "confidence": 0.61},
        ],
        "half_life": [
            {"position": 66, "original_aa": "T", "suggested_aa": "N", "rationale": "Introduces N-linked glycosylation site; glycan shields from proteolysis and extends plasma half-life", "confidence": 0.74},
        ],
        "specificity": [
            {"position": 345, "original_aa": "Y", "suggested_aa": "F", "rationale": "Removal of hydroxyl group reduces binding of structurally similar ceramide substrates", "confidence": 0.58},
        ],
    },
    "GLA": {
        "activity": [
            {"position": 203, "original_aa": "D", "suggested_aa": "E", "rationale": "Extended side chain improves transition state stabilization for galactosyl transfer", "confidence": 0.69},
            {"position": 231, "original_aa": "W", "suggested_aa": "Y", "rationale": "Hydroxyl addition enables additional hydrogen bond with C4-OH of substrate", "confidence": 0.63},
        ],
        "stability": [
            {"position": 85, "original_aa": "C", "suggested_aa": "S", "rationale": "Removal of unpaired cysteine at C85 prevents misfolding disulfide under oxidative conditions", "confidence": 0.81},
        ],
        "immunogenicity": [
            {"position": 340, "original_aa": "K", "suggested_aa": "R", "rationale": "Conservative substitution reduces predicted T-cell epitope affinity", "confidence": 0.59},
        ],
        "half_life": [
            {"position": 108, "original_aa": "S", "suggested_aa": "N", "rationale": "New N-linked glycan reduces renal clearance; extends t½ by estimated 2-fold", "confidence": 0.77},
        ],
        "specificity": [
            {"position": 259, "original_aa": "R", "suggested_aa": "K", "rationale": "Reduces activity against secondary substrate globotriaosylsphingosine (lyso-Gb3)", "confidence": 0.54},
        ],
    },
    "ADA": {
        "activity": [
            {"position": 295, "original_aa": "H", "suggested_aa": "Q", "rationale": "Repositions zinc coordination geometry to improve deoxyadenosine turnover", "confidence": 0.64},
        ],
        "stability": [
            {"position": 182, "original_aa": "S", "suggested_aa": "A", "rationale": "Eliminates phosphorylation site that reduces enzyme stability in vivo", "confidence": 0.70},
        ],
        "immunogenicity": [
            {"position": 75, "original_aa": "T", "suggested_aa": "A", "rationale": "Ablates MHC-II epitope hotspot; reduces anti-drug antibody formation risk", "confidence": 0.67},
        ],
        "half_life": [
            {"position": 201, "original_aa": "K", "suggested_aa": "N", "rationale": "New glycosylation site reduces urinary clearance", "confidence": 0.71},
        ],
        "specificity": [
            {"position": 14, "original_aa": "D", "suggested_aa": "N", "rationale": "Shifts substrate preference toward 2'-deoxyadenosine over adenosine", "confidence": 0.55},
        ],
    },
}


def suggest_mutations(
    enzyme_gene: str, objective: str = "activity"
) -> list[MutationSuggestion]:
    """Suggest mutations for a given enzyme and optimization objective."""
    g = enzyme_gene.upper()
    valid_objectives = {"activity", "stability", "specificity", "half_life", "immunogenicity"}
    obj = objective.lower() if objective.lower() in valid_objectives else "activity"
    enzyme_data = _MUTATION_DB.get(g, {})
    entries = enzyme_data.get(obj, [])
    return [
        MutationSuggestion(
            position=e["position"],
            original_aa=e["original_aa"],
            suggested_aa=e["suggested_aa"],
            rationale=e["rationale"],
            predicted_effect=obj,
            confidence=e["confidence"],
        )
        for e in entries
    ]


# ---------------------------------------------------------------------------
# ERT design helper
# ---------------------------------------------------------------------------

@dataclass
class ERTDesign:
    enzyme_gene: str
    disease: str
    wild_type_issues: list[str]
    suggested_modifications: list[str]
    glycosylation_sites: list[int]
    half_life_improvement: str


_ERT_DB: dict[str, dict] = {
    "GBA": {
        "disease": "Gaucher disease",
        "wild_type_issues": [
            "Short plasma half-life (~4 min)",
            "Poor macrophage uptake without M6P targeting",
            "Immunogenic without CHO glycoengineering",
        ],
        "suggested_modifications": [
            "Remodel N-glycans to expose mannose residues for mannose receptor-mediated macrophage uptake",
            "PEGylation of surface lysines to extend half-life",
            "Codon-optimize for CHO expression",
            "Remove O-GalNAc sites that trigger immune recognition",
        ],
        "glycosylation_sites": [19, 59, 146, 233, 328, 368],
        "half_life_improvement": "From ~4 min (wt) to ~10 min post glycoengineering (Cerezyme); PEG further extends to ~60 min",
    },
    "GLA": {
        "disease": "Fabry disease",
        "wild_type_issues": [
            "Rapid clearance by asialoglycoprotein receptor in liver",
            "Limited penetration to podocytes and cardiomyocytes",
            "ADA immunogenicity in ERT-naïve patients",
        ],
        "suggested_modifications": [
            "Pegunigalsidase alfa approach: PEGylation to reduce immunogenicity and extend t½",
            "Introduce M6P residues for lysosomal targeting in non-macrophage cells",
            "Surface charge engineering to improve vascular endothelial uptake",
            "Remove dominant T-cell epitopes by sequence deimmunization",
        ],
        "glycosylation_sites": [108, 139, 192, 215],
        "half_life_improvement": "From ~60 min (agalsidase) to ~80 h (Pegunigalsidase alfa / PRX-102)",
    },
    "GAA": {
        "disease": "Pompe disease",
        "wild_type_issues": [
            "Inadequate M6P glycosylation from CHO cells reduces lysosomal targeting",
            "Inefficient muscle uptake via CI-MPR",
            "Large protein (110 kDa) limits tissue penetration",
        ],
        "suggested_modifications": [
            "Use avalglucosidase alfa (Nexviazyme) approach: high M6P content via GlcNAc-1-phosphotransferase expression",
            "IGF2-fusion peptide (cipaglucosidase alfa) for CI-MPR-independent uptake",
            "Optimize pro-peptide cleavage sequence for efficient lysosomal processing",
        ],
        "glycosylation_sites": [140, 233, 390, 470, 652, 882, 925],
        "half_life_improvement": "Standard alglucosidase t½ ~2.3 h; next-gen with IGF2 fusion show improved tissue exposure",
    },
    "IDUA": {
        "disease": "Hurler syndrome (MPS I)",
        "wild_type_issues": [
            "CNS penetration absent with IV ERT",
            "Neutralizing antibodies in MPS I-H patients",
            "Suboptimal joint tissue penetration",
        ],
        "suggested_modifications": [
            "Fusion with BBB-crossing peptide (anti-TfR1 antibody) for CNS delivery",
            "Deimmunization of immunodominant MHC-II epitopes",
            "Increase M6P density to improve fibroblast/chondrocyte uptake",
        ],
        "glycosylation_sites": [110, 190, 336, 372, 415, 451],
        "half_life_improvement": "Laronidase t½ ~3.6 h; BBB-crossing variants in preclinical development",
    },
    "SMPD1": {
        "disease": "Niemann-Pick disease type A/B",
        "wild_type_issues": [
            "Highly immunogenic in null patients",
            "Zinc cofactor loss during CHO expression",
            "Dose-limiting hepatotoxicity at higher doses",
        ],
        "suggested_modifications": [
            "Olipudase alfa approach: recombinant human ASM produced in CHO",
            "Optimize zinc coordination residues to maintain metalloenzyme activity",
            "Introduce PEG shielding on immunogenic surface patches",
        ],
        "glycosylation_sites": [86, 180, 335, 395],
        "half_life_improvement": "Olipudase alfa t½ ~16 h; PEGylation could extend further",
    },
    "ADA": {
        "disease": "ADA-SCID",
        "wild_type_issues": [
            "Very short half-life (~30 min native)",
            "Immunogenicity limits repeated dosing",
            "Does not restore lymphocyte-intrinsic signaling",
        ],
        "suggested_modifications": [
            "PEGylation (Pegademase / Elapegademase) to extend half-life dramatically",
            "PEG chain length optimization for immunogenicity vs activity tradeoff",
            "Consider mRNA delivery for transient hepatic expression as bridge to gene therapy",
        ],
        "glycosylation_sites": [74, 116, 201],
        "half_life_improvement": "Native ~30 min; Pegademase (PEG-ADA) t½ ~3–6 days; Elapegademase ~4–6 days",
    },
}


def design_ert(enzyme_gene: str, disease: str) -> ERTDesign | None:
    """Return ERT design recommendations for a given enzyme. None if not in database."""
    g = enzyme_gene.upper()
    entry = _ERT_DB.get(g)
    if entry is None:
        return None
    return ERTDesign(
        enzyme_gene=g,
        disease=entry["disease"],
        wild_type_issues=entry["wild_type_issues"],
        suggested_modifications=entry["suggested_modifications"],
        glycosylation_sites=entry["glycosylation_sites"],
        half_life_improvement=entry["half_life_improvement"],
    )


# ---------------------------------------------------------------------------
# Prodrug activation
# ---------------------------------------------------------------------------

@dataclass
class ProdugSystem:
    enzyme: str
    prodrug: str
    active_drug: str
    activation_mechanism: str
    tumor_selectivity: str


KNOWN_PRODRUG_SYSTEMS: dict[str, dict] = {
    "HSV-TK": {
        "enzyme": "HSV-TK",
        "prodrug": "Ganciclovir",
        "active_drug": "Ganciclovir triphosphate",
        "activation_mechanism": "Herpes simplex virus thymidine kinase phosphorylates ganciclovir; cellular kinases complete activation to GCV-TP which inhibits viral/tumor DNA polymerase",
        "tumor_selectivity": "High — HSV-TK expressed only in transduced tumor cells via viral vector delivery",
    },
    "CD": {
        "enzyme": "CD",
        "prodrug": "5-Fluorocytosine (5-FC)",
        "active_drug": "5-Fluorouracil (5-FU)",
        "activation_mechanism": "Cytosine deaminase (bacterial/yeast) deaminates 5-FC to 5-FU which inhibits thymidylate synthase and is incorporated into RNA/DNA",
        "tumor_selectivity": "High — CD absent in mammalian cells; expressed via tumor-targeted gene therapy vector",
    },
    "NTR": {
        "enzyme": "NTR",
        "prodrug": "CB1954",
        "active_drug": "CB1954 4-hydroxylamine",
        "activation_mechanism": "Bacterial nitroreductase reduces the 4-nitro group of CB1954 to 4-hydroxylamine; alkylates DNA causing interstrand crosslinks",
        "tumor_selectivity": "Moderate — NTR is bacterial enzyme; bystander effect important for solid tumor coverage",
    },
    "CYP2B6": {
        "enzyme": "CYP2B6",
        "prodrug": "Cyclophosphamide",
        "active_drug": "Phosphoramide mustard",
        "activation_mechanism": "CYP2B6/2C9 hydroxylate cyclophosphamide to 4-OH-cyclophosphamide; spontaneous ring opening releases phosphoramide mustard DNA alkylator",
        "tumor_selectivity": "Low-moderate — relies on hepatic activation; GDEPT with intratumoral CYP2B6 improves selectivity",
    },
    "PNP": {
        "enzyme": "PNP",
        "prodrug": "6-Methylpurine deoxyriboside (MePdR)",
        "active_drug": "6-Methylpurine",
        "activation_mechanism": "E. coli purine nucleoside phosphorylase cleaves MePdR to 6-methylpurine, a potent inhibitor of RNA synthesis with strong bystander effect",
        "tumor_selectivity": "High — E. coli PNP is 10^6-fold more efficient than human enzyme at MePdR cleavage",
    },
    "TYMP": {
        "enzyme": "TYMP",
        "prodrug": "Capecitabine",
        "active_drug": "5-Fluorouracil (5-FU)",
        "activation_mechanism": "Capecitabine converted to 5'-DFUR by carboxylesterase/cytidine deaminase; thymidine phosphorylase (TYMP) cleaves 5'-DFUR to 5-FU preferentially in tumor tissue",
        "tumor_selectivity": "High — TYMP is overexpressed in many tumors; tumor/normal tissue 5-FU ratio ~10:1",
    },
}


def find_prodrug_system(enzyme_gene: str) -> ProdugSystem | None:
    """Return known prodrug system for an enzyme or None."""
    g = enzyme_gene.upper()
    for key, entry in KNOWN_PRODRUG_SYSTEMS.items():
        if key.upper() == g or entry["enzyme"].upper() == g:
            return ProdugSystem(
                enzyme=entry["enzyme"],
                prodrug=entry["prodrug"],
                active_drug=entry["active_drug"],
                activation_mechanism=entry["activation_mechanism"],
                tumor_selectivity=entry["tumor_selectivity"],
            )
    return None
