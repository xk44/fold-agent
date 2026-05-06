import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.structure_viewer import (
    build_compare_structure_viewer_html,
    build_structure_viewer_html,
    choose_compare_artifact,
    format_structure_artifact_option,
    format_structure_confidence_operator_summary,
    format_structure_confidence_summary,
    list_structure_artifacts,
    select_structure_artifact,
    viewer_format_for_artifact,
)


def test_select_structure_artifact_prefers_harvested_model_cif() -> None:
    artifact = select_structure_artifact(
        [
            {
                "artifact_type": "execution_log",
                "filename": "run.log",
                "path": "/tmp/run.log",
            },
            {
                "artifact_type": "alphafold_model_cif",
                "filename": "best_model.cif",
                "path": "/tmp/best_model.cif",
            },
            {
                "artifact_type": "alphafold_summary_confidences",
                "filename": "summary.json",
                "path": "/tmp/summary.json",
            },
        ]
    )

    assert artifact is not None
    assert artifact["artifact_type"] == "alphafold_model_cif"
    assert artifact["filename"] == "best_model.cif"


def test_viewer_format_for_artifact_maps_mmcif_to_mcif() -> None:
    format_name = viewer_format_for_artifact(
        {"filename": "best_model.cif"},
        {"confidence_metrics": {"output_format": "mmcif"}},
    )

    assert format_name == "mcif"


def test_build_structure_viewer_html_embeds_structure_payload() -> None:
    html = build_structure_viewer_html("data_demo\n#", "mcif")

    assert "3D structure viewer" in html
    assert "https://3dmol.org/build/3Dmol-min.js" in html
    assert 'addModel(structureText, "mcif")' in html
    assert "data_demo" in html


def test_list_structure_artifacts_filters_to_structure_files() -> None:
    artifacts = list_structure_artifacts(
        [
            {
                "artifact_type": "execution_log",
                "filename": "run.log",
                "path": "/tmp/run.log",
            },
            {
                "artifact_type": "alphafold_model_cif",
                "filename": "best_model.cif",
                "path": "/tmp/best_model.cif",
            },
            {
                "artifact_type": "execution_output",
                "filename": "ranked_0.pdb",
                "path": "/tmp/ranked_0.pdb",
            },
        ]
    )

    assert [artifact["filename"] for artifact in artifacts] == [
        "best_model.cif",
        "ranked_0.pdb",
    ]


def test_format_structure_artifact_option_surfaces_type_and_name() -> None:
    label = format_structure_artifact_option(
        {"artifact_type": "alphafold_model_cif", "filename": "best_model.cif"},
        {"confidence_metrics": {"output_format": "mmcif"}},
    )

    assert label == "alphafold_model_cif · mcif · best_model.cif"


def test_format_structure_confidence_summary_surfaces_scores() -> None:
    summary = format_structure_confidence_summary(
        {
            "output_path": "/tmp/best_model.cif",
            "confidence_metrics": {
                "ranking_score": 0.91,
                "ptm": 0.72,
                "iptm": 0.88,
                "source_url": "https://alphafold.ebi.ac.uk/entry/P04637",
                "output_format": "mmcif",
                "model_cif": "/tmp/best_model.cif",
            },
        }
    )

    assert summary["ranking_score"] == "0.91"
    assert summary["ptm"] == "0.72"
    assert summary["iptm"] == "0.88"
    assert summary["output_format"] == "mmcif"
    assert summary["model_path"] == "/tmp/best_model.cif"
    assert summary["source_url"].endswith("P04637")


def test_choose_compare_artifact_picks_different_structure_file() -> None:
    artifacts = [
        {
            "artifact_type": "alphafold_model_cif",
            "filename": "best_model.cif",
            "path": "/tmp/best_model.cif",
        },
        {
            "artifact_type": "execution_output",
            "filename": "ranked_0.pdb",
            "path": "/tmp/ranked_0.pdb",
        },
    ]

    compare_artifact = choose_compare_artifact(artifacts, artifacts[0])

    assert compare_artifact is not None
    assert compare_artifact["path"] == "/tmp/ranked_0.pdb"


def test_build_compare_structure_viewer_html_embeds_both_payloads() -> None:
    html = build_compare_structure_viewer_html(
        left_structure_text="data_left\n#",
        left_format="mcif",
        left_label="best_model.cif",
        right_structure_text="ATOM 1",
        right_format="pdb",
        right_label="ranked_0.pdb",
    )

    assert "Compare structures" in html
    assert 'addModel(leftStructureText, "mcif")' in html
    assert 'addModel(rightStructureText, "pdb")' in html
    assert "best_model.cif" in html
    assert "ranked_0.pdb" in html


def test_select_structure_artifact_returns_none_without_structure_files() -> None:
    artifact = select_structure_artifact(
        [
            {
                "artifact_type": "execution_log",
                "filename": "run.log",
                "path": "/tmp/run.log",
            },
            {
                "artifact_type": "alphafold_summary_confidences",
                "filename": "summary.json",
            },
        ]
    )

    assert artifact is None


def test_choose_compare_artifact_returns_none_for_single_artifact() -> None:
    artifact = {
        "artifact_type": "alphafold_model_cif",
        "filename": "best_model.cif",
        "path": "/tmp/best_model.cif",
    }

    assert choose_compare_artifact([artifact], artifact) is None


def test_viewer_format_for_artifact_defaults_to_pdb_without_metadata() -> None:
    assert viewer_format_for_artifact(None, None) == "pdb"


def test_format_structure_confidence_summary_handles_empty_payload() -> None:
    summary = format_structure_confidence_summary(None)

    assert summary == {
        "ranking_score": "n/a",
        "ptm": "n/a",
        "iptm": "n/a",
        "output_format": "n/a",
        "source_url": "n/a",
        "model_path": "n/a",
    }


def test_format_structure_confidence_operator_summary_surfaces_scores_and_paths() -> None:
    text = format_structure_confidence_operator_summary(
        {
            "output_path": "/tmp/fallback.cif",
            "confidence_metrics": {
                "ranking_score": 0.91,
                "ptm": 0.72,
                "iptm": 0.88,
                "source_url": "https://alphafold.ebi.ac.uk/entry/P04637",
                "output_format": "mmcif",
                "model_cif": "/tmp/best_model.cif",
            },
        }
    )

    assert "ranking_score=0.91" in text
    assert "ptm=0.72" in text
    assert "iptm=0.88" in text
    assert "format=mmcif" in text
    assert "source=https://alphafold.ebi.ac.uk/entry/P04637" in text
    assert "model=/tmp/best_model.cif" in text


def test_format_structure_confidence_operator_summary_flags_missing_metrics() -> None:
    text = format_structure_confidence_operator_summary({"output_path": "/tmp/model.pdb"})

    assert text.startswith("Structure confidence incomplete")
    assert "ranking_score=n/a" in text
    assert "ptm=n/a" in text
    assert "iptm=n/a" in text
    assert "model=/tmp/model.pdb" in text
