import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.variant_explorer import (
    apply_variant_column_preset,
    build_variant_column_presets,
    build_variant_detail,
    build_variant_review_status_options,
    filter_variants,
    flatten_variant_rows,
    format_variant_option,
    sort_variants,
)


def test_flatten_variant_rows_extracts_quality_metrics_and_missing_fields() -> None:
    rows = flatten_variant_rows(
        [
            {
                "id": "var-1",
                "case_id": "case-1",
                "sample_id": "sample-1",
                "genomic_coordinates": "7:140453136A>T",
                "gene": "KIT",
                "transcript": "NM_000222.3",
                "protein_change": "p.V600E",
                "caller_source": "mock",
                "quality_metrics": {"parsed_from": "vcf", "vaf": 0.42},
                "annotation_source": "vep",
                "review_status": "unreviewed",
                "last_parsed_execution_id": "exec-1",
                "created_at": "2026-04-22T18:00:00Z",
            },
            {
                "id": "var-2",
                "case_id": "case-1",
                "genomic_coordinates": "1:10A>T",
                "review_status": "needs_data",
            },
        ]
    )

    assert rows[0]["quality_parsed_from"] == "vcf"
    assert rows[0]["quality_vaf"] == 0.42
    assert rows[0]["gene"] == "KIT"
    assert rows[1]["quality_parsed_from"] is None
    assert rows[1]["protein_change"] is None


def test_filter_and_sort_variants_respect_status_gene_range_defaults_and_none_values() -> None:
    variants = [
        {
            "id": "v1",
            "gene": "KIT",
            "protein_change": "p.A1",
            "review_status": "unreviewed",
            "created_at": "2026-04-22T00:00:00Z",
            "quality_metrics": {"vaf": 0.42},
        },
        {
            "id": "v2",
            "gene": None,
            "protein_change": None,
            "review_status": "needs_data",
            "created_at": None,
            "quality_metrics": {},
        },
        {
            "id": "v3",
            "gene": "BRAF",
            "protein_change": "p.B2",
            "review_status": "expert_rejected",
            "created_at": "2026-04-21T00:00:00Z",
            "quality_metrics": {"vaf": 0.91},
        },
    ]

    filtered = filter_variants(
        variants,
        review_status="unreviewed",
        gene_query="kit",
        vaf_min=0.4,
        vaf_max=0.5,
    )
    assert [item["id"] for item in filtered] == ["v1"]

    no_range_filter = filter_variants(
        variants,
        review_status="all",
        gene_query="",
        vaf_min=None,
        vaf_max=None,
    )
    assert [item["id"] for item in no_range_filter] == ["v1", "v2", "v3"]

    sorted_variants = sort_variants(variants, key="gene")
    assert [item["id"] for item in sorted_variants] == ["v3", "v1", "v2"]

    newest_first = sort_variants(variants, key="created_at", reverse=True)
    assert [item["id"] for item in newest_first] == ["v1", "v3", "v2"]


def test_build_variant_detail_and_option_formatting_cover_fallbacks() -> None:
    variant = {
        "id": "abc-1234-def",
        "gene": "KIT",
        "protein_change": "p.V600E",
        "quality_metrics": {"parsed_from": "vcf", "vaf": 0.42},
        "review_status": "unreviewed",
    }

    detail = build_variant_detail(variant)
    assert detail["gene"] == "KIT"
    assert detail["quality_parsed_from"] == "vcf"
    assert detail["quality_vaf"] == 0.42
    assert format_variant_option(variant) == "KIT · p.V600E"
    assert (
        format_variant_option({"id": "abc-1234-def", "gene": None, "protein_change": None})
        == "unknown · abc-1234"
    )


def test_build_variant_review_status_options_matches_expected_order() -> None:
    assert build_variant_review_status_options() == [
        "unreviewed",
        "needs_data",
        "expert_rejected",
        "expert_accepted_for_further_research",
    ]


def test_variant_column_presets_trim_rows_to_expected_fields() -> None:
    presets = build_variant_column_presets()
    assert "review" in presets
    assert "traceability" in presets

    rows = [
        {
            "gene": "KIT",
            "protein_change": "p.V600E",
            "review_status": "unreviewed",
            "quality_vaf": 0.42,
            "genomic_coordinates": "7:140453136A>T",
            "last_parsed_execution_id": "exec-1",
        }
    ]
    trimmed = apply_variant_column_preset(rows, "review")
    assert list(trimmed[0].keys()) == presets["review"]
    traceability = apply_variant_column_preset(rows, "traceability")
    assert "genomic_coordinates" in traceability[0]
    assert "quality_vaf" not in traceability[0]
