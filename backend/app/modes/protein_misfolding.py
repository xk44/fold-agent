"""Protein Misfolding Mode.

Provides:
  - Misfolding risk assessment per gene/mutation
  - Aggregation-prone region identification (hydrophobicity + beta-sheet propensity)
  - Pharmacological chaperone target lookup
  - Prion-like domain detection (Q/N-rich windows)
  - Lysosomal storage disorder analysis
  - Neurodegeneration structural analysis (Alzheimer's, Parkinson's, ALS, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Misfolding disease map
# ---------------------------------------------------------------------------

MISFOLDING_DISEASES: dict[str, str] = {
    "APP": "Alzheimer's disease (amyloid-β aggregation)",
    "PSEN1": "Alzheimer's disease (amyloid-β aggregation)",
    "PSEN2": "Alzheimer's disease (amyloid-β aggregation)",
    "SNCA": "Parkinson's disease (α-synuclein aggregation)",
    "HTT": "Huntington's disease (huntingtin polyQ expansion)",
    "SOD1": "Amyotrophic lateral sclerosis (ALS)",
    "PRNP": "Prion diseases (CJD, GSS, FFI)",
    "CFTR": "Cystic fibrosis (ΔF508 misfolding)",
    "TTR": "Transthyretin amyloidosis",
    "GBA": "Gaucher disease (GCase misfolding)",
    "HBB": "Sickle cell disease (HbS aggregation)",
    "SERPINA1": "α1-antitrypsin deficiency",
    "FGA": "Fibrinogen amyloidosis",
    "FGB": "Fibrinogen amyloidosis",
    "LYST": "Chédiak-Higashi syndrome",
    "ATP7B": "Wilson's disease (copper transporter misfolding)",
    "HEXA": "Tay-Sachs disease (β-hexosaminidase A deficiency)",
}

# ---------------------------------------------------------------------------
# Destabilizing mutation patterns (rough heuristics)
# ---------------------------------------------------------------------------

# Mutations known to be especially destabilizing (proline disrupts secondary
# structure; glycine breaks alpha-helices; introduction of charged residues in
# hydrophobic cores; cysteine disruptions, etc.)
_DESTABILIZING_TO: set[str] = {"P", "G"}  # proline/glycine as replacement
_DESTABILIZING_FROM: set[str] = {"C"}  # loss of structural cysteine

# Known high-risk gene-specific mutations
_KNOWN_DESTABILIZING: dict[str, list[str]] = {
    "CFTR": ["F508del", "ΔF508", "G551D", "R553X", "N1303K", "W1282X"],
    "SOD1": ["A4V", "G93A", "G85R", "H46R", "D90A"],
    "TTR": ["V30M", "V122I", "T60A", "L55P"],
    "SNCA": ["A53T", "A30P", "E46K", "G51D", "H50Q"],
    "PRNP": ["D178N", "E200K", "P102L", "Q212P", "V210I"],
    "GBA": ["N370S", "L444P", "84GG", "IVS2+1"],
    "SERPINA1": ["Z-variant (E342K)", "S-variant (E264V)"],
    "HTT": ["polyQ>36", "polyQ>40"],
    "APP": ["V717I", "K670N/M671L", "A692G"],
    "PSEN1": ["M146L", "L166P", "A246E"],
    "HBB": ["E6V (HbS)", "E6K (HbC)"],
}


def _infer_destabilizing_mutations(gene: str, mutations: list[str] | None) -> list[str]:
    """Return destabilizing mutations: combine known DB with heuristic scan."""
    known = list(_KNOWN_DESTABILIZING.get(gene.upper(), []))
    if mutations:
        for mut in mutations:
            if not mut:
                continue
            # heuristic: replacement to P or G is typically destabilizing
            if len(mut) >= 2 and mut[-1].upper() in _DESTABILIZING_TO:
                if mut not in known:
                    known.append(mut)
    return known


# ---------------------------------------------------------------------------
# MisfoldingRisk
# ---------------------------------------------------------------------------


@dataclass
class MisfoldingRisk:
    gene: str
    risk_level: str  # high / moderate / low
    aggregation_prone_regions: list[dict]
    destabilizing_mutations: list[str]
    known_misfolding_disease: str | None
    confidence: str  # high / moderate / low


def assess_misfolding_risk(
    gene: str,
    mutations: list[str] | None = None,
) -> MisfoldingRisk:
    """Assess misfolding risk for a gene with optional mutation list.

    Risk level heuristics:
      - Known misfolding disease gene → starts at moderate
      - Any known destabilizing mutation present → escalates to high
      - No disease association + no destabilizing mutations → low
    """
    gene_upper = gene.upper()
    disease = MISFOLDING_DISEASES.get(gene_upper)
    destabilizing = _infer_destabilizing_mutations(gene_upper, mutations)

    # Determine risk level
    if disease and destabilizing:
        risk_level = "high"
        confidence = "high"
    elif disease:
        risk_level = "moderate"
        confidence = "moderate"
    elif destabilizing:
        risk_level = "moderate"
        confidence = "low"
    else:
        risk_level = "low"
        confidence = "low"

    # Build aggregation prone region stubs for high-risk genes
    aggregation_prone_regions: list[dict] = []
    _APR_STUBS: dict[str, list[dict]] = {
        "SNCA": [{"start": 61, "end": 95, "mechanism": "amyloid", "note": "NAC region"}],
        "HTT": [{"start": 1, "end": 17, "mechanism": "amyloid", "note": "polyQ flanking"}],
        "SOD1": [{"start": 101, "end": 115, "mechanism": "amorphous", "note": "Greek-key loop"}],
        "PRNP": [{"start": 113, "end": 135, "mechanism": "prion-like", "note": "hydrophobic core"}],
        "TTR": [{"start": 10, "end": 20, "mechanism": "amyloid", "note": "strand A"}],
        "APP": [{"start": 672, "end": 714, "mechanism": "amyloid", "note": "Aβ region"}],
    }
    if gene_upper in _APR_STUBS:
        aggregation_prone_regions = _APR_STUBS[gene_upper]

    return MisfoldingRisk(
        gene=gene_upper,
        risk_level=risk_level,
        aggregation_prone_regions=aggregation_prone_regions,
        destabilizing_mutations=destabilizing,
        known_misfolding_disease=disease,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Aggregation-prone region identification
# ---------------------------------------------------------------------------

# Kyte-Doolittle hydrophobicity scale
HYDROPHOBICITY: dict[str, float] = {
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

# Chou-Fasman beta-sheet propensity
BETA_PROPENSITY: dict[str, float] = {
    "A": 0.83,
    "R": 0.93,
    "N": 0.89,
    "D": 0.54,
    "C": 1.19,
    "Q": 1.10,
    "E": 0.37,
    "G": 0.75,
    "H": 0.87,
    "I": 1.60,
    "L": 1.30,
    "K": 0.74,
    "M": 1.05,
    "F": 1.38,
    "P": 0.55,
    "S": 0.75,
    "T": 1.19,
    "W": 1.37,
    "Y": 1.47,
    "V": 1.70,
}

_WINDOW = 7
_HYDRO_THRESHOLD = 1.5
_BETA_THRESHOLD = 1.1
_APR_COMBINED_THRESHOLD = 2.4  # sum of normalised scores


@dataclass
class AggregationRegion:
    start: int
    end: int
    sequence: str
    score: float
    mechanism: str  # amyloid / amorphous / prion-like


def _window_score(seq_window: str) -> float:
    """Combined hydrophobicity + beta-sheet propensity score for a window."""
    h = sum(HYDROPHOBICITY.get(aa.upper(), 0.0) for aa in seq_window) / len(seq_window)
    b = sum(BETA_PROPENSITY.get(aa.upper(), 1.0) for aa in seq_window) / len(seq_window)
    return h + b


def _classify_mechanism(seq_window: str) -> str:
    """Classify aggregation mechanism from window composition."""
    upper = seq_window.upper()
    qn = sum(1 for aa in upper if aa in "QN")
    if qn / len(upper) > 0.3:
        return "prion-like"
    hydro = sum(HYDROPHOBICITY.get(aa, 0.0) for aa in upper) / len(upper)
    if hydro > 2.0:
        return "amyloid"
    return "amorphous"


def identify_aggregation_regions(protein_sequence: str) -> list[AggregationRegion]:
    """Identify aggregation-prone regions using a sliding window of 7 residues.

    Regions with combined hydrophobicity + beta-sheet propensity score above
    threshold are flagged.  Adjacent flagged windows are merged.
    """
    seq = protein_sequence.upper()
    if len(seq) < _WINDOW:
        return []

    flagged: list[tuple[int, int, float]] = []  # (start, end, score)
    for i in range(len(seq) - _WINDOW + 1):
        window = seq[i : i + _WINDOW]
        score = _window_score(window)
        if score >= _APR_COMBINED_THRESHOLD:
            flagged.append((i, i + _WINDOW - 1, score))

    if not flagged:
        return []

    # Merge overlapping / adjacent windows
    merged: list[AggregationRegion] = []
    cur_start, cur_end, cur_score = flagged[0]
    for start, end, score in flagged[1:]:
        if start <= cur_end + 1:
            cur_end = max(cur_end, end)
            cur_score = max(cur_score, score)
        else:
            window_seq = seq[cur_start : cur_end + 1]
            merged.append(
                AggregationRegion(
                    start=cur_start,
                    end=cur_end,
                    sequence=window_seq,
                    score=round(cur_score, 3),
                    mechanism=_classify_mechanism(window_seq),
                )
            )
            cur_start, cur_end, cur_score = start, end, score

    window_seq = seq[cur_start : cur_end + 1]
    merged.append(
        AggregationRegion(
            start=cur_start,
            end=cur_end,
            sequence=window_seq,
            score=round(cur_score, 3),
            mechanism=_classify_mechanism(window_seq),
        )
    )
    return merged


# ---------------------------------------------------------------------------
# Pharmacological chaperone targets
# ---------------------------------------------------------------------------


@dataclass
class ChaperoneTarget:
    gene: str
    disease: str
    binding_site_residues: list[int]
    known_chaperones: list[str]
    mechanism: str  # stabilization / folding_correction / trafficking_rescue


KNOWN_CHAPERONE_TARGETS: dict[str, ChaperoneTarget] = {
    "GLA": ChaperoneTarget(
        gene="GLA",
        disease="Fabry disease",
        binding_site_residues=[170, 231, 266, 349],
        known_chaperones=["migalastat (AT1001)", "DGJ"],
        mechanism="stabilization",
    ),
    "TTR": ChaperoneTarget(
        gene="TTR",
        disease="Transthyretin amyloidosis",
        binding_site_residues=[10, 16, 54, 57, 98, 119],
        known_chaperones=["tafamidis", "diflunisal", "acoramidis"],
        mechanism="stabilization",
    ),
    "CFTR": ChaperoneTarget(
        gene="CFTR",
        disease="Cystic fibrosis",
        binding_site_residues=[508, 170, 346, 1030],
        known_chaperones=["lumacaftor (VX-809)", "tezacaftor (VX-661)", "elexacaftor (VX-445)"],
        mechanism="folding_correction",
    ),
    "GBA": ChaperoneTarget(
        gene="GBA",
        disease="Gaucher disease",
        binding_site_residues=[228, 341, 345, 368, 444],
        known_chaperones=["isofagomine", "ambroxol", "AT2220"],
        mechanism="stabilization",
    ),
    "HEXA": ChaperoneTarget(
        gene="HEXA",
        disease="Tay-Sachs disease",
        binding_site_residues=[269, 303, 323, 450],
        known_chaperones=["pyrimethamine", "NOEV (N-octyl-valienamine)"],
        mechanism="folding_correction",
    ),
    "GAA": ChaperoneTarget(
        gene="GAA",
        disease="Pompe disease",
        binding_site_residues=[282, 516, 613, 674],
        known_chaperones=["1-deoxynojirimycin", "N-butyl-DNJ", "AT2220 (duvoglustat)"],
        mechanism="trafficking_rescue",
    ),
    "IDUA": ChaperoneTarget(
        gene="IDUA",
        disease="Hurler syndrome (MPS I)",
        binding_site_residues=[178, 245, 292],
        known_chaperones=["laronidase (ERT)", "investigational chaperones"],
        mechanism="folding_correction",
    ),
    "SMPD1": ChaperoneTarget(
        gene="SMPD1",
        disease="Niemann-Pick disease type A/B",
        binding_site_residues=[314, 391, 476],
        known_chaperones=["arimoclomol (investigational)"],
        mechanism="stabilization",
    ),
}


def find_chaperone_targets(gene: str) -> ChaperoneTarget | None:
    """Return pharmacological chaperone target info for a gene, or None."""
    return KNOWN_CHAPERONE_TARGETS.get(gene.upper())


# ---------------------------------------------------------------------------
# Prion-like domain detection
# ---------------------------------------------------------------------------

_PRION_WINDOW = 60
_QN_THRESHOLD = 0.30  # >30% Q+N content


@dataclass
class PrionDomain:
    start: int
    end: int
    sequence: str
    q_n_content: float
    gln_asn_ratio: float  # Q/(Q+N), or 0 if no Q/N
    prion_score: float  # 0–1 composite score


_KNOWN_PRION_PROTEINS: set[str] = {"TDP-43", "FUS", "HNRNPA1", "EWSR1", "TIA1", "ATXN2"}


def _prion_score(seq: str) -> float:
    """Compute a 0-1 prion-like domain score from a window."""
    upper = seq.upper()
    n = len(upper)
    if n == 0:
        return 0.0
    q = upper.count("Q")
    asn = upper.count("N")
    s = upper.count("S")
    y = upper.count("Y")
    g = upper.count("G")
    qn = q + asn
    # Score: QN content + aromatic/disorder enrichment (Y/G)
    base = qn / n
    aromatic_boost = (y + g) / n * 0.3
    return min(1.0, base + aromatic_boost)


def detect_prion_domains(protein_sequence: str) -> list[PrionDomain]:
    """Scan for Q/N-rich prion-like domains using a 60-residue sliding window.

    Regions with >30% Q+N content are flagged and merged.
    """
    seq = protein_sequence.upper()
    if len(seq) < _PRION_WINDOW:
        return []

    flagged: list[tuple[int, int]] = []
    for i in range(len(seq) - _PRION_WINDOW + 1):
        window = seq[i : i + _PRION_WINDOW]
        qn = (window.count("Q") + window.count("N")) / _PRION_WINDOW
        if qn > _QN_THRESHOLD:
            flagged.append((i, i + _PRION_WINDOW - 1))

    if not flagged:
        return []

    # Merge
    merged_ranges: list[tuple[int, int]] = []
    cur_s, cur_e = flagged[0]
    for s, e in flagged[1:]:
        if s <= cur_e + 1:
            cur_e = max(cur_e, e)
        else:
            merged_ranges.append((cur_s, cur_e))
            cur_s, cur_e = s, e
    merged_ranges.append((cur_s, cur_e))

    domains: list[PrionDomain] = []
    for start, end in merged_ranges:
        window_seq = seq[start : end + 1]
        n = len(window_seq)
        q = window_seq.count("Q")
        asn = window_seq.count("N")
        qn_content = (q + asn) / n
        gln_asn_ratio = q / (q + asn) if (q + asn) > 0 else 0.0
        domains.append(
            PrionDomain(
                start=start,
                end=end,
                sequence=window_seq,
                q_n_content=round(qn_content, 3),
                gln_asn_ratio=round(gln_asn_ratio, 3),
                prion_score=round(_prion_score(window_seq), 3),
            )
        )
    return domains


# ---------------------------------------------------------------------------
# Lysosomal storage disorder analysis
# ---------------------------------------------------------------------------


@dataclass
class LSDAnalysis:
    enzyme_gene: str
    disease_name: str
    enzyme_deficiency: str
    substrate_accumulation: str
    available_therapies: list[str]
    therapy_type: str  # ERT / SRT / chaperone / gene_therapy


LYSOSOMAL_STORAGE_DISORDERS: dict[str, LSDAnalysis] = {
    "GBA": LSDAnalysis(
        enzyme_gene="GBA",
        disease_name="Gaucher disease",
        enzyme_deficiency="β-glucocerebrosidase (GCase)",
        substrate_accumulation="glucocerebroside",
        available_therapies=[
            "imiglucerase (Cerezyme)",
            "velaglucerase alfa (VPRIV)",
            "taliglucerase alfa (Elelyso)",
            "miglustat (Zavesca)",
            "eliglustat (Cerdelga)",
        ],
        therapy_type="ERT",
    ),
    "GLA": LSDAnalysis(
        enzyme_gene="GLA",
        disease_name="Fabry disease",
        enzyme_deficiency="α-galactosidase A",
        substrate_accumulation="globotriaosylceramide (Gb3)",
        available_therapies=[
            "agalsidase alfa (Replagal)",
            "agalsidase beta (Fabrazyme)",
            "migalastat (Galafold)",
        ],
        therapy_type="ERT",
    ),
    "GAA": LSDAnalysis(
        enzyme_gene="GAA",
        disease_name="Pompe disease (GSD-II)",
        enzyme_deficiency="acid α-glucosidase",
        substrate_accumulation="glycogen",
        available_therapies=[
            "alglucosidase alfa (Myozyme/Lumizyme)",
            "avalglucosidase alfa (Nexviazyme)",
            "cipaglucosidase alfa + miglustat",
        ],
        therapy_type="ERT",
    ),
    "IDUA": LSDAnalysis(
        enzyme_gene="IDUA",
        disease_name="Hurler syndrome (MPS I)",
        enzyme_deficiency="α-L-iduronidase",
        substrate_accumulation="heparan sulfate, dermatan sulfate",
        available_therapies=["laronidase (Aldurazyme)", "hematopoietic stem cell transplant"],
        therapy_type="ERT",
    ),
    "IDS": LSDAnalysis(
        enzyme_gene="IDS",
        disease_name="Hunter syndrome (MPS II)",
        enzyme_deficiency="iduronate-2-sulfatase",
        substrate_accumulation="heparan sulfate, dermatan sulfate",
        available_therapies=["idursulfase (Elaprase)", "pabinafusp alfa (Hunterase ICV)"],
        therapy_type="ERT",
    ),
    "SGSH": LSDAnalysis(
        enzyme_gene="SGSH",
        disease_name="Sanfilippo syndrome type A (MPS IIIA)",
        enzyme_deficiency="heparan N-sulfatase",
        substrate_accumulation="heparan sulfate",
        available_therapies=[
            "gene therapy (investigational)",
            "substrate reduction (investigational)",
        ],
        therapy_type="gene_therapy",
    ),
    "SMPD1": LSDAnalysis(
        enzyme_gene="SMPD1",
        disease_name="Niemann-Pick disease type A/B",
        enzyme_deficiency="acid sphingomyelinase",
        substrate_accumulation="sphingomyelin",
        available_therapies=["olipudase alfa (Xenpozyme)", "arimoclomol (investigational)"],
        therapy_type="ERT",
    ),
    "GALC": LSDAnalysis(
        enzyme_gene="GALC",
        disease_name="Krabbe disease",
        enzyme_deficiency="galactocerebrosidase",
        substrate_accumulation="galactocerebroside, psychosine",
        available_therapies=["hematopoietic stem cell transplant (neonatal)"],
        therapy_type="gene_therapy",
    ),
    "ARSA": LSDAnalysis(
        enzyme_gene="ARSA",
        disease_name="Metachromatic leukodystrophy (MLD)",
        enzyme_deficiency="arylsulfatase A",
        substrate_accumulation="sulfatide",
        available_therapies=[
            "atidarsagene autotemcel (Libmeldy)",
            "hematopoietic stem cell transplant",
        ],
        therapy_type="gene_therapy",
    ),
    "HEXA": LSDAnalysis(
        enzyme_gene="HEXA",
        disease_name="Tay-Sachs disease",
        enzyme_deficiency="β-hexosaminidase A (α-subunit)",
        substrate_accumulation="GM2 ganglioside",
        available_therapies=[
            "gene therapy (investigational)",
            "substrate reduction (miglustat, investigational)",
        ],
        therapy_type="gene_therapy",
    ),
    "HEXB": LSDAnalysis(
        enzyme_gene="HEXB",
        disease_name="Sandhoff disease",
        enzyme_deficiency="β-hexosaminidase A and B (β-subunit)",
        substrate_accumulation="GM2 ganglioside, globoside",
        available_therapies=[
            "gene therapy (investigational)",
            "substrate reduction (investigational)",
        ],
        therapy_type="gene_therapy",
    ),
    "CLN3": LSDAnalysis(
        enzyme_gene="CLN3",
        disease_name="Batten disease (CLN3/juvenile NCL)",
        enzyme_deficiency="CLN3 (battenin) — lysosomal transmembrane protein",
        substrate_accumulation="ceroid lipofuscin (subunit c of ATP synthase)",
        available_therapies=[
            "cerliponase alfa (Brineura, CLN2)",
            "gene therapy (investigational for CLN3)",
        ],
        therapy_type="gene_therapy",
    ),
}


def analyze_lsd(gene: str) -> LSDAnalysis | None:
    """Return LSD analysis for a gene, or None if not in the database."""
    return LYSOSOMAL_STORAGE_DISORDERS.get(gene.upper())


# ---------------------------------------------------------------------------
# Neurodegeneration structural analysis
# ---------------------------------------------------------------------------


@dataclass
class NeurodegAnalysis:
    disease: str
    key_protein: str
    aggregation_mechanism: str
    known_mutations: list[str]
    therapeutic_strategies: list[str]
    structural_targets: list[str]


_NEURODEG_DB: dict[str, NeurodegAnalysis] = {
    "alzheimers": NeurodegAnalysis(
        disease="Alzheimer's disease",
        key_protein="Amyloid-β (Aβ) and Tau",
        aggregation_mechanism=(
            "Amyloid precursor protein (APP) cleaved by β- and γ-secretase generates Aβ42/40 "
            "peptides that form oligomers → protofibrils → amyloid plaques; "
            "hyperphosphorylated tau forms neurofibrillary tangles"
        ),
        known_mutations=[
            "APP V717I",
            "APP K670N/M671L",
            "PSEN1 M146L",
            "PSEN1 L166P",
            "PSEN2 N141I",
        ],
        therapeutic_strategies=[
            "β-secretase (BACE1) inhibitors",
            "γ-secretase modulators",
            "anti-Aβ immunotherapy (lecanemab, donanemab)",
            "anti-tau immunotherapy",
            "tau aggregation inhibitors",
        ],
        structural_targets=[
            "Aβ42 fibril core (U-shaped β-arch)",
            "Tau PHF core (residues 306-378)",
            "BACE1 active site",
            "γ-secretase presenilin catalytic domain",
        ],
    ),
    "parkinsons": NeurodegAnalysis(
        disease="Parkinson's disease",
        key_protein="α-synuclein (SNCA)",
        aggregation_mechanism=(
            "α-synuclein misfolds from helical membrane-bound state to β-sheet-rich "
            "amyloid fibrils; Lewy body formation; NAC region (residues 61-95) drives "
            "aggregation nucleation"
        ),
        known_mutations=[
            "SNCA A53T",
            "SNCA A30P",
            "SNCA E46K",
            "SNCA G51D",
            "LRRK2 G2019S",
            "PARKIN exon 3 deletion",
        ],
        therapeutic_strategies=[
            "α-synuclein aggregation inhibitors (ANLE138b)",
            "anti-α-synuclein immunotherapy (prasinezumab)",
            "LRRK2 kinase inhibitors",
            "GBA chaperones (ambroxol)",
            "autophagy enhancers",
        ],
        structural_targets=[
            "α-synuclein NAC region (61-95)",
            "α-synuclein fibril polymorph structures",
            "LRRK2 kinase domain",
            "GBA active site",
        ],
    ),
    "als": NeurodegAnalysis(
        disease="Amyotrophic lateral sclerosis (ALS)",
        key_protein="SOD1 and TDP-43",
        aggregation_mechanism=(
            "SOD1 mutations destabilize the β-barrel fold leading to amorphous aggregation; "
            "TDP-43 (TARDBP) mislocalizes from nucleus to cytoplasm forming stress granule-seeded "
            "aggregates; FUS follows similar prion-like aggregation"
        ),
        known_mutations=[
            "SOD1 A4V",
            "SOD1 G93A",
            "SOD1 H46R",
            "TARDBP A315T",
            "FUS R521C",
            "C9orf72 GGGGCC repeat",
        ],
        therapeutic_strategies=[
            "SOD1 antisense oligonucleotides (tofersen)",
            "TDP-43 nuclear retention strategies",
            "C9orf72 repeat-targeting ASOs",
            "riluzole (glutamate excitotoxicity)",
            "edaravone (oxidative stress)",
        ],
        structural_targets=[
            "SOD1 β-barrel dimer interface",
            "TDP-43 RNA recognition motifs",
            "TDP-43 C-terminal prion-like domain",
            "FUS low-complexity domain",
        ],
    ),
    "huntingtons": NeurodegAnalysis(
        disease="Huntington's disease",
        key_protein="Huntingtin (HTT)",
        aggregation_mechanism=(
            "CAG trinucleotide repeat expansion (>36 repeats) in exon 1 of HTT encodes "
            "polyglutamine (polyQ) tract; polyQ >40 leads to misfolding, intranuclear inclusions, "
            "and transcriptional dysregulation"
        ),
        known_mutations=[
            "HTT polyQ>36 (reduced penetrance)",
            "HTT polyQ>40 (full penetrance)",
            "HTT polyQ>60 (juvenile onset)",
        ],
        therapeutic_strategies=[
            "HTT-lowering ASOs (tominersen)",
            "RNAi/siRNA HTT silencing",
            "polyQ aggregation inhibitors",
            "transglutaminase inhibitors",
            "mitochondrial dysfunction rescue",
        ],
        structural_targets=[
            "HTT exon 1 polyQ fibril core",
            "N-terminal 17-aa amphipathic helix (membrane anchor)",
            "HTT HEAT repeat solenoid",
        ],
    ),
    "prion": NeurodegAnalysis(
        disease="Prion diseases (CJD, GSS, FFI, scrapie)",
        key_protein="PrP (PRNP)",
        aggregation_mechanism=(
            "Cellular prion protein PrP^C (α-helix-rich) undergoes conformational conversion "
            "to PrP^Sc (β-sheet-rich scrapie form); PrP^Sc acts as a template propagating "
            "misfolding in a self-catalytic prion mechanism"
        ),
        known_mutations=[
            "PRNP D178N (FFI)",
            "PRNP E200K (sCJD)",
            "PRNP P102L (GSS)",
            "PRNP V210I",
            "PRNP Q212P",
        ],
        therapeutic_strategies=[
            "PrP^C expression reduction (ASOs, RNAi)",
            "anti-PrP immunotherapy",
            "small molecule PrP^Sc inhibitors (anle138b, quinacrine)",
            "compounds stabilizing PrP^C fold",
        ],
        structural_targets=[
            "PrP^C GPI-anchored globular domain (helices 2-3)",
            "PrP^Sc parallel in-register β-sheet core",
            "PrP copper-binding octapeptide repeat region",
        ],
    ),
}

# Aliases
_NEURODEG_ALIASES: dict[str, str] = {
    "alzheimer": "alzheimers",
    "alzheimer's": "alzheimers",
    "parkinson": "parkinsons",
    "parkinson's": "parkinsons",
    "amyotrophic lateral sclerosis": "als",
    "huntington": "huntingtons",
    "huntington's": "huntingtons",
    "prion disease": "prion",
    "creutzfeldt-jakob": "prion",
    "cjd": "prion",
}


def analyze_neurodegeneration(disease: str) -> NeurodegAnalysis | None:
    """Return neurodegenerative disease structural analysis, or None if not found."""
    key = disease.lower().strip()
    resolved = _NEURODEG_ALIASES.get(key, key)
    return _NEURODEG_DB.get(resolved)
