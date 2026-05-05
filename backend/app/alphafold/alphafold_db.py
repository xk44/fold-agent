"""AlphaFold DB lookup helper."""

from __future__ import annotations

from backend.app.alphafold.schemas import AlphaFoldDbLookupRequest


def build_alphafold_db_command(request: AlphaFoldDbLookupRequest) -> list[str]:
    return ["alphafold_db_lookup", request.accession]


def build_alphafold_db_result(request: AlphaFoldDbLookupRequest) -> dict:
    accession = request.accession
    return {
        "structure": {
            "backend": "alphafold_db",
            "status": "completed",
            "source_url": f"https://alphafold.ebi.ac.uk/entry/{accession}",
            "model_cif": f"https://alphafold.ebi.ac.uk/files/AF-{accession}-F1-model_v4.cif",
            "summary_confidences_json": f"https://alphafold.ebi.ac.uk/files/AF-{accession}-F1-predicted_aligned_error_v4.json",
            "output_format": "mmcif",
            "accession": accession,
        }
    }
