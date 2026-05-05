from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
import re


_FILENAME_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_upload_filename(filename: str) -> str:
    name = Path(filename or "upload.dat").name
    if "." in name:
        stem, suffix = name.split(".", 1)
        stem = _FILENAME_SAFE_CHARS.sub("_", stem).strip("._-") or "upload"
        suffix = _FILENAME_SAFE_CHARS.sub("_", suffix).strip("._-")
        return f"{stem}.{suffix}" if suffix else stem
    return _FILENAME_SAFE_CHARS.sub("_", name).strip("._-") or "upload"


def stage_uploaded_sample(
    content: bytes,
    filename: str,
    *,
    case_id: str,
    sample_type: str,
    root_dir: str | Path,
) -> dict:
    sanitized_name = sanitize_upload_filename(filename)
    target_dir = Path(root_dir) / case_id / sample_type
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / sanitized_name
    target_path.write_bytes(content)
    return {
        "path": str(target_path),
        "filename": sanitized_name,
        "checksum": sha256(content).hexdigest(),
        "size_bytes": len(content),
        "staged_at": datetime.now(UTC).isoformat(),
    }


def build_subject_creation_payload(
    *,
    display_name: str,
    species: str | None = None,
    notes: str | None = None,
    privacy_mode: str = "redacted",
) -> dict:
    return {
        "anonymized_display_name": display_name,
        "metadata_json": {
            "species": species,
            "intake_notes": notes,
        },
        "privacy_flags": {
            "redacted": privacy_mode == "redacted",
        },
    }


def build_sample_registration_payload(
    *,
    sample_type: str,
    staged_upload: dict,
    source_lab: str | None = None,
    notes: str | None = None,
    subject_id: str | None = None,
) -> dict:
    payload = {
        "sample_type": sample_type,
        "subject_id": subject_id,
        "file_paths": {"primary": staged_upload["path"]},
        "checksum": staged_upload.get("checksum"),
        "source_lab": source_lab or None,
        "custody_metadata": {
            "uploaded_filename": staged_upload.get("filename"),
            "size_bytes": staged_upload.get("size_bytes"),
            "notes": notes or None,
            "staging_mode": "streamlit_upload",
        },
    }
    return payload
