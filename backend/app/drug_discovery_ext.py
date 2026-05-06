"""Drug Discovery Extensions — Phase 24 Tier 2

Integrated druggability pipeline, cryptic sites, allostery, therapeutic reasoning, batch ΔΔG.
RESEARCH USE ONLY.
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Feature 1: Structure → druggability → docking pipeline
# ---------------------------------------------------------------------------


@dataclass
class PocketResult:
    pocket_id: int
    center: tuple[float, float, float]
    volume_angstrom3: float
    druggability_score: float  # 0-1
    residues: list[str]
    rank: int


@dataclass
class DockingResult:
    compound_name: str
    binding_energy_kcal: float
    pose_rmsd: float
    contact_residues: list[str]
    score: float


@dataclass
class DrugPipelineResult:
    target_gene: str
    pockets: list[PocketResult]
    docking_results: list[DockingResult]
    best_compound: str | None
    pipeline_runtime_sec: float


# Residue letter codes used in mock pocket generation
_RESIDUE_POOL = [
    "ALA",
    "ARG",
    "ASN",
    "ASP",
    "CYS",
    "GLN",
    "GLU",
    "GLY",
    "HIS",
    "ILE",
    "LEU",
    "LYS",
    "MET",
    "PHE",
    "PRO",
    "SER",
    "THR",
    "TRP",
    "TYR",
    "VAL",
]

# Residue labels with sequence numbers for mock pockets
_RESIDUE_LABELS = [f"{aa}{i}" for aa in _RESIDUE_POOL for i in range(1, 21)]


def _seed_from_string(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest(), 16) % (2**31)


def predict_pockets(pdb_data: str, gene: str = "") -> list[PocketResult]:
    """Mock fpocket-style pocket detection — 2-5 pockets per structure."""
    seed = _seed_from_string(pdb_data[:200] + gene)
    rng = random.Random(seed)

    n_pockets = rng.randint(2, 5)
    pockets: list[PocketResult] = []

    for i in range(n_pockets):
        cx = rng.uniform(-30.0, 30.0)
        cy = rng.uniform(-30.0, 30.0)
        cz = rng.uniform(-30.0, 30.0)
        volume = rng.uniform(150.0, 900.0)
        drug_score = rng.uniform(0.25, 0.95)
        n_res = rng.randint(6, 18)
        residues = rng.sample(_RESIDUE_LABELS, n_res)
        pockets.append(
            PocketResult(
                pocket_id=i + 1,
                center=(round(cx, 2), round(cy, 2), round(cz, 2)),
                volume_angstrom3=round(volume, 1),
                druggability_score=round(drug_score, 3),
                residues=sorted(residues),
                rank=i + 1,
            )
        )

    # Sort by druggability descending, re-rank
    pockets.sort(key=lambda p: p.druggability_score, reverse=True)
    for idx, p in enumerate(pockets):
        p.rank = idx + 1

    return pockets


def dock_compound(
    pocket: PocketResult,
    compound_smiles: str,
    compound_name: str,
) -> DockingResult:
    """Mock AutoDock/Vina docking against a pocket."""
    seed = _seed_from_string(compound_smiles + str(pocket.pocket_id) + compound_name)
    rng = random.Random(seed)

    # Better pockets (higher druggability) yield better scores
    base_energy = -rng.uniform(4.0, 12.0) * (0.5 + 0.5 * pocket.druggability_score)
    pose_rmsd = rng.uniform(0.3, 2.5)
    n_contacts = rng.randint(3, min(len(pocket.residues), 10))
    contacts = rng.sample(pocket.residues, n_contacts)
    # Normalize score 0-1 (−12 kcal → 1.0, −4 kcal → 0.0)
    score = max(0.0, min(1.0, (abs(base_energy) - 4.0) / 8.0))

    return DockingResult(
        compound_name=compound_name,
        binding_energy_kcal=round(base_energy, 3),
        pose_rmsd=round(pose_rmsd, 3),
        contact_residues=sorted(contacts),
        score=round(score, 3),
    )


# Default compound library for pipeline
_DEFAULT_LIBRARY: list[dict] = [
    {"name": "Erlotinib", "smiles": "C1=C2C(=CC(=C1OCC)OCC)C(=NC=N2)NC3=CC=CC(=C3)C#C"},
    {
        "name": "Imatinib",
        "smiles": "CN1CCN(CC1)CC2=CC=C(C=C2)C(=O)NC3=CC(=CC=C3)NC4=NC=CC(=N4)C5=CC=CN=C5",
    },
    {
        "name": "Sorafenib",
        "smiles": "CNC(=O)C1=NC=CC(=C1)OC2=CC=C(C=C2)NC(=O)NC3=CC(=C(C=C3)Cl)C(F)(F)F",
    },
    {
        "name": "Sunitinib",
        "smiles": "CCN(CC)CCNC(=O)C1=C(NC2=CC=CC3=CC=CC=C23)C(=C(N1)C)C=O",
    },  # simplified
    {
        "name": "Vemurafenib",
        "smiles": "CCCS(=O)(=O)NC1=CC(=C(C=C1)F)C2=CN=C(N=C2)NC3=CC=CC(=C3)C4=CC=NC=C4",
    },
    {
        "name": "Osimertinib",
        "smiles": "CN1C=C(C2=CC=CC=C21)C3=NC(=NC=C3)NC4=CC(=C(C=C4)N5CCN(CC5)C)OC",
    },
    {
        "name": "Crizotinib",
        "smiles": "CC(C1=C(C=CC(=C1Cl)F)Cl)OC2=CC(=NC=C2)NC3=CC(=CN=C3)N4CCNCC4",
    },
    {
        "name": "Alpelisib",
        "smiles": "CC1=C(C(=O)NC2=C(C=CN=C2)C3=CC=CC=C3F)C=NC(=N1)NS(=O)(=O)C4CCCC4",
    },
    {"name": "Sotorasib", "smiles": "C1CN2C(=C(C=N2)NC3=C(C=C(C=C3)F)F)C(=O)N1C4=CC5=CC=CC=C5N=C4"},
    {
        "name": "Palbociclib",
        "smiles": "CC1=C(C(=O)N(C(=O)N1C2=NC3=CC=CC=C3C=C2)C4=CC=C(C=C4)N5CCNCC5)C",
    },
]


def run_drug_pipeline(
    target_gene: str,
    compound_library: list[dict] | None = None,
) -> DrugPipelineResult:
    """Full pipeline: predict structure → find pockets → dock library → rank."""
    t0 = time.monotonic()
    library = compound_library or _DEFAULT_LIBRARY

    # Mock PDB data seeded from gene name
    seed = _seed_from_string(target_gene)
    rng = random.Random(seed)
    mock_pdb = (
        f"ATOM      1  CA  ALA A   1    {rng.uniform(-10, 10):.3f} {rng.uniform(-10, 10):.3f} {rng.uniform(-10, 10):.3f}  1.00 10.00           C\n"
        * 10
    )

    pockets = predict_pockets(mock_pdb, gene=target_gene)
    top_pocket = pockets[0] if pockets else None

    docking_results: list[DockingResult] = []
    if top_pocket:
        for compound in library:
            dr = dock_compound(
                top_pocket, compound.get("smiles", ""), compound.get("name", "unknown")
            )
            docking_results.append(dr)
        docking_results.sort(key=lambda d: d.binding_energy_kcal)

    best = docking_results[0].compound_name if docking_results else None
    runtime = round(time.monotonic() - t0, 4)

    return DrugPipelineResult(
        target_gene=target_gene,
        pockets=pockets,
        docking_results=docking_results,
        best_compound=best,
        pipeline_runtime_sec=runtime,
    )


# ---------------------------------------------------------------------------
# Feature 2: Cryptic binding site detection
# ---------------------------------------------------------------------------


@dataclass
class CrypticSite:
    site_id: int
    residues: list[str]
    opening_probability: float
    trigger: str  # "ligand_induced" | "conformational" | "allosteric"
    druggability_if_open: float
    confidence: float


# 8 proteins with documented cryptic sites
KNOWN_CRYPTIC_SITES: dict[str, dict] = {
    "MAPK14": {
        "common_name": "p38α MAPK",
        "site_type": "DFG-loop allosteric pocket",
        "trigger": "conformational",
        "reference_residues": ["THR106", "ILE84", "LEU86", "MET109", "GLY110"],
        "note": "Opens upon activation loop displacement",
    },
    "BLAT_ECOLX": {
        "common_name": "TEM-1 β-lactamase",
        "site_type": "Omega-loop cryptic pocket",
        "trigger": "ligand_induced",
        "reference_residues": ["GLU166", "ASN170", "ARG244", "SER235"],
        "note": "Inhibitor binding opens Omega-loop cavity",
    },
    "IL2": {
        "common_name": "Interleukin-2",
        "site_type": "Hydrophobic core expansion",
        "trigger": "ligand_induced",
        "reference_residues": ["LEU72", "ILE92", "THR51", "PHE42"],
        "note": "Small molecule displaces hydrophobic core residues",
    },
    "ABL1": {
        "common_name": "c-Abl tyrosine kinase",
        "site_type": "Myristoyl-binding pocket",
        "trigger": "allosteric",
        "reference_residues": ["TYR253", "PHE317", "ALA337", "VAL338", "ILE521"],
        "note": "N-terminal myristoyl group controls kinase conformation",
    },
    "CASP3": {
        "common_name": "Caspase-3",
        "site_type": "Dimer interface cryptic site",
        "trigger": "allosteric",
        "reference_residues": ["TYR197", "GLN161", "PHE250", "TRP206"],
        "note": "Allosteric pocket at dimer interface regulates activity",
    },
    "MDM2": {
        "common_name": "MDM2 proto-oncogene",
        "site_type": "p53-binding groove secondary site",
        "trigger": "conformational",
        "reference_residues": ["LEU26", "VAL75", "ILE99", "TYR100"],
        "note": "Secondary groove near p53-binding site, conformationally accessible",
    },
    "HIV1_PR": {
        "common_name": "HIV-1 Protease",
        "site_type": "Exosite flap region",
        "trigger": "ligand_induced",
        "reference_residues": ["MET36", "SER37", "LYS55", "ASP60"],
        "note": "Flap region opens secondary binding cavity under ligand pressure",
    },
    "HSP90AA1": {
        "common_name": "HSP90α",
        "site_type": "C-terminal MEEVD peptide pocket",
        "trigger": "conformational",
        "reference_residues": ["ARG400", "LYS588", "ASP572", "ILE573"],
        "note": "C-terminal dimerization interface harbors allosteric cryptic pocket",
    },
}


def detect_cryptic_sites(sequence: str, gene: str = "") -> list[CrypticSite]:
    """Analyze sequence for regions likely to harbor cryptic pockets."""
    gene_upper = gene.upper()
    sites: list[CrypticSite] = []

    # Check known cryptic database first
    if gene_upper in KNOWN_CRYPTIC_SITES:
        db_entry = KNOWN_CRYPTIC_SITES[gene_upper]
        sites.append(
            CrypticSite(
                site_id=1,
                residues=db_entry["reference_residues"],
                opening_probability=0.75 + _seed_from_string(gene_upper) % 20 / 100.0,
                trigger=db_entry["trigger"],
                druggability_if_open=0.65 + _seed_from_string(gene_upper + "d") % 30 / 100.0,
                confidence=0.82,
            )
        )

    # De novo prediction from sequence properties
    seed = _seed_from_string(sequence[:100] + gene)
    rng = random.Random(seed)

    # Analyze for hydrophobic stretches (potential buried pockets)
    hydrophobic = set("VILMFYWCA")
    n = len(sequence)
    window = 8
    buried_regions: list[int] = []
    for i in range(n - window):
        chunk = sequence[i : i + window]
        hyd_frac = sum(1 for aa in chunk if aa in hydrophobic) / window
        if hyd_frac >= 0.625:  # ≥5/8 hydrophobic
            buried_regions.append(i)

    n_de_novo = min(rng.randint(0, 3), max(0, len(buried_regions)))
    start_id = len(sites) + 1
    for j in range(n_de_novo):
        region_start = (
            buried_regions[j * max(1, len(buried_regions) // max(1, n_de_novo))]
            if buried_regions
            else rng.randint(0, max(0, n - 10))
        )
        residues = [
            f"{rng.choice(_RESIDUE_POOL)}{region_start + k + 1}" for k in range(rng.randint(4, 9))
        ]
        trigger = rng.choice(["ligand_induced", "conformational", "allosteric"])
        sites.append(
            CrypticSite(
                site_id=start_id + j,
                residues=residues,
                opening_probability=round(rng.uniform(0.2, 0.7), 3),
                trigger=trigger,
                druggability_if_open=round(rng.uniform(0.3, 0.85), 3),
                confidence=round(rng.uniform(0.3, 0.65), 3),
            )
        )

    return sites


# ---------------------------------------------------------------------------
# Feature 3: Allostery prediction
# ---------------------------------------------------------------------------


@dataclass
class AllostericSite:
    site_id: int
    residues: list[str]
    communication_score: float
    target_active_site_residues: list[str]
    modulation_type: str  # "positive" | "negative" | "switch"
    druggability: float


@dataclass
class AllosteryResult:
    gene: str
    active_site_residues: list[str]
    allosteric_sites: list[AllostericSite]
    communication_pathways: list[list[int]]
    overall_allosteric_potential: float


# Known active site residues for common targets
_KNOWN_ACTIVE_SITES: dict[str, list[str]] = {
    "EGFR": ["LYS745", "THR790", "CYS797", "ASP855", "PHE856"],
    "ABL1": ["LYS271", "THR315", "GLU286", "ASP381", "PHE382"],
    "BRAF": ["LYS483", "GLU501", "ASP594", "PHE595", "GLY466"],
    "KRAS": ["GLY12", "GLY13", "GLN61", "LYS117", "ASP119"],
    "TP53": ["CYS176", "HIS179", "CYS238", "CYS242", "ARG248"],
    "PIK3CA": ["LYS802", "ASP810", "TRP780", "SER831", "ASN832"],
    "MAPK14": ["LYS53", "GLU71", "THR106", "ASP168", "PHE169"],
    "HSP90AA1": ["ASP93", "GLY97", "ASN51", "THR184", "GLY137"],
}


def predict_allostery(
    sequence: str,
    gene: str = "",
    active_site_residues: list[int] | None = None,
) -> AllosteryResult:
    """Mock AlloSigMA2-style allosteric site prediction."""
    gene_upper = gene.upper()
    seed = _seed_from_string(sequence[:100] + gene)
    rng = random.Random(seed)

    # Determine active site residues
    if gene_upper in _KNOWN_ACTIVE_SITES:
        active_res = _KNOWN_ACTIVE_SITES[gene_upper]
    elif active_site_residues:
        active_res = [f"RES{r}" for r in active_site_residues]
    else:
        # Predict: often catalytic residues at ~1/3 of sequence length
        pos = max(10, len(sequence) // 3)
        active_res = [f"{rng.choice(_RESIDUE_POOL)}{pos + k}" for k in range(5)]

    # Generate 1-4 allosteric sites
    n_sites = rng.randint(1, 4)
    allo_sites: list[AllostericSite] = []
    pathways: list[list[int]] = []

    for i in range(n_sites):
        n_res = rng.randint(5, 12)
        offset = rng.randint(10, max(11, len(sequence) - 10))
        residues = [f"{rng.choice(_RESIDUE_POOL)}{offset + k}" for k in range(n_res)]
        comm_score = round(rng.uniform(0.35, 0.92), 3)
        target_res = rng.sample(active_res, min(3, len(active_res)))
        modulation = rng.choice(["positive", "negative", "switch"])
        drug_score = round(rng.uniform(0.3, 0.88), 3)

        allo_sites.append(
            AllostericSite(
                site_id=i + 1,
                residues=residues,
                communication_score=comm_score,
                target_active_site_residues=target_res,
                modulation_type=modulation,
                druggability=drug_score,
            )
        )

        # Communication pathway as residue indices
        path_len = rng.randint(3, 8)
        pathway = sorted(
            rng.sample(range(1, max(2, len(sequence))), min(path_len, len(sequence) - 1))
        )
        pathways.append(pathway)

    overall = (
        round(sum(s.communication_score for s in allo_sites) / max(1, len(allo_sites)), 3)
        if allo_sites
        else 0.0
    )

    return AllosteryResult(
        gene=gene,
        active_site_residues=active_res,
        allosteric_sites=allo_sites,
        communication_pathways=pathways,
        overall_allosteric_potential=overall,
    )


# ---------------------------------------------------------------------------
# Feature 4: Therapeutic reasoning chain
# ---------------------------------------------------------------------------


@dataclass
class ReasoningStep:
    step: int
    description: str
    input_data: str
    output_data: str
    confidence: float


@dataclass
class TherapeuticReasoningResult:
    variant: str
    gene: str
    steps: list[ReasoningStep]
    final_recommendation: str
    existing_drug_matches: list[dict]
    novel_target_score: float
    reasoning_chain_confidence: float


# 15 gene → drug pocket similarity entries (ChEMBL mock)
CHEMBL_MOCK_SIMILARITIES: dict[str, list[dict]] = {
    "EGFR": [
        {
            "drug": "Erlotinib",
            "chembl_id": "CHEMBL553",
            "pocket_similarity": 0.94,
            "mechanism": "ATP-competitive",
        },
        {
            "drug": "Gefitinib",
            "chembl_id": "CHEMBL939",
            "pocket_similarity": 0.91,
            "mechanism": "ATP-competitive",
        },
        {
            "drug": "Osimertinib",
            "chembl_id": "CHEMBL3353410",
            "pocket_similarity": 0.87,
            "mechanism": "covalent",
        },
    ],
    "ABL1": [
        {
            "drug": "Imatinib",
            "chembl_id": "CHEMBL941",
            "pocket_similarity": 0.93,
            "mechanism": "Type-II",
        },
        {
            "drug": "Dasatinib",
            "chembl_id": "CHEMBL1642",
            "pocket_similarity": 0.88,
            "mechanism": "Type-I",
        },
        {
            "drug": "Ponatinib",
            "chembl_id": "CHEMBL1171837",
            "pocket_similarity": 0.82,
            "mechanism": "Type-II",
        },
    ],
    "BRAF": [
        {
            "drug": "Vemurafenib",
            "chembl_id": "CHEMBL1229517",
            "pocket_similarity": 0.90,
            "mechanism": "Type-I½",
        },
        {
            "drug": "Dabrafenib",
            "chembl_id": "CHEMBL2028663",
            "pocket_similarity": 0.86,
            "mechanism": "Type-I½",
        },
    ],
    "KRAS": [
        {
            "drug": "Sotorasib",
            "chembl_id": "CHEMBL4523659",
            "pocket_similarity": 0.88,
            "mechanism": "covalent-G12C",
        },
        {
            "drug": "Adagrasib",
            "chembl_id": "CHEMBL4523582",
            "pocket_similarity": 0.84,
            "mechanism": "covalent-G12C",
        },
    ],
    "PIK3CA": [
        {
            "drug": "Alpelisib",
            "chembl_id": "CHEMBL2007641",
            "pocket_similarity": 0.89,
            "mechanism": "isoform-selective",
        },
        {
            "drug": "Idelalisib",
            "chembl_id": "CHEMBL2180676",
            "pocket_similarity": 0.76,
            "mechanism": "PI3Kδ-selective",
        },
    ],
    "ALK": [
        {
            "drug": "Crizotinib",
            "chembl_id": "CHEMBL601719",
            "pocket_similarity": 0.91,
            "mechanism": "Type-I",
        },
        {
            "drug": "Alectinib",
            "chembl_id": "CHEMBL2180692",
            "pocket_similarity": 0.88,
            "mechanism": "Type-I",
        },
        {
            "drug": "Brigatinib",
            "chembl_id": "CHEMBL3545063",
            "pocket_similarity": 0.85,
            "mechanism": "Type-I",
        },
    ],
    "CDK4": [
        {
            "drug": "Palbociclib",
            "chembl_id": "CHEMBL189963",
            "pocket_similarity": 0.90,
            "mechanism": "ATP-competitive",
        },
        {
            "drug": "Ribociclib",
            "chembl_id": "CHEMBL3545112",
            "pocket_similarity": 0.87,
            "mechanism": "ATP-competitive",
        },
    ],
    "MAPK14": [
        {
            "drug": "SB-203580",
            "chembl_id": "CHEMBL57850",
            "pocket_similarity": 0.85,
            "mechanism": "ATP-competitive",
        },
    ],
    "HSP90AA1": [
        {
            "drug": "Geldanamycin",
            "chembl_id": "CHEMBL37",
            "pocket_similarity": 0.83,
            "mechanism": "N-terminal ATPase",
        },
        {
            "drug": "17-AAG",
            "chembl_id": "CHEMBL52734",
            "pocket_similarity": 0.80,
            "mechanism": "N-terminal ATPase",
        },
    ],
    "MDM2": [
        {
            "drug": "Nutlin-3",
            "chembl_id": "CHEMBL1290562",
            "pocket_similarity": 0.86,
            "mechanism": "p53-MDM2 disruptor",
        },
        {
            "drug": "AMG-232",
            "chembl_id": "CHEMBL3707339",
            "pocket_similarity": 0.81,
            "mechanism": "piperidinone",
        },
    ],
    "VEGFR": [
        {
            "drug": "Sunitinib",
            "chembl_id": "CHEMBL535",
            "pocket_similarity": 0.88,
            "mechanism": "multi-kinase",
        },
        {
            "drug": "Pazopanib",
            "chembl_id": "CHEMBL477772",
            "pocket_similarity": 0.85,
            "mechanism": "multi-kinase",
        },
    ],
    "MET": [
        {
            "drug": "Cabozantinib",
            "chembl_id": "CHEMBL2105717",
            "pocket_similarity": 0.87,
            "mechanism": "multi-kinase",
        },
        {
            "drug": "Tepotinib",
            "chembl_id": "CHEMBL3955278",
            "pocket_similarity": 0.83,
            "mechanism": "Type-Ib",
        },
    ],
    "RET": [
        {
            "drug": "Selpercatinib",
            "chembl_id": "CHEMBL4523578",
            "pocket_similarity": 0.89,
            "mechanism": "selective",
        },
        {
            "drug": "Pralsetinib",
            "chembl_id": "CHEMBL4523625",
            "pocket_similarity": 0.86,
            "mechanism": "selective",
        },
    ],
    "FGFR1": [
        {
            "drug": "Erdafitinib",
            "chembl_id": "CHEMBL3836085",
            "pocket_similarity": 0.88,
            "mechanism": "pan-FGFR",
        },
        {
            "drug": "Infigratinib",
            "chembl_id": "CHEMBL3188463",
            "pocket_similarity": 0.83,
            "mechanism": "pan-FGFR",
        },
    ],
    "IDH1": [
        {
            "drug": "Ivosidenib",
            "chembl_id": "CHEMBL3989839",
            "pocket_similarity": 0.90,
            "mechanism": "allosteric-IDH1m",
        },
    ],
}


def run_therapeutic_reasoning(gene: str, variant: str) -> TherapeuticReasoningResult:
    """6-step chain: protein → structural impact → pocket → ChEMBL → drugs → strategy."""
    gene_upper = gene.upper()
    seed = _seed_from_string(gene + variant)
    rng = random.Random(seed)

    steps: list[ReasoningStep] = []

    # Step 1: Identify affected protein
    steps.append(
        ReasoningStep(
            step=1,
            description="Identify affected protein and functional domain",
            input_data=f"Gene: {gene}, Variant: {variant}",
            output_data=f"{gene} protein — variant {variant} maps to {'kinase domain' if 'kinase' not in gene_upper else 'active region'}",
            confidence=0.95,
        )
    )

    # Step 2: Predict structural impact
    aa_change = variant  # e.g. "V600E"
    structural_impact = rng.choice(
        [
            "disrupts hydrophobic core packing",
            "alters activation loop conformation",
            "introduces steric clash at binding interface",
            "modifies electrostatic surface potential",
            "destabilizes α-helix C positioning",
        ]
    )
    steps.append(
        ReasoningStep(
            step=2,
            description="Predict structural impact of variant",
            input_data=f"Variant: {aa_change}",
            output_data=f"Predicted effect: {structural_impact}",
            confidence=round(rng.uniform(0.65, 0.88), 3),
        )
    )

    # Step 3: Find druggable pocket
    pocket_type = rng.choice(
        [
            "ATP-binding cleft (deep, hydrophobic)",
            "allosteric DFG-out pocket",
            "protein-protein interaction groove",
            "covalent cysteine-proximal pocket",
        ]
    )
    steps.append(
        ReasoningStep(
            step=3,
            description="Identify druggable binding pocket on variant structure",
            input_data=f"Structural model with {aa_change} mutation",
            output_data=f"Top pocket: {pocket_type}, druggability score {round(rng.uniform(0.55, 0.95), 2)}",
            confidence=round(rng.uniform(0.60, 0.85), 3),
        )
    )

    # Step 4: Compare pocket to ChEMBL
    chembl_hits = CHEMBL_MOCK_SIMILARITIES.get(gene_upper, [])
    chembl_result = (
        f"{len(chembl_hits)} ChEMBL drug-pocket matches found"
        if chembl_hits
        else "No direct ChEMBL matches; searching structural analogs"
    )
    steps.append(
        ReasoningStep(
            step=4,
            description="Compare pocket geometry to ChEMBL known drug-target pockets",
            input_data=f"Pocket shape descriptor for {gene_upper}",
            output_data=chembl_result,
            confidence=round(rng.uniform(0.70, 0.92), 3),
        )
    )

    # Step 5: Drug similarity scoring
    drug_matches = []
    for entry in chembl_hits:
        adj_sim = round(max(0.3, entry["pocket_similarity"] - rng.uniform(0.0, 0.15)), 3)
        drug_matches.append(
            {
                "drug": entry["drug"],
                "chembl_id": entry["chembl_id"],
                "pocket_similarity": adj_sim,
                "mechanism": entry["mechanism"],
                "repurposing_confidence": round(adj_sim * rng.uniform(0.8, 1.0), 3),
            }
        )
    drug_matches.sort(key=lambda x: x["pocket_similarity"], reverse=True)
    top_drug = drug_matches[0]["drug"] if drug_matches else "novel scaffold required"

    steps.append(
        ReasoningStep(
            step=5,
            description="Rank existing drugs by pocket similarity score",
            input_data=f"{len(drug_matches)} candidate drugs",
            output_data=f"Top match: {top_drug}",
            confidence=round(rng.uniform(0.65, 0.88), 3),
        )
    )

    # Step 6: Strategy recommendation
    if drug_matches and drug_matches[0]["pocket_similarity"] >= 0.80:
        strategy = f"REPURPOSE: {top_drug} shows high pocket similarity ({drug_matches[0]['pocket_similarity']:.2f}). Recommend in vitro validation with {gene_upper}-{variant} cell line."
    elif drug_matches:
        strategy = f"OPTIMIZE: {top_drug} scaffold matches moderately. Medicinal chemistry optimization targeting {variant}-induced structural change recommended."
    else:
        strategy = f"NOVEL: {gene_upper}-{variant} creates a unique pocket. De novo drug design or covalent fragment screening recommended."

    steps.append(
        ReasoningStep(
            step=6,
            description="Generate therapeutic strategy recommendation",
            input_data="Drug similarity ranking + structural analysis",
            output_data=strategy,
            confidence=round(rng.uniform(0.55, 0.80), 3),
        )
    )

    novel_score = round(1.0 - (drug_matches[0]["pocket_similarity"] if drug_matches else 1.0), 3)
    chain_confidence = round(sum(s.confidence for s in steps) / len(steps), 3)

    return TherapeuticReasoningResult(
        variant=variant,
        gene=gene,
        steps=steps,
        final_recommendation=strategy,
        existing_drug_matches=drug_matches,
        novel_target_score=novel_score,
        reasoning_chain_confidence=chain_confidence,
    )


# ---------------------------------------------------------------------------
# Feature 5: Batch ΔΔG prediction
# ---------------------------------------------------------------------------


@dataclass
class DDGPrediction:
    variant: str
    ddg_foldx: float
    ddg_rosetta: float
    ddg_spurs: float
    consensus_ddg: float
    stability_effect: str  # "stabilizing" | "neutral" | "destabilizing" | "highly_destabilizing"
    confidence: float


@dataclass
class BatchDDGResult:
    gene: str
    variants: list[DDGPrediction]
    destabilizing_count: int
    stabilizing_count: int
    most_destabilizing: str | None


# Amino acid biophysical properties (hydrophobicity, charge, size, flexibility)
AMINO_ACID_PROPERTIES: dict[str, dict] = {
    "A": {"hydrophobicity": 1.8, "charge": 0, "size": 1.0, "flexibility": 0.36, "name": "Alanine"},
    "R": {
        "hydrophobicity": -4.5,
        "charge": 1,
        "size": 4.7,
        "flexibility": 0.53,
        "name": "Arginine",
    },
    "N": {
        "hydrophobicity": -3.5,
        "charge": 0,
        "size": 2.6,
        "flexibility": 0.46,
        "name": "Asparagine",
    },
    "D": {
        "hydrophobicity": -3.5,
        "charge": -1,
        "size": 2.5,
        "flexibility": 0.51,
        "name": "Aspartate",
    },
    "C": {"hydrophobicity": 2.5, "charge": 0, "size": 1.9, "flexibility": 0.35, "name": "Cysteine"},
    "Q": {
        "hydrophobicity": -3.5,
        "charge": 0,
        "size": 3.4,
        "flexibility": 0.49,
        "name": "Glutamine",
    },
    "E": {
        "hydrophobicity": -3.5,
        "charge": -1,
        "size": 3.4,
        "flexibility": 0.50,
        "name": "Glutamate",
    },
    "G": {"hydrophobicity": -0.4, "charge": 0, "size": 0.5, "flexibility": 0.54, "name": "Glycine"},
    "H": {
        "hydrophobicity": -3.2,
        "charge": 0.1,
        "size": 3.2,
        "flexibility": 0.32,
        "name": "Histidine",
    },
    "I": {
        "hydrophobicity": 4.5,
        "charge": 0,
        "size": 2.8,
        "flexibility": 0.30,
        "name": "Isoleucine",
    },
    "L": {"hydrophobicity": 3.8, "charge": 0, "size": 2.8, "flexibility": 0.40, "name": "Leucine"},
    "K": {"hydrophobicity": -3.9, "charge": 1, "size": 3.6, "flexibility": 0.47, "name": "Lysine"},
    "M": {
        "hydrophobicity": 1.9,
        "charge": 0,
        "size": 3.0,
        "flexibility": 0.28,
        "name": "Methionine",
    },
    "F": {
        "hydrophobicity": 2.8,
        "charge": 0,
        "size": 3.8,
        "flexibility": 0.31,
        "name": "Phenylalanine",
    },
    "P": {"hydrophobicity": -1.6, "charge": 0, "size": 2.0, "flexibility": 0.51, "name": "Proline"},
    "S": {"hydrophobicity": -0.8, "charge": 0, "size": 1.6, "flexibility": 0.51, "name": "Serine"},
    "T": {
        "hydrophobicity": -0.7,
        "charge": 0,
        "size": 2.0,
        "flexibility": 0.44,
        "name": "Threonine",
    },
    "W": {
        "hydrophobicity": -0.9,
        "charge": 0,
        "size": 5.2,
        "flexibility": 0.28,
        "name": "Tryptophan",
    },
    "Y": {
        "hydrophobicity": -1.3,
        "charge": 0,
        "size": 4.6,
        "flexibility": 0.42,
        "name": "Tyrosine",
    },
    "V": {"hydrophobicity": 4.2, "charge": 0, "size": 2.3, "flexibility": 0.39, "name": "Valine"},
}

# Three-letter to one-letter AA code
_AA3TO1: dict[str, str] = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
}


def _parse_variant(variant: str) -> tuple[str, int, str] | None:
    """Parse variant string like 'V600E' → (wt_aa, position, mut_aa)."""
    import re

    m = re.match(r"^([A-Za-z*]+)(\d+)([A-Za-z*]+)$", variant.strip())
    if not m:
        return None
    wt = m.group(1).upper()
    pos = int(m.group(2))
    mut = m.group(3).upper()
    # Handle 3-letter codes
    if len(wt) == 3:
        wt = _AA3TO1.get(wt, wt[0])
    if len(mut) == 3:
        mut = _AA3TO1.get(mut, mut[0])
    return wt, pos, mut


def predict_ddg(gene: str, variant: str) -> DDGPrediction:
    """Compute ΔΔG from amino acid property changes; mock FoldX/Rosetta/SPURS."""
    parsed = _parse_variant(variant)
    seed = _seed_from_string(gene + variant)
    rng = random.Random(seed)

    if parsed and parsed[0] in AMINO_ACID_PROPERTIES and parsed[2] in AMINO_ACID_PROPERTIES:
        wt_aa, pos, mut_aa = parsed
        wt_props = AMINO_ACID_PROPERTIES[wt_aa]
        mut_props = AMINO_ACID_PROPERTIES[mut_aa]

        delta_hyd = mut_props["hydrophobicity"] - wt_props["hydrophobicity"]
        delta_charge = abs(mut_props["charge"] - wt_props["charge"])
        delta_size = abs(mut_props["size"] - wt_props["size"])
        delta_flex = abs(mut_props["flexibility"] - wt_props["flexibility"])

        # Empirical weights (loosely calibrated to observed ΔΔG ranges)
        base_ddg = (
            -0.4 * delta_hyd  # burial of hydrophobic residues stabilizes
            + 1.8 * delta_charge  # charge changes destabilize in hydrophobic core
            + 0.9 * delta_size  # size clashes are costly
            + 2.5 * delta_flex  # flexibility changes near rigid cores
        )
        # Position penalty: buried positions (middle of protein) are more sensitive
        # We model this as a mild position-dependent noise
        position_factor = 0.8 + 0.4 * math.sin(pos * 0.1)
        base_ddg *= position_factor

        # Correlated noise for the three tools (correlated via shared offset)
        shared_noise = rng.gauss(0, 0.5)
        ddg_foldx = round(base_ddg + shared_noise + rng.gauss(0, 0.3), 2)
        ddg_rosetta = round(base_ddg + shared_noise + rng.gauss(0, 0.4), 2)
        ddg_spurs = round(base_ddg + shared_noise + rng.gauss(0, 0.35), 2)
        confidence = round(rng.uniform(0.70, 0.92), 3)
    else:
        # Unknown / non-standard variant — use hash-seeded values
        base = rng.gauss(1.5, 2.5)
        shared_noise = rng.gauss(0, 0.5)
        ddg_foldx = round(base + shared_noise + rng.gauss(0, 0.3), 2)
        ddg_rosetta = round(base + shared_noise + rng.gauss(0, 0.4), 2)
        ddg_spurs = round(base + shared_noise + rng.gauss(0, 0.35), 2)
        confidence = round(rng.uniform(0.40, 0.65), 3)

    consensus_ddg = round((ddg_foldx + ddg_rosetta + ddg_spurs) / 3.0, 2)

    if consensus_ddg <= -1.0:
        effect = "stabilizing"
    elif consensus_ddg <= 1.0:
        effect = "neutral"
    elif consensus_ddg <= 4.0:
        effect = "destabilizing"
    else:
        effect = "highly_destabilizing"

    return DDGPrediction(
        variant=variant,
        ddg_foldx=ddg_foldx,
        ddg_rosetta=ddg_rosetta,
        ddg_spurs=ddg_spurs,
        consensus_ddg=consensus_ddg,
        stability_effect=effect,
        confidence=confidence,
    )


def batch_predict_ddg(gene: str, variants: list[str]) -> BatchDDGResult:
    """Run ΔΔG prediction for all variants and summarize."""
    predictions = [predict_ddg(gene, v) for v in variants]

    destabilizing = sum(
        1 for p in predictions if p.stability_effect in ("destabilizing", "highly_destabilizing")
    )
    stabilizing = sum(1 for p in predictions if p.stability_effect == "stabilizing")

    most_dest: str | None = None
    if predictions:
        worst = max(predictions, key=lambda p: p.consensus_ddg)
        if worst.stability_effect in ("destabilizing", "highly_destabilizing"):
            most_dest = worst.variant

    return BatchDDGResult(
        gene=gene,
        variants=predictions,
        destabilizing_count=destabilizing,
        stabilizing_count=stabilizing,
        most_destabilizing=most_dest,
    )
