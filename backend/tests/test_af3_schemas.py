"""Unit tests for AlphaFold 3 JSON input dialect schemas and command builder.

TDD: These tests cover:
- AF3InputJSON and sub-models (ProteinEntity, RnaEntity, DnaEntity, LigandEntity, etc.)
- Validation rules (mutually exclusive fields, required fields, etc.)
- Serialization to the AF3-expected JSON format
- AF3 command builder (writes JSON input file, builds CLI args)
"""

from __future__ import annotations

import json

import pytest

from backend.app.alphafold.alphafold3_local import (
    build_af3_json_input_file,
    build_alphafold3_local_command,
)
from backend.app.alphafold.schemas import (
    AF3InputJSON,
    AlphaFold3LocalJobRequest,
    BondAtomSpec,
    DnaEntity,
    DnaModification,
    LigandEntity,
    ProteinEntity,
    ProteinModification,
    ProteinTemplate,
    RnaEntity,
    RnaModification,
    SequenceEntry,
)

# ---------------------------------------------------------------------------
# ProteinModification
# ---------------------------------------------------------------------------


class TestProteinModification:
    def test_basic_creation(self):
        m = ProteinModification(ptmType="HY3", ptmPosition=1)
        assert m.ptmType == "HY3"
        assert m.ptmPosition == 1

    def test_serialization(self):
        m = ProteinModification(ptmType="P1L", ptmPosition=5)
        d = m.model_dump()
        assert d == {"ptmType": "P1L", "ptmPosition": 5}


# ---------------------------------------------------------------------------
# ProteinTemplate
# ---------------------------------------------------------------------------


class TestProteinTemplate:
    def test_template_with_inline_mmcif(self):
        t = ProteinTemplate(
            mmcif="data_test\n...",
            queryIndices=[0, 1, 2],
            templateIndices=[0, 2, 5],
        )
        assert t.mmcif == "data_test\n..."
        assert t.queryIndices == [0, 1, 2]
        assert t.templateIndices == [0, 2, 5]

    def test_template_with_mmcif_path(self):
        t = ProteinTemplate(
            mmcifPath="/path/to/template.cif",
            queryIndices=[0, 1],
            templateIndices=[3, 4],
        )
        assert t.mmcif is None
        assert t.mmcifPath == "/path/to/template.cif"

    def test_both_mmcif_sources_raises(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            ProteinTemplate(
                mmcif="data",
                mmcifPath="/path/to/template.cif",
                queryIndices=[0],
                templateIndices=[0],
            )

    def test_neither_mmcif_source_raises(self):
        with pytest.raises(ValueError, match="at least one"):
            ProteinTemplate(
                queryIndices=[0],
                templateIndices=[0],
            )

    def test_mismatched_indices_lengths_raises(self):
        with pytest.raises(ValueError, match="same length"):
            ProteinTemplate(
                mmcif="data",
                queryIndices=[0, 1],
                templateIndices=[3],
            )


# ---------------------------------------------------------------------------
# ProteinEntity
# ---------------------------------------------------------------------------


class TestProteinEntity:
    def test_minimal_protein(self):
        p = ProteinEntity(id="A", sequence="PVLSCGEWQL")
        assert p.id == "A"
        assert p.sequence == "PVLSCGEWQL"
        assert p.modifications is None

    def test_protein_with_modifications(self):
        p = ProteinEntity(
            id="A",
            sequence="PVLSCGEWQL",
            modifications=[
                ProteinModification(ptmType="HY3", ptmPosition=1),
                ProteinModification(ptmType="P1L", ptmPosition=5),
            ],
        )
        assert len(p.modifications) == 2
        assert p.modifications[0].ptmType == "HY3"

    def test_protein_with_msa_inline(self):
        p = ProteinEntity(
            id="A",
            sequence="PVLSCGEWQL",
            unpairedMsa=">query\nPVLSCGEWQL",
            pairedMsa="",
        )
        assert p.unpairedMsa == ">query\nPVLSCGEWQL"
        assert p.pairedMsa == ""

    def test_protein_with_msa_path(self):
        p = ProteinEntity(
            id="A",
            sequence="PVLSCGEWQL",
            unpairedMsaPath="/path/to/unpaired.a3m",
            pairedMsaPath="/path/to/paired.a3m",
        )
        assert p.unpairedMsaPath == "/path/to/unpaired.a3m"

    def test_protein_msa_inline_and_path_both_raises(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            ProteinEntity(
                id="A",
                sequence="PVLSCGEWQL",
                unpairedMsa=">query\nSEQ",
                unpairedMsaPath="/path/to/msa.a3m",
            )

    def test_protein_paired_msa_inline_and_path_both_raises(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            ProteinEntity(
                id="A",
                sequence="SEQ",
                pairedMsa="",
                pairedMsaPath="/path/to/paired.a3m",
            )

    def test_protein_with_homomeric_id_list(self):
        p = ProteinEntity(id=["A", "B", "C"], sequence="MYP")
        assert p.id == ["A", "B", "C"]

    def test_protein_with_templates_empty(self):
        p = ProteinEntity(
            id="B",
            sequence="RPACQLW",
            templates=[],
        )
        assert p.templates == []

    def test_protein_with_template(self):
        p = ProteinEntity(
            id="B",
            sequence="RPACQLW",
            templates=[
                ProteinTemplate(
                    mmcifPath="/path/to/template.cif",
                    queryIndices=[0, 1, 2, 4, 5, 6],
                    templateIndices=[0, 1, 2, 3, 4, 8],
                )
            ],
        )
        assert len(p.templates) == 1

    def test_protein_with_description(self):
        p = ProteinEntity(
            id="A",
            sequence="PVLSCGEWQL",
            description="10-residue protein with 2 modifications",
        )
        assert p.description == "10-residue protein with 2 modifications"


# ---------------------------------------------------------------------------
# RnaModification / RnaEntity
# ---------------------------------------------------------------------------


class TestRnaModification:
    def test_basic_creation(self):
        m = RnaModification(modificationType="2MG", basePosition=1)
        assert m.modificationType == "2MG"
        assert m.basePosition == 1


class TestRnaEntity:
    def test_minimal_rna(self):
        r = RnaEntity(id="E", sequence="AGCU")
        assert r.id == "E"
        assert r.sequence == "AGCU"

    def test_rna_with_modifications(self):
        r = RnaEntity(
            id="E",
            sequence="AGCU",
            modifications=[
                RnaModification(modificationType="2MG", basePosition=1),
                RnaModification(modificationType="5MC", basePosition=4),
            ],
        )
        assert len(r.modifications) == 2

    def test_rna_with_msa_inline(self):
        r = RnaEntity(id="E", sequence="AGCU", unpairedMsa=">query\nAGCU")
        assert r.unpairedMsa == ">query\nAGCU"

    def test_rna_with_msa_path(self):
        r = RnaEntity(id="E", sequence="AGCU", unpairedMsaPath="/path/to/rna_msa.a3m")
        assert r.unpairedMsaPath == "/path/to/rna_msa.a3m"

    def test_rna_msa_inline_and_path_both_raises(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            RnaEntity(
                id="E",
                sequence="AGCU",
                unpairedMsa=">query\nAGCU",
                unpairedMsaPath="/path/to/msa.a3m",
            )


# ---------------------------------------------------------------------------
# DnaModification / DnaEntity
# ---------------------------------------------------------------------------


class TestDnaModification:
    def test_basic_creation(self):
        m = DnaModification(modificationType="6OG", basePosition=1)
        assert m.modificationType == "6OG"
        assert m.basePosition == 1


class TestDnaEntity:
    def test_minimal_dna(self):
        d = DnaEntity(id="C", sequence="GACCTCT")
        assert d.id == "C"
        assert d.sequence == "GACCTCT"

    def test_dna_with_modifications(self):
        d = DnaEntity(
            id="C",
            sequence="GACCTCT",
            modifications=[
                DnaModification(modificationType="6OG", basePosition=1),
                DnaModification(modificationType="6MA", basePosition=2),
            ],
        )
        assert len(d.modifications) == 2

    def test_dna_with_description(self):
        d = DnaEntity(id="C", sequence="GACCTCT", description="Target DNA")
        assert d.description == "Target DNA"


# ---------------------------------------------------------------------------
# LigandEntity
# ---------------------------------------------------------------------------


class TestLigandEntity:
    def test_ligand_with_ccd_codes(self):
        lig = LigandEntity(id=["F", "G", "H"], ccdCodes=["ATP"])
        assert lig.id == ["F", "G", "H"]
        assert lig.ccdCodes == ["ATP"]

    def test_ligand_with_single_ccd_code(self):
        lig = LigandEntity(id="I", ccdCodes=["NAG", "FUC"])
        assert lig.ccdCodes == ["NAG", "FUC"]

    def test_ligand_with_smiles(self):
        lig = LigandEntity(id="Z", smiles="CC(=O)OC1C[NH+]2CCC1CC2")
        assert lig.smiles == "CC(=O)OC1C[NH+]2CCC1CC2"

    def test_ligand_with_custom_ccd_code(self):
        lig = LigandEntity(id="J", ccdCodes=["LIG-1337"])
        assert lig.ccdCodes == ["LIG-1337"]

    def test_ligand_both_ccd_and_smiles_raises(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            LigandEntity(id="Z", ccdCodes=["ATP"], smiles="CC(=O)O")

    def test_ligand_neither_ccd_nor_smiles_raises(self):
        with pytest.raises(ValueError, match="either.*ccdCodes.*smiles"):
            LigandEntity(id="Z")

    def test_ligand_with_description(self):
        lig = LigandEntity(id="Z", smiles="C", description="Methane")
        assert lig.description == "Methane"


# ---------------------------------------------------------------------------
# SequenceEntry
# ---------------------------------------------------------------------------


class TestSequenceEntry:
    def test_protein_entry(self):
        seq = SequenceEntry(protein=ProteinEntity(id="A", sequence="PVLSCGEWQL"))
        assert seq.protein is not None
        assert seq.rna is None
        assert seq.dna is None
        assert seq.ligand is None

    def test_rna_entry(self):
        seq = SequenceEntry(rna=RnaEntity(id="E", sequence="AGCU"))
        assert seq.rna is not None
        assert seq.protein is None

    def test_dna_entry(self):
        seq = SequenceEntry(dna=DnaEntity(id="C", sequence="GACCTCT"))
        assert seq.dna is not None

    def test_ligand_entry(self):
        seq = SequenceEntry(ligand=LigandEntity(id="Z", ccdCodes=["ATP"]))
        assert seq.ligand is not None

    def test_no_entity_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            SequenceEntry()

    def test_multiple_entities_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            SequenceEntry(
                protein=ProteinEntity(id="A", sequence="SEQ"),
                rna=RnaEntity(id="B", sequence="AGCU"),
            )


# ---------------------------------------------------------------------------
# BondAtomSpec
# ---------------------------------------------------------------------------


class TestBondAtomSpec:
    def test_valid_spec(self):
        spec = BondAtomSpec(root=["A", 145, "SG"])
        assert spec.root == ["A", 145, "SG"]

    def test_invalid_length_raises(self):
        with pytest.raises(ValueError):
            BondAtomSpec(root=["A", 145])

    def test_invalid_entity_id_type_raises(self):
        with pytest.raises(ValueError):
            BondAtomSpec(root=[123, 145, "SG"])

    def test_invalid_residue_id_type_raises(self):
        with pytest.raises(ValueError):
            BondAtomSpec(root=["A", "145", "SG"])

    def test_invalid_atom_name_type_raises(self):
        with pytest.raises(ValueError):
            BondAtomSpec(root=["A", 145, 123])

    def test_serialization_to_list(self):
        spec = BondAtomSpec(root=["A", 1, "CA"])
        data = spec.model_dump()
        assert data == ["A", 1, "CA"]


# ---------------------------------------------------------------------------
# AF3InputJSON (top-level)
# ---------------------------------------------------------------------------


class TestAF3InputJSON:
    def test_minimal_input(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="PVLSCGEWQL"))],
        )
        assert af3.name == "test"
        assert af3.modelSeeds == [1]
        assert len(af3.sequences) == 1
        assert af3.dialect == "alphafold3"
        assert af3.version == 4
        assert af3.bondedAtomPairs is None
        assert af3.userCCD is None
        assert af3.userCCDPath is None

    def test_full_input(self):
        af3 = AF3InputJSON(
            name="Hello fold",
            modelSeeds=[10, 42],
            sequences=[
                SequenceEntry(
                    protein=ProteinEntity(
                        id="A",
                        sequence="PVLSCGEWQL",
                        modifications=[
                            ProteinModification(ptmType="HY3", ptmPosition=1),
                            ProteinModification(ptmType="P1L", ptmPosition=5),
                        ],
                        description="10-residue protein with 2 modifications",
                        unpairedMsa=">query\nPVLSCGEWQL",
                        pairedMsa="",
                    )
                ),
                SequenceEntry(
                    dna=DnaEntity(
                        id="C",
                        sequence="GACCTCT",
                        modifications=[
                            DnaModification(modificationType="6OG", basePosition=1),
                            DnaModification(modificationType="6MA", basePosition=2),
                        ],
                    )
                ),
                SequenceEntry(
                    rna=RnaEntity(
                        id="E",
                        sequence="AGCU",
                        modifications=[
                            RnaModification(modificationType="2MG", basePosition=1),
                        ],
                        unpairedMsa=">query\nAGCU",
                    )
                ),
                SequenceEntry(ligand=LigandEntity(id=["F", "G", "H"], ccdCodes=["ATP"])),
                SequenceEntry(ligand=LigandEntity(id="Z", smiles="CC(=O)OC1C[NH+]2CCC1CC2")),
            ],
            bondedAtomPairs=[
                [BondAtomSpec(root=["A", 145, "SG"]), BondAtomSpec(root=["L", 1, "C04"])],
                [BondAtomSpec(root=["J", 1, "O6"]), BondAtomSpec(root=["J", 2, "C1"])],
            ],
            dialect="alphafold3",
            version=4,
        )
        assert af3.name == "Hello fold"
        assert af3.modelSeeds == [10, 42]
        assert len(af3.sequences) == 5

    def test_user_ccd_and_path_both_raises(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            AF3InputJSON(
                name="test",
                modelSeeds=[1],
                sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
                userCCD="data_MY-X7F\n...",
                userCCDPath="/path/to/custom.cif",
            )

    def test_dialect_must_be_alphafold3(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
        )
        assert af3.dialect == "alphafold3"

    def test_version_must_be_valid(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
            version=1,
        )
        assert af3.version == 1

    def test_version_2_is_valid(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
            version=2,
        )
        assert af3.version == 2

    def test_version_3_is_valid(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
            version=3,
        )
        assert af3.version == 3

    def test_version_4_is_valid(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
            version=4,
        )
        assert af3.version == 4

    def test_invalid_version_raises(self):
        with pytest.raises(Exception):
            AF3InputJSON(
                name="test",
                modelSeeds=[1],
                sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
                version=5,
            )

    def test_model_seeds_required(self):
        with pytest.raises(ValueError, match="at least one seed"):
            AF3InputJSON(
                name="test",
                modelSeeds=[],
                sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
            )


# ---------------------------------------------------------------------------
# Serialization to AF3 JSON format
# ---------------------------------------------------------------------------


class TestAF3JSONSerialization:
    def test_minimal_protein_serialization(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="PVLSCGEWQL"))],
        )
        d = af3.to_af3_json_dict()
        assert d["name"] == "test"
        assert d["modelSeeds"] == [1]
        assert d["dialect"] == "alphafold3"
        assert d["version"] == 4
        assert len(d["sequences"]) == 1
        assert "protein" in d["sequences"][0]
        assert d["sequences"][0]["protein"]["id"] == "A"
        assert d["sequences"][0]["protein"]["sequence"] == "PVLSCGEWQL"

    def test_none_fields_omitted_in_serialization(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
        )
        d = af3.to_af3_json_dict()
        protein_dict = d["sequences"][0]["protein"]
        # Optional fields should not appear if not set
        assert "modifications" not in protein_dict
        assert "description" not in protein_dict
        assert "unpairedMsa" not in protein_dict
        assert "pairedMsa" not in protein_dict
        assert "templates" not in protein_dict

    def test_ligand_ccd_serialization(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[SequenceEntry(ligand=LigandEntity(id=["F", "G", "H"], ccdCodes=["ATP"]))],
        )
        d = af3.to_af3_json_dict()
        lig_dict = d["sequences"][0]["ligand"]
        assert lig_dict["id"] == ["F", "G", "H"]
        assert lig_dict["ccdCodes"] == ["ATP"]
        assert "smiles" not in lig_dict

    def test_ligand_smiles_serialization(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[
                SequenceEntry(ligand=LigandEntity(id="Z", smiles="CC(=O)OC1C[NH+]2CCC1CC2"))
            ],
        )
        d = af3.to_af3_json_dict()
        lig_dict = d["sequences"][0]["ligand"]
        assert lig_dict["smiles"] == "CC(=O)OC1C[NH+]2CCC1CC2"
        assert "ccdCodes" not in lig_dict

    def test_bonded_atom_pairs_serialization(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
            bondedAtomPairs=[
                [BondAtomSpec(root=["A", 145, "SG"]), BondAtomSpec(root=["L", 1, "C04"])],
            ],
        )
        d = af3.to_af3_json_dict()
        assert d["bondedAtomPairs"] == [[["A", 145, "SG"], ["L", 1, "C04"]]]

    def test_user_ccd_serialization(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
            userCCD="data_MY-X7F\n...",
        )
        d = af3.to_af3_json_dict()
        assert d["userCCD"] == "data_MY-X7F\n..."
        assert "userCCDPath" not in d

    def test_user_ccd_path_serialization(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
            userCCDPath="/path/to/custom.cif",
        )
        d = af3.to_af3_json_dict()
        assert d["userCCDPath"] == "/path/to/custom.cif"
        assert "userCCD" not in d

    def test_rna_with_msa_serialization(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[
                SequenceEntry(
                    rna=RnaEntity(
                        id="E",
                        sequence="AGCU",
                        unpairedMsa=">query\nAGCU",
                    )
                )
            ],
        )
        d = af3.to_af3_json_dict()
        rna_dict = d["sequences"][0]["rna"]
        assert rna_dict["unpairedMsa"] == ">query\nAGCU"

    def test_protein_with_template_serialization(self):
        af3 = AF3InputJSON(
            name="test",
            modelSeeds=[1],
            sequences=[
                SequenceEntry(
                    protein=ProteinEntity(
                        id="B",
                        sequence="RPACQLW",
                        templates=[
                            ProteinTemplate(
                                mmcifPath="/path/to/template.cif",
                                queryIndices=[0, 1, 2, 4, 5, 6],
                                templateIndices=[0, 1, 2, 3, 4, 8],
                            )
                        ],
                    )
                )
            ],
        )
        d = af3.to_af3_json_dict()
        prot_dict = d["sequences"][0]["protein"]
        assert len(prot_dict["templates"]) == 1
        template = prot_dict["templates"][0]
        assert template["mmcifPath"] == "/path/to/template.cif"
        assert template["queryIndices"] == [0, 1, 2, 4, 5, 6]

    def test_full_json_roundtrip(self):
        """Ensure the serialized dict is valid JSON."""
        af3 = AF3InputJSON(
            name="Hello fold",
            modelSeeds=[10, 42],
            sequences=[
                SequenceEntry(
                    protein=ProteinEntity(
                        id="A",
                        sequence="PVLSCGEWQL",
                        modifications=[ProteinModification(ptmType="HY3", ptmPosition=1)],
                        description="Test protein",
                    )
                ),
                SequenceEntry(ligand=LigandEntity(id="Z", smiles="CC(=O)OC1C[NH+]2CCC1CC2")),
            ],
        )
        d = af3.to_af3_json_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["name"] == "Hello fold"
        assert parsed["modelSeeds"] == [10, 42]
        assert len(parsed["sequences"]) == 2


# ---------------------------------------------------------------------------
# AF3InputJSON.model_validate from dict
# ---------------------------------------------------------------------------


class TestAF3InputJSONFromDict:
    def test_from_dict_minimal(self):
        data = {
            "name": "test",
            "modelSeeds": [1],
            "sequences": [{"protein": {"id": "A", "sequence": "SEQ"}}],
        }
        af3 = AF3InputJSON.model_validate(data)
        assert af3.name == "test"
        assert af3.sequences[0].protein.id == "A"

    def test_from_dict_full_example(self):
        data = {
            "name": "Hello fold",
            "modelSeeds": [10, 42],
            "sequences": [
                {
                    "protein": {
                        "id": "A",
                        "sequence": "PVLSCGEWQL",
                        "modifications": [{"ptmType": "HY3", "ptmPosition": 1}],
                    }
                },
                {"dna": {"id": "C", "sequence": "GACCTCT"}},
                {"rna": {"id": "E", "sequence": "AGCU"}},
                {"ligand": {"id": ["F", "G"], "ccdCodes": ["ATP"]}},
                {"ligand": {"id": "Z", "smiles": "CC(=O)O"}},
            ],
            "bondedAtomPairs": [[["A", 145, "SG"], ["L", 1, "C04"]]],
            "dialect": "alphafold3",
            "version": 4,
        }
        af3 = AF3InputJSON.model_validate(data)
        assert af3.name == "Hello fold"
        assert len(af3.sequences) == 5
        assert af3.bondedAtomPairs is not None
        assert len(af3.bondedAtomPairs) == 1


# ---------------------------------------------------------------------------
# Command builder: build_af3_json_input_file
# ---------------------------------------------------------------------------


class TestBuildAF3JsonInputFile:
    def test_writes_json_file(self, tmp_path):
        af3 = AF3InputJSON(
            name="test_cmd",
            modelSeeds=[42],
            sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="PVLSCGEWQL"))],
        )
        output_path = tmp_path / "input.json"
        result_path = build_af3_json_input_file(af3, output_path)
        assert result_path == str(output_path)
        assert output_path.exists()
        with open(output_path) as f:
            data = json.load(f)
        assert data["name"] == "test_cmd"
        assert data["modelSeeds"] == [42]
        assert data["dialect"] == "alphafold3"

    def test_json_matches_af3_format(self, tmp_path):
        af3 = AF3InputJSON(
            name="format_test",
            modelSeeds=[1, 2],
            sequences=[
                SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ")),
                SequenceEntry(ligand=LigandEntity(id="L", smiles="C")),
            ],
            bondedAtomPairs=[
                [BondAtomSpec(root=["A", 1, "CA"]), BondAtomSpec(root=["L", 1, "C01"])],
            ],
        )
        output_path = tmp_path / "input.json"
        build_af3_json_input_file(af3, output_path)
        with open(output_path) as f:
            data = json.load(f)
        # Verify exact AF3-format structure
        assert set(data.keys()) >= {"name", "modelSeeds", "sequences", "dialect", "version"}
        assert "protein" in data["sequences"][0]
        assert "ligand" in data["sequences"][1]
        assert data["bondedAtomPairs"] == [[["A", 1, "CA"], ["L", 1, "C01"]]]


# ---------------------------------------------------------------------------
# Command builder: build_alphafold3_local_command
# ---------------------------------------------------------------------------


class TestBuildAlphafold3LocalCommand:
    def test_json_path_command(self):
        req = AlphaFold3LocalJobRequest(
            input_kind="json",
            json_path="/path/to/input.json",
        )
        cmd = build_alphafold3_local_command(req)
        assert cmd[0] == "alphafold"
        assert "--json_path" in cmd
        assert "/path/to/input.json" in cmd

    def test_input_dir_command(self):
        req = AlphaFold3LocalJobRequest(
            input_kind="input_dir",
            input_dir="/path/to/inputs/",
        )
        cmd = build_alphafold3_local_command(req)
        assert cmd[0] == "alphafold"
        assert "--input_dir" in cmd
        assert "/path/to/inputs/" in cmd

    def test_command_with_model_dir(self):
        req = AlphaFold3LocalJobRequest(
            input_kind="json",
            json_path="/path/to/input.json",
            model_dir="/models/af3",
        )
        cmd = build_alphafold3_local_command(req)
        assert "--model_dir" in cmd
        assert "/models/af3" in cmd

    def test_command_with_db_dir(self):
        req = AlphaFold3LocalJobRequest(
            input_kind="json",
            json_path="/path/to/input.json",
            db_dir="/data/dbs",
        )
        cmd = build_alphafold3_local_command(req)
        assert "--db_dir" in cmd
        assert "/data/dbs" in cmd

    def test_command_with_af3_input_and_output_dir(self, tmp_path):
        """Command builder should write JSON and include --json_path when af3_input is provided."""
        af3 = AF3InputJSON(
            name="cmd_test",
            modelSeeds=[99],
            sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        json_path = tmp_path / "af3_input.json"
        req = AlphaFold3LocalJobRequest(
            input_kind="json",
            af3_input=af3,
            output_dir=str(output_dir),
        )
        cmd = build_alphafold3_local_command(req, json_output_path=str(json_path))
        assert "--json_path" in cmd
        # Check JSON file was written
        assert json_path.exists()
        with open(json_path) as f:
            data = json.load(f)
        assert data["name"] == "cmd_test"

    def test_af3_input_and_json_path_mutually_exclusive(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            AlphaFold3LocalJobRequest(
                input_kind="json",
                json_path="/path/to/existing.json",
                af3_input=AF3InputJSON(
                    name="test",
                    modelSeeds=[1],
                    sequences=[SequenceEntry(protein=ProteinEntity(id="A", sequence="SEQ"))],
                ),
            )


# ---------------------------------------------------------------------------
# Integration-style: full example from docs
# ---------------------------------------------------------------------------


class TestFullExampleFromDocs:
    def test_full_example_roundtrip(self):
        """Test construction and serialization of the full example from AF3 docs."""
        af3 = AF3InputJSON(
            name="Hello fold",
            modelSeeds=[10, 42],
            sequences=[
                SequenceEntry(
                    protein=ProteinEntity(
                        id="A",
                        sequence="PVLSCGEWQL",
                        modifications=[
                            ProteinModification(ptmType="HY3", ptmPosition=1),
                            ProteinModification(ptmType="P1L", ptmPosition=5),
                        ],
                        description="10-residue protein with 2 modifications",
                        unpairedMsa=">query\nPVLSCGEWQL",
                        pairedMsa="",
                    )
                ),
                SequenceEntry(
                    protein=ProteinEntity(
                        id="B",
                        sequence="RPACQLW",
                        templates=[
                            ProteinTemplate(
                                mmcifPath="/path/to/template.cif",
                                queryIndices=[0, 1, 2, 4, 5, 6],
                                templateIndices=[0, 1, 2, 3, 4, 8],
                            )
                        ],
                    )
                ),
                SequenceEntry(
                    dna=DnaEntity(
                        id="C",
                        sequence="GACCTCT",
                        modifications=[
                            DnaModification(modificationType="6OG", basePosition=1),
                            DnaModification(modificationType="6MA", basePosition=2),
                        ],
                    )
                ),
                SequenceEntry(
                    rna=RnaEntity(
                        id="E",
                        sequence="AGCU",
                        modifications=[
                            RnaModification(modificationType="2MG", basePosition=1),
                            RnaModification(modificationType="5MC", basePosition=4),
                        ],
                        unpairedMsa=">query\nAGCU",
                    )
                ),
                SequenceEntry(ligand=LigandEntity(id=["F", "G", "H"], ccdCodes=["ATP"])),
                SequenceEntry(ligand=LigandEntity(id="I", ccdCodes=["NAG", "FUC"])),
                SequenceEntry(ligand=LigandEntity(id="Z", smiles="CC(=O)OC1C[NH+]2CCC1CC2")),
            ],
            bondedAtomPairs=[
                [BondAtomSpec(root=["A", 1, "CA"]), BondAtomSpec(root=["G", 1, "CHA"])],
                [BondAtomSpec(root=["I", 1, "O6"]), BondAtomSpec(root=["I", 2, "C1"])],
            ],
            dialect="alphafold3",
            version=4,
        )
        d = af3.to_af3_json_dict()
        json_str = json.dumps(d, indent=2)
        parsed = json.loads(json_str)

        # Verify top-level structure
        assert parsed["name"] == "Hello fold"
        assert parsed["modelSeeds"] == [10, 42]
        assert parsed["dialect"] == "alphafold3"
        assert parsed["version"] == 4
        assert len(parsed["sequences"]) == 7

        # Verify protein with modifications
        prot_a = parsed["sequences"][0]["protein"]
        assert prot_a["id"] == "A"
        assert prot_a["sequence"] == "PVLSCGEWQL"
        assert prot_a["modifications"] == [
            {"ptmType": "HY3", "ptmPosition": 1},
            {"ptmType": "P1L", "ptmPosition": 5},
        ]
        assert prot_a["description"] == "10-residue protein with 2 modifications"

        # Verify protein with template
        prot_b = parsed["sequences"][1]["protein"]
        assert prot_b["id"] == "B"
        assert len(prot_b["templates"]) == 1

        # Verify DNA
        dna_c = parsed["sequences"][2]["dna"]
        assert dna_c["id"] == "C"
        assert dna_c["sequence"] == "GACCTCT"

        # Verify RNA
        rna_e = parsed["sequences"][3]["rna"]
        assert rna_e["id"] == "E"

        # Verify ligands
        lig_fgh = parsed["sequences"][4]["ligand"]
        assert lig_fgh["id"] == ["F", "G", "H"]
        assert lig_fgh["ccdCodes"] == ["ATP"]

        # Verify bonds
        assert len(parsed["bondedAtomPairs"]) == 2
        assert parsed["bondedAtomPairs"][0] == [["A", 1, "CA"], ["G", 1, "CHA"]]
