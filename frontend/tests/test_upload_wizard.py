import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.upload_wizard import (
    build_sample_registration_payload,
    sanitize_upload_filename,
    stage_uploaded_sample,
)


def test_sanitize_upload_filename_strips_path_and_unsafe_chars() -> None:
    sanitized = sanitize_upload_filename("../Tumor Panel (final).vcf.gz")

    assert sanitized == "Tumor_Panel_final.vcf.gz"


def test_stage_uploaded_sample_writes_local_file_and_checksum(tmp_path) -> None:
    staged = stage_uploaded_sample(
        b"chr1\t10\t.\tA\tT\n",
        "tumor panel.vcf",
        case_id="case-123",
        sample_type="tumor",
        root_dir=tmp_path,
    )

    saved_path = Path(staged["path"])
    assert saved_path.exists()
    assert saved_path.read_bytes() == b"chr1\t10\t.\tA\tT\n"
    assert saved_path.parent == tmp_path / "case-123" / "tumor"
    assert staged["filename"] == "tumor_panel.vcf"
    assert staged["size_bytes"] == len(b"chr1\t10\t.\tA\tT\n")
    assert len(staged["checksum"]) == 64


def test_build_sample_registration_payload_includes_primary_path_and_custody_metadata() -> None:
    payload = build_sample_registration_payload(
        sample_type="rna",
        staged_upload={
            "path": "/tmp/foldagent/case-123/rna/demo.fastq.gz",
            "filename": "demo.fastq.gz",
            "checksum": "abc123",
            "size_bytes": 42,
        },
        source_lab="Local Sequencing Core",
        notes="paired-end lane 1",
    )

    assert payload == {
        "sample_type": "rna",
        "subject_id": None,
        "file_paths": {"primary": "/tmp/foldagent/case-123/rna/demo.fastq.gz"},
        "checksum": "abc123",
        "source_lab": "Local Sequencing Core",
        "custody_metadata": {
            "uploaded_filename": "demo.fastq.gz",
            "size_bytes": 42,
            "notes": "paired-end lane 1",
            "staging_mode": "streamlit_upload",
        },
    }
