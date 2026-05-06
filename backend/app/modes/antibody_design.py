"""Antibody Design Mode — Computational Antibody Engineering Pipeline.

Provides:
  - Antibody-antigen docking (AF3 stub, multi-seed)
  - Nanobody binding prediction
  - De novo binder design (RFdiffusion + ProteinMPNN pipeline stub)
  - Checkpoint inhibitor analysis
  - CDR loop modeling
  - Antibody humanization assessment
  - Bispecific antibody design
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Known antibody targets
# ---------------------------------------------------------------------------

KNOWN_ANTIBODY_TARGETS: dict[str, dict] = {
    "PD-1": {
        "full_name": "Programmed Cell Death Protein 1",
        "gene": "PDCD1",
        "approved_antibodies": ["Pembrolizumab", "Nivolumab", "Cemiplimab"],
        "indication": ["melanoma", "NSCLC", "Hodgkin lymphoma", "MSI-H tumors"],
        "target_class": "immune_checkpoint",
    },
    "PD-L1": {
        "full_name": "Programmed Death-Ligand 1",
        "gene": "CD274",
        "approved_antibodies": ["Atezolizumab", "Durvalumab", "Avelumab"],
        "indication": ["urothelial", "NSCLC", "triple-negative breast cancer"],
        "target_class": "immune_checkpoint",
    },
    "CTLA-4": {
        "full_name": "Cytotoxic T-Lymphocyte-Associated Protein 4",
        "gene": "CTLA4",
        "approved_antibodies": ["Ipilimumab", "Tremelimumab"],
        "indication": ["melanoma", "HCC", "NSCLC"],
        "target_class": "immune_checkpoint",
    },
    "HER2": {
        "full_name": "Human Epidermal Growth Factor Receptor 2",
        "gene": "ERBB2",
        "approved_antibodies": ["Trastuzumab", "Pertuzumab", "Trastuzumab deruxtecan"],
        "indication": ["breast cancer", "gastric cancer"],
        "target_class": "receptor_tyrosine_kinase",
    },
    "EGFR": {
        "full_name": "Epidermal Growth Factor Receptor",
        "gene": "EGFR",
        "approved_antibodies": ["Cetuximab", "Panitumumab"],
        "indication": ["colorectal", "head and neck", "NSCLC"],
        "target_class": "receptor_tyrosine_kinase",
    },
    "CD20": {
        "full_name": "B-Lymphocyte Antigen CD20",
        "gene": "MS4A1",
        "approved_antibodies": ["Rituximab", "Ofatumumab", "Obinutuzumab"],
        "indication": ["NHL", "CLL", "follicular lymphoma"],
        "target_class": "B_cell_surface_antigen",
    },
    "VEGF": {
        "full_name": "Vascular Endothelial Growth Factor A",
        "gene": "VEGFA",
        "approved_antibodies": ["Bevacizumab", "Ramucirumab"],
        "indication": ["colorectal", "NSCLC", "glioblastoma", "renal"],
        "target_class": "angiogenesis_factor",
    },
    "TNF-alpha": {
        "full_name": "Tumor Necrosis Factor Alpha",
        "gene": "TNF",
        "approved_antibodies": ["Adalimumab", "Infliximab", "Certolizumab"],
        "indication": ["rheumatoid arthritis", "Crohn's disease", "psoriasis"],
        "target_class": "cytokine",
    },
    "IL-6R": {
        "full_name": "Interleukin-6 Receptor",
        "gene": "IL6R",
        "approved_antibodies": ["Tocilizumab", "Sarilumab"],
        "indication": ["rheumatoid arthritis", "cytokine release syndrome", "giant cell arteritis"],
        "target_class": "cytokine_receptor",
    },
    "CD19": {
        "full_name": "B-Lymphocyte Antigen CD19",
        "gene": "CD19",
        "approved_antibodies": ["Blinatumomab", "Tafasitamab", "Loncastuximab"],
        "indication": ["ALL", "DLBCL", "relapsed B-cell malignancies"],
        "target_class": "B_cell_surface_antigen",
    },
    "LAG-3": {
        "full_name": "Lymphocyte Activation Gene-3",
        "gene": "LAG3",
        "approved_antibodies": ["Relatlimab"],
        "indication": ["melanoma (combined with PD-1)"],
        "target_class": "immune_checkpoint",
    },
    "TIGIT": {
        "full_name": "T Cell Immunoreceptor with Ig and ITIM Domains",
        "gene": "TIGIT",
        "approved_antibodies": ["Tiragolumab (investigational)"],
        "indication": ["NSCLC", "SCLC (investigational)"],
        "target_class": "immune_checkpoint",
    },
    "CD38": {
        "full_name": "ADP-Ribosyl Cyclase 1",
        "gene": "CD38",
        "approved_antibodies": ["Daratumumab", "Isatuximab"],
        "indication": ["multiple myeloma"],
        "target_class": "plasma_cell_antigen",
    },
    "RANKL": {
        "full_name": "Receptor Activator of Nuclear Factor Kappa-B Ligand",
        "gene": "TNFSF11",
        "approved_antibodies": ["Denosumab"],
        "indication": ["osteoporosis", "bone metastases", "GCTB"],
        "target_class": "cytokine",
    },
    "PCSK9": {
        "full_name": "Proprotein Convertase Subtilisin/Kexin Type 9",
        "gene": "PCSK9",
        "approved_antibodies": ["Evolocumab", "Alirocumab"],
        "indication": ["hypercholesterolemia", "cardiovascular disease prevention"],
        "target_class": "metabolic_enzyme",
    },
}


# ---------------------------------------------------------------------------
# Known nanobodies
# ---------------------------------------------------------------------------

KNOWN_NANOBODIES: dict[str, dict] = {
    "caplacizumab": {
        "target": "vWF",
        "target_gene": "VWF",
        "cdr3": "AAAGSGYSSS",
        "indication": "acquired thrombotic thrombocytopenic purpura",
        "kd_nm": 0.31,
        "format": "bivalent_nanobody",
    },
    "ozoralizumab": {
        "target": "TNF-alpha",
        "target_gene": "TNF",
        "cdr3": "ARDFGYYYYGMDV",
        "indication": "rheumatoid arthritis",
        "kd_nm": 0.18,
        "format": "trivalent_bispecific_nanobody",
    },
    "sonelokimab": {
        "target": "IL-17A",
        "target_gene": "IL17A",
        "cdr3": "AARGSSYYYY",
        "indication": "psoriasis",
        "kd_nm": 0.04,
        "format": "bivalent_nanobody",
    },
    "abelacimab": {
        "target": "Factor XI",
        "target_gene": "F11",
        "cdr3": "AARDSSYYYR",
        "indication": "atrial fibrillation / thrombosis prevention",
        "kd_nm": 2.1,
        "format": "monovalent_nanobody",
    },
    "lulizumab": {
        "target": "CD28",
        "target_gene": "CD28",
        "cdr3": "AATGGSYYYS",
        "indication": "lupus (investigational)",
        "kd_nm": 14.0,
        "format": "monovalent_nanobody",
    },
    "nb_pd_l1_001": {
        "target": "PD-L1",
        "target_gene": "CD274",
        "cdr3": "AARYGGSSYY",
        "indication": "solid tumors (preclinical)",
        "kd_nm": 5.5,
        "format": "monovalent_nanobody",
    },
    "nb_her2_002": {
        "target": "HER2",
        "target_gene": "ERBB2",
        "cdr3": "AARSYGGYYY",
        "indication": "HER2-positive breast cancer (preclinical)",
        "kd_nm": 3.2,
        "format": "biparatopic_nanobody",
    },
    "nb_egfr_003": {
        "target": "EGFR",
        "target_gene": "EGFR",
        "cdr3": "AARFYYSYYY",
        "indication": "EGFR-driven tumors (preclinical)",
        "kd_nm": 8.7,
        "format": "monovalent_nanobody",
    },
}


# ---------------------------------------------------------------------------
# Checkpoint inhibitor data
# ---------------------------------------------------------------------------

_CHECKPOINT_DATA: dict[str, dict] = {
    "PD-1": {
        "drug_name": "Pembrolizumab / Nivolumab",
        "mechanism": (
            "Blocks PD-1/PD-L1 axis, preventing T-cell exhaustion and restoring "
            "cytotoxic anti-tumor immunity"
        ),
        "binding_interface": [
            "PD-1 CC' loop (Asn58, Thr59, Thr76)",
            "BC loop (Leu128, Ile126)",
            "FG loop (Tyr68, Met70)",
        ],
        "resistance_mutations": [
            "PDCD1 loss-of-function",
            "CD274 amplification",
            "JAK1/JAK2 inactivating mutations",
            "B2M loss",
            "STK11/LKB1 mutation",
        ],
    },
    "PD-L1": {
        "drug_name": "Atezolizumab / Durvalumab / Avelumab",
        "mechanism": (
            "Blocks PD-L1 binding to PD-1 and CD80, preventing adaptive immune "
            "resistance in tumor microenvironment"
        ),
        "binding_interface": [
            "CD274 IgV domain (Tyr56, Glu58, Arg113)",
            "CC' loop contacts",
            "GFCC' face of IgV domain",
        ],
        "resistance_mutations": [
            "CD274 exon 3 splice mutation",
            "POLE/POLD1 mutations (hypermutation bypass)",
            "CMTM6 loss (PD-L1 stabilization loss)",
            "AP1/2 complex mutations (antigen presentation)",
        ],
    },
    "CTLA-4": {
        "drug_name": "Ipilimumab / Tremelimumab",
        "mechanism": (
            "Blocks CTLA-4/CD80/CD86 interaction, releasing brake on early T-cell "
            "activation in lymph nodes; also depletes Treg in TME"
        ),
        "binding_interface": [
            "CTLA4 MYPPPY motif (Met99, Tyr100, Pro101, Pro102, Pro103)",
            "FG loop residues Tyr104",
            "Hydrophobic core contacts with CD80 domain",
        ],
        "resistance_mutations": [
            "CTLA4 coding variants (rare)",
            "FOXP3+ Treg expansion",
            "IDO1 upregulation",
            "Wnt/beta-catenin activation (T-cell exclusion)",
        ],
    },
    "LAG-3": {
        "drug_name": "Relatlimab",
        "mechanism": (
            "Blocks LAG-3 interaction with MHC class II and FGL1, restoring "
            "exhausted T-cell function; synergizes with PD-1 blockade"
        ),
        "binding_interface": [
            "LAG-3 D1 domain loop (Lys73, Arg75, Glu90)",
            "Extra loop between D1 and D2",
            "Fibrinogen-like domain contacts",
        ],
        "resistance_mutations": [
            "LAG3 splice variants",
            "Compensatory TIM-3 upregulation",
            "TIGIT co-expression",
        ],
    },
    "TIM-3": {
        "drug_name": "Sabatolimab (investigational)",
        "mechanism": (
            "Blocks TIM-3/Galectin-9 interaction, restoring T-cell function; "
            "also affects HMGB1 and phosphatidylserine signaling"
        ),
        "binding_interface": [
            "TIM-3 IgV domain CC' loop",
            "FG loop (His58, Tyr82)",
            "Galectin-9 carbohydrate recognition domain contacts",
        ],
        "resistance_mutations": [
            "HAVCR2 loss (rare)",
            "LAG-3 compensatory upregulation",
            "TIGIT upregulation in TME",
        ],
    },
    "TIGIT": {
        "drug_name": "Tiragolumab / Ociperlimab (investigational)",
        "mechanism": (
            "Blocks TIGIT/CD155 (PVR) interaction on NK and T cells, "
            "enhancing cytotoxic anti-tumor activity; synergizes with PD-L1"
        ),
        "binding_interface": [
            "TIGIT IgV domain (Ser131, Arg135)",
            "CC' loop contacts with CD155",
            "FG loop Tyr113",
        ],
        "resistance_mutations": [
            "CD155 overexpression persistence",
            "NK cell dysfunction beyond TIGIT axis",
            "TIM-3 compensatory upregulation",
            "PVR amplification",
        ],
    },
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DockingResult:
    antibody_id: str
    antigen_gene: str
    interface_residues: list[int]
    binding_score: float  # kcal/mol, more negative = better
    rmsd_estimate: float  # Angstrom
    epitope_type: str  # "linear" | "conformational"
    confidence: str  # "high" | "medium" | "low"


@dataclass
class NanobodyHit:
    nanobody_id: str
    target: str
    cdr3_sequence: str
    binding_score: float  # kcal/mol
    epitope_residues: list[int]
    kd_estimate_nm: float


@dataclass
class DesignedBinder:
    backbone_pdb: str  # mock PDB stub string
    designed_sequence: str
    target_gene: str
    hotspot_residues: list[int]
    binding_energy_estimate: float  # kcal/mol
    design_method: str  # "rfdiffusion" | "proteinmpnn" | "rfdiffusion+proteinmpnn"


@dataclass
class CheckpointAnalysis:
    target: str
    drug_name: str
    mechanism: str
    binding_interface: list[str]
    resistance_mutations: list[str]


@dataclass
class CDRRegion:
    name: str  # "H1" | "H2" | "H3" | "L1" | "L2" | "L3"
    start: int
    end: int
    sequence: str
    length: int
    loop_type: str  # "heavy" | "light"


@dataclass
class HumanizationResult:
    original_sequence: str
    humanized_sequence: str
    framework_identity: float  # 0-1, fraction matching human germline
    cdr_preserved: bool
    risk_score: float  # 0-1, immunogenicity risk


@dataclass
class BispecificDesign:
    arm1_target: str
    arm2_target: str
    format: str  # "BiTE" | "DVD-Ig" | "knobs-in-holes"
    linker_sequence: str


# ---------------------------------------------------------------------------
# Antibody-antigen docking (AF3 stub)
# ---------------------------------------------------------------------------

_LINKER_SEQS: dict[str, str] = {
    "BiTE": "GGGGSGGGGS",
    "DVD-Ig": "PAPAP",
    "knobs-in-holes": "DKTHTCPPCPAPELLGGPSVFLFPPKPKDTLMISR",
}

_EPITOPE_TYPE_BY_TARGET: dict[str, str] = {
    "PD-1": "conformational",
    "PD-L1": "conformational",
    "CTLA-4": "conformational",
    "HER2": "conformational",
    "EGFR": "conformational",
    "CD20": "linear",
    "VEGF": "linear",
    "TNF-alpha": "conformational",
    "IL-6R": "conformational",
    "CD19": "linear",
    "LAG-3": "conformational",
    "TIGIT": "conformational",
    "CD38": "conformational",
    "RANKL": "linear",
    "PCSK9": "conformational",
}


def dock_antibody_antigen(
    antibody_sequence: str,
    antigen_gene: str,
    n_seeds: int = 10,
) -> list[DockingResult]:
    """Stub multi-seed AF3-style antibody-antigen docking.

    Returns mock DockingResult objects with varied scores across seeds.
    Scores are deterministically derived from sequence + gene hash for
    reproducibility.
    """
    gene_upper = antigen_gene.upper()
    seq_hash = int(hashlib.md5(antibody_sequence.encode()).hexdigest(), 16)
    epitope_type = _EPITOPE_TYPE_BY_TARGET.get(antigen_gene, "conformational")

    results: list[DockingResult] = []
    for seed in range(n_seeds):
        # Deterministic variation per seed
        variation = ((seq_hash + seed * 7919) % 1000) / 1000.0  # 0..1
        base_score = -9.5 - variation * 2.5  # -9.5 to -12.0
        rmsd = 1.2 + variation * 2.8  # 1.2 to 4.0 Å

        # Interface residues: deterministic set per seed
        seed_offset = (seed * 13 + seq_hash) % 30
        interface = sorted(
            set(
                [
                    100 + seed_offset,
                    105 + seed_offset,
                    112 + seed_offset,
                    200 + seed_offset % 20,
                    207 + seed_offset % 15,
                    215 + seed_offset % 10,
                ]
            )
        )

        confidence = "high" if variation < 0.33 else ("medium" if variation < 0.66 else "low")

        results.append(
            DockingResult(
                antibody_id=f"ab_{gene_upper}_seed{seed:02d}",
                antigen_gene=gene_upper,
                interface_residues=interface,
                binding_score=round(base_score, 3),
                rmsd_estimate=round(rmsd, 3),
                epitope_type=epitope_type,
                confidence=confidence,
            )
        )

    # Sort by binding score (most negative first)
    results.sort(key=lambda r: r.binding_score)
    return results


# ---------------------------------------------------------------------------
# Nanobody binding prediction
# ---------------------------------------------------------------------------


def predict_nanobody_binding(
    nanobody_sequence: str,
    target_gene: str,
) -> NanobodyHit:
    """Stub nanobody binding prediction.

    Checks known nanobody database for target_gene match, otherwise
    returns a de-novo predicted hit derived from sequence hash.
    """
    gene_upper = target_gene.upper()
    seq_hash = int(hashlib.md5(nanobody_sequence.encode()).hexdigest(), 16)

    # Check known nanobodies first
    for nb_id, nb_data in KNOWN_NANOBODIES.items():
        if nb_data["target_gene"].upper() == gene_upper:
            variation = (seq_hash % 100) / 100.0
            epitope_residues = [
                nb_data.get("kd_nm", 5) * 10 + i * 7  # deterministic but plausible
                for i in range(6)
            ]
            return NanobodyHit(
                nanobody_id=nb_id,
                target=nb_data["target"],
                cdr3_sequence=nb_data["cdr3"],
                binding_score=round(-8.2 - variation * 2.0, 3),
                epitope_residues=[int(r) for r in epitope_residues],
                kd_estimate_nm=round(nb_data["kd_nm"] * (1.0 + variation * 0.3), 3),
            )

    # De-novo prediction for unlisted targets
    variation = (seq_hash % 1000) / 1000.0
    epitope_residues = [50 + i * 11 + (seq_hash % 5) for i in range(6)]
    cdr3_len = 10 + seq_hash % 8
    cdr3_stub = (
        nanobody_sequence[-cdr3_len:] if len(nanobody_sequence) >= cdr3_len else nanobody_sequence
    )

    return NanobodyHit(
        nanobody_id=f"nb_denovo_{gene_upper[:4].lower()}",
        target=gene_upper,
        cdr3_sequence=cdr3_stub,
        binding_score=round(-6.5 - variation * 3.0, 3),
        epitope_residues=sorted(set(epitope_residues)),
        kd_estimate_nm=round(20.0 + variation * 180.0, 3),
    )


# ---------------------------------------------------------------------------
# De novo binder design (RFdiffusion + ProteinMPNN pipeline stub)
# ---------------------------------------------------------------------------

_DESIGN_SEQUENCES: dict[str, str] = {
    "rfdiffusion": (
        "MAEVIRLFQGSSPVTQTLAKSVGDRAVLSCTSPRSQHNLYWYRQTPSQGLFQLLSYYGAGNTDKGEIPDRFSGSSDPQNTLYLIIQNLEDSATYFCASSYGG"
        "GYTFGSGTKLTVL"
    ),
    "proteinmpnn": (
        "MKVLSLLYLLTALPGAEASEVQLVQSGAEVKKPGASVKVSCKASGYTFTSYWMHWVRQAPGQGLEWMGEINPSRGSTNYNEKFKSRVTMTTDTSTTTAYME"
        "LRSLRSDDTAVYYCAR"
    ),
    "rfdiffusion+proteinmpnn": (
        "MEVQLVQSGAEVKKPGASVKVSCKASGYTFTSYWMHWVRQAPGQGLEWMGEVINPYRGSTSYNQKFQGRVTMTTDTSTTTAYMELRSLRSDDTAVYYCTR"
        "GGSYFDYWGQGTLVTV"
    ),
}

_BACKBONE_PDB_STUB = (
    "ATOM      1  N   GLY A   1       1.000   1.000   1.000  1.00  0.00           N\n"
    "ATOM      2  CA  GLY A   1       1.458   2.347   1.000  1.00  0.00           C\n"
    "ATOM      3  C   GLY A   1       2.971   2.347   1.000  1.00  0.00           C\n"
    "ATOM      4  O   GLY A   1       3.702   1.358   1.000  1.00  0.00           O\n"
    "END\n"
)


def design_binder(
    target_gene: str,
    hotspot_residues: list[int],
    method: str = "rfdiffusion",
) -> DesignedBinder:
    """Stub de novo binder design using RFdiffusion / ProteinMPNN pipeline.

    Supported methods: rfdiffusion, proteinmpnn, rfdiffusion+proteinmpnn.
    Returns a DesignedBinder with a mock backbone PDB stub and designed sequence.
    """
    gene_upper = target_gene.upper()
    valid_methods = {"rfdiffusion", "proteinmpnn", "rfdiffusion+proteinmpnn"}
    if method not in valid_methods:
        method = "rfdiffusion"

    hotspot_hash = sum(hotspot_residues) if hotspot_residues else 0
    binding_energy = round(-12.0 - (hotspot_hash % 50) / 10.0, 2)

    return DesignedBinder(
        backbone_pdb=_BACKBONE_PDB_STUB,
        designed_sequence=_DESIGN_SEQUENCES[method],
        target_gene=gene_upper,
        hotspot_residues=sorted(hotspot_residues),
        binding_energy_estimate=binding_energy,
        design_method=method,
    )


# ---------------------------------------------------------------------------
# Checkpoint inhibitor analysis
# ---------------------------------------------------------------------------


def analyze_checkpoint_target(target: str) -> CheckpointAnalysis | None:
    """Return checkpoint inhibitor analysis for a known immune checkpoint target.

    Returns None for unknown targets.
    Covers: PD-1, PD-L1, CTLA-4, LAG-3, TIM-3, TIGIT.
    """
    data = _CHECKPOINT_DATA.get(target)
    if data is None:
        return None
    return CheckpointAnalysis(
        target=target,
        drug_name=data["drug_name"],
        mechanism=data["mechanism"],
        binding_interface=list(data["binding_interface"]),
        resistance_mutations=list(data["resistance_mutations"]),
    )


# ---------------------------------------------------------------------------
# CDR loop modeling (Kabat-like heuristics)
# ---------------------------------------------------------------------------

# Approximate Kabat CDR positions for a typical ~120aa VH + ~107aa VL antibody
# These are positional heuristics: (start, end) in 1-based amino acid numbering
_KABAT_CDR_POSITIONS: dict[str, tuple[int, int]] = {
    "H1": (26, 35),
    "H2": (50, 65),
    "H3": (95, 102),
    "L1": (24, 34),
    "L2": (50, 56),
    "L3": (89, 97),
}


def identify_cdr_regions(antibody_sequence: str) -> list[CDRRegion]:
    """Identify CDR regions in an antibody variable domain sequence.

    Uses Kabat-like positional heuristics. Assumes the input is either:
    - A VH sequence (~120 aa): returns H1, H2, H3
    - A VL sequence (~107 aa): returns L1, L2, L3
    - A full Fv concatenation (~227 aa): returns all 6 CDRs (H then L)

    Residue positions are 1-based.
    """
    seq_len = len(antibody_sequence)
    regions: list[CDRRegion] = []

    if seq_len >= 200:
        # Full Fv — split at midpoint, handle both heavy and light
        vh_seq = antibody_sequence[:120]
        vl_seq = antibody_sequence[120:]
        heavy_names = ["H1", "H2", "H3"]
        light_names = ["L1", "L2", "L3"]
    elif seq_len >= 100:
        # Assume VH
        vh_seq = antibody_sequence
        vl_seq = ""
        heavy_names = ["H1", "H2", "H3"]
        light_names = []
    else:
        # Short: treat as VL
        vh_seq = ""
        vl_seq = antibody_sequence
        heavy_names = []
        light_names = ["L1", "L2", "L3"]

    for name in heavy_names:
        start, end = _KABAT_CDR_POSITIONS[name]
        start = min(start, len(vh_seq))
        end = min(end, len(vh_seq))
        cdr_seq = vh_seq[start - 1 : end] if start <= end else ""
        regions.append(
            CDRRegion(
                name=name,
                start=start,
                end=end,
                sequence=cdr_seq,
                length=len(cdr_seq),
                loop_type="heavy",
            )
        )

    vl_offset = len(vh_seq)
    for name in light_names:
        start, end = _KABAT_CDR_POSITIONS[name]
        start = min(start, len(vl_seq))
        end = min(end, len(vl_seq))
        cdr_seq = vl_seq[start - 1 : end] if start <= end else ""
        regions.append(
            CDRRegion(
                name=name,
                start=start + vl_offset,
                end=end + vl_offset,
                sequence=cdr_seq,
                length=len(cdr_seq),
                loop_type="light",
            )
        )

    return regions


def score_cdr_h3(sequence: str) -> dict:
    """Score a CDR-H3 loop sequence for length, flexibility and binding potential.

    Returns a dict with keys: length, flexibility_score, binding_potential.
    """
    length = len(sequence)
    # Flexibility: longer loops = more flexible; normalize 0-1 over range 5-25
    flexibility_score = round(min(max((length - 5) / 20.0, 0.0), 1.0), 3)

    # Binding potential based on aromatic/charged residue content
    aromatic = sum(1 for aa in sequence.upper() if aa in "FYWH")
    charged = sum(1 for aa in sequence.upper() if aa in "DEKR")
    total = max(length, 1)
    binding_potential = round(min((aromatic * 0.15 + charged * 0.08) / total + 0.3, 1.0), 3)

    return {
        "length": length,
        "flexibility_score": flexibility_score,
        "binding_potential": binding_potential,
    }


# ---------------------------------------------------------------------------
# Antibody humanization
# ---------------------------------------------------------------------------

# Human germline VH framework consensus (simplified): positions known to cause
# immunogenicity if they retain murine residues. Heuristic only.
_HUMAN_GERMLINE_VH_CONSENSUS = "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYADSVKGRFTISRDNSKNTLYLQMNSLRAEDTAVYYCAR"

_HUMAN_GERMLINE_VL_CONSENSUS = "DIQMTQSPSSLSASVGDRVTITCRASQSVSSFLAWYQQKPGKAPKLLIYAASSLQSGVPSRFSGSGSGTDFTLTISSLQPEDFATYYCQQSYSTPFT"


def assess_humanization(antibody_sequence: str) -> HumanizationResult:
    """Assess antibody humanization by comparing against human germline frameworks.

    Compares the query sequence to a human germline VH/VL consensus and
    estimates CDR preservation and immunogenicity risk.
    """
    seq_len = len(antibody_sequence)

    # Select reference based on length
    if seq_len >= 100:
        reference = _HUMAN_GERMLINE_VH_CONSENSUS
    else:
        reference = _HUMAN_GERMLINE_VL_CONSENSUS

    # Compute framework identity (exclude approximate CDR positions)
    cdr_positions: set[int] = set()
    for cdr_name in ["H1", "H2", "H3"] if seq_len >= 100 else ["L1", "L2", "L3"]:
        start, end = _KABAT_CDR_POSITIONS[cdr_name]
        cdr_positions.update(range(start - 1, end))

    min_len = min(len(antibody_sequence), len(reference))
    framework_matches = 0
    framework_positions = 0
    for i in range(min_len):
        if i not in cdr_positions:
            framework_positions += 1
            if antibody_sequence[i].upper() == reference[i].upper():
                framework_matches += 1

    framework_identity = (
        round(framework_matches / framework_positions, 3) if framework_positions > 0 else 0.0
    )

    # CDR preservation: check that CDR sequences are non-trivially non-identical to germline
    cdrs = identify_cdr_regions(antibody_sequence)
    cdr_preserved = len(cdrs) > 0 and all(r.length > 0 for r in cdrs)

    # Risk score: inverse of framework identity, penalized for short sequences
    length_penalty = max(0.0, (80 - seq_len) / 80.0) * 0.2
    risk_score = round(min(max(1.0 - framework_identity + length_penalty, 0.0), 1.0), 3)

    # Build a mock humanized sequence: replace non-CDR positions with germline
    humanized_parts = list(antibody_sequence)
    for i in range(min_len):
        if i not in cdr_positions:
            humanized_parts[i] = reference[i]
    humanized_sequence = "".join(humanized_parts)

    return HumanizationResult(
        original_sequence=antibody_sequence,
        humanized_sequence=humanized_sequence,
        framework_identity=framework_identity,
        cdr_preserved=cdr_preserved,
        risk_score=risk_score,
    )


# ---------------------------------------------------------------------------
# Bispecific antibody design
# ---------------------------------------------------------------------------

_BISPECIFIC_LINKERS: dict[str, str] = {
    "BiTE": "GGGGSGGGGS",
    "DVD-Ig": "PAPAPAPAP",
    "knobs-in-holes": "DKTHTCPPCPAPELLGGPSVFLFPPKPKDTLMISR",
}

_VALID_BISPECIFIC_FORMATS = {"BiTE", "DVD-Ig", "knobs-in-holes"}


def design_bispecific(
    target1: str,
    target2: str,
    format: str = "BiTE",
) -> BispecificDesign:
    """Design a bispecific antibody stub targeting two antigens.

    Supported formats: BiTE, DVD-Ig, knobs-in-holes.
    Falls back to BiTE for unknown formats.
    """
    if format not in _VALID_BISPECIFIC_FORMATS:
        format = "BiTE"
    linker = _BISPECIFIC_LINKERS[format]
    return BispecificDesign(
        arm1_target=target1.upper(),
        arm2_target=target2.upper(),
        format=format,
        linker_sequence=linker,
    )
