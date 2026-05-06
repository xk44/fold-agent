import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.upload_wizard import (
    build_sample_registration_payload,
    build_subject_creation_payload,
)


def test_build_subject_creation_payload_includes_metadata_and_privacy_flags() -> None:
    payload = build_subject_creation_payload(
        display_name="Rosie-demo",
        species="dog",
        notes="left flank biopsy",
        privacy_mode="redacted",
    )

    assert payload == {
        "anonymized_display_name": "Rosie-demo",
        "metadata_json": {"species": "dog", "intake_notes": "left flank biopsy"},
        "privacy_flags": {"redacted": True},
    }


def test_build_sample_registration_payload_can_link_subject_and_preserve_notes() -> None:
    payload = build_sample_registration_payload(
        sample_type="tumor",
        staged_upload={
            "path": "/tmp/foldagent/case-123/tumor/demo.fastq.gz",
            "filename": "demo.fastq.gz",
            "checksum": "abc123",
            "size_bytes": 42,
        },
        source_lab="Local Sequencing Core",
        notes="paired-end lane 1",
        subject_id="subject-123",
    )

    assert payload["subject_id"] == "subject-123"
    assert payload["custody_metadata"]["notes"] == "paired-end lane 1"
    assert payload["file_paths"]["primary"].endswith("demo.fastq.gz")
