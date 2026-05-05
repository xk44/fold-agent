"""Tests for the 3 new framework pipeline adapters and their API endpoints.

Covers: NetMHCIIpanStep, RNAExpressionValidationStep, MHCMetadataStep,
GET /pipeline/framework/adapters, POST /pipeline/framework/adapters/{name}/test.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.pipeline.framework import (
    FRAMEWORK_STEPS,
    ErrorCategory,
    MHCMetadataStep,
    NetMHCIIpanStep,
    RNAExpressionValidationStep,
)


# ---------------------------------------------------------------------------
# NetMHCIIpanStep
# ---------------------------------------------------------------------------


class TestNetMHCIIpanStep:
    def setup_method(self) -> None:
        self.step = NetMHCIIpanStep()

    def test_name_and_description(self) -> None:
        assert self.step.name == "netmhciipan"
        assert "MHC class II" in self.step.description

    def test_valid_input_returns_success(self) -> None:
        result = self.step.run(
            {"peptides": ["ACDEFGHIKLM"], "alleles": ["HLA-DRB1*01:01"]}
        )
        assert result.status == "success"
        assert result.step_name == "netmhciipan"

    def test_output_keys_present(self) -> None:
        result = self.step.run(
            {"peptides": ["ACDEFGHIKLM"], "alleles": ["HLA-DRB1*01:01"]}
        )
        out = result.output
        assert "predictions" in out
        assert "peptide_count" in out
        assert "allele_count" in out
        assert "tool" in out
        assert out["tool"] == "netmhciipan"

    def test_prediction_fields_per_entry(self) -> None:
        result = self.step.run(
            {"peptides": ["ACDEFGHIKLM", "MNPQRSTVWY"], "alleles": ["HLA-DRB1*01:01"]}
        )
        for pred in result.output["predictions"]:
            assert "allele" in pred
            assert "peptide" in pred
            assert "ic50" in pred
            assert "rank" in pred
            assert "strong_binder" in pred
            assert "weak_binder" in pred

    def test_multiple_alleles_multiple_peptides(self) -> None:
        peptides = ["ACDEFGHIKLM", "MNPQRSTVWY", "ACGHIKLMNPQ"]
        alleles = ["HLA-DRB1*01:01", "HLA-DRB1*03:01", "HLA-DQB1*02:01"]
        result = self.step.run({"peptides": peptides, "alleles": alleles})
        assert result.status == "success"
        assert result.output["peptide_count"] == len(peptides)
        assert result.output["allele_count"] == len(alleles)
        # one prediction per (allele, peptide) combination
        assert len(result.output["predictions"]) == len(peptides) * len(alleles)

    def test_missing_peptides_field_returns_failed(self) -> None:
        result = self.step.run({"alleles": ["HLA-DRB1*01:01"]})
        assert result.status == "failed"
        assert result.error_category == ErrorCategory.input_error
        assert "peptides" in result.error

    def test_missing_alleles_field_returns_failed(self) -> None:
        result = self.step.run({"peptides": ["ACDEFGHIKLM"]})
        assert result.status == "failed"
        assert result.error_category == ErrorCategory.input_error
        assert "alleles" in result.error

    def test_empty_peptides_returns_success_with_no_predictions(self) -> None:
        result = self.step.run({"peptides": [], "alleles": ["HLA-DRB1*01:01"]})
        assert result.status == "success"
        assert result.output["predictions"] == []


# ---------------------------------------------------------------------------
# RNAExpressionValidationStep
# ---------------------------------------------------------------------------


class TestRNAExpressionValidationStep:
    def setup_method(self) -> None:
        self.step = RNAExpressionValidationStep()

    def test_name_and_description(self) -> None:
        assert self.step.name == "rna_expression_validation"
        assert "expression" in self.step.description.lower()

    def test_valid_input_returns_success(self) -> None:
        result = self.step.run({"expression_data": {"KRAS": 5.0, "TP53": 0.5}})
        assert result.status == "success"
        assert result.step_name == "rna_expression_validation"

    def test_genes_above_threshold_are_validated(self) -> None:
        result = self.step.run(
            {"expression_data": {"EGFR": 10.0, "MYC": 3.5, "BRCA1": 1.0}}
        )
        out = result.output
        assert "EGFR" in out["validated_genes"]
        assert "MYC" in out["validated_genes"]
        assert "BRCA1" in out["validated_genes"]

    def test_genes_below_threshold_are_flagged(self) -> None:
        result = self.step.run(
            {"expression_data": {"LOWGENE": 0.5, "ZEROGENE": 0.0}}
        )
        out = result.output
        assert "LOWGENE" in out["low_expression_genes"]
        assert "ZEROGENE" in out["low_expression_genes"]
        assert out["filtered_count"] == 2

    def test_mixed_expression_levels(self) -> None:
        expression = {
            "KRAS": 8.2,     # above threshold
            "NRAS": 0.8,     # below
            "BRAF": 1.0,     # exactly at threshold → validated
            "CDKN2A": 0.1,   # below
            "TP53": 15.0,    # above
        }
        result = self.step.run({"expression_data": expression})
        out = result.output
        assert "KRAS" in out["validated_genes"]
        assert "BRAF" in out["validated_genes"]
        assert "TP53" in out["validated_genes"]
        assert "NRAS" in out["low_expression_genes"]
        assert "CDKN2A" in out["low_expression_genes"]
        assert out["filtered_count"] == 2
        assert out["total_genes"] == 5

    def test_output_keys_present(self) -> None:
        result = self.step.run({"expression_data": {"KRAS": 5.0}})
        out = result.output
        for key in ("validated_genes", "low_expression_genes", "filtered_count", "total_genes", "threshold_tpm"):
            assert key in out

    def test_missing_expression_data_field_returns_failed(self) -> None:
        result = self.step.run({})
        assert result.status == "failed"
        assert result.error_category == ErrorCategory.input_error
        assert "expression_data" in result.error

    def test_empty_expression_data(self) -> None:
        result = self.step.run({"expression_data": {}})
        assert result.status == "success"
        assert result.output["validated_genes"] == []
        assert result.output["low_expression_genes"] == []
        assert result.output["filtered_count"] == 0


# ---------------------------------------------------------------------------
# MHCMetadataStep
# ---------------------------------------------------------------------------


class TestMHCMetadataStep:
    def setup_method(self) -> None:
        self.step = MHCMetadataStep()

    def test_name_and_description(self) -> None:
        assert self.step.name == "mhc_metadata"
        assert "metadata" in self.step.description.lower()

    def test_human_hla_allele_known_supertype(self) -> None:
        result = self.step.run(
            {"species": "human", "alleles": ["HLA-DRB1*01:01"]}
        )
        assert result.status == "success"
        meta = result.output["allele_metadata"]
        assert len(meta) == 1
        entry = meta[0]
        assert entry["allele"] == "HLA-DRB1*01:01"
        assert entry["locus"] == "DRB1"
        assert entry["species"] == "human"
        assert entry["supertype"] == "DR1"
        assert entry["known"] is True

    def test_multiple_human_alleles(self) -> None:
        alleles = ["HLA-DRB1*03:01", "HLA-DQB1*02:01", "HLA-DPB1*04:01"]
        result = self.step.run({"species": "human", "alleles": alleles})
        out = result.output
        assert out["allele_count"] == 3
        assert out["known_count"] == 3
        loci = {m["locus"] for m in out["allele_metadata"]}
        assert loci == {"DRB1", "DQB1", "DPB1"}

    def test_dog_dla_allele_known_supertype(self) -> None:
        result = self.step.run(
            {"species": "dog", "alleles": ["DLA-DRB1*001:01"]}
        )
        assert result.status == "success"
        entry = result.output["allele_metadata"][0]
        assert entry["allele"] == "DLA-DRB1*001:01"
        assert entry["species"] == "dog"
        assert entry["supertype"] == "DLA-DR1"
        assert entry["known"] is True

    def test_dog_canine_species_alias(self) -> None:
        result = self.step.run(
            {"species": "canine", "alleles": ["DLA-DQB1*002:01"]}
        )
        assert result.status == "success"
        assert result.output["allele_metadata"][0]["species"] == "dog"

    def test_unknown_allele_returns_unknown_supertype(self) -> None:
        result = self.step.run(
            {"species": "human", "alleles": ["HLA-DRB1*99:99"]}
        )
        entry = result.output["allele_metadata"][0]
        assert entry["supertype"] == "unknown"
        assert entry["known"] is False

    def test_output_keys_present(self) -> None:
        result = self.step.run({"species": "human", "alleles": ["HLA-DRB1*01:01"]})
        out = result.output
        for key in ("species", "allele_metadata", "allele_count", "known_count"):
            assert key in out

    def test_missing_species_field_returns_failed(self) -> None:
        result = self.step.run({"alleles": ["HLA-DRB1*01:01"]})
        assert result.status == "failed"
        assert result.error_category == ErrorCategory.input_error
        assert "species" in result.error

    def test_missing_alleles_field_returns_failed(self) -> None:
        result = self.step.run({"species": "human"})
        assert result.status == "failed"
        assert result.error_category == ErrorCategory.input_error
        assert "alleles" in result.error


# ---------------------------------------------------------------------------
# FRAMEWORK_STEPS registry
# ---------------------------------------------------------------------------


def test_framework_steps_includes_new_adapters() -> None:
    names = [step.name for step in FRAMEWORK_STEPS]
    assert "netmhciipan" in names
    assert "rna_expression_validation" in names
    assert "mhc_metadata" in names


def test_framework_steps_has_seven_entries() -> None:
    assert len(FRAMEWORK_STEPS) == 7


# ---------------------------------------------------------------------------
# API: GET /pipeline/framework/adapters
# ---------------------------------------------------------------------------


def test_list_framework_adapters_returns_200(client: TestClient) -> None:
    response = client.get("/pipeline/framework/adapters")
    assert response.status_code == 200


def test_list_framework_adapters_returns_list(client: TestClient) -> None:
    response = client.get("/pipeline/framework/adapters")
    payload = response.json()
    assert isinstance(payload, list)


def test_list_framework_adapters_count(client: TestClient) -> None:
    response = client.get("/pipeline/framework/adapters")
    payload = response.json()
    assert len(payload) == len(FRAMEWORK_STEPS)


def test_list_framework_adapters_contains_all_names(client: TestClient) -> None:
    response = client.get("/pipeline/framework/adapters")
    names = [item["name"] for item in response.json()]
    for step in FRAMEWORK_STEPS:
        assert step.name in names


def test_list_framework_adapters_entry_shape(client: TestClient) -> None:
    response = client.get("/pipeline/framework/adapters")
    for item in response.json():
        assert "name" in item
        assert "description" in item


# ---------------------------------------------------------------------------
# API: POST /pipeline/framework/adapters/{name}/test
# ---------------------------------------------------------------------------


def test_test_endpoint_netmhciipan_success(client: TestClient) -> None:
    response = client.post(
        "/pipeline/framework/adapters/netmhciipan/test",
        json={"peptides": ["ACDEFGHIKLM"], "alleles": ["HLA-DRB1*01:01"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["step_name"] == "netmhciipan"
    assert "predictions" in payload["output"]


def test_test_endpoint_rna_expression_success(client: TestClient) -> None:
    response = client.post(
        "/pipeline/framework/adapters/rna_expression_validation/test",
        json={"expression_data": {"KRAS": 5.0, "LOWGENE": 0.2}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert "validated_genes" in payload["output"]
    assert "LOWGENE" in payload["output"]["low_expression_genes"]


def test_test_endpoint_mhc_metadata_success(client: TestClient) -> None:
    response = client.post(
        "/pipeline/framework/adapters/mhc_metadata/test",
        json={"species": "human", "alleles": ["HLA-DRB1*01:01", "HLA-DQB1*02:01"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["output"]["allele_count"] == 2


def test_test_endpoint_unknown_adapter_returns_404(client: TestClient) -> None:
    response = client.post(
        "/pipeline/framework/adapters/nonexistent_adapter/test",
        json={},
    )
    assert response.status_code == 404
    assert "nonexistent_adapter" in response.json()["detail"]


def test_test_endpoint_step_result_shape(client: TestClient) -> None:
    response = client.post(
        "/pipeline/framework/adapters/alignment/test",
        json={},
    )
    assert response.status_code == 200
    payload = response.json()
    for key in ("step_name", "status", "output", "error", "duration_seconds"):
        assert key in payload


def test_test_endpoint_bad_input_returns_failed_not_500(client: TestClient) -> None:
    """A step that rejects its input should return 200 with status=failed, not 500."""
    response = client.post(
        "/pipeline/framework/adapters/netmhciipan/test",
        json={"alleles": ["HLA-DRB1*01:01"]},  # missing 'peptides'
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
