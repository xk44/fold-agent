"""AlphaFold output parsing helpers.

Extracts structure payloads from AlphaFold-family backend output (stdout JSON
and AF3-style output directories). This module isolates the parsing contract
from the HTTP/DB layer in main.py, making it independently testable and
extendable for new backend families.

Parsing strategies:
  1. Inline structure: ColabFold / AF2 / AF-Server backends emit a JSON blob
     on stdout containing a ``"structure"`` key holding the result metadata.
  2. AF3 output directory: AlphaFold3 writes ``*_model.cif``,
     ``*_summary_confidences.json``, ``*_confidences.json``, ``*_data.json``,
     per-seed/per-sample sub-directories, and optional embedding / distogram
     files into an output directory whose path is communicated via the
     ``"output_dir"`` key in stdout JSON.

Consumers (main.py, future backend-family modules) call
:func:`extract_alphafold_structure_payload` as the top-level entry point.
Lower-level helpers (:func:`parse_alphafold_stdout`,
:func:`extract_inline_structure`, :func:`harvest_af3_output_dir`) are exposed
for direct unit testing.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import TypedDict


# Canonical keys propagated from a parsed structure payload into the
# candidate ``structure_evidence`` dict and the ``StructureJob.confidence_metrics``.
STRUCTURE_EVIDENCE_KEYS: tuple[str, ...] = (
    "pdb_file",
    "model_cif",
    "summary_confidences_json",
    "confidences_json",
    "data_json",
    "source_url",
    "output_format",
    "accession",
    "pLDDT_mean",
    "pAE_mean",
    "ranking_score",
    "ptm",
    "iptm",
    "chain_pair_iptm",
    "pae",
    "atom_plddts",
    "chain_ptm",
    "chain_iptm",
)


class Af3HarvestedOutput(TypedDict, total=False):
    """Typed representation of harvested AF3 output directory artifacts.

    Captures all file paths and metric values discoverable from an AF3-style
    output directory.  All keys are optional (``total=False``) because
    different AF3 runs may produce different subsets of output files.
    """

    backend: str
    status: str
    output_dir: str
    output_format: str
    # Primary output files
    model_cif: str
    summary_confidences_json: str
    confidences_json: str
    data_json: str
    # Optional artifact file paths
    embeddings_path: str
    distogram_path: str
    # Per-seed / per-sample subdirectory paths
    seed_sample_dirs: list[str]


class ParsedStructurePayload(TypedDict, total=False):
    """Typed representation of a parsed AlphaFold structure payload.

    Fields correspond to the canonical set of metadata extracted from
    AlphaFold-family backend output.  All keys are optional (``total=False``)
    because different backend families populate different subsets.
    """

    backend: str
    status: str
    output_dir: str
    output_format: str
    pdb_file: str
    model_cif: str
    summary_confidences_json: str
    confidences_json: str
    data_json: str
    embeddings_path: str
    distogram_path: str
    seed_sample_dirs: list[str]
    source_url: str
    accession: str
    pLDDT_mean: float
    pAE_mean: float
    ranking_score: float
    ptm: float
    iptm: float
    chain_pair_iptm: dict
    pae: dict
    atom_plddts: dict
    chain_ptm: dict
    chain_iptm: dict


def parse_alphafold_stdout(stdout: str) -> dict | None:
    """Parse the JSON blob from an AlphaFold backend's stdout.

    Returns the parsed dict, or ``None`` if *stdout* is empty or is not
    valid JSON.
    """
    try:
        return json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return None


def extract_inline_structure(parsed_stdout: dict) -> dict | None:
    """Return the inline ``"structure"`` dict from *parsed_stdout*, if present.

    A non-empty dict value under the ``"structure"`` key is returned as-is.
    Missing, empty, or non-dict values yield ``None``.
    """
    structure = parsed_stdout.get("structure")
    if isinstance(structure, dict) and structure:
        return structure
    return None


def _harvest_af3_confidences_json(
    payload: dict,
    confidences_path: Path,
) -> None:
    """Extract detailed per-residue metrics from ``*_confidences.json``.

    AF3 emits a companion ``*_confidences.json`` alongside the summary file.
    It may contain ``pae`` (predicted aligned error), ``atom_plddts``, and
    per-chain confidence metrics (``chain_ptm``, ``chain_iptm``).
    Mutates *payload* in-place.
    """
    payload["confidences_json"] = str(confidences_path)
    try:
        conf_data = json.loads(confidences_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(conf_data, dict):
        return
    for key in ("pae", "atom_plddts", "chain_ptm", "chain_iptm"):
        if key in conf_data:
            payload[key] = conf_data[key]


def _harvest_af3_data_json(
    payload: dict,
    data_path: Path,
) -> None:
    """Record the ``*_data.json`` path and extract simple metrics from it.

    The ``*_data.json`` file holds input features and may carry a
    ``ranking_score`` when no summary confidences file is present.
    Mutates *payload* in-place.
    """
    payload["data_json"] = str(data_path)
    try:
        data_content = json.loads(data_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(data_content, dict):
        return
    # ranking_score can appear at the top level of data.json
    if "ranking_score" in data_content and "ranking_score" not in payload:
        payload["ranking_score"] = data_content["ranking_score"]


def _harvest_af3_seed_sample_dirs(
    payload: dict,
    output_dir: Path,
) -> None:
    """Discover per-seed and per-sample subdirectories inside *output_dir*.

    AF3 organises outputs under ``seed-*/sample-N/`` sub-directories.  Each
    such directory may contain its own ``*_model.cif``, ``*_confidences.json``,
    etc.  We record the discovered subdirectory paths and harvest the
    ``*_confidences.json`` from the first sample if the top-level confidences
    file was not found.
    Mutates *payload* in-place.
    """
    seed_dirs: list[str] = []
    # Collect seed-*/sample-* directories
    for seed_path in sorted(output_dir.glob("seed-*")):
        if not seed_path.is_dir():
            continue
        for sample_path in sorted(seed_path.glob("sample-*")):
            if sample_path.is_dir():
                seed_dirs.append(str(sample_path))
        # Also record the seed dir itself if it has no sample sub-dirs
        # but contains model/confidences files directly
        if not any(seed_path.glob("sample-*")) and any(seed_path.glob("*_model.cif")):
            seed_dirs.append(str(seed_path))

    if seed_dirs:
        payload["seed_sample_dirs"] = seed_dirs


def _harvest_af3_embeddings_and_distograms(
    payload: dict,
    output_dir: Path,
) -> None:
    """Discover optional embedding and distogram files in the output directory.

    AF3 may emit embeddings and distograms in two locations:

    1. Top-level: ``*_embeddings.npy`` / ``*_embeddings.npz`` and
       ``*_distogram.npy`` / ``*_distogram.npz``
    2. Per-seed subdirectories: ``seed-<seed>_embeddings/embeddings.npz`` and
       ``seed-<seed>_distogram/distogram.npz`` (the canonical AF3 layout when
       ``--save_embeddings=true`` or ``--save_distogram=true`` is used).

    We check both locations, preferring the per-seed subdirectory layout when
    present because it is the documented canonical form.
    Mutates *payload* in-place.
    """
    # --- Per-seed canonical layout (preferred) ---
    for seed_emb_dir in sorted(output_dir.glob("seed-*_embeddings")):
        if seed_emb_dir.is_dir() and "embeddings_path" not in payload:
            candidates = sorted(seed_emb_dir.glob("*.npz")) + sorted(seed_emb_dir.glob("*.npy"))
            if candidates:
                payload["embeddings_path"] = str(candidates[0])
                break

    for seed_dist_dir in sorted(output_dir.glob("seed-*_distogram")):
        if seed_dist_dir.is_dir() and "distogram_path" not in payload:
            candidates = sorted(seed_dist_dir.glob("*.npz")) + sorted(seed_dist_dir.glob("*.npy"))
            if candidates:
                payload["distogram_path"] = str(candidates[0])
                break

    # --- Top-level fallback ---
    for pattern, key in (
        ("*_embeddings.npy", "embeddings_path"),
        ("*_embeddings.npz", "embeddings_path"),
        ("*_distogram.npy", "distogram_path"),
        ("*_distogram.npz", "distogram_path"),
    ):
        if key not in payload:
            candidates = sorted(output_dir.glob(pattern))
            if candidates:
                payload[key] = str(candidates[0])


def harvest_af3_output_dir(
    output_dir: Path,
    *,
    backend: str | None = None,
    status: str | None = None,
) -> dict | None:
    """Harvest structure metadata from an AF3-style output directory.

    Discovers the following artifacts inside *output_dir*:

    - ``*_model.cif`` — primary model structure (mmCIF)
    - ``*_summary_confidences.json`` — aggregate confidence metrics (ptm,
      iptm, ranking_score, chain_pair_iptm)
    - ``*_ranking_scores.csv`` — fallback ranking metrics when summary
      confidences are absent
    - ``*_confidences.json`` — detailed per-residue metrics (pae,
      atom_plddts, chain_ptm, chain_iptm)
    - ``*_data.json`` — input features / sequencing data
    - ``seed-*/sample-*/`` — per-seed per-sample subdirectory paths
    - ``*_embeddings.{npy,npz}`` — optional embedding vectors
    - ``*_distogram.{npy,npz}`` — optional distogram arrays

    Returns a dict with at least the four base keys (``backend``,
    ``status``, ``output_dir``, ``output_format``) plus any harvested
    fields, **or** ``None`` if the directory is missing, not a directory,
    or contains no interesting output files (i.e. the result dict would
    not exceed the four base keys).
    """
    if not output_dir.exists() or not output_dir.is_dir():
        return None

    model_cif_candidates = sorted(output_dir.glob("*_model.cif"))
    summary_candidates = sorted(output_dir.glob("*_summary_confidences.json"))
    ranking_score_candidates = sorted(output_dir.glob("*_ranking_scores.csv"))
    confidences_candidates = sorted(output_dir.glob("*_confidences.json"))
    data_candidates = sorted(output_dir.glob("*_data.json"))

    payload: dict = {
        "backend": backend,
        "status": status,
        "output_dir": str(output_dir),
        "output_format": "mmcif",
    }
    if model_cif_candidates:
        payload["model_cif"] = str(model_cif_candidates[0])
    if summary_candidates:
        payload["summary_confidences_json"] = str(summary_candidates[0])
        try:
            summary_data = json.loads(summary_candidates[0].read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary_data = {}
        for key in ("ptm", "iptm", "ranking_score", "chain_pair_iptm"):
            if key in summary_data:
                payload[key] = summary_data[key]
    elif ranking_score_candidates:
        try:
            with ranking_score_candidates[0].open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except csv.Error:
            rows = []
        if rows:
            first_row = rows[0]
            for key in ("ranking_score", "ptm", "iptm"):
                raw_value = first_row.get(key)
                if raw_value not in (None, ""):
                    try:
                        payload[key] = float(raw_value)
                    except ValueError:
                        pass

    # --- Extended AF3 harvesting ---
    if confidences_candidates:
        _harvest_af3_confidences_json(payload, confidences_candidates[0])

    if data_candidates:
        _harvest_af3_data_json(payload, data_candidates[0])

    _harvest_af3_seed_sample_dirs(payload, output_dir)

    _harvest_af3_embeddings_and_distograms(payload, output_dir)

    # Require at least one interesting file beyond the 4 base keys
    return payload if len(payload) > 4 else None


def extract_alphafold_structure_payload(result: dict) -> dict | None:
    """Extract structure payload from an AlphaFold execution result dict.

    Attempts two parsing strategies in order:

    1. If *stdout* JSON has an inline ``"structure"`` key, return it directly
       (ColabFold / AF2 / AF-Server path).
    2. If *stdout* JSON has an ``"output_dir"`` key, attempt AF3-style
       directory harvesting for ``*_model.cif`` and
       ``*_summary_confidences.json`` (AlphaFold3 path).

    Returns ``None`` if no structure data can be extracted.
    """
    parsed = parse_alphafold_stdout(result.get("stdout") or "")
    if parsed is None:
        return None

    inline = extract_inline_structure(parsed)
    if inline is not None:
        return inline

    output_dir_value = parsed.get("output_dir")
    if not output_dir_value:
        return None

    return harvest_af3_output_dir(
        Path(output_dir_value),
        backend=result.get("backend"),
        status=result.get("status"),
    )


def filter_structure_evidence(source: dict) -> dict:
    """Filter *source* to only canonical :data:`STRUCTURE_EVIDENCE_KEYS`.

    Useful when writing a subset of structure metadata into the candidate
    ``structure_evidence`` JSON column or the ``StructureJob.confidence_metrics``
    column.
    """
    return {k: source[k] for k in STRUCTURE_EVIDENCE_KEYS if k in source}