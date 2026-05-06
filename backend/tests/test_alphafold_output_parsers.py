"""Unit tests for backend.app.alphafold.output_parsers.

These tests target the pure parsing helpers extracted from main.py, covering:
- parse_alphafold_stdout: JSON blob extraction from backend stdout
- extract_inline_structure: inline "structure" key extraction
- harvest_af3_output_dir: AF3 directory harvesting for model.cif / summary confidences
- extract_alphafold_structure_payload: top-level orchestrator
- filter_structure_evidence: canonical key filtering
- STRUCTURE_EVIDENCE_KEYS: constant shape verification
"""

from __future__ import annotations

import json
import textwrap

from backend.app.alphafold.output_parsers import (
    STRUCTURE_EVIDENCE_KEYS,
    Af3HarvestedOutput,
    ParsedStructurePayload,
    _harvest_af3_confidences_json,
    _harvest_af3_data_json,
    _harvest_af3_embeddings_and_distograms,
    _harvest_af3_seed_sample_dirs,
    extract_alphafold_structure_payload,
    extract_inline_structure,
    filter_structure_evidence,
    harvest_af3_output_dir,
    parse_alphafold_stdout,
)

# ---------------------------------------------------------------------------
# STRUCTURE_EVIDENCE_KEYS
# ---------------------------------------------------------------------------


class TestStructureEvidenceKeys:
    def test_keys_is_a_tuple_of_strings(self):
        assert isinstance(STRUCTURE_EVIDENCE_KEYS, tuple)
        for key in STRUCTURE_EVIDENCE_KEYS:
            assert isinstance(key, str)

    def test_expected_canonical_keys_present(self):
        expected = {
            "pdb_file",
            "model_cif",
            "summary_confidences_json",
            "confidences_json",
            "data_json",
            "source_url",
            "output_format",
            "accession",
            "pLDDT_mean",
            "pAE_mean",
            "ranking_score",
            "ptm",
            "iptm",
            "chain_pair_iptm",
            "pae",
            "atom_plddts",
            "chain_ptm",
            "chain_iptm",
        }
        assert set(STRUCTURE_EVIDENCE_KEYS) == expected

    def test_no_duplicates(self):
        assert len(STRUCTURE_EVIDENCE_KEYS) == len(set(STRUCTURE_EVIDENCE_KEYS))


# ---------------------------------------------------------------------------
# parse_alphafold_stdout
# ---------------------------------------------------------------------------


class TestParseAlphafoldStdout:
    def test_valid_json(self):
        data = {"structure": {"pdb_file": "/tmp/x.pdb", "pLDDT_mean": 92.1}}
        result = parse_alphafold_stdout(json.dumps(data))
        assert result == data

    def test_empty_string_returns_empty_dict(self):
        result = parse_alphafold_stdout("")
        assert result == {}

    def test_none_returns_empty_dict(self):
        """When stdout is missing, main.py passes result.get('stdout') or '' to the fn."""
        result = parse_alphafold_stdout("")
        assert result == {}

    def test_invalid_json_returns_none(self):
        result = parse_alphafold_stdout("not json at all")
        assert result is None

    def test_whitespace_only_json_returns_empty_or_none(self):
        """Parsed as valid JSON if it's just whitespace-around empty."""
        # json.loads of "  " raises JSONDecodeError, but our fn returns None for invalid JSON
        result = parse_alphafold_stdout("  ")
        assert result is None

    def test_empty_object(self):
        result = parse_alphafold_stdout("{}")
        assert result == {}

    def test_nested_structure(self):
        data = {"structure": {"pLDDT_mean": 88.5}, "output_dir": "/tmp/out"}
        result = parse_alphafold_stdout(json.dumps(data))
        assert result["structure"]["pLDDT_mean"] == 88.5


# ---------------------------------------------------------------------------
# extract_inline_structure
# ---------------------------------------------------------------------------


class TestExtractInlineStructure:
    def test_returns_structure_when_present(self):
        parsed = {"structure": {"backend": "colabfold", "status": "completed", "pLDDT_mean": 91.2}}
        result = extract_inline_structure(parsed)
        assert result == {"backend": "colabfold", "status": "completed", "pLDDT_mean": 91.2}

    def test_returns_none_when_no_structure_key(self):
        parsed = {"output_dir": "/tmp/out"}
        assert extract_inline_structure(parsed) is None

    def test_returns_none_when_structure_is_empty(self):
        """An empty dict for 'structure' is falsy — should return None."""
        parsed = {"structure": {}}
        result = extract_inline_structure(parsed)
        assert result is None

    def test_returns_none_when_structure_is_not_dict(self):
        parsed = {"structure": "not a dict"}
        # The value is present but not a dict, so return None
        result = extract_inline_structure(parsed)
        assert result is None

    def test_returns_full_inline_payload(self):
        payload = {
            "backend": "colabfold",
            "status": "completed",
            "pdb_file": "/tmp/demo_out/predicted_structure.pdb",
            "pLDDT_mean": 91.2,
            "pAE_mean": 4.8,
        }
        parsed = {"structure": payload}
        result = extract_inline_structure(parsed)
        assert result == payload


# ---------------------------------------------------------------------------
# harvest_af3_output_dir
# ---------------------------------------------------------------------------


class TestHarvestAf3OutputDir:
    def test_nonexistent_dir_returns_none(self, tmp_path):
        missing = tmp_path / "no_such_dir"
        assert harvest_af3_output_dir(missing) is None

    def test_empty_dir_returns_none(self, tmp_path):
        """An empty output dir has no model.cif or summary JSON — should return None."""
        out = tmp_path / "empty_run"
        out.mkdir()
        result = harvest_af3_output_dir(out)
        # Only 4 base keys (backend, status, output_dir, output_format), so len <= 4 → None
        assert result is None

    def test_dir_with_model_cif(self, tmp_path):
        out = tmp_path / "af3_run"
        out.mkdir()
        cif_file = out / "fold1_model.cif"
        cif_file.write_text("# mmCIF content placeholder\n", encoding="utf-8")

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        assert result["backend"] == "alphafold3_local"
        assert result["status"] == "completed"
        assert result["output_dir"] == str(out)
        assert result["output_format"] == "mmcif"
        assert result["model_cif"] == str(cif_file)

    def test_dir_with_summary_confidences(self, tmp_path):
        out = tmp_path / "af3_run2"
        out.mkdir()
        summary = out / "fold1_summary_confidences.json"
        summary.write_text(
            json.dumps(
                {"ptm": 0.85, "iptm": 0.72, "ranking_score": 0.91, "chain_pair_iptm": {"A": 0.7}}
            ),
            encoding="utf-8",
        )

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        assert result["summary_confidences_json"] == str(summary)
        assert result["ptm"] == 0.85
        assert result["iptm"] == 0.72
        assert result["ranking_score"] == 0.91
        assert result["chain_pair_iptm"] == {"A": 0.7}

    def test_dir_with_model_cif_and_summary(self, tmp_path):
        out = tmp_path / "af3_run3"
        out.mkdir()
        cif_file = out / "fold1_model.cif"
        cif_file.write_text("# mmCIF", encoding="utf-8")
        summary = out / "fold1_summary_confidences.json"
        summary.write_text(json.dumps({"ptm": 0.88, "ranking_score": 0.95}), encoding="utf-8")

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        assert "model_cif" in result
        assert "summary_confidences_json" in result
        assert result["ptm"] == 0.88
        assert result["ranking_score"] == 0.95

    def test_invalid_summary_json_is_ignored(self, tmp_path):
        out = tmp_path / "af3_run_bad_summary"
        out.mkdir()
        cif_file = out / "fold1_model.cif"
        cif_file.write_text("# mmCIF", encoding="utf-8")
        summary = out / "fold1_summary_confidences.json"
        summary.write_text("NOT VALID JSON {{{", encoding="utf-8")

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        assert "model_cif" in result
        # Summary path recorded but metric keys absent (invalid JSON)
        assert "summary_confidences_json" in result
        assert "ptm" not in result

    def test_ranking_scores_csv_is_used_when_summary_confidences_missing(self, tmp_path):
        out = tmp_path / "af3_run_ranking_csv"
        out.mkdir()
        (out / "fold1_model.cif").write_text("# mmCIF", encoding="utf-8")
        ranking_csv = out / "fold1_ranking_scores.csv"
        ranking_csv.write_text(
            textwrap.dedent(
                """\
                seed,sample,ranking_score,ptm,iptm
                1,0,0.97,0.88,0.76
                """
            ),
            encoding="utf-8",
        )

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        assert result["ranking_score"] == 0.97
        assert result["ptm"] == 0.88
        assert result["iptm"] == 0.76

    def test_summary_confidences_preferred_over_ranking_scores_csv(self, tmp_path):
        out = tmp_path / "af3_run_both_confidence_sources"
        out.mkdir()
        (out / "fold1_model.cif").write_text("# mmCIF", encoding="utf-8")
        summary = out / "fold1_summary_confidences.json"
        summary.write_text(
            json.dumps({"ptm": 0.91, "iptm": 0.81, "ranking_score": 0.99}), encoding="utf-8"
        )
        ranking_csv = out / "fold1_ranking_scores.csv"
        ranking_csv.write_text(
            textwrap.dedent(
                """\
                seed,sample,ranking_score,ptm,iptm
                1,0,0.70,0.60,0.50
                """
            ),
            encoding="utf-8",
        )

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        assert result["ranking_score"] == 0.99
        assert result["ptm"] == 0.91
        assert result["iptm"] == 0.81

    def test_file_not_a_dir_returns_none(self, tmp_path):
        a_file = tmp_path / "some_file.txt"
        a_file.write_text("hello", encoding="utf-8")
        assert harvest_af3_output_dir(a_file) is None

    def test_sorts_multiple_cif_files(self, tmp_path):
        out = tmp_path / "af3_multi"
        out.mkdir()
        (out / "fold2_model.cif").write_text("# CIF 2", encoding="utf-8")
        (out / "fold1_model.cif").write_text("# CIF 1", encoding="utf-8")

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        # Should pick the first sorted name
        assert result["model_cif"] == str(out / "fold1_model.cif")


# ---------------------------------------------------------------------------
# extract_alphafold_structure_payload (top-level orchestrator)
# ---------------------------------------------------------------------------


class TestExtractAlphafoldStructurePayload:
    def test_inline_structure_from_stdout(self):
        payload = {
            "backend": "colabfold",
            "status": "completed",
            "stdout": json.dumps(
                {
                    "structure": {
                        "backend": "colabfold",
                        "status": "completed",
                        "pdb_file": "/tmp/demo_out/predicted_structure.pdb",
                        "pLDDT_mean": 91.2,
                        "pAE_mean": 4.8,
                    }
                }
            ),
        }
        result = extract_alphafold_structure_payload(payload)
        assert result is not None
        assert result["backend"] == "colabfold"
        assert result["pdb_file"] == "/tmp/demo_out/predicted_structure.pdb"
        assert result["pLDDT_mean"] == 91.2
        assert result["pAE_mean"] == 4.8

    def test_invalid_json_returns_none(self):
        payload = {"backend": "colabfold", "status": "completed", "stdout": "not valid json"}
        assert extract_alphafold_structure_payload(payload) is None

    def test_no_structure_no_output_dir_returns_none(self):
        payload = {"backend": "colabfold", "status": "completed", "stdout": json.dumps({})}
        assert extract_alphafold_structure_payload(payload) is None

    def test_no_stdout_returns_none(self):
        payload = {"backend": "colabfold", "status": "completed"}
        # result.get("stdout") would be None, which our parse handles as ""
        result = extract_alphafold_structure_payload(payload)
        assert result is None

    def test_af3_output_dir_harvesting(self, tmp_path):
        out = tmp_path / "af3_out"
        out.mkdir()
        cif_file = out / "fold1_model.cif"
        cif_file.write_text("# mmCIF", encoding="utf-8")
        summary = out / "fold1_summary_confidences.json"
        summary.write_text(json.dumps({"ptm": 0.9, "ranking_score": 0.92}), encoding="utf-8")

        payload = {
            "backend": "alphafold3_local",
            "status": "completed",
            "stdout": json.dumps({"output_dir": str(out)}),
        }
        result = extract_alphafold_structure_payload(payload)
        assert result is not None
        assert result["output_format"] == "mmcif"
        assert result["model_cif"] == str(cif_file)
        assert result["ptm"] == 0.9
        assert result["ranking_score"] == 0.92

    def test_missing_output_dir_returns_none(self, tmp_path):
        payload = {
            "backend": "alphafold3_local",
            "status": "completed",
            "stdout": json.dumps({"output_dir": str(tmp_path / "nonexistent")}),
        }
        assert extract_alphafold_structure_payload(payload) is None

    def test_empty_structure_key_returns_none(self):
        """If stdout JSON has 'structure': {}, we should get None (empty dict falsy check)."""
        payload = {
            "backend": "colabfold",
            "status": "completed",
            "stdout": json.dumps({"structure": {}}),
        }
        assert extract_alphafold_structure_payload(payload) is None


# ---------------------------------------------------------------------------
# filter_structure_evidence
# ---------------------------------------------------------------------------


class TestFilterStructureEvidence:
    def test_filters_to_canonical_keys(self):
        source = {
            "backend": "colabfold",
            "status": "completed",
            "pdb_file": "/tmp/x.pdb",
            "pLDDT_mean": 91.2,
            "pAE_mean": 4.8,
            "ranking_score": 0.88,
            "extra_key": "should be dropped",
        }
        result = filter_structure_evidence(source)
        assert "extra_key" not in result
        assert "backend" not in result
        assert "status" not in result
        assert result["pdb_file"] == "/tmp/x.pdb"
        assert result["pLDDT_mean"] == 91.2
        assert result["pAE_mean"] == 4.8
        assert result["ranking_score"] == 0.88

    def test_empty_dict_returns_empty(self):
        assert filter_structure_evidence({}) == {}

    def test_only_non_canonical_keys_returns_empty(self):
        result = filter_structure_evidence({"foo": "bar", "baz": 42})
        assert result == {}

    def test_all_canonical_keys_pass_through(self):
        source = {key: f"value_{key}" for key in STRUCTURE_EVIDENCE_KEYS}
        result = filter_structure_evidence(source)
        assert result == source

    def test_none_values_included(self):
        source = {"pdb_file": None, "pLDDT_mean": 0.0}
        result = filter_structure_evidence(source)
        assert result["pdb_file"] is None
        assert result["pLDDT_mean"] == 0.0


# ---------------------------------------------------------------------------
# ParsedStructurePayload TypedDict verification
# ---------------------------------------------------------------------------


class TestParsedStructurePayload:
    def test_typed_dict_fields_include_all_evidence_keys(self):
        """TypedDict should have fields for all canonical structure evidence keys plus extras."""
        annotations = ParsedStructurePayload.__annotations__
        for key in STRUCTURE_EVIDENCE_KEYS:
            assert key in annotations, f"Missing key: {key}"

    def test_extra_fields_present(self):
        """The TypedDict should also include backend, status, output_dir, output_format."""
        annotations = ParsedStructurePayload.__annotations__
        for extra_key in ("backend", "status", "output_dir", "output_format"):
            assert extra_key in annotations, f"Missing extra key: {extra_key}"

    def test_new_af3_fields_present(self):
        """TypedDict should include new AF3 fields: confidences_json, data_json,
        embeddings_path, distogram_path, seed_sample_dirs, pae, atom_plddts,
        chain_ptm, chain_iptm."""
        annotations = ParsedStructurePayload.__annotations__
        for key in (
            "confidences_json",
            "data_json",
            "embeddings_path",
            "distogram_path",
            "seed_sample_dirs",
            "pae",
            "atom_plddts",
            "chain_ptm",
            "chain_iptm",
        ):
            assert key in annotations, f"Missing AF3 field: {key}"


# ---------------------------------------------------------------------------
# Af3HarvestedOutput TypedDict verification
# ---------------------------------------------------------------------------


class TestAf3HarvestedOutput:
    def test_typed_dict_has_primary_file_fields(self):
        annotations = Af3HarvestedOutput.__annotations__
        for key in (
            "backend",
            "status",
            "output_dir",
            "output_format",
            "model_cif",
            "summary_confidences_json",
            "confidences_json",
            "data_json",
        ):
            assert key in annotations, f"Missing key in Af3HarvestedOutput: {key}"

    def test_typed_dict_has_optional_artifact_fields(self):
        annotations = Af3HarvestedOutput.__annotations__
        for key in ("embeddings_path", "distogram_path", "seed_sample_dirs"):
            assert key in annotations, f"Missing optional artifact key: {key}"

    def test_all_fields_are_total_false(self):
        """Af3HarvestedOutput should be total=False so all fields are optional."""
        assert Af3HarvestedOutput.__total__ is False


# ---------------------------------------------------------------------------
# _harvest_af3_confidences_json
# ---------------------------------------------------------------------------


class TestHarvestAf3ConfidencesJson:
    def test_extracts_pae_and_atom_plddts(self, tmp_path):
        conf_file = tmp_path / "fold1_confidences.json"
        conf_data = {
            "pae": [[0.1, 0.5], [0.3, 0.2]],
            "atom_plddts": {"A": [90.1, 85.3]},
            "chain_ptm": {"A": 0.88, "B": 0.76},
            "chain_iptm": {"A": 0.72, "B": 0.65},
        }
        conf_file.write_text(json.dumps(conf_data), encoding="utf-8")

        payload: dict = {}
        _harvest_af3_confidences_json(payload, conf_file)

        assert payload["confidences_json"] == str(conf_file)
        assert payload["pae"] == [[0.1, 0.5], [0.3, 0.2]]
        assert payload["atom_plddts"] == {"A": [90.1, 85.3]}
        assert payload["chain_ptm"] == {"A": 0.88, "B": 0.76}
        assert payload["chain_iptm"] == {"A": 0.72, "B": 0.65}

    def test_partial_confidences_file(self, tmp_path):
        conf_file = tmp_path / "fold1_confidences.json"
        conf_file.write_text(json.dumps({"pae": [[1.0]]}), encoding="utf-8")

        payload: dict = {}
        _harvest_af3_confidences_json(payload, conf_file)

        assert "pae" in payload
        assert "atom_plddts" not in payload
        assert "chain_ptm" not in payload
        assert "chain_iptm" not in payload

    def test_invalid_json_is_ignored_gracefully(self, tmp_path):
        conf_file = tmp_path / "fold1_confidences.json"
        conf_file.write_text("BROKEN JSON {{{", encoding="utf-8")

        payload: dict = {}
        _harvest_af3_confidences_json(payload, conf_file)

        assert payload["confidences_json"] == str(conf_file)
        # No metric keys should be set
        assert "pae" not in payload
        assert "atom_plddts" not in payload

    def test_non_dict_json_is_ignored(self, tmp_path):
        conf_file = tmp_path / "fold1_confidences.json"
        conf_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        payload: dict = {}
        _harvest_af3_confidences_json(payload, conf_file)

        assert payload["confidences_json"] == str(conf_file)
        assert "pae" not in payload


# ---------------------------------------------------------------------------
# _harvest_af3_data_json
# ---------------------------------------------------------------------------


class TestHarvestAf3DataJson:
    def test_records_data_json_path(self, tmp_path):
        data_file = tmp_path / "fold1_data.json"
        data_file.write_text(json.dumps({"sequences": "ACGT"}), encoding="utf-8")

        payload: dict = {}
        _harvest_af3_data_json(payload, data_file)

        assert payload["data_json"] == str(data_file)

    def test_extracts_ranking_score_when_absent_from_payload(self, tmp_path):
        data_file = tmp_path / "fold1_data.json"
        data_file.write_text(
            json.dumps({"ranking_score": 0.93, "sequences": "ACGT"}),
            encoding="utf-8",
        )

        payload: dict = {}
        _harvest_af3_data_json(payload, data_file)

        assert payload["ranking_score"] == 0.93

    def test_does_not_overwrite_existing_ranking_score(self, tmp_path):
        data_file = tmp_path / "fold1_data.json"
        data_file.write_text(json.dumps({"ranking_score": 0.50}), encoding="utf-8")

        payload: dict = {"ranking_score": 0.99}
        _harvest_af3_data_json(payload, data_file)

        # Existing value should not be overwritten
        assert payload["ranking_score"] == 0.99

    def test_invalid_json_still_records_path(self, tmp_path):
        data_file = tmp_path / "fold1_data.json"
        data_file.write_text("NOT JSON", encoding="utf-8")

        payload: dict = {}
        _harvest_af3_data_json(payload, data_file)

        assert payload["data_json"] == str(data_file)
        assert "ranking_score" not in payload

    def test_non_dict_json_still_records_path(self, tmp_path):
        data_file = tmp_path / "fold1_data.json"
        data_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        payload: dict = {}
        _harvest_af3_data_json(payload, data_file)

        assert payload["data_json"] == str(data_file)
        assert "ranking_score" not in payload


# ---------------------------------------------------------------------------
# _harvest_af3_seed_sample_dirs
# ---------------------------------------------------------------------------


class TestHarvestAf3SeedSampleDirs:
    def test_discovers_seed_sample_dirs(self, tmp_path):
        sample_dir = tmp_path / "seed-1" / "sample-0"
        sample_dir.mkdir(parents=True)

        payload: dict = {}
        _harvest_af3_seed_sample_dirs(payload, tmp_path)

        assert "seed_sample_dirs" in payload
        assert str(sample_dir) in payload["seed_sample_dirs"]

    def test_multiple_seeds_and_samples(self, tmp_path):
        (tmp_path / "seed-1" / "sample-0").mkdir(parents=True)
        (tmp_path / "seed-1" / "sample-1").mkdir(parents=True)
        (tmp_path / "seed-2" / "sample-0").mkdir(parents=True)

        payload: dict = {}
        _harvest_af3_seed_sample_dirs(payload, tmp_path)

        assert len(payload["seed_sample_dirs"]) == 3

    def test_seed_dir_with_model_cif_no_samples(self, tmp_path):
        """A seed dir containing model.cif but no sample subdirs should be recorded."""
        seed_dir = tmp_path / "seed-1"
        seed_dir.mkdir()
        (seed_dir / "fold1_model.cif").write_text("# mmCIF", encoding="utf-8")

        payload: dict = {}
        _harvest_af3_seed_sample_dirs(payload, tmp_path)

        assert "seed_sample_dirs" in payload
        assert str(seed_dir) in payload["seed_sample_dirs"]

    def test_seed_dir_with_samples_takes_samples_not_seed(self, tmp_path):
        """When a seed dir has sample subdirs, record sample dirs, not the seed dir."""
        sample_dir = tmp_path / "seed-1" / "sample-0"
        sample_dir.mkdir(parents=True)
        (tmp_path / "seed-1" / "fold1_model.cif").write_text("# mmCIF", encoding="utf-8")

        payload: dict = {}
        _harvest_af3_seed_sample_dirs(payload, tmp_path)

        assert str(sample_dir) in payload["seed_sample_dirs"]
        # seed dir should NOT be in the list because it has sample subdirs
        assert str(tmp_path / "seed-1") not in payload["seed_sample_dirs"]

    def test_no_seed_dirs_yields_no_key(self, tmp_path):
        payload: dict = {}
        _harvest_af3_seed_sample_dirs(payload, tmp_path)

        assert "seed_sample_dirs" not in payload

    def test_ignores_non_directory_seed_entries(self, tmp_path):
        (tmp_path / "seed-1.txt").write_text("not a dir", encoding="utf-8")

        payload: dict = {}
        _harvest_af3_seed_sample_dirs(payload, tmp_path)

        assert "seed_sample_dirs" not in payload


# ---------------------------------------------------------------------------
# _harvest_af3_embeddings_and_distograms
# ---------------------------------------------------------------------------


class TestHarvestAf3EmbeddingsAndDistograms:
    def test_discovers_npy_embeddings(self, tmp_path):
        emb_file = tmp_path / "fold1_embeddings.npy"
        emb_file.write_bytes(b"\x00" * 8)

        payload: dict = {}
        _harvest_af3_embeddings_and_distograms(payload, tmp_path)

        assert payload["embeddings_path"] == str(emb_file)

    def test_discovers_npz_embeddings(self, tmp_path):
        emb_file = tmp_path / "fold1_embeddings.npz"
        emb_file.write_bytes(b"\x00" * 8)

        payload: dict = {}
        _harvest_af3_embeddings_and_distograms(payload, tmp_path)

        assert payload["embeddings_path"] == str(emb_file)

    def test_npy_preferred_over_npz_for_embeddings(self, tmp_path):
        """If both .npy and .npz exist, .npy should win because it sorts first."""
        (tmp_path / "fold1_embeddings.npy").write_bytes(b"\x00" * 8)
        npz_file = tmp_path / "fold1_embeddings.npz"
        npz_file.write_bytes(b"\x00" * 8)

        payload: dict = {}
        _harvest_af3_embeddings_and_distograms(payload, tmp_path)

        assert payload["embeddings_path"].endswith(".npy")

    def test_discovers_npy_distogram(self, tmp_path):
        dist_file = tmp_path / "fold1_distogram.npy"
        dist_file.write_bytes(b"\x00" * 8)

        payload: dict = {}
        _harvest_af3_embeddings_and_distograms(payload, tmp_path)

        assert payload["distogram_path"] == str(dist_file)

    def test_discovers_npz_distogram(self, tmp_path):
        dist_file = tmp_path / "fold1_distogram.npz"
        dist_file.write_bytes(b"\x00" * 8)

        payload: dict = {}
        _harvest_af3_embeddings_and_distograms(payload, tmp_path)

        assert payload["distogram_path"] == str(dist_file)

    def test_no_artifacts_yields_no_keys(self, tmp_path):
        payload: dict = {}
        _harvest_af3_embeddings_and_distograms(payload, tmp_path)

        assert "embeddings_path" not in payload
        assert "distogram_path" not in payload

    def test_discovers_per_seed_embeddings_npz(self, tmp_path):
        """AF3 canonical layout puts embeddings under seed-<seed>_embeddings/."""
        emb_dir = tmp_path / "seed-1234_embeddings"
        emb_dir.mkdir()
        emb_file = emb_dir / "hello_fold_seed-1234_embeddings.npz"
        emb_file.write_bytes(b"\x00" * 8)

        payload: dict = {}
        _harvest_af3_embeddings_and_distograms(payload, tmp_path)

        assert payload["embeddings_path"] == str(emb_file)

    def test_discovers_per_seed_distogram_npz(self, tmp_path):
        """AF3 canonical layout puts distograms under seed-<seed>_distogram/."""
        dist_dir = tmp_path / "seed-1234_distogram"
        dist_dir.mkdir()
        dist_file = dist_dir / "hello_fold_seed-1234_distogram.npz"
        dist_file.write_bytes(b"\x00" * 8)

        payload: dict = {}
        _harvest_af3_embeddings_and_distograms(payload, tmp_path)

        assert payload["distogram_path"] == str(dist_file)

    def test_per_seed_layout_preferred_over_top_level(self, tmp_path):
        """When both per-seed and top-level files exist, per-seed wins."""
        # Top-level fallback
        (tmp_path / "fold1_embeddings.npy").write_bytes(b"\x00" * 8)

        # Per-seed canonical
        emb_dir = tmp_path / "seed-1234_embeddings"
        emb_dir.mkdir()
        emb_file = emb_dir / "hello_fold_seed-1234_embeddings.npz"
        emb_file.write_bytes(b"\x00" * 8)

        payload: dict = {}
        _harvest_af3_embeddings_and_distograms(payload, tmp_path)

        assert payload["embeddings_path"] == str(emb_file)

    def test_discovers_per_seed_embeddings_npy(self, tmp_path):
        emb_dir = tmp_path / "seed-1_embeddings"
        emb_dir.mkdir()
        emb_file = emb_dir / "fold1_embeddings.npy"
        emb_file.write_bytes(b"\x00" * 8)

        payload: dict = {}
        _harvest_af3_embeddings_and_distograms(payload, tmp_path)

        assert payload["embeddings_path"] == str(emb_file)

    def test_does_not_overwrite_existing_embeddings_path(self, tmp_path):
        payload: dict = {"embeddings_path": "/pre-existing/path.npy"}
        _harvest_af3_embeddings_and_distograms(payload, tmp_path)

        assert payload["embeddings_path"] == "/pre-existing/path.npy"

    def test_both_embeddings_and_distogram_together(self, tmp_path):
        emb_file = tmp_path / "fold1_embeddings.npy"
        emb_file.write_bytes(b"\x00" * 8)
        dist_file = tmp_path / "fold1_distogram.npy"
        dist_file.write_bytes(b"\x00" * 8)

        payload: dict = {}
        _harvest_af3_embeddings_and_distograms(payload, tmp_path)

        assert payload["embeddings_path"] == str(emb_file)
        assert payload["distogram_path"] == str(dist_file)


# ---------------------------------------------------------------------------
# Extended harvest_af3_output_dir integration tests
# ---------------------------------------------------------------------------


class TestHarvestAf3OutputDirExtended:
    """Integration tests for extended AF3 harvesting in harvest_af3_output_dir."""

    def test_dir_with_confidences_json(self, tmp_path):
        out = tmp_path / "af3_conf"
        out.mkdir()
        (out / "fold1_model.cif").write_text("# mmCIF", encoding="utf-8")
        conf_file = out / "fold1_confidences.json"
        conf_data = {
            "pae": [[0.1, 0.5], [0.3, 0.2]],
            "atom_plddts": {"A": [90.1, 85.3]},
            "chain_ptm": {"A": 0.92},
            "chain_iptm": {"A": 0.78},
        }
        conf_file.write_text(json.dumps(conf_data), encoding="utf-8")

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        assert result["confidences_json"] == str(conf_file)
        assert result["pae"] == [[0.1, 0.5], [0.3, 0.2]]
        assert result["atom_plddts"] == {"A": [90.1, 85.3]}
        assert result["chain_ptm"] == {"A": 0.92}
        assert result["chain_iptm"] == {"A": 0.78}

    def test_dir_with_data_json(self, tmp_path):
        out = tmp_path / "af3_data"
        out.mkdir()
        (out / "fold1_model.cif").write_text("# mmCIF", encoding="utf-8")
        data_file = out / "fold1_data.json"
        data_file.write_text(
            json.dumps({"ranking_score": 0.95, "sequences": "ACGT"}), encoding="utf-8"
        )

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        assert result["data_json"] == str(data_file)
        assert result["ranking_score"] == 0.95

    def test_data_json_does_not_overwrite_summary_ranking_score(self, tmp_path):
        """When summary confidences provides ranking_score, data.json should NOT override it."""
        out = tmp_path / "af3_priority"
        out.mkdir()
        (out / "fold1_model.cif").write_text("# mmCIF", encoding="utf-8")
        summary = out / "fold1_summary_confidences.json"
        summary.write_text(json.dumps({"ranking_score": 0.99, "ptm": 0.90}), encoding="utf-8")
        data_file = out / "fold1_data.json"
        data_file.write_text(json.dumps({"ranking_score": 0.50}), encoding="utf-8")

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        # Summary confidences ranking_score should take priority
        assert result["ranking_score"] == 0.99

    def test_dir_with_seed_sample_subdirs(self, tmp_path):
        out = tmp_path / "af3_seed"
        out.mkdir()
        (out / "fold1_model.cif").write_text("# mmCIF", encoding="utf-8")
        (out / "seed-1" / "sample-0").mkdir(parents=True)

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        assert "seed_sample_dirs" in result
        assert len(result["seed_sample_dirs"]) == 1

    def test_dir_with_embeddings_npy(self, tmp_path):
        out = tmp_path / "af3_emb"
        out.mkdir()
        (out / "fold1_model.cif").write_text("# mmCIF", encoding="utf-8")
        emb_file = out / "fold1_embeddings.npy"
        emb_file.write_bytes(b"\x00" * 8)

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        assert result["embeddings_path"] == str(emb_file)

    def test_dir_with_distogram_npz(self, tmp_path):
        out = tmp_path / "af3_dist"
        out.mkdir()
        (out / "fold1_model.cif").write_text("# mmCIF", encoding="utf-8")
        dist_file = out / "fold1_distogram.npz"
        dist_file.write_bytes(b"\x00" * 8)

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        assert result["distogram_path"] == str(dist_file)

    def test_full_af3_output_directory(self, tmp_path):
        """A comprehensive test with all AF3 output files present at once."""
        out = tmp_path / "af3_full"
        out.mkdir()

        # Model CIF
        (out / "fold1_model.cif").write_text("# mmCIF", encoding="utf-8")

        # Summary confidences
        summary = out / "fold1_summary_confidences.json"
        summary.write_text(
            json.dumps(
                {"ptm": 0.88, "iptm": 0.75, "ranking_score": 0.95, "chain_pair_iptm": {"A_B": 0.74}}
            ),
            encoding="utf-8",
        )

        # Detailed confidences
        conf_file = out / "fold1_confidences.json"
        conf_data = {
            "pae": [[0.1, 0.5], [0.3, 0.2]],
            "atom_plddts": {"A": [92.0, 88.5]},
            "chain_ptm": {"A": 0.91, "B": 0.85},
            "chain_iptm": {"A": 0.78, "B": 0.70},
        }
        conf_file.write_text(json.dumps(conf_data), encoding="utf-8")

        # Data JSON
        data_file = out / "fold1_data.json"
        data_file.write_text(
            json.dumps({"ranking_score": 0.50, "sequences": "MMM"}), encoding="utf-8"
        )

        # Seed/sample dirs
        (out / "seed-1" / "sample-0").mkdir(parents=True)
        (out / "seed-1" / "sample-1").mkdir(parents=True)

        # Embeddings & distograms
        (out / "fold1_embeddings.npy").write_bytes(b"\x00" * 8)
        (out / "fold1_distogram.npy").write_bytes(b"\x00" * 8)

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None

        # Base keys
        assert result["backend"] == "alphafold3_local"
        assert result["status"] == "completed"
        assert result["output_format"] == "mmcif"

        # Primary files
        assert "model_cif" in result
        assert "summary_confidences_json" in result
        assert "confidences_json" in result
        assert "data_json" in result

        # Summary metrics
        assert result["ptm"] == 0.88
        assert result["iptm"] == 0.75
        assert result["ranking_score"] == 0.95
        assert result["chain_pair_iptm"] == {"A_B": 0.74}

        # Detailed confidences metrics
        assert result["pae"] == [[0.1, 0.5], [0.3, 0.2]]
        assert result["atom_plddts"] == {"A": [92.0, 88.5]}
        assert result["chain_ptm"] == {"A": 0.91, "B": 0.85}
        assert result["chain_iptm"] == {"A": 0.78, "B": 0.70}

        # Data JSON ranking_score should NOT override summary's 0.95
        assert result["ranking_score"] == 0.95

        # Seed/sample directories
        assert "seed_sample_dirs" in result
        assert len(result["seed_sample_dirs"]) == 2

        # Embeddings & distograms
        assert "embeddings_path" in result
        assert "distogram_path" in result

    def test_confidences_json_with_invalid_json_still_records_path(self, tmp_path):
        out = tmp_path / "af3_bad_conf"
        out.mkdir()
        (out / "fold1_model.cif").write_text("# mmCIF", encoding="utf-8")
        conf_file = out / "fold1_confidences.json"
        conf_file.write_text("INVALID JSON{{{{", encoding="utf-8")

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        assert result["confidences_json"] == str(conf_file)
        assert "pae" not in result
        assert "atom_plddts" not in result

    def test_data_json_with_invalid_json_still_records_path(self, tmp_path):
        out = tmp_path / "af3_bad_data"
        out.mkdir()
        (out / "fold1_model.cif").write_text("# mmCIF", encoding="utf-8")
        data_file = out / "fold1_data.json"
        data_file.write_text("NOT JSON", encoding="utf-8")

        result = harvest_af3_output_dir(out, backend="alphafold3_local", status="completed")
        assert result is not None
        assert result["data_json"] == str(data_file)
        assert "ranking_score" not in result


# ---------------------------------------------------------------------------
# filter_structure_evidence with new AF3 keys
# ---------------------------------------------------------------------------


class TestFilterStructureEvidenceExtended:
    def test_new_af3_keys_pass_through_filter(self):
        source = {
            "confidences_json": "/tmp/conf.json",
            "data_json": "/tmp/data.json",
            "pae": [[0.1]],
            "atom_plddts": {"A": [90.0]},
            "chain_ptm": {"A": 0.88},
            "chain_iptm": {"A": 0.72},
        }
        result = filter_structure_evidence(source)
        assert result == source

    def test_new_af3_keys_filtered_from_non_canonical(self):
        """Keys that are harvested but NOT in STRUCTURE_EVIDENCE_KEYS should be filtered out."""
        source = {
            "confidences_json": "/tmp/conf.json",
            "embeddings_path": "/tmp/emb.npy",
            "distogram_path": "/tmp/dist.npy",
            "seed_sample_dirs": ["/tmp/seed-1/sample-0"],
            "non_canonical_key": "should be removed",
        }
        result = filter_structure_evidence(source)
        assert "confidences_json" in result
        assert "data_json" not in result  # data_json IS in STRUCTURE_EVIDENCE_KEYS now
        assert "embeddings_path" not in result  # NOT in STRUCTURE_EVIDENCE_KEYS
        assert "distogram_path" not in result  # NOT in STRUCTURE_EVIDENCE_KEYS
        assert "seed_sample_dirs" not in result  # NOT in STRUCTURE_EVIDENCE_KEYS
        assert "non_canonical_key" not in result
