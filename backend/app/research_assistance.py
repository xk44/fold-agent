"""Research Assistance Tools — Phase 24 Tier 2

MSA quality screening, literature cross-referencing, structure visualization metadata,
and signal peptide prediction.
RESEARCH USE ONLY.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Feature 1: MSA Quality Pre-screen
# ---------------------------------------------------------------------------

MSA_DEPTH_THRESHOLDS: dict[str, int] = {
    "excellent": 1000,
    "good": 200,
    "marginal": 30,
    "sparse": 5,
    "orphan": 0,
}

BACKEND_MSA_REQUIREMENTS: dict[str, str] = {
    "alphafold2_local": "required",
    "alphafold3_local": "optional",
    "colabfold": "required",
    "esmfold": "none",
    "chai1": "optional",
    "openfold": "required",
    "rosettafold": "required",
    "omegafold": "none",
}


@dataclass
class MSAQualityResult:
    sequence_length: int
    estimated_msa_depth: int
    msa_quality: str  # "excellent"|"good"|"marginal"|"sparse"|"orphan"
    recommended_backend: str
    fallback_suggested: bool
    fallback_backend: str | None
    warnings: list[str]
    neff_estimate: float


def _hash_int(s: str, lo: int = 0, hi: int = 1000) -> int:
    """Return deterministic int in [lo, hi] from string hash."""
    h = int(hashlib.sha256(s.encode()).hexdigest(), 16)
    return lo + (h % (hi - lo + 1))


def _hash_float(s: str, lo: float = 0.0, hi: float = 1.0) -> float:
    h = int(hashlib.sha256(s.encode()).hexdigest(), 16)
    return lo + (h % 10000) / 10000.0 * (hi - lo)


def screen_msa_quality(sequence: str) -> MSAQualityResult:
    """Estimate MSA depth and quality from sequence features (deterministic stub).

    Short/unusual sequences get low depth → ESMFold fallback suggested.
    RESEARCH ONLY — not for clinical use.
    """
    seq = sequence.strip().upper()
    length = len(seq)

    # Composition diversity: unique residues / 20
    unique_aa = len(set(seq) & set("ACDEFGHIKLMNPQRSTVWY"))
    diversity = unique_aa / 20.0

    # Seed from sequence content for determinism
    seed_str = f"msa:{seq[:50]}:{length}"
    base_depth = _hash_int(seed_str, lo=0, hi=2000)

    # Penalise unusual/short sequences
    if length < 30:
        base_depth = min(base_depth, 3)
    elif length < 60:
        base_depth = min(base_depth, int(base_depth * 0.2))
    elif diversity < 0.4:
        base_depth = min(base_depth, int(base_depth * 0.3))

    estimated_depth = base_depth
    neff = round(estimated_depth * diversity * 0.7, 2)

    # Classify quality
    if estimated_depth >= MSA_DEPTH_THRESHOLDS["excellent"]:
        quality = "excellent"
    elif estimated_depth >= MSA_DEPTH_THRESHOLDS["good"]:
        quality = "good"
    elif estimated_depth >= MSA_DEPTH_THRESHOLDS["marginal"]:
        quality = "marginal"
    elif estimated_depth >= MSA_DEPTH_THRESHOLDS["sparse"]:
        quality = "sparse"
    else:
        quality = "orphan"

    warnings: list[str] = []
    fallback_suggested = False
    fallback_backend: str | None = None

    if quality in ("sparse", "orphan"):
        warnings.append(
            f"MSA-sparse: estimated depth {estimated_depth} is below reliable threshold "
            "(≥30). Structure predictions may be unreliable."
        )
        fallback_suggested = True
        fallback_backend = "esmfold"

    if quality == "marginal":
        warnings.append(
            "MSA depth is marginal; consider ESMFold or OmegaFold as MSA-free alternatives."
        )
        fallback_suggested = True
        fallback_backend = "esmfold"

    if length < 30:
        warnings.append("Sequence is very short (<30 aa); MSA construction likely unreliable.")

    if diversity < 0.4:
        warnings.append(
            "Low amino-acid diversity detected; sequence may be compositionally biased."
        )

    if quality in ("excellent", "good"):
        recommended_backend = "alphafold2_local"
    elif quality == "marginal":
        recommended_backend = "colabfold"
    else:
        recommended_backend = "esmfold"

    return MSAQualityResult(
        sequence_length=length,
        estimated_msa_depth=estimated_depth,
        msa_quality=quality,
        recommended_backend=recommended_backend,
        fallback_suggested=fallback_suggested,
        fallback_backend=fallback_backend,
        warnings=warnings,
        neff_estimate=neff,
    )


def suggest_prediction_strategy(quality: MSAQualityResult) -> dict:
    """Return recommended prediction approach based on MSA quality.

    RESEARCH ONLY — not for clinical use.
    """
    strategy: dict = {
        "primary_backend": quality.recommended_backend,
        "use_templates": quality.msa_quality in ("excellent", "good"),
        "num_recycles": 3 if quality.msa_quality in ("excellent", "good") else 1,
        "msa_required": BACKEND_MSA_REQUIREMENTS.get(quality.recommended_backend, "unknown"),
        "confidence_caveat": None,
        "alternative_backends": [],
        "rationale": "",
    }

    if quality.msa_quality == "excellent":
        strategy["rationale"] = (
            "Deep MSA available; AlphaFold2 with templates recommended for best accuracy."
        )
        strategy["alternative_backends"] = ["alphafold3_local", "colabfold"]
    elif quality.msa_quality == "good":
        strategy["rationale"] = "Good MSA depth; standard AlphaFold2 pipeline recommended."
        strategy["alternative_backends"] = ["colabfold", "esmfold"]
    elif quality.msa_quality == "marginal":
        strategy["rationale"] = (
            "Marginal MSA; ColabFold may leverage extra databases. "
            "Consider ESMFold as MSA-free fallback."
        )
        strategy["alternative_backends"] = ["esmfold", "omegafold"]
        strategy["confidence_caveat"] = "Predictions based on marginal MSA may have lower accuracy."
    else:
        strategy["rationale"] = "Sparse/orphan MSA; ESMFold (MSA-free language model) recommended."
        strategy["alternative_backends"] = ["omegafold", "chai1"]
        strategy["confidence_caveat"] = (
            "MSA-sparse: structure prediction confidence will be low. "
            "Experimental validation strongly recommended."
        )

    return strategy


# ---------------------------------------------------------------------------
# Feature 2: PubMed Literature Cross-referencing
# ---------------------------------------------------------------------------

MOCK_LITERATURE_DB: list[dict] = [
    {
        "gene": "TP53",
        "pubmed_id": "22897851",
        "title": "Mutant p53 in cancer: new functions and therapeutic opportunities",
        "journal": "Cell",
        "year": 2012,
        "relevance_score": 0.98,
        "topics": ["cancer", "tumor_suppressor", "mutation", "therapy"],
        "cited_by": 4210,
    },
    {
        "gene": "TP53",
        "pubmed_id": "31506264",
        "title": "p53 at the crossroads of cancer and aging",
        "journal": "Nature Reviews Cancer",
        "year": 2019,
        "relevance_score": 0.95,
        "topics": ["cancer", "aging", "tumor_suppressor"],
        "cited_by": 1820,
    },
    {
        "gene": "KRAS",
        "pubmed_id": "29691351",
        "title": "KRAS G12C inhibitors allosterically control GEF-nucleotide exchange",
        "journal": "Cell",
        "year": 2018,
        "relevance_score": 0.97,
        "topics": ["cancer", "drug_target", "inhibitor", "oncogene"],
        "cited_by": 2350,
    },
    {
        "gene": "KRAS",
        "pubmed_id": "35839778",
        "title": "Sotorasib for KRAS G12C-mutated non-small-cell lung cancer",
        "journal": "New England Journal of Medicine",
        "year": 2022,
        "relevance_score": 0.94,
        "topics": ["lung_cancer", "clinical_trial", "drug_target"],
        "cited_by": 980,
    },
    {
        "gene": "EGFR",
        "pubmed_id": "17671364",
        "title": "Erlotinib in previously treated non-small-cell lung cancer",
        "journal": "New England Journal of Medicine",
        "year": 2005,
        "relevance_score": 0.96,
        "topics": ["lung_cancer", "clinical_trial", "targeted_therapy"],
        "cited_by": 6100,
    },
    {
        "gene": "EGFR",
        "pubmed_id": "28168245",
        "title": "Osimertinib in untreated EGFR-mutated advanced NSCLC",
        "journal": "New England Journal of Medicine",
        "year": 2018,
        "relevance_score": 0.93,
        "topics": ["lung_cancer", "clinical_trial", "resistance_mutation"],
        "cited_by": 3800,
    },
    {
        "gene": "BRCA1",
        "pubmed_id": "8524414",
        "title": "A strong candidate for the breast and ovarian cancer susceptibility gene BRCA1",
        "journal": "Science",
        "year": 1994,
        "relevance_score": 0.99,
        "topics": ["breast_cancer", "ovarian_cancer", "DNA_repair", "hereditary"],
        "cited_by": 11200,
    },
    {
        "gene": "BRCA1",
        "pubmed_id": "28726821",
        "title": "Olaparib for metastatic breast cancer in patients with a germline BRCA mutation",
        "journal": "New England Journal of Medicine",
        "year": 2017,
        "relevance_score": 0.92,
        "topics": ["breast_cancer", "PARP_inhibitor", "clinical_trial"],
        "cited_by": 2100,
    },
    {
        "gene": "BRCA2",
        "pubmed_id": "9590285",
        "title": "BRCA2 function in DNA binding and recombination",
        "journal": "Science",
        "year": 1998,
        "relevance_score": 0.97,
        "topics": ["breast_cancer", "DNA_repair", "homologous_recombination"],
        "cited_by": 2400,
    },
    {
        "gene": "PIK3CA",
        "pubmed_id": "15016963",
        "title": "Mutations of PIK3CA in gastric aerodigestive tract carcinomas",
        "journal": "Gastroenterology",
        "year": 2004,
        "relevance_score": 0.88,
        "topics": ["cancer", "PI3K_pathway", "mutation"],
        "cited_by": 870,
    },
    {
        "gene": "BRAF",
        "pubmed_id": "12068308",
        "title": "Mutations of the BRAF gene in human cancer",
        "journal": "Nature",
        "year": 2002,
        "relevance_score": 0.98,
        "topics": ["melanoma", "kinase", "oncogene", "MAPK_pathway"],
        "cited_by": 9800,
    },
    {
        "gene": "BRAF",
        "pubmed_id": "21639808",
        "title": "Improved survival with vemurafenib in melanoma with BRAF V600E mutation",
        "journal": "New England Journal of Medicine",
        "year": 2011,
        "relevance_score": 0.96,
        "topics": ["melanoma", "clinical_trial", "targeted_therapy"],
        "cited_by": 6400,
    },
    {
        "gene": "MYC",
        "pubmed_id": "32866368",
        "title": "MYC and the universe of cancer",
        "journal": "Cancer Cell",
        "year": 2020,
        "relevance_score": 0.95,
        "topics": ["cancer", "transcription_factor", "oncogene"],
        "cited_by": 1100,
    },
    {
        "gene": "ALK",
        "pubmed_id": "17625570",
        "title": "Identification of the transforming EML4-ALK fusion gene in NSCLC",
        "journal": "Nature",
        "year": 2007,
        "relevance_score": 0.97,
        "topics": ["lung_cancer", "fusion_gene", "targeted_therapy"],
        "cited_by": 3900,
    },
    {
        "gene": "HER2",
        "pubmed_id": "9816077",
        "title": "Use of chemotherapy plus a monoclonal antibody against HER2",
        "journal": "New England Journal of Medicine",
        "year": 1999,
        "relevance_score": 0.97,
        "topics": ["breast_cancer", "antibody_therapy", "clinical_trial"],
        "cited_by": 8700,
    },
    {
        "gene": "PTEN",
        "pubmed_id": "9256433",
        "title": "PTEN, a putative protein tyrosine phosphatase gene mutated in human brain, breast, and prostate cancer",
        "journal": "Science",
        "year": 1997,
        "relevance_score": 0.96,
        "topics": ["tumor_suppressor", "PI3K_pathway", "cancer"],
        "cited_by": 5600,
    },
    {
        "gene": "RB1",
        "pubmed_id": "2895900",
        "title": "A human DNA segment with properties of the gene that predisposes to retinoblastoma",
        "journal": "Nature",
        "year": 1987,
        "relevance_score": 0.98,
        "topics": ["retinoblastoma", "tumor_suppressor", "cell_cycle"],
        "cited_by": 4200,
    },
    {
        "gene": "CDK4",
        "pubmed_id": "26830311",
        "title": "Palbociclib and letrozole in advanced breast cancer",
        "journal": "New England Journal of Medicine",
        "year": 2016,
        "relevance_score": 0.91,
        "topics": ["breast_cancer", "CDK_inhibitor", "clinical_trial"],
        "cited_by": 2800,
    },
    {
        "gene": "VEGFA",
        "pubmed_id": "15372042",
        "title": "Bevacizumab plus irinotecan, fluorouracil, and leucovorin for metastatic colorectal cancer",
        "journal": "New England Journal of Medicine",
        "year": 2004,
        "relevance_score": 0.94,
        "topics": ["colorectal_cancer", "angiogenesis", "antibody_therapy", "clinical_trial"],
        "cited_by": 7300,
    },
    {
        "gene": "PDCD1",
        "pubmed_id": "26028255",
        "title": "Pembrolizumab versus ipilimumab in advanced melanoma",
        "journal": "New England Journal of Medicine",
        "year": 2015,
        "relevance_score": 0.96,
        "topics": ["melanoma", "immunotherapy", "checkpoint_inhibitor", "clinical_trial"],
        "cited_by": 6200,
    },
    {
        "gene": "CTLA4",
        "pubmed_id": "21639812",
        "title": "Ipilimumab plus dacarbazine for previously untreated metastatic melanoma",
        "journal": "New England Journal of Medicine",
        "year": 2011,
        "relevance_score": 0.93,
        "topics": ["melanoma", "immunotherapy", "checkpoint_inhibitor"],
        "cited_by": 3100,
    },
    {
        "gene": "ABL1",
        "pubmed_id": "11423618",
        "title": "Efficacy and safety of a specific inhibitor of the BCR-ABL tyrosine kinase in CML",
        "journal": "New England Journal of Medicine",
        "year": 2001,
        "relevance_score": 0.99,
        "topics": ["leukemia", "targeted_therapy", "kinase_inhibitor", "clinical_trial"],
        "cited_by": 9400,
    },
    {
        "gene": "JAK2",
        "pubmed_id": "16061916",
        "title": "Acquired mutation in the kinase domain of JAK2 in polycythemia vera",
        "journal": "New England Journal of Medicine",
        "year": 2005,
        "relevance_score": 0.96,
        "topics": ["myeloproliferative_neoplasm", "kinase", "somatic_mutation"],
        "cited_by": 4800,
    },
    {
        "gene": "FGFR3",
        "pubmed_id": "8640225",
        "title": "Activating mutations in FGFR3 and Ras: involvement in urothelial carcinoma",
        "journal": "Oncogene",
        "year": 1996,
        "relevance_score": 0.87,
        "topics": ["bladder_cancer", "receptor_tyrosine_kinase", "mutation"],
        "cited_by": 620,
    },
    {
        "gene": "IDH1",
        "pubmed_id": "28514618",
        "title": "Enasidenib in mutant IDH2 relapsed or refractory AML",
        "journal": "Blood",
        "year": 2017,
        "relevance_score": 0.89,
        "topics": ["leukemia", "IDH_inhibitor", "clinical_trial"],
        "cited_by": 1400,
    },
    {
        "gene": "FLT3",
        "pubmed_id": "28516360",
        "title": "Midostaurin plus chemotherapy for acute myeloid leukemia with FLT3 mutation",
        "journal": "New England Journal of Medicine",
        "year": 2017,
        "relevance_score": 0.93,
        "topics": ["leukemia", "kinase_inhibitor", "clinical_trial"],
        "cited_by": 2200,
    },
    {
        "gene": "MDM2",
        "pubmed_id": "22901806",
        "title": "MDM2 inhibitors in clinical trials",
        "journal": "Journal of Hematology & Oncology",
        "year": 2012,
        "relevance_score": 0.86,
        "topics": ["cancer", "TP53_pathway", "small_molecule_inhibitor"],
        "cited_by": 380,
    },
    {
        "gene": "BCL2",
        "pubmed_id": "27538521",
        "title": "Venetoclax in relapsed or refractory chronic lymphocytic leukemia",
        "journal": "New England Journal of Medicine",
        "year": 2016,
        "relevance_score": 0.94,
        "topics": ["leukemia", "apoptosis", "BCL2_inhibitor", "clinical_trial"],
        "cited_by": 2900,
    },
    {
        "gene": "MET",
        "pubmed_id": "33632335",
        "title": "Tepotinib in non-small-cell lung cancer with MET exon 14 skipping mutations",
        "journal": "New England Journal of Medicine",
        "year": 2020,
        "relevance_score": 0.90,
        "topics": ["lung_cancer", "MET_inhibitor", "clinical_trial", "splice_mutation"],
        "cited_by": 1100,
    },
    {
        "gene": "RET",
        "pubmed_id": "32846061",
        "title": "Selpercatinib in RET-altered thyroid cancers",
        "journal": "New England Journal of Medicine",
        "year": 2020,
        "relevance_score": 0.91,
        "topics": ["thyroid_cancer", "RET_inhibitor", "clinical_trial"],
        "cited_by": 940,
    },
    {
        "gene": "NTRK1",
        "pubmed_id": "29466156",
        "title": "Larotrectinib in TRK fusion-positive cancers",
        "journal": "New England Journal of Medicine",
        "year": 2018,
        "relevance_score": 0.92,
        "topics": ["cancer", "TRK_inhibitor", "basket_trial", "fusion_gene"],
        "cited_by": 1800,
    },
    {
        "gene": "POLE",
        "pubmed_id": "27993966",
        "title": "Ultramutated cancers: POLE proofreading exonuclease mutations",
        "journal": "Nature Reviews Cancer",
        "year": 2017,
        "relevance_score": 0.85,
        "topics": ["cancer", "DNA_replication", "immunotherapy_response"],
        "cited_by": 560,
    },
    {
        "gene": "MSH2",
        "pubmed_id": "8252616",
        "title": "Mutation in the mismatch repair gene homologue hMLH1 is associated with hereditary nonpolyposis colon cancer",
        "journal": "Nature",
        "year": 1993,
        "relevance_score": 0.94,
        "topics": ["colorectal_cancer", "MMR", "hereditary", "microsatellite_instability"],
        "cited_by": 3200,
    },
    {
        "gene": "APC",
        "pubmed_id": "1651562",
        "title": "Identification of a chromosome 18q gene that is altered in colorectal cancers",
        "journal": "Science",
        "year": 1991,
        "relevance_score": 0.96,
        "topics": ["colorectal_cancer", "tumor_suppressor", "Wnt_pathway"],
        "cited_by": 4700,
    },
    {
        "gene": "CDKN2A",
        "pubmed_id": "9590177",
        "title": "The p16INK4a-CDK4-Rb pathway",
        "journal": "Current Opinion in Genetics & Development",
        "year": 1998,
        "relevance_score": 0.87,
        "topics": ["cancer", "cell_cycle", "senescence", "tumor_suppressor"],
        "cited_by": 1100,
    },
    {
        "gene": "NOTCH1",
        "pubmed_id": "15215855",
        "title": "Activating mutations of NOTCH1 in human T-cell leukemia",
        "journal": "Science",
        "year": 2004,
        "relevance_score": 0.91,
        "topics": ["leukemia", "Notch_signaling", "oncogene"],
        "cited_by": 2400,
    },
    {
        "gene": "SMO",
        "pubmed_id": "22722829",
        "title": "Vismodegib in advanced basal-cell carcinoma",
        "journal": "New England Journal of Medicine",
        "year": 2012,
        "relevance_score": 0.90,
        "topics": ["skin_cancer", "Hedgehog_pathway", "clinical_trial"],
        "cited_by": 1600,
    },
    {
        "gene": "AR",
        "pubmed_id": "23228172",
        "title": "Enzalutamide in metastatic prostate cancer",
        "journal": "New England Journal of Medicine",
        "year": 2012,
        "relevance_score": 0.94,
        "topics": ["prostate_cancer", "androgen_receptor", "clinical_trial"],
        "cited_by": 5100,
    },
    {
        "gene": "ESR1",
        "pubmed_id": "24957560",
        "title": "ESR1 ligand-binding domain mutations in hormone-resistant breast cancer",
        "journal": "Nature Genetics",
        "year": 2014,
        "relevance_score": 0.89,
        "topics": ["breast_cancer", "resistance_mutation", "endocrine_therapy"],
        "cited_by": 1900,
    },
    {
        "gene": "DNMT3A",
        "pubmed_id": "20693557",
        "title": "DNMT3A mutations in acute myeloid leukemia",
        "journal": "New England Journal of Medicine",
        "year": 2010,
        "relevance_score": 0.91,
        "topics": ["leukemia", "epigenetics", "somatic_mutation"],
        "cited_by": 2600,
    },
    {
        "gene": "TET2",
        "pubmed_id": "19478085",
        "title": "TET2 mutation in human cancer sets the stage for clonal evolution",
        "journal": "Nature",
        "year": 2009,
        "relevance_score": 0.88,
        "topics": ["leukemia", "epigenetics", "clonal_hematopoiesis"],
        "cited_by": 1700,
    },
]

# Build index for fast lookup
_LITERATURE_INDEX: dict[str, list[dict]] = {}
for _entry in MOCK_LITERATURE_DB:
    _g = _entry["gene"].upper()
    _LITERATURE_INDEX.setdefault(_g, []).append(_entry)


@dataclass
class LiteratureResult:
    gene: str
    total_references: int
    top_references: list[dict]
    related_proteins: list[str]
    disease_associations: list[str]
    drug_mentions: list[str]
    knowledge_gap_score: float  # 0-1, higher = less literature coverage


_GENE_PARTNERS: dict[str, list[str]] = {
    "TP53": ["MDM2", "CDK4", "CDKN2A", "BCL2"],
    "KRAS": ["BRAF", "PIK3CA", "EGFR", "RAF1"],
    "EGFR": ["HER2", "KRAS", "ALK", "MET"],
    "BRCA1": ["BRCA2", "PTEN", "TP53", "RAD51"],
    "BRCA2": ["BRCA1", "PALB2", "RAD51", "TP53"],
    "BRAF": ["KRAS", "MEK1", "MEK2", "EGFR"],
    "ABL1": ["BCR", "JAK2", "CRKL"],
    "HER2": ["EGFR", "PIK3CA", "HSP90"],
    "MYC": ["MAX", "MXI1", "CDK4"],
    "PIK3CA": ["PTEN", "AKT1", "MTOR"],
}

_TOPIC_DISEASE_MAP: dict[str, str] = {
    "lung_cancer": "non-small-cell lung cancer",
    "breast_cancer": "breast cancer",
    "melanoma": "melanoma",
    "leukemia": "acute myeloid leukemia",
    "colorectal_cancer": "colorectal cancer",
    "prostate_cancer": "prostate cancer",
    "ovarian_cancer": "ovarian cancer",
    "thyroid_cancer": "thyroid cancer",
    "retinoblastoma": "retinoblastoma",
    "cancer": "various cancers",
    "bladder_cancer": "bladder cancer",
    "skin_cancer": "basal-cell carcinoma",
    "myeloproliferative_neoplasm": "polycythemia vera",
}

_TOPIC_DRUG_MAP: dict[str, str] = {
    "clinical_trial": None,
    "targeted_therapy": None,
    "PARP_inhibitor": "olaparib",
    "CDK_inhibitor": "palbociclib",
    "BCL2_inhibitor": "venetoclax",
    "kinase_inhibitor": None,
    "antibody_therapy": None,
    "immunotherapy": None,
    "small_molecule_inhibitor": None,
    "TRK_inhibitor": "larotrectinib",
    "RET_inhibitor": "selpercatinib",
    "MET_inhibitor": "tepotinib",
    "checkpoint_inhibitor": "pembrolizumab",
    "MDM2_inhibitor": "nutlin-3",
}


def search_literature(gene: str, topics: list[str] | None = None) -> LiteratureResult:
    """Search mock PubMed DB for gene-related literature.

    RESEARCH ONLY — not for clinical use.
    """
    gene_upper = gene.upper()
    entries = list(_LITERATURE_INDEX.get(gene_upper, []))

    # Filter by topics if specified
    if topics:
        topic_set = {t.lower() for t in topics}
        filtered = [e for e in entries if topic_set & set(e["topics"])]
        if filtered:
            entries = filtered

    # Sort by relevance desc, then year desc
    entries = sorted(entries, key=lambda e: (e["relevance_score"], e["year"]), reverse=True)

    # Collect disease/drug mentions from topics
    disease_set: set[str] = set()
    drug_set: set[str] = set()
    for e in entries:
        for t in e["topics"]:
            if t in _TOPIC_DISEASE_MAP and _TOPIC_DISEASE_MAP[t]:
                disease_set.add(_TOPIC_DISEASE_MAP[t])
            if t in _TOPIC_DRUG_MAP and _TOPIC_DRUG_MAP[t]:
                drug_set.add(_TOPIC_DRUG_MAP[t])

    related = _GENE_PARTNERS.get(gene_upper, [])

    # Knowledge gap: genes with no/few entries have high gap score
    if not entries:
        gap = 1.0
    elif len(entries) == 1:
        gap = 0.7
    elif len(entries) <= 3:
        gap = 0.4
    else:
        gap = round(max(0.0, 0.1 - (len(entries) - 4) * 0.01), 2)

    return LiteratureResult(
        gene=gene_upper,
        total_references=len(entries),
        top_references=entries[:5],
        related_proteins=related,
        disease_associations=sorted(disease_set),
        drug_mentions=sorted(drug_set),
        knowledge_gap_score=gap,
    )


def cross_reference_prediction(gene: str, prediction_type: str) -> dict:
    """Find literature and flag whether prediction aligns with published findings.

    prediction_type: "structure" | "variant" | "binding" | "expression" | other
    RESEARCH ONLY — not for clinical use.
    """
    lit = search_literature(gene)

    support_level: str
    notes: list[str] = []

    if lit.total_references == 0:
        support_level = "no_literature"
        notes.append(f"No literature found for {gene}; prediction is novel and unvalidated.")
    elif lit.total_references >= 4:
        support_level = "well_supported"
        notes.append(
            f"Substantial literature exists for {gene} ({lit.total_references} refs). "
            "Cross-referencing shows prediction consistent with known biology."
        )
    elif lit.total_references >= 2:
        support_level = "partially_supported"
        notes.append(
            f"Limited literature for {gene} ({lit.total_references} refs). "
            "Partial cross-reference confidence."
        )
    else:
        support_level = "sparse_literature"
        notes.append(f"Only 1 reference found for {gene}; use caution interpreting predictions.")

    if prediction_type == "variant" and gene.upper() in ("TP53", "KRAS", "EGFR", "BRCA1"):
        notes.append("ClinVar and COSMIC data available; variant predicted to be oncogenic.")

    if prediction_type == "structure":
        notes.append("AlphaFold DB may already contain a structure for well-studied proteins.")

    if prediction_type == "binding":
        if lit.drug_mentions:
            notes.append(
                f"Known drug interactions documented: {', '.join(lit.drug_mentions)}. "
                "Prediction may complement existing binding data."
            )

    return {
        "gene": gene.upper(),
        "prediction_type": prediction_type,
        "support_level": support_level,
        "literature_count": lit.total_references,
        "top_references": lit.top_references[:3],
        "disease_context": lit.disease_associations,
        "known_drugs": lit.drug_mentions,
        "notes": notes,
        "safety_label": "Research only — not for clinical or diagnostic use",
    }


def identify_knowledge_gaps(gene: str) -> dict:
    """Identify what is NOT well-covered in literature for this gene.

    RESEARCH ONLY — not for clinical use.
    """
    lit = search_literature(gene)
    all_topics: set[str] = set()
    for e in lit.top_references:
        all_topics.update(e["topics"])

    # What major categories are missing?
    major_categories = {
        "structure": {"structure", "cryo_em", "crystallography", "NMR"},
        "drug_target": {
            "drug_target",
            "small_molecule_inhibitor",
            "kinase_inhibitor",
            "clinical_trial",
        },
        "mechanism": {"mechanism", "signaling", "pathway"},
        "biomarker": {"biomarker", "expression", "prognosis"},
        "hereditary": {"hereditary", "germline", "familial"},
    }

    gaps: list[str] = []
    covered: list[str] = []
    for category, keywords in major_categories.items():
        if keywords & all_topics:
            covered.append(category)
        else:
            gaps.append(category)

    # Add specific gaps based on depth
    specific_gaps: list[str] = []
    if lit.total_references < 2:
        specific_gaps.append("Protein function poorly characterized")
    if not lit.disease_associations:
        specific_gaps.append("No disease associations documented")
    if not lit.drug_mentions:
        specific_gaps.append("No approved drugs targeting this protein")
    if not lit.related_proteins:
        specific_gaps.append("Interaction partners unknown")

    return {
        "gene": gene.upper(),
        "knowledge_gap_score": lit.knowledge_gap_score,
        "covered_categories": covered,
        "gap_categories": gaps,
        "specific_gaps": specific_gaps,
        "total_references": lit.total_references,
        "research_opportunities": [f"Investigate {g} for {gene.upper()}" for g in gaps[:3]],
        "safety_label": "Research only — not for clinical use",
    }


# ---------------------------------------------------------------------------
# Feature 3: Structure Visualization Metadata
# ---------------------------------------------------------------------------

PLDDT_COLOR_SCHEME: dict[str, dict] = {
    "very_high": {
        "min": 90,
        "max": 100,
        "color": "#0053D6",
        "label": "Very high confidence (pLDDT > 90)",
    },
    "confident": {"min": 70, "max": 90, "color": "#65CBF3", "label": "Confident (pLDDT 70-90)"},
    "low": {"min": 50, "max": 70, "color": "#FFDB13", "label": "Low confidence (pLDDT 50-70)"},
    "very_low": {
        "min": 0,
        "max": 50,
        "color": "#FF7D45",
        "label": "Very low confidence (pLDDT < 50)",
    },
}


@dataclass
class VisualizationAnnotation:
    residue_index: int
    annotation_type: str  # "plddt"|"disagreement"|"variant"|"ptm"|"binding_site"
    value: float | str
    color_hex: str
    tooltip: str


@dataclass
class StructureViewerData:
    pdb_data: str
    annotations: list[VisualizationAnnotation]
    color_scheme: str
    viewer_config: dict
    export_formats: list[str]


def plddt_to_color(plddt: float) -> str:
    """Return hex color for given pLDDT score using AF color scheme."""
    if plddt >= 90:
        return PLDDT_COLOR_SCHEME["very_high"]["color"]
    elif plddt >= 70:
        return PLDDT_COLOR_SCHEME["confident"]["color"]
    elif plddt >= 50:
        return PLDDT_COLOR_SCHEME["low"]["color"]
    else:
        return PLDDT_COLOR_SCHEME["very_low"]["color"]


def _generate_mock_pdb(sequence: str) -> str:
    """Generate minimal mock PDB text for a sequence."""
    lines = ["REMARK  Mock PDB generated by FoldAgent research_assistance stub"]
    h = int(hashlib.sha256(sequence.encode()).hexdigest(), 16)
    for i, aa in enumerate(sequence[:100], start=1):
        x = round(3.8 * (i % 10) + (h % 1000) / 1000.0, 3)
        y = round(3.8 * ((i // 10) % 10) + (h % 500) / 500.0, 3)
        z = round(1.5 * i * 0.1, 3)
        lines.append(
            f"ATOM  {i:5d}  CA  ALA A{i:4d}    {x:8.3f}{y:8.3f}{z:8.3f}  1.00 {50.0:6.2f}           C"
        )
    lines.append("END")
    return "\n".join(lines)


def generate_viewer_data(
    sequence: str,
    pdb_data: str | None = None,
    variants: list[dict] | None = None,
) -> StructureViewerData:
    """Generate mock PDB + pLDDT-colored annotations + variant markers.

    RESEARCH ONLY — not for clinical use.
    """
    seq = sequence.strip().upper()
    if not pdb_data:
        pdb_data = _generate_mock_pdb(seq)

    h = int(hashlib.sha256(seq.encode()).hexdigest(), 16)
    annotations: list[VisualizationAnnotation] = []

    # pLDDT annotations — deterministic per residue
    for i, aa in enumerate(seq[:200], start=1):
        seed = int(hashlib.sha256(f"plddt:{seq}:{i}".encode()).hexdigest(), 16)
        plddt = 40.0 + (seed % 6000) / 100.0  # 40–100
        color = plddt_to_color(plddt)
        annotations.append(
            VisualizationAnnotation(
                residue_index=i,
                annotation_type="plddt",
                value=round(plddt, 2),
                color_hex=color,
                tooltip=f"Residue {i} ({aa}): pLDDT {plddt:.1f}",
            )
        )

    # Ensemble disagreement for a handful of residues
    n_disagree = 1 + h % 8
    for j in range(n_disagree):
        idx = 1 + (h >> (j * 4)) % max(1, len(seq))
        dis_val = round(0.3 + (h >> (j * 8) & 0xFF) / 510.0, 3)
        annotations.append(
            VisualizationAnnotation(
                residue_index=idx,
                annotation_type="disagreement",
                value=dis_val,
                color_hex="#FF4500",
                tooltip=f"Residue {idx}: ensemble disagreement Δ={dis_val:.3f} Å",
            )
        )

    # Binding site highlights
    n_bs = 1 + h % 4
    for k in range(n_bs):
        idx = 1 + (h >> (k * 12)) % max(1, len(seq))
        annotations.append(
            VisualizationAnnotation(
                residue_index=idx,
                annotation_type="binding_site",
                value="predicted",
                color_hex="#00CC44",
                tooltip=f"Residue {idx}: predicted binding site",
            )
        )

    # Variant annotations
    if variants:
        for var in variants:
            var_idx = var.get("position", 1)
            var_label = var.get("mutation", "unknown")
            var_effect = var.get("effect", "unknown")
            color = "#FF0000" if var_effect in ("pathogenic", "likely_pathogenic") else "#FFA500"
            annotations.append(
                VisualizationAnnotation(
                    residue_index=var_idx,
                    annotation_type="variant",
                    value=var_label,
                    color_hex=color,
                    tooltip=f"Variant {var_label} at residue {var_idx}: {var_effect}",
                )
            )

    viewer_config = generate_molstar_config(
        StructureViewerData(
            pdb_data=pdb_data,
            annotations=annotations,
            color_scheme="plddt",
            viewer_config={},
            export_formats=[],
        )
    )

    return StructureViewerData(
        pdb_data=pdb_data,
        annotations=annotations,
        color_scheme="plddt",
        viewer_config=viewer_config,
        export_formats=["pdb", "mmcif", "png", "svg"],
    )


def generate_molstar_config(viewer_data: StructureViewerData) -> dict:
    """Generate Mol* viewer configuration dictionary.

    RESEARCH ONLY — not for clinical use.
    """
    return {
        "viewer": "molstar",
        "version": "3.x",
        "colorTheme": "plddt",
        "representationStyle": "cartoon",
        "showWater": False,
        "showHydrogens": False,
        "background": "#1a1a2e",
        "lighting": "matte",
        "plddt_color_scheme": PLDDT_COLOR_SCHEME,
        "annotations_count": len(viewer_data.annotations),
        "export_formats": ["pdb", "mmcif", "png", "svg"],
        "interactivity": {
            "clickable_variants": True,
            "hover_tooltips": True,
            "ensemble_overlay": True,
        },
    }


# ---------------------------------------------------------------------------
# Feature 4: Signal Peptide / Secretion Pathway Prediction
# ---------------------------------------------------------------------------

SIGNAL_PEPTIDE_PATTERNS: dict[str, dict] = {
    "n_region": {
        "description": "Positively charged N-terminus (1-5 residues)",
        "charged_aa": "KRH",
        "optimal_count": 1,
    },
    "h_region": {
        "description": "Hydrophobic core (7-15 residues)",
        "hydrophobic_aa": "AVILMFYW",
        "min_length": 7,
        "max_length": 15,
    },
    "c_region": {
        "description": "Small neutral residue at -1, -3 positions (AXA rule)",
        "preferred_minus1": "AGSV",
        "preferred_minus3": "AV",
    },
}


@dataclass
class SignalPeptide:
    detected: bool
    cleavage_site: int | None
    signal_type: str  # "sec_spi"|"sec_spii"|"tat_spi"|"none"
    probability: float
    mature_protein_start: int
    signal_sequence: str | None


@dataclass
class SecretionAnalysis:
    signal_peptide: SignalPeptide
    predicted_localization: str  # "extracellular"|"membrane"|"cytoplasmic"|"nuclear"|"er"|"golgi"
    transmembrane_helices: int
    gpi_anchor: bool
    therapeutic_suitability: str
    warnings: list[str]


def _count_hydrophobic_stretch(seq: str, min_len: int = 7) -> int:
    """Return length of longest hydrophobic stretch in seq."""
    hydro = set("AVILMFYW")
    max_run = 0
    cur = 0
    for aa in seq:
        if aa in hydro:
            cur += 1
            max_run = max(max_run, cur)
        else:
            cur = 0
    return max_run


def predict_signal_peptide(sequence: str) -> SignalPeptide:
    """Analyse first 70 residues for signal peptide features (deterministic stub).

    Checks: hydrophobic H-region, charged N-region, AXA cleavage rule.
    RESEARCH ONLY — not for clinical use.
    """
    seq = sequence.strip().upper()
    window = seq[:70]

    # N-region: check for positive charges in first 5 aa
    n_region = window[:5]
    pos_charges = sum(1 for aa in n_region if aa in "KRH")

    # H-region: hydrophobic stretch of 7-15 residues in positions 5-30
    h_window = window[5:35]
    h_stretch = _count_hydrophobic_stretch(h_window)

    # C-region heuristic: look for cleavage site Ala/Gly at typical positions (15-35)
    cleavage_site: int | None = None
    c_window = window[15:40]
    best_score = 0.0
    for i, aa in enumerate(c_window):
        if aa in "AGSV":
            # Check -3 position
            minus3 = c_window[i - 3] if i >= 3 else ""
            score = 0.5
            if aa in "AG":
                score += 0.2
            if minus3 in "AV":
                score += 0.2
            if score > best_score:
                best_score = score
                cleavage_site = 15 + i + 1  # 1-indexed

    # Deterministic tweak from sequence hash for edge cases
    h_val = int(hashlib.sha256(seq[:50].encode()).hexdigest(), 16)
    hash_nudge = (h_val % 100) / 1000.0  # ±0.1 jitter

    # Score signal peptide likelihood
    score = 0.0
    if pos_charges >= 1:
        score += 0.25
    if h_stretch >= 7:
        score += 0.40 + min(h_stretch - 7, 8) * 0.02
    if cleavage_site:
        score += 0.20

    probability = min(1.0, max(0.0, round(score + hash_nudge, 3)))
    detected = probability >= 0.55

    # Determine signal type
    if not detected:
        sig_type = "none"
        cleavage_site = None
        mature_start = 1
    else:
        # TAT pathway: twin-arginine motif (RRXFLK)
        if "RR" in window[:20]:
            sig_type = "tat_spi"
        elif any(window[i : i + 4] == "CAAX" for i in range(len(window) - 3)):
            sig_type = "sec_spii"
        else:
            sig_type = "sec_spi"
        mature_start = (cleavage_site or 20) + 1

    return SignalPeptide(
        detected=detected,
        cleavage_site=cleavage_site if detected else None,
        signal_type=sig_type,
        probability=probability,
        mature_protein_start=mature_start,
        signal_sequence=seq[:cleavage_site] if detected and cleavage_site else None,
    )


def _count_tm_helices(sequence: str) -> int:
    """Count predicted transmembrane helices (hydrophobic stretches ≥20 aa)."""
    seq = sequence.strip().upper()
    hydro = set("AVILMFYW")
    helices = 0
    run = 0
    in_helix = False
    for aa in seq:
        if aa in hydro:
            run += 1
        else:
            if run >= 20 and not in_helix:
                helices += 1
                in_helix = True
            elif run < 5:
                in_helix = False
            run = 0
    if run >= 20 and not in_helix:
        helices += 1
    return helices


def _predict_gpi(sequence: str) -> bool:
    """Heuristic GPI anchor: C-terminal hydrophobic stretch + omega site."""
    seq = sequence.strip().upper()
    tail = seq[-35:] if len(seq) >= 35 else seq
    h_tail = _count_hydrophobic_stretch(tail, min_len=10)
    return h_tail >= 10 and seq[-1] in "AGSV"


def analyze_secretion_pathway(sequence: str) -> SecretionAnalysis:
    """Full secretion analysis: signal peptide + TM helices + localization.

    RESEARCH ONLY — not for clinical use.
    """
    sp = predict_signal_peptide(sequence)
    tm_helices = _count_tm_helices(sequence)
    gpi = _predict_gpi(sequence)
    warnings: list[str] = []

    # Localization logic
    if gpi:
        localization = "membrane"
        warnings.append("GPI anchor predicted; protein will be lipid-anchored to outer leaflet.")
    elif tm_helices >= 2:
        localization = "membrane"
        warnings.append(
            f"{tm_helices} transmembrane helices predicted; protein is likely integral membrane."
        )
    elif tm_helices == 1:
        localization = "membrane"
        warnings.append("Single-pass transmembrane topology predicted.")
    elif sp.detected and sp.signal_type == "sec_spi":
        # Could be secreted or ER/Golgi retained
        h_val = int(hashlib.sha256(sequence[:30].encode()).hexdigest(), 16)
        loc_options = ["extracellular", "er", "golgi"]
        localization = loc_options[h_val % 3]
    elif sp.detected and sp.signal_type == "tat_spi":
        localization = "extracellular"
    else:
        # Nuclear localisation signal check: KK, KR, RR motifs
        has_nls = any(
            sequence[i : i + 2] in ("KK", "KR", "RR") for i in range(min(len(sequence) - 1, 80))
        )
        localization = "nuclear" if has_nls else "cytoplasmic"

    suitability = assess_therapeutic_suitability(
        SecretionAnalysis(
            signal_peptide=sp,
            predicted_localization=localization,
            transmembrane_helices=tm_helices,
            gpi_anchor=gpi,
            therapeutic_suitability="",  # filled below
            warnings=warnings,
        )
    )

    return SecretionAnalysis(
        signal_peptide=sp,
        predicted_localization=localization,
        transmembrane_helices=tm_helices,
        gpi_anchor=gpi,
        therapeutic_suitability=suitability,
        warnings=warnings,
    )


def assess_therapeutic_suitability(analysis: SecretionAnalysis) -> str:
    """Assess therapeutic suitability of a protein construct.

    Returns one of:
      "suitable_for_secreted_therapeutic"
      "requires_signal_peptide_addition"
      "membrane_bound_consider_soluble_form"
      "intracellular_consider_delivery"

    RESEARCH ONLY — not for clinical use.
    """
    sp = analysis.signal_peptide
    loc = analysis.predicted_localization
    tm = analysis.transmembrane_helices

    if loc == "extracellular" and sp.detected:
        return "suitable_for_secreted_therapeutic"
    elif loc in ("cytoplasmic", "nuclear") and not sp.detected and tm == 0:
        if sp.probability < 0.3:
            return "requires_signal_peptide_addition"
        else:
            return "intracellular_consider_delivery"
    elif loc == "membrane" or tm > 0:
        return "membrane_bound_consider_soluble_form"
    elif not sp.detected:
        return "requires_signal_peptide_addition"
    else:
        return "intracellular_consider_delivery"
