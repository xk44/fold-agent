"""Tests for typed pipeline adapter request schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.pipeline.schemas import (
    BwaRequest,
    GatkMutect2Request,
    PvactoolsRequest,
    VepRequest,
    parse_pipeline_request,
)


class TestBwaRequest:
    def test_valid_bwa_request(self):
        req = BwaRequest(reference="/ref.fa", fastq_1="/r1.fq", fastq_2="/r2.fq")
        assert req.reference == "/ref.fa"
        assert req.fastq_1 == "/r1.fq"
        assert req.fastq_2 == "/r2.fq"

    def test_missing_reference_raises(self):
        with pytest.raises(ValidationError):
            BwaRequest(reference="", fastq_1="/r1.fq")

    def test_missing_fastq_1_raises(self):
        with pytest.raises(ValidationError):
            BwaRequest(reference="/ref.fa", fastq_1="")


class TestGatkMutect2Request:
    def test_valid_request(self):
        req = GatkMutect2Request(
            input_bam="/tumor.bam", normal_bam="/normal.bam", tumor_sample="T001"
        )
        assert req.input_bam == "/tumor.bam"
        assert req.normal_bam == "/normal.bam"

    def test_missing_input_bam_raises(self):
        with pytest.raises(ValidationError):
            GatkMutect2Request(input_bam="")


class TestVepRequest:
    def test_valid_request(self):
        req = VepRequest(input_vcf="/in.vcf", output_path="/out.txt", everything=True)
        assert req.input_vcf == "/in.vcf"
        assert req.everything is True

    def test_missing_input_vcf_raises(self):
        with pytest.raises(ValidationError):
            VepRequest(input_vcf="")


class TestPvactoolsRequest:
    def test_valid_request(self):
        req = PvactoolsRequest(
            input_vcf="/in.vcf",
            sample_name="S1",
            alleles=["HLA-A*02:01"],
            prediction_algorithms=["NetMHC"],
        )
        assert req.sample_name == "S1"
        assert req.alleles == ["HLA-A*02:01"]

    def test_empty_alleles_raises(self):
        with pytest.raises(ValidationError):
            PvactoolsRequest(input_vcf="/in.vcf", sample_name="S1", alleles=[])

    def test_missing_sample_name_raises(self):
        with pytest.raises(ValidationError):
            PvactoolsRequest(input_vcf="/in.vcf", sample_name="", alleles=["HLA-A*02:01"])


class TestParsePipelineRequest:
    def test_routes_bwa(self):
        req = parse_pipeline_request("bwa", {"reference": "/ref.fa", "fastq_1": "/r1.fq"})
        assert isinstance(req, BwaRequest)

    def test_routes_gatk(self):
        req = parse_pipeline_request("gatk_mutect2", {"input_bam": "/t.bam"})
        assert isinstance(req, GatkMutect2Request)

    def test_routes_vep(self):
        req = parse_pipeline_request("vep", {"input_vcf": "/in.vcf"})
        assert isinstance(req, VepRequest)

    def test_routes_pvactools(self):
        req = parse_pipeline_request(
            "pvactools", {"input_vcf": "/in.vcf", "sample_name": "S1", "alleles": ["HLA-A*02:01"]}
        )
        assert isinstance(req, PvactoolsRequest)

    def test_unknown_adapter_raises(self):
        with pytest.raises(ValueError, match="Unknown pipeline adapter"):
            parse_pipeline_request("unknown", {})
