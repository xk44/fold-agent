"""Typed pipeline adapter request schemas.

Provides Pydantic models for validated pipeline adapter payloads,
aligned with the shell adapter stubs in ``backend.app.pipeline.shells``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class PipelineAdapterRequestBase(BaseModel):
    """Common fields for all pipeline adapter requests."""

    model_config = ConfigDict(extra="ignore")

    case_id: str | None = None
    timeout_seconds: int = 30
    threads: int | None = None
    memory_gb: int | None = None


class BwaRequest(PipelineAdapterRequestBase):
    """BWA or BWA-MEM2 alignment request."""

    adapter: Literal["bwa", "bwa_mem2"] = "bwa_mem2"
    reference: str
    fastq_1: str
    fastq_2: str | None = None
    output_bam: str | None = None
    read_group: str | None = None

    @model_validator(mode="after")
    def validate_paths(self) -> "BwaRequest":
        if not self.reference:
            raise ValueError("reference path is required")
        if not self.fastq_1:
            raise ValueError("fastq_1 path is required")
        return self


class GatkMutect2Request(PipelineAdapterRequestBase):
    """GATK Mutect2 somatic variant calling request."""

    adapter: Literal["gatk_mutect2"] = "gatk_mutect2"
    input_bam: str
    output_vcf: str | None = None
    reference: str | None = None
    tumor_sample: str | None = None
    normal_bam: str | None = None
    intervals: str | None = None
    panel_of_normals: str | None = None
    germline_resource: str | None = None

    @model_validator(mode="after")
    def validate_input(self) -> "GatkMutect2Request":
        if not self.input_bam:
            raise ValueError("input_bam is required")
        return self


class VepRequest(PipelineAdapterRequestBase):
    """Ensembl VEP annotation request."""

    adapter: Literal["vep"] = "vep"
    input_vcf: str
    output_path: str | None = None
    cache_dir: str | None = None
    assembly: str | None = None
    fork: int | None = None
    everything: bool = False
    hgvs: bool = False
    symbol: bool = True
    canonical: bool = True

    @model_validator(mode="after")
    def validate_input(self) -> "VepRequest":
        if not self.input_vcf:
            raise ValueError("input_vcf is required")
        return self


class PvactoolsRequest(PipelineAdapterRequestBase):
    """pVACtools neoantigen prioritization request."""

    adapter: Literal["pvactools"] = "pvactools"
    input_vcf: str
    sample_name: str
    alleles: list[str]
    prediction_algorithms: list[str] | None = None
    output_dir: str | None = None
    peptide_length: int | None = None
    netmhc_stab: bool = False

    @field_validator("alleles")
    @classmethod
    def alleles_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("alleles must contain at least one HLA allele")
        return v

    @model_validator(mode="after")
    def validate_input(self) -> "PvactoolsRequest":
        if not self.input_vcf:
            raise ValueError("input_vcf is required")
        if not self.sample_name:
            raise ValueError("sample_name is required")
        return self


def parse_pipeline_request(adapter_name: str, payload: dict) -> BaseModel:
    """Route a raw payload to the correct typed pipeline adapter request."""
    if adapter_name in {"bwa", "bwa_mem2"}:
        return BwaRequest.model_validate(payload)
    if adapter_name == "gatk_mutect2":
        return GatkMutect2Request.model_validate(payload)
    if adapter_name == "vep":
        return VepRequest.model_validate(payload)
    if adapter_name == "pvactools":
        return PvactoolsRequest.model_validate(payload)
    raise ValueError(f"Unknown pipeline adapter: {adapter_name}")
