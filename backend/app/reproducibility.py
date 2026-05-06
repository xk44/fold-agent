"""Reproducibility Infrastructure — Phase 24 Tier 1

Pipeline reproducibility manifests and FAIR-compliant report generation.

RESEARCH USE ONLY.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _hash_dict(d: dict) -> str:
    return _sha256(json.dumps(d, sort_keys=True, default=str))


# ---------------------------------------------------------------------------
# Feature 1: Pipeline Reproducibility Manifest
# ---------------------------------------------------------------------------


@dataclass
class ToolVersion:
    name: str
    version: str
    source: str  # "local" | "cloud" | "container"
    checksum: str | None = None


@dataclass
class DatabaseVersion:
    name: str
    version: str
    last_updated: str  # ISO
    entry_count: int


@dataclass
class EnvironmentSnapshot:
    python_version: str
    platform: str
    cpu_count: int
    gpu_available: bool
    env_hash: str  # SHA-256 of relevant env vars


@dataclass
class PipelineManifest:
    manifest_id: str  # UUID
    created_at: str  # ISO
    tool_versions: list[ToolVersion]
    database_versions: list[DatabaseVersion]
    environment: EnvironmentSnapshot
    random_seeds: dict[str, int]
    input_hashes: dict[str, str]
    output_hashes: dict[str, str]
    reproducibility_score: float  # 0-1
    rerun_command: str


# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------

TOOL_VERSION_REGISTRY: dict[str, str] = {
    "mock": "1.0.0",
    "colabfold": "1.5.5",
    "local_colabfold": "1.5.5",
    "alphafold2_local": "2.3.2",
    "alphafold3_local": "3.0.0",
    "alphafold_server": "2.3.2",
    "alphafold_db": "2.3.2",
    "boltz1": "1.0.0",
    "boltz2": "2.0.0",
    "esmfold": "1.0.3",
    "openfold": "1.0.1",
    "rfdiffusion": "1.1.0",
    "proteinmpnn": "1.0.1",
    "chai1": "1.0.0",
    "rfdiffusion2": "2.0.0",
}

DATABASE_VERSION_REGISTRY: dict[str, dict] = {
    "clinvar": {
        "version": "2024-03",
        "last_updated": "2024-03-01T00:00:00+00:00",
        "entry_count": 1_200_000,
    },
    "alphamissense": {
        "version": "2023-12",
        "last_updated": "2023-12-01T00:00:00+00:00",
        "entry_count": 71_000_000,
    },
    "uniprot": {
        "version": "2024_01",
        "last_updated": "2024-01-24T00:00:00+00:00",
        "entry_count": 250_000_000,
    },
    "pdb": {
        "version": "2024-04",
        "last_updated": "2024-04-01T00:00:00+00:00",
        "entry_count": 210_000,
    },
    "pfam": {
        "version": "36.0",
        "last_updated": "2023-09-01T00:00:00+00:00",
        "entry_count": 20_000,
    },
}


# ---------------------------------------------------------------------------
# Environment capture
# ---------------------------------------------------------------------------


def capture_environment() -> EnvironmentSnapshot:
    """Capture current execution environment snapshot."""
    relevant_env_vars = {
        k: v
        for k, v in os.environ.items()
        if any(k.startswith(p) for p in ("FOLDAGENT_", "CUDA_", "PATH", "PYTHONPATH"))
    }
    env_hash = _sha256(json.dumps(relevant_env_vars, sort_keys=True))

    gpu_available = False
    try:
        import importlib

        spec = importlib.util.find_spec("torch")
        if spec is not None:
            import torch  # type: ignore

            gpu_available = torch.cuda.is_available()
    except Exception:
        pass
    if not gpu_available:
        gpu_available = bool(os.environ.get("CUDA_VISIBLE_DEVICES", ""))

    return EnvironmentSnapshot(
        python_version=sys.version,
        platform=platform.platform(),
        cpu_count=os.cpu_count() or 0,
        gpu_available=gpu_available,
        env_hash=env_hash,
    )


# ---------------------------------------------------------------------------
# Manifest creation / verification / storage
# ---------------------------------------------------------------------------


def _hash_value(v: object) -> str:
    return _sha256(json.dumps(v, sort_keys=True, default=str))


def create_manifest(
    tool_names: list[str],
    inputs: dict,
    outputs: dict,
    seeds: dict | None = None,
) -> PipelineManifest:
    """Build a full pipeline reproducibility manifest."""
    tool_versions: list[ToolVersion] = []
    for name in tool_names:
        version = TOOL_VERSION_REGISTRY.get(name, "unknown")
        checksum = _sha256(f"{name}:{version}")
        source = "local" if "server" not in name and "db" not in name else "cloud"
        tool_versions.append(
            ToolVersion(name=name, version=version, source=source, checksum=checksum)
        )

    db_versions: list[DatabaseVersion] = []
    for db_name, db_info in DATABASE_VERSION_REGISTRY.items():
        db_versions.append(
            DatabaseVersion(
                name=db_name,
                version=db_info["version"],
                last_updated=db_info["last_updated"],
                entry_count=db_info["entry_count"],
            )
        )

    env = capture_environment()

    input_hashes = {k: _hash_value(v) for k, v in inputs.items()}
    output_hashes = {k: _hash_value(v) for k, v in outputs.items()}

    random_seeds = seeds or {}

    # Score: fraction of tools with known versions + env captured
    known = sum(1 for t in tool_versions if t.version != "unknown")
    score = (known / max(len(tool_versions), 1)) * 0.8 + 0.2
    score = round(min(score, 1.0), 4)

    manifest_id = str(uuid.uuid4())
    manifest = PipelineManifest(
        manifest_id=manifest_id,
        created_at=_now_iso(),
        tool_versions=tool_versions,
        database_versions=db_versions,
        environment=env,
        random_seeds=random_seeds,
        input_hashes=input_hashes,
        output_hashes=output_hashes,
        reproducibility_score=score,
        rerun_command="",  # filled below
    )
    manifest.rerun_command = generate_rerun_command(manifest)
    return manifest


def verify_manifest(manifest: PipelineManifest) -> tuple[bool, list[str]]:
    """Verify current environment matches manifest. Returns (ok, issues)."""
    issues: list[str] = []
    current_env = capture_environment()

    if current_env.python_version != manifest.environment.python_version:
        issues.append(
            f"Python version mismatch: manifest={manifest.environment.python_version!r} "
            f"current={current_env.python_version!r}"
        )

    if current_env.platform != manifest.environment.platform:
        issues.append(
            f"Platform mismatch: manifest={manifest.environment.platform!r} "
            f"current={current_env.platform!r}"
        )

    for tv in manifest.tool_versions:
        current_version = TOOL_VERSION_REGISTRY.get(tv.name)
        if current_version is None:
            issues.append(f"Tool {tv.name!r} not found in current registry")
        elif current_version != tv.version:
            issues.append(
                f"Tool {tv.name!r} version mismatch: manifest={tv.version!r} "
                f"current={current_version!r}"
            )

    return (len(issues) == 0, issues)


def generate_rerun_command(manifest: PipelineManifest) -> str:
    """Produce a CLI-style command that would reproduce the run."""
    tools = ",".join(t.name for t in manifest.tool_versions)
    seeds_part = ""
    if manifest.random_seeds:
        seeds_str = ",".join(f"{k}={v}" for k, v in manifest.random_seeds.items())
        seeds_part = f" --seeds {seeds_str}"
    return (
        f"foldagent run"
        f" --manifest-id {manifest.manifest_id}"
        f" --tools {tools}"
        f"{seeds_part}"
        f" --input-hashes {json.dumps(manifest.input_hashes)}"
    )


# ---------------------------------------------------------------------------
# Manifest store
# ---------------------------------------------------------------------------

_manifest_store: dict[str, PipelineManifest] = {}


def store_manifest(manifest: PipelineManifest) -> str:
    _manifest_store[manifest.manifest_id] = manifest
    return manifest.manifest_id


def get_manifest(manifest_id: str) -> PipelineManifest | None:
    return _manifest_store.get(manifest_id)


def list_manifests() -> list[dict]:
    return [
        {
            "manifest_id": m.manifest_id,
            "created_at": m.created_at,
            "tool_count": len(m.tool_versions),
            "reproducibility_score": m.reproducibility_score,
        }
        for m in _manifest_store.values()
    ]


# ---------------------------------------------------------------------------
# Feature 2: FAIR-compliant structured prediction reports
# ---------------------------------------------------------------------------

SCHEMA_ORG_CONTEXT: dict[str, str] = {
    "@context": "https://schema.org/",
    "Dataset": "https://schema.org/Dataset",
    "creator": "https://schema.org/creator",
    "dateCreated": "https://schema.org/dateCreated",
    "license": "https://schema.org/license",
    "keywords": "https://schema.org/keywords",
    "identifier": "https://schema.org/identifier",
    "description": "https://schema.org/description",
    "name": "https://schema.org/name",
}

EDAM_ONTOLOGY_TERMS: dict[str, str] = {
    "protein_structure_prediction": "http://edamontology.org/operation_0474",
    "sequence_analysis": "http://edamontology.org/operation_2403",
    "variant_effect": "http://edamontology.org/operation_3461",
    "structure_visualisation": "http://edamontology.org/operation_0570",
    "molecular_docking": "http://edamontology.org/operation_0478",
    "protein_sequence": "http://edamontology.org/data_2976",
    "protein_structure": "http://edamontology.org/data_1460",
    "vcf": "http://edamontology.org/format_3016",
    "pdb_format": "http://edamontology.org/format_1476",
    "json_format": "http://edamontology.org/format_3464",
    "neoantigen": "http://edamontology.org/topic_3930",
    "immunoinformatics": "http://edamontology.org/topic_3948",
}


@dataclass
class FAIRMetadata:
    persistent_id: str  # "foldagent:pred/{uuid}"
    title: str
    description: str
    creators: list[str]
    created_date: str  # ISO
    modified_date: str  # ISO
    license: str
    keywords: list[str]
    ontology_terms: list[str]
    format_mimetype: str
    schema_version: str


@dataclass
class FAIRReport:
    metadata: FAIRMetadata
    content: dict
    machine_readable_json_ld: str
    human_readable_summary: str
    deposition_ready: bool
    suggested_repository: str


def generate_fair_metadata(
    title: str,
    description: str,
    creators: list[str],
    keywords: list[str],
) -> FAIRMetadata:
    """Auto-generate FAIR metadata with persistent ID and EDAM ontology terms."""
    pid = f"foldagent:pred/{uuid.uuid4()}"
    now = _now_iso()

    # Map keywords to EDAM terms
    relevant_edam: list[str] = []
    kw_lower = {k.lower() for k in keywords}
    if any(w in kw_lower for w in ("structure", "protein", "fold")):
        relevant_edam.append(EDAM_ONTOLOGY_TERMS["protein_structure_prediction"])
        relevant_edam.append(EDAM_ONTOLOGY_TERMS["protein_structure"])
    if any(w in kw_lower for w in ("variant", "mutation", "snp")):
        relevant_edam.append(EDAM_ONTOLOGY_TERMS["variant_effect"])
    if any(w in kw_lower for w in ("neoantigen", "immunogen", "vaccine")):
        relevant_edam.append(EDAM_ONTOLOGY_TERMS["neoantigen"])
        relevant_edam.append(EDAM_ONTOLOGY_TERMS["immunoinformatics"])
    if any(w in kw_lower for w in ("sequence", "amino acid")):
        relevant_edam.append(EDAM_ONTOLOGY_TERMS["sequence_analysis"])
        relevant_edam.append(EDAM_ONTOLOGY_TERMS["protein_sequence"])
    # Default: always include JSON format term
    relevant_edam.append(EDAM_ONTOLOGY_TERMS["json_format"])

    return FAIRMetadata(
        persistent_id=pid,
        title=title,
        description=description,
        creators=creators,
        created_date=now,
        modified_date=now,
        license="https://creativecommons.org/licenses/by/4.0/",
        keywords=keywords,
        ontology_terms=list(dict.fromkeys(relevant_edam)),  # deduplicated, ordered
        format_mimetype="application/json",
        schema_version="1.0",
    )


def create_fair_report(prediction_data: dict, metadata: FAIRMetadata) -> FAIRReport:
    """Wrap prediction in FAIR-compliant JSON-LD report."""
    json_ld = {
        "@context": "https://schema.org/",
        "@type": "Dataset",
        "@id": metadata.persistent_id,
        "identifier": metadata.persistent_id,
        "name": metadata.title,
        "description": metadata.description,
        "creator": [{"@type": "Person", "name": c} for c in metadata.creators],
        "dateCreated": metadata.created_date,
        "dateModified": metadata.modified_date,
        "license": metadata.license,
        "keywords": metadata.keywords,
        "encodingFormat": metadata.format_mimetype,
        "schemaVersion": metadata.schema_version,
        "subjectOf": EDAM_ONTOLOGY_TERMS,
        "additionalType": metadata.ontology_terms,
        "variableMeasured": list(prediction_data.keys()),
        "contentUrl": f"https://foldagent.research/data/{metadata.persistent_id}",
    }

    machine_readable = json.dumps(json_ld, indent=2)

    # Human-readable summary
    lines = [
        "FoldAgent Prediction Report",
        "========================",
        f"ID: {metadata.persistent_id}",
        f"Title: {metadata.title}",
        f"Created: {metadata.created_date}",
        f"Creators: {', '.join(metadata.creators)}",
        f"License: {metadata.license}",
        f"Keywords: {', '.join(metadata.keywords)}",
        f"Ontology terms: {len(metadata.ontology_terms)} EDAM terms",
        f"Data fields: {', '.join(list(prediction_data.keys())[:10])}",
        "",
        "RESEARCH USE ONLY — not for clinical or regulatory decision-making.",
    ]
    human_summary = "\n".join(lines)

    # Deposition ready: has PID, creators, license, description, keywords
    deposition_ready = bool(
        metadata.persistent_id
        and metadata.creators
        and metadata.license
        and metadata.description
        and metadata.keywords
    )

    suggested_repo = suggest_repository_from_metadata(metadata, prediction_data)

    return FAIRReport(
        metadata=metadata,
        content=prediction_data,
        machine_readable_json_ld=machine_readable,
        human_readable_summary=human_summary,
        deposition_ready=deposition_ready,
        suggested_repository=suggested_repo,
    )


def validate_fair_compliance(report: FAIRReport) -> dict:
    """Validate FAIR principles. Returns per-criterion scores (0-1)."""
    m = report.metadata

    # Findable: has PID, has metadata title/description/keywords
    findable_score = 0.0
    findable_checks = {
        "has_persistent_id": bool(m.persistent_id),
        "has_title": bool(m.title),
        "has_description": bool(m.description),
        "has_keywords": bool(m.keywords),
    }
    findable_score = sum(findable_checks.values()) / len(findable_checks)

    # Accessible: has format info, has content URL in JSON-LD
    accessible_checks = {
        "has_format_mimetype": bool(m.format_mimetype),
        "has_schema_version": bool(m.schema_version),
        "has_content": bool(report.content),
        "has_machine_readable": bool(report.machine_readable_json_ld),
    }
    accessible_score = sum(accessible_checks.values()) / len(accessible_checks)

    # Interoperable: uses standard vocabulary (EDAM terms present), JSON-LD
    interoperable_checks = {
        "has_ontology_terms": bool(m.ontology_terms),
        "has_json_ld": "schema.org" in report.machine_readable_json_ld,
        "has_edam_terms": any("edamontology.org" in t for t in m.ontology_terms),
        "uses_standard_license_uri": m.license.startswith("http"),
    }
    interoperable_score = sum(interoperable_checks.values()) / len(interoperable_checks)

    # Reusable: has license, has provenance (creators, date), has schema version
    reusable_checks = {
        "has_license": bool(m.license),
        "has_creators": bool(m.creators),
        "has_created_date": bool(m.created_date),
        "has_schema_version": bool(m.schema_version),
    }
    reusable_score = sum(reusable_checks.values()) / len(reusable_checks)

    overall = (findable_score + accessible_score + interoperable_score + reusable_score) / 4.0

    return {
        "findable": round(findable_score, 4),
        "accessible": round(accessible_score, 4),
        "interoperable": round(interoperable_score, 4),
        "reusable": round(reusable_score, 4),
        "overall": round(overall, 4),
        "details": {
            "findable_checks": findable_checks,
            "accessible_checks": accessible_checks,
            "interoperable_checks": interoperable_checks,
            "reusable_checks": reusable_checks,
        },
        "deposition_ready": report.deposition_ready,
    }


def suggest_repository(report: FAIRReport) -> str:
    return suggest_repository_from_metadata(report.metadata, report.content)


def suggest_repository_from_metadata(metadata: FAIRMetadata, content: dict) -> str:
    """Suggest a repository based on content type."""
    kw_lower = {k.lower() for k in metadata.keywords}
    content_keys = {k.lower() for k in content}
    all_terms = kw_lower | content_keys

    if any(w in all_terms for w in ("pdb", "structure", "coordinates", "protein_structure")):
        return "Protein Data Bank (https://www.rcsb.org/)"
    if any(w in all_terms for w in ("genomic", "variant", "vcf", "snp", "mutation")):
        return "European Nucleotide Archive (https://www.ebi.ac.uk/ena/)"
    if any(w in all_terms for w in ("neoantigen", "immunogen", "mhc", "hla", "vaccine")):
        return "Zenodo (https://zenodo.org/)"
    return "Figshare (https://figshare.com/)"
