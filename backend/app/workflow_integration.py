"""Workflow Integration — Phase 24 Tier 1

Per-residue ensemble analysis, smart backend selection, batch provenance,
format normalization, and version pinning.

RESEARCH USE ONLY.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Feature 1: Per-residue ensemble disagreement heatmap
# ---------------------------------------------------------------------------

# 3-letter amino acid codes for mock residue names
_AA_THREE = {
    "A": "ALA",
    "R": "ARG",
    "N": "ASN",
    "D": "ASP",
    "C": "CYS",
    "E": "GLU",
    "Q": "GLN",
    "G": "GLY",
    "H": "HIS",
    "I": "ILE",
    "L": "LEU",
    "K": "LYS",
    "M": "MET",
    "F": "PHE",
    "P": "PRO",
    "S": "SER",
    "T": "THR",
    "W": "TRP",
    "Y": "TYR",
    "V": "VAL",
}


def _hash_float(seed: str, lo: float = 60.0, hi: float = 95.0) -> float:
    """Deterministic float in [lo, hi] from a string seed."""
    digest = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    frac = (digest % 100_000) / 100_000.0
    return round(lo + frac * (hi - lo), 2)


@dataclass
class PerResidueDisagreement:
    residue_index: int
    residue_name: str
    plddt_values: list[float]
    mean_plddt: float
    std_plddt: float
    disagreement_level: str  # "low" | "medium" | "high"


@dataclass
class EnsembleHeatmapResult:
    sequence: str
    per_residue: list[PerResidueDisagreement]
    high_disagreement_regions: list[tuple[int, int]]
    overall_disagreement: float


def compute_ensemble_heatmap(
    sequence: str,
    backend_names: list[str],
) -> EnsembleHeatmapResult:
    """Compute per-residue pLDDT disagreement across backends.

    Uses deterministic hash-based mock pLDDT values (no randomness).
    """
    per_residue: list[PerResidueDisagreement] = []

    for idx, aa in enumerate(sequence):
        residue_name = _AA_THREE.get(aa.upper(), "UNK")
        plddts: list[float] = []
        for backend in backend_names:
            seed = f"{backend}:{sequence}:{idx}:{aa}"
            plddts.append(_hash_float(seed, 50.0, 99.0))

        n = len(plddts)
        mean = sum(plddts) / n if n else 0.0
        variance = sum((v - mean) ** 2 for v in plddts) / n if n else 0.0
        std = variance**0.5

        if std < 5.0:
            level = "low"
        elif std < 12.0:
            level = "medium"
        else:
            level = "high"

        per_residue.append(
            PerResidueDisagreement(
                residue_index=idx,
                residue_name=residue_name,
                plddt_values=plddts,
                mean_plddt=round(mean, 4),
                std_plddt=round(std, 4),
                disagreement_level=level,
            )
        )

    # Identify contiguous high-disagreement regions
    high_disagreement_regions: list[tuple[int, int]] = []
    start: int | None = None
    for pr in per_residue:
        if pr.disagreement_level == "high":
            if start is None:
                start = pr.residue_index
        else:
            if start is not None:
                high_disagreement_regions.append((start, pr.residue_index - 1))
                start = None
    if start is not None:
        high_disagreement_regions.append((start, len(sequence) - 1))

    overall = sum(pr.std_plddt for pr in per_residue) / len(per_residue) if per_residue else 0.0

    return EnsembleHeatmapResult(
        sequence=sequence,
        per_residue=per_residue,
        high_disagreement_regions=high_disagreement_regions,
        overall_disagreement=round(overall, 4),
    )


# ---------------------------------------------------------------------------
# Feature 2: Input-type-aware backend selector with accuracy benchmarks
# ---------------------------------------------------------------------------

# task_class -> list of (backend_name, accuracy_score) sorted descending
TASK_CLASS_BENCHMARKS: dict[str, list[tuple[str, float]]] = {
    "monomer": [
        ("alphafold2_local", 0.94),
        ("alphafold3_local", 0.93),
        ("colabfold", 0.91),
        ("local_colabfold", 0.91),
        ("esmfold", 0.87),
        ("openfold", 0.86),
        ("boltz1", 0.85),
        ("mock", 0.50),
    ],
    "multimer": [
        ("alphafold3_local", 0.92),
        ("alphafold2_local", 0.88),
        ("boltz1", 0.87),
        ("boltz2", 0.86),
        ("colabfold", 0.84),
        ("local_colabfold", 0.84),
        ("chai1", 0.83),
        ("mock", 0.50),
    ],
    "antibody_antigen": [
        ("alphafold3_local", 0.91),
        ("chai1", 0.89),
        ("boltz2", 0.87),
        ("boltz1", 0.85),
        ("colabfold", 0.82),
        ("mock", 0.50),
    ],
    "small_molecule": [
        ("boltz2", 0.90),
        ("boltz1", 0.88),
        ("alphafold3_local", 0.85),
        ("chai1", 0.84),
        ("mock", 0.50),
    ],
    "nucleic_acid": [
        ("alphafold3_local", 0.89),
        ("boltz1", 0.86),
        ("boltz2", 0.85),
        ("chai1", 0.83),
        ("mock", 0.50),
    ],
    "enzyme_design": [
        ("rfdiffusion2", 0.88),
        ("rfdiffusion", 0.85),
        ("proteinmpnn", 0.82),
        ("alphafold3_local", 0.80),
        ("mock", 0.50),
    ],
    "backbone_design": [
        ("rfdiffusion", 0.91),
        ("rfdiffusion2", 0.89),
        ("proteinmpnn", 0.83),
        ("mock", 0.50),
    ],
}

_CLOUD_BACKENDS = {"alphafold_server", "alphafold_db"}


@dataclass
class BackendRecommendation:
    task_class: str
    recommended: str
    alternatives: list[str]
    accuracy_estimate: float
    reasoning: str


def recommend_backend(
    task_class: str,
    allow_cloud: bool = False,
) -> BackendRecommendation:
    """Recommend the best backend for a given task class.

    Args:
        task_class: one of the keys in TASK_CLASS_BENCHMARKS
        allow_cloud: if False, cloud-only backends are excluded

    Returns:
        BackendRecommendation with ranked options and reasoning

    Raises:
        ValueError: if task_class is not recognized
    """
    if task_class not in TASK_CLASS_BENCHMARKS:
        valid = sorted(TASK_CLASS_BENCHMARKS)
        raise ValueError(f"Unknown task class {task_class!r}. Valid classes: {valid}")

    ranked = TASK_CLASS_BENCHMARKS[task_class]
    if not allow_cloud:
        ranked = [(b, s) for b, s in ranked if b not in _CLOUD_BACKENDS]

    if not ranked:
        raise RuntimeError(
            f"No backends available for task class {task_class!r} with allow_cloud={allow_cloud}"
        )

    best_name, best_score = ranked[0]
    alts = [b for b, _ in ranked[1:]]

    return BackendRecommendation(
        task_class=task_class,
        recommended=best_name,
        alternatives=alts,
        accuracy_estimate=best_score,
        reasoning=(
            f"Backend '{best_name}' has the highest benchmark accuracy "
            f"({best_score:.0%}) for {task_class} tasks among "
            f"{'all' if allow_cloud else 'local'} backends."
        ),
    )


# ---------------------------------------------------------------------------
# Feature 3: Batch prediction with per-sequence provenance tracking
# ---------------------------------------------------------------------------

_BACKEND_VERSIONS: dict[str, str] = {
    "mock": "1.0.0",
    "colabfold": "1.5.5",
    "local_colabfold": "1.5.5",
    "alphafold2_local": "2.3.2",
    "alphafold3_local": "3.0.0",
    "alphafold_server": "3.0.0",
    "alphafold_db": "4.0.0",
    "boltz1": "1.0.0",
    "boltz2": "2.0.0",
    "esmfold": "1.0.1",
    "openfold": "2.1.0",
    "rfdiffusion": "1.1.0",
    "proteinmpnn": "1.0.1",
    "chai1": "1.0.0",
    "rfdiffusion2": "2.0.0",
}


@dataclass
class SequenceProvenance:
    sequence_id: str
    input_hash: str  # SHA-256
    backend_name: str
    backend_version: str
    timestamp: str  # ISO 8601
    runtime_seconds: float
    pdb_data: str | None
    confidence: dict


@dataclass
class BatchResult:
    batch_id: str  # UUID
    total: int
    completed: int
    provenances: list[SequenceProvenance]
    manifest_hash: str  # SHA-256 over all provenance hashes


def _sequence_hash(sequence: str) -> str:
    return hashlib.sha256(sequence.encode()).hexdigest()


def _mock_predict_deterministic(sequence: str, backend_name: str) -> tuple[str | None, dict, float]:
    """Deterministic mock prediction — no randomness."""
    seed = f"{backend_name}:{sequence}"
    plddt_mean = _hash_float(seed + ":plddt_mean", 70.0, 92.0)
    plddt_min = _hash_float(seed + ":plddt_min", 55.0, 70.0)
    plddt_max = _hash_float(seed + ":plddt_max", 90.0, 99.0)
    runtime = _hash_float(seed + ":runtime", 0.001, 0.05)

    lines = [
        "REMARK  FoldAgent deterministic mock structure",
        f"REMARK  sequence length: {len(sequence)}",
    ]
    for i, aa in enumerate(sequence[:50], start=1):
        plddt = _hash_float(f"{seed}:ca:{i}", 60.0, 95.0)
        lines.append(
            f"ATOM  {i:5d}  CA  {_AA_THREE.get(aa.upper(), 'UNK'):3s} A{i:4d}    "
            f"   0.000   0.000   0.000  1.00 {plddt:5.2f}           C"
        )
    lines.append("END")
    pdb = "\n".join(lines)

    confidence = {
        "pLDDT_mean": plddt_mean,
        "pLDDT_min": plddt_min,
        "pLDDT_max": plddt_max,
        "model_version": f"{backend_name}-deterministic-mock",
        "warning": "Deterministic mock — not real structure data.",
    }
    return pdb, confidence, round(runtime, 4)


def run_batch_prediction(
    sequences: list[str],
    backend_name: str = "mock",
) -> BatchResult:
    """Run batch predictions with full per-sequence provenance.

    Uses deterministic mock predictions (hash-based, no randomness).
    """
    if not sequences:
        raise ValueError("sequences list must not be empty")

    batch_id = str(
        uuid.UUID(hashlib.sha256(json.dumps(sequences + [backend_name]).encode()).hexdigest()[:32])
    )

    version = _BACKEND_VERSIONS.get(backend_name, "0.0.0")
    provenances: list[SequenceProvenance] = []

    for idx, seq in enumerate(sequences):
        seq_id = f"seq_{idx:04d}"
        input_hash = _sequence_hash(seq)
        pdb, confidence, runtime = _mock_predict_deterministic(seq, backend_name)
        ts = datetime.fromtimestamp(
            # Deterministic timestamp offset from batch hash
            1_700_000_000 + int(input_hash[:8], 16) % 86400,
            tz=UTC,
        ).isoformat()

        provenances.append(
            SequenceProvenance(
                sequence_id=seq_id,
                input_hash=input_hash,
                backend_name=backend_name,
                backend_version=version,
                timestamp=ts,
                runtime_seconds=runtime,
                pdb_data=pdb,
                confidence=confidence,
            )
        )

    # Manifest hash = SHA-256 over all input hashes concatenated
    manifest_payload = json.dumps([p.input_hash for p in provenances], sort_keys=True).encode()
    manifest_hash = hashlib.sha256(manifest_payload).hexdigest()

    return BatchResult(
        batch_id=batch_id,
        total=len(sequences),
        completed=len(provenances),
        provenances=provenances,
        manifest_hash=manifest_hash,
    )


# ---------------------------------------------------------------------------
# Feature 4: Universal PDB/mmCIF format normalizer
# ---------------------------------------------------------------------------


@dataclass
class NormalizedStructure:
    format: str  # "pdb" or "mmcif"
    data: str
    chain_map: dict[str, str]  # original_chain -> new_chain
    n_atoms: int
    n_residues: int
    warnings: list[str]


def detect_format(data: str) -> str:
    """Detect whether data is PDB or mmCIF based on content heuristics.

    Returns "mmcif" if it looks like CIF, else "pdb".
    """
    stripped = data.lstrip()
    if stripped.startswith("data_") or "_atom_site." in data or "loop_" in data:
        return "mmcif"
    if (
        stripped.startswith("ATOM")
        or stripped.startswith("REMARK")
        or stripped.startswith("HEADER")
    ):
        return "pdb"
    # Fall back to checking for PDB-style records
    pdb_keywords = ("ATOM  ", "HETATM", "REMARK", "MODEL ", "ENDMDL", "TER   ", "END")
    for line in data.splitlines():
        if any(line.startswith(kw) for kw in pdb_keywords):
            return "pdb"
    return "pdb"  # default


def _strip_insertion_code(residue_seq_field: str) -> str:
    """Remove insertion code from a PDB residue sequence field (cols 23-26).

    The insertion code is the last character of the 4-char field if non-numeric.
    """
    s = residue_seq_field.strip()
    if s and not s[-1].isdigit() and s[-1] != " ":
        return s[:-1].strip()
    return s.strip()


def normalize_pdb(
    pdb_data: str,
    target_format: str = "pdb",
    chain_rename: dict[str, str] | None = None,
) -> NormalizedStructure:
    """Normalize a PDB or mmCIF structure.

    Operations performed:
    - Rename chains according to chain_rename mapping
    - Strip insertion codes from residue sequence numbers
    - Count ATOM/HETATM records
    - Collect unique residues
    - Warn about HETATM records and insertion codes found

    Args:
        pdb_data: raw PDB or mmCIF text
        target_format: currently only "pdb" supported (mmCIF pass-through)
        chain_rename: optional mapping of original chain IDs to new chain IDs
    """
    fmt = detect_format(pdb_data)
    warnings: list[str] = []
    chain_map: dict[str, str] = {}

    if fmt == "mmcif":
        warnings.append(
            "mmCIF format detected; full normalization not yet supported — returning as-is"
        )
        return NormalizedStructure(
            format="mmcif",
            data=pdb_data,
            chain_map={},
            n_atoms=pdb_data.count("ATOM"),
            n_residues=0,
            warnings=warnings,
        )

    output_lines: list[str] = []
    atom_count = 0
    residues: set[tuple[str, str, str]] = set()  # (chain, resseq, resname)
    hetatm_count = 0
    insertion_code_count = 0

    rename = chain_rename or {}

    for line in pdb_data.splitlines():
        record = line[:6].rstrip()

        if record in ("ATOM", "HETATM"):
            if len(line) < 26:
                output_lines.append(line)
                continue

            # PDB columns (0-indexed):
            # 0-5: record type
            # 12-15: atom name
            # 17-19: residue name
            # 21: chain ID
            # 22-25: residue seq number (22-25) + insertion code col 26
            chain_id = line[21] if len(line) > 21 else " "
            new_chain = rename.get(chain_id, chain_id)
            if chain_id != new_chain:
                chain_map[chain_id] = new_chain

            # Check for insertion code at col 26
            insertion_code = line[26] if len(line) > 26 else " "
            if insertion_code not in (" ", ""):
                insertion_code_count += 1

            # Rebuild line with new chain and stripped insertion code
            new_line = (
                line[:21]
                + new_chain
                + line[22:26]
                + " "  # blank out insertion code
                + (line[27:] if len(line) > 27 else "")
            )

            res_seq = line[22:26]
            res_name = line[17:20].strip()
            residues.add((new_chain, res_seq.strip(), res_name))

            if record == "HETATM":
                hetatm_count += 1

            atom_count += 1
            output_lines.append(new_line)
        else:
            output_lines.append(line)

    if hetatm_count > 0:
        warnings.append(f"Found {hetatm_count} HETATM record(s) — non-standard residues present")

    if insertion_code_count > 0:
        warnings.append(
            f"Stripped {insertion_code_count} insertion code(s) from residue sequence numbers"
        )

    # Also record any rename entries that were not encountered in atoms
    for orig, new in rename.items():
        if orig not in chain_map and orig != new:
            chain_map[orig] = new

    return NormalizedStructure(
        format="pdb",
        data="\n".join(output_lines),
        chain_map=chain_map,
        n_atoms=atom_count,
        n_residues=len(residues),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Feature 5: Automatic version pinning with supersession alerts
# ---------------------------------------------------------------------------

TOOL_VERSIONS: dict[str, str] = {
    "alphafold2_local": "2.3.2",
    "alphafold3_local": "3.0.0",
    "colabfold": "1.5.5",
    "local_colabfold": "1.5.5",
    "alphafold_server": "3.0.0",
    "alphafold_db": "4.0.0",
    "boltz1": "1.0.0",
    "boltz2": "2.0.0",
    "esmfold": "1.0.1",
    "openfold": "2.1.0",
    "rfdiffusion": "1.1.0",
    "proteinmpnn": "1.0.1",
    "chai1": "1.0.0",
    "rfdiffusion2": "2.0.0",
    "mock": "1.0.0",
    # Workflow integration tools
    "foldagent_workflow": "24.1.0",
    "foldagent_ensemble": "1.2.0",
    "foldagent_batch": "1.1.0",
    "foldagent_normalizer": "1.0.0",
}

# Supersession map: tool -> tool that supersedes it
_SUPERSEDED_BY: dict[str, str] = {
    "alphafold2_local": "alphafold3_local",
    "colabfold": "local_colabfold",
    "boltz1": "boltz2",
    "rfdiffusion": "rfdiffusion2",
    "alphafold_server": "alphafold3_local",
}


@dataclass
class VersionPin:
    tool_name: str
    pinned_version: str
    current_version: str
    superseded: bool
    supersession_warning: str | None


def pin_version(tool_name: str) -> VersionPin:
    """Pin and check a tool's version.

    Args:
        tool_name: name of the tool to pin

    Returns:
        VersionPin with version info and supersession alert if applicable

    Raises:
        KeyError: if tool_name is not in TOOL_VERSIONS
    """
    if tool_name not in TOOL_VERSIONS:
        raise KeyError(f"Unknown tool: {tool_name!r}. Known tools: {sorted(TOOL_VERSIONS)}")

    version = TOOL_VERSIONS[tool_name]
    superseded_by = _SUPERSEDED_BY.get(tool_name)
    superseded = superseded_by is not None

    warning: str | None = None
    if superseded:
        new_ver = TOOL_VERSIONS.get(superseded_by, "unknown")
        warning = (
            f"Tool '{tool_name}' v{version} has been superseded by "
            f"'{superseded_by}' v{new_ver}. "
            f"Consider migrating for improved accuracy."
        )

    return VersionPin(
        tool_name=tool_name,
        pinned_version=version,
        current_version=version,
        superseded=superseded,
        supersession_warning=warning,
    )


def check_all_versions() -> list[VersionPin]:
    """Check version pins for all known tools, flagging superseded ones."""
    return [pin_version(name) for name in sorted(TOOL_VERSIONS)]


def get_version_manifest() -> dict:
    """Return full version manifest for reproducibility."""
    pins = check_all_versions()
    return {
        "versions": {p.tool_name: p.current_version for p in pins},
        "superseded": {p.tool_name: p.supersession_warning for p in pins if p.superseded},
        "total_tools": len(pins),
        "superseded_count": sum(1 for p in pins if p.superseded),
        "manifest_hash": hashlib.sha256(
            json.dumps(
                {p.tool_name: p.current_version for p in pins},
                sort_keys=True,
            ).encode()
        ).hexdigest(),
    }
