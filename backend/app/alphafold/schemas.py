"""Typed AlphaFold request schemas for backend-specific builders.

Includes AF3 JSON input dialect models for constructing AlphaFold 3
compatible prediction requests.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, RootModel, field_validator, model_validator


InputKind = Literal["fasta", "a3m", "csv", "tsv", "json", "input_dir"]


# ---------------------------------------------------------------------------
# AlphaFold 3 JSON Input Dialect Models
# ---------------------------------------------------------------------------

class ProteinModification(BaseModel):
    """Post-translational modification on a protein chain."""

    ptmType: str
    ptmPosition: int


class ProteinTemplate(BaseModel):
    """Structural template for a protein chain."""

    mmcif: str | None = None
    mmcifPath: str | None = None
    queryIndices: list[int]
    templateIndices: list[int]

    @model_validator(mode="after")
    def validate_mmcif_source(self) -> "ProteinTemplate":
        if self.mmcif is not None and self.mmcifPath is not None:
            raise ValueError("mmcif and mmcifPath are mutually exclusive")
        if self.mmcif is None and self.mmcifPath is None:
            raise ValueError("at least one of mmcif or mmcifPath must be provided")
        if len(self.queryIndices) != len(self.templateIndices):
            raise ValueError("queryIndices and templateIndices must have the same length")
        return self


class ProteinEntity(BaseModel):
    """Specifies a single protein chain for AF3 input."""

    id: str | list[str]
    sequence: str
    modifications: list[ProteinModification] | None = None
    description: str | None = None
    unpairedMsa: str | None = None
    unpairedMsaPath: str | None = None
    pairedMsa: str | None = None
    pairedMsaPath: str | None = None
    templates: list[ProteinTemplate] | None = None

    @model_validator(mode="after")
    def validate_msa_sources(self) -> "ProteinEntity":
        if self.unpairedMsa is not None and self.unpairedMsaPath is not None:
            raise ValueError("unpairedMsa and unpairedMsaPath are mutually exclusive")
        if self.pairedMsa is not None and self.pairedMsaPath is not None:
            raise ValueError("pairedMsa and pairedMsaPath are mutually exclusive")
        return self


class RnaModification(BaseModel):
    """Modification on an RNA chain."""

    modificationType: str
    basePosition: int


class RnaEntity(BaseModel):
    """Specifies a single RNA chain for AF3 input."""

    id: str | list[str]
    sequence: str
    modifications: list[RnaModification] | None = None
    description: str | None = None
    unpairedMsa: str | None = None
    unpairedMsaPath: str | None = None

    @model_validator(mode="after")
    def validate_msa_sources(self) -> "RnaEntity":
        if self.unpairedMsa is not None and self.unpairedMsaPath is not None:
            raise ValueError("unpairedMsa and unpairedMsaPath are mutually exclusive")
        return self


class DnaModification(BaseModel):
    """Modification on a DNA chain."""

    modificationType: str
    basePosition: int


class DnaEntity(BaseModel):
    """Specifies a single DNA chain for AF3 input."""

    id: str | list[str]
    sequence: str
    modifications: list[DnaModification] | None = None
    description: str | None = None


class LigandEntity(BaseModel):
    """Specifies a single ligand for AF3 input.

    Each ligand must specify either ccdCodes or smiles, but not both.
    """

    id: str | list[str]
    ccdCodes: list[str] | None = None
    smiles: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_ligand_source(self) -> "LigandEntity":
        if self.ccdCodes is not None and self.smiles is not None:
            raise ValueError("ccdCodes and smiles are mutually exclusive")
        if self.ccdCodes is None and self.smiles is None:
            raise ValueError("either ccdCodes or smiles must be provided for a ligand")
        return self


class SequenceEntry(BaseModel):
    """A single sequence entry in the AF3 input JSON.

    Exactly one of protein, rna, dna, or ligand must be specified.
    """

    protein: ProteinEntity | None = None
    rna: RnaEntity | None = None
    dna: DnaEntity | None = None
    ligand: LigandEntity | None = None

    @model_validator(mode="after")
    def validate_exactly_one_entity(self) -> "SequenceEntry":
        entities = [e for e in (self.protein, self.rna, self.dna, self.ligand) if e is not None]
        if len(entities) != 1:
            raise ValueError("exactly one of protein, rna, dna, or ligand must be specified")
        return self


class BondAtomSpec(RootModel):
    """Atom specification in a covalent bond: [entity_id, residue_id, atom_name].

    Used within bondedAtomPairs. Each atom is identified by:
    - entity_id: corresponds to the 'id' field of the entity
    - residue_id: 1-based residue index within the chain (1 for single-residue ligands)
    - atom_name: unique atom name within the given residue
    """

    root: list

    @model_validator(mode="after")
    def validate_spec(self) -> "BondAtomSpec":
        if len(self.root) != 3:
            raise ValueError(
                "BondAtomSpec must have exactly 3 elements: [entity_id, residue_id, atom_name]"
            )
        entity_id, residue_id, atom_name = self.root
        if not isinstance(entity_id, str):
            raise ValueError("entity_id must be a string")
        if not isinstance(residue_id, int):
            raise ValueError("residue_id must be an integer")
        if not isinstance(atom_name, str):
            raise ValueError("atom_name must be a string")
        return self


class AF3InputJSON(BaseModel):
    """Top-level AlphaFold 3 JSON input model.

    Follows the AF3 JSON input dialect specification. See:
    docs/reference/alphafold/alphafold3/docs/input.md
    """

    model_config = ConfigDict(extra="ignore")

    name: str
    modelSeeds: list[int]
    sequences: list[SequenceEntry]
    bondedAtomPairs: list[list[BondAtomSpec]] | None = None
    userCCD: str | None = None
    userCCDPath: str | None = None
    dialect: Literal["alphafold3"] = "alphafold3"
    version: Literal[1, 2, 3, 4] = 4

    @field_validator("modelSeeds")
    @classmethod
    def model_seeds_must_not_be_empty(cls, v: list[int]) -> list[int]:
        if len(v) == 0:
            raise ValueError("modelSeeds must contain at least one seed")
        return v

    @model_validator(mode="after")
    def validate_user_ccd(self) -> "AF3InputJSON":
        if self.userCCD is not None and self.userCCDPath is not None:
            raise ValueError("userCCD and userCCDPath are mutually exclusive")
        return self

    def to_af3_json_dict(self) -> dict:
        """Serialize to a dict matching the exact AF3 JSON input format.

        Omits None values so the output matches AF3 expectations where
        optional fields are simply absent.
        """
        return _serialize_af3(self.model_dump(exclude_none=True))


def _serialize_af3(data: dict) -> dict:
    """Recursively convert the Pydantic-serialized dict to the exact AF3 JSON format.

    Key transformations:
    - SequenceEntry dicts with None entity keys are cleaned up.
    - BondAtomSpec values (RootModel lists) are already in the right format.
    """
    result: dict = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = _serialize_af3(value)
        elif isinstance(value, list):
            result[key] = [_serialize_item(item) for item in value]
        else:
            result[key] = value
    return result


def _serialize_item(item):
    """Serialize a single list item, handling dicts and nested structures."""
    if isinstance(item, dict):
        return _serialize_af3(item)
    return item


# ---------------------------------------------------------------------------
# Legacy / generic backend request models
# ---------------------------------------------------------------------------

class AlphaFoldJobRequestBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: str | None = None
    candidate_id: str | None = None
    job_name: str = "foldagent"
    timeout_seconds: int = 30
    input_kind: InputKind = "fasta"


class ColabFoldJobRequest(AlphaFoldJobRequestBase):
    sequence: str | None = None
    input_path: str | None = None
    host_url: str | None = None
    num_recycle: int | None = None
    num_seeds: int | None = None
    use_templates: bool = False
    use_dropout: bool = False
    custom_template_path: str | None = None
    random_seed: int | None = None
    max_msa: str | None = None
    overwrite_existing_results: bool = False

    @model_validator(mode="after")
    def validate_input_source(self) -> "ColabFoldJobRequest":
        if self.input_kind == "fasta" and not (self.sequence or self.input_path):
            raise ValueError("fasta input requires sequence or input_path")
        if self.input_kind in {"a3m", "csv", "tsv", "input_dir"} and not self.input_path:
            raise ValueError(f"{self.input_kind} input requires input_path")
        return self


class AlphaFold2LocalJobRequest(AlphaFoldJobRequestBase):
    sequence: str | None = None
    fasta_path: str | None = None
    data_dir: str | None = None
    max_template_date: str | None = None
    model_preset: str | None = None
    db_preset: str | None = None

    @model_validator(mode="after")
    def validate_input_source(self) -> "AlphaFold2LocalJobRequest":
        if not (self.sequence or self.fasta_path):
            raise ValueError("alphafold2_local requires sequence or fasta_path")
        return self


class AlphaFold3LocalJobRequest(AlphaFoldJobRequestBase):
    input_kind: Literal["json", "input_dir"] = "json"
    json_path: str | None = None
    input_dir: str | None = None
    model_dir: str | None = None
    db_dir: str | None = None
    output_dir: str | None = None
    af3_input: AF3InputJSON | None = None

    @model_validator(mode="after")
    def validate_input_source(self) -> "AlphaFold3LocalJobRequest":
        if self.af3_input and self.json_path:
            raise ValueError(
                "af3_input and json_path are mutually exclusive; "
                "use af3_input to have the builder generate the JSON file"
            )
        if self.input_kind == "json" and not (self.json_path or self.af3_input):
            raise ValueError("alphafold3_local with input_kind=json requires json_path or af3_input")
        if self.input_kind == "input_dir" and not self.input_dir:
            raise ValueError("alphafold3_local with input_kind=input_dir requires input_dir")
        return self


class AlphaFoldServerJobRequest(AlphaFoldJobRequestBase):
    input_kind: Literal["json"] = "json"
    json_path: str | None = None
    acknowledge_external_upload: bool = False

    @model_validator(mode="after")
    def validate_input_source(self) -> "AlphaFoldServerJobRequest":
        if not self.json_path:
            raise ValueError("alphafold_server requires json_path")
        return self


class AlphaFoldDbLookupRequest(AlphaFoldJobRequestBase):
    accession: str


def parse_alphafold_request(backend_name: str, payload: dict) -> BaseModel:
    if backend_name in {"colabfold", "local_colabfold"}:
        return ColabFoldJobRequest.model_validate(payload)
    if backend_name == "alphafold2_local":
        return AlphaFold2LocalJobRequest.model_validate(payload)
    if backend_name == "alphafold3_local":
        return AlphaFold3LocalJobRequest.model_validate(payload)
    if backend_name == "alphafold_server":
        return AlphaFoldServerJobRequest.model_validate(payload)
    if backend_name == "alphafold_db":
        return AlphaFoldDbLookupRequest.model_validate(payload)
    return AlphaFoldJobRequestBase.model_validate(payload)