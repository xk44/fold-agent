from pathlib import Path
from tempfile import gettempdir

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.alphafold.alphafold2_local import build_alphafold2_local_command
from backend.app.alphafold.alphafold3_local import build_alphafold3_local_command
from backend.app.alphafold.alphafold_db import (
    build_alphafold_db_command,
    build_alphafold_db_result,
)
from backend.app.alphafold.alphafold_server import build_alphafold_server_command
from backend.app.alphafold.colabfold import build_colabfold_command
from backend.app.alphafold.schemas import (
    AF3InputJSON,
    AlphaFold2LocalJobRequest,
    AlphaFold3LocalJobRequest,
    AlphaFoldDbLookupRequest,
    AlphaFoldJobRequestBase,
    AlphaFoldServerJobRequest,
    ColabFoldJobRequest,
    ProteinEntity,
    SequenceEntry,
    parse_alphafold_request,
)


def _temp_path(name: str) -> str:
    return str(Path(gettempdir()) / name)


def _flag_value(command: list[str], flag: str) -> str:
    return command[command.index(flag) + 1]


def _minimal_af3_input() -> AF3InputJSON:
    return AF3InputJSON(
        name="af3-inline",
        modelSeeds=[1],
        sequences=[
            SequenceEntry(
                protein=ProteinEntity(id="A", sequence="MTEYKLVVVGAGGVGKSALTIQLIQ")
            )
        ],
    )


class TestColabFoldCommandBuilder:
    def test_default_command_with_sequence_uses_temp_fasta_and_output_dir(self) -> None:
        request = ColabFoldJobRequest(sequence="MTEYK", job_name="demo-job")

        command = build_colabfold_command(request)

        assert command[:3] == [
            "colabfold_batch",
            _temp_path("demo-job.fa"),
            _temp_path("demo-job_out"),
        ]

    def test_input_path_is_used_as_command_input(self) -> None:
        request = ColabFoldJobRequest(input_path="/inputs/demo.a3m", input_kind="a3m")

        command = build_colabfold_command(request)

        assert command[1] == "/inputs/demo.a3m"

    def test_host_url_and_recycle_flags_are_rendered(self) -> None:
        request = ColabFoldJobRequest(
            sequence="MTEYK",
            host_url="https://msa.example.org",
            num_recycle=6,
            num_seeds=3,
        )

        command = build_colabfold_command(request)

        assert _flag_value(command, "--host-url") == "https://msa.example.org"
        assert _flag_value(command, "--num-recycle") == "6"
        assert _flag_value(command, "--num-seeds") == "3"

    def test_template_dropout_and_overwrite_flags_are_rendered(self) -> None:
        request = ColabFoldJobRequest(
            sequence="MTEYK",
            use_templates=True,
            use_dropout=True,
            overwrite_existing_results=True,
        )

        command = build_colabfold_command(request)

        assert "--templates" in command
        assert "--use-dropout" in command
        assert "--overwrite-existing-results" in command

    def test_custom_template_random_seed_and_max_msa_flags_are_rendered(self) -> None:
        request = ColabFoldJobRequest(
            sequence="MTEYK",
            custom_template_path="/templates",
            random_seed=123,
            max_msa="32:64",
        )

        command = build_colabfold_command(request)

        assert _flag_value(command, "--custom-template-path") == "/templates"
        assert _flag_value(command, "--random-seed") == "123"
        assert _flag_value(command, "--max-msa") == "32:64"

    def test_a3m_input_requires_input_path(self) -> None:
        with pytest.raises(ValidationError, match="a3m input requires input_path"):
            ColabFoldJobRequest(input_kind="a3m")


class TestAlphaFold2CommandBuilder:
    def test_default_command_with_fasta_path(self) -> None:
        request = AlphaFold2LocalJobRequest(fasta_path="/inputs/demo.fa")

        command = build_alphafold2_local_command(request)

        assert command[:5] == [
            "run_alphafold",
            "--fasta_paths",
            "/inputs/demo.fa",
            "--output_dir",
            _temp_path("neovax_out"),
        ]

    def test_sequence_uses_temp_fasta_path(self) -> None:
        request = AlphaFold2LocalJobRequest(sequence="MTEYK", job_name="af2-demo")

        command = build_alphafold2_local_command(request)

        assert _flag_value(command, "--fasta_paths") == _temp_path("af2-demo.fa")

    def test_data_template_model_and_db_flags_are_rendered(self) -> None:
        request = AlphaFold2LocalJobRequest(
            fasta_path="/inputs/demo.fa",
            data_dir="/data/af2",
            max_template_date="2024-01-01",
            model_preset="monomer_ptm",
            db_preset="full_dbs",
        )

        command = build_alphafold2_local_command(request)

        assert _flag_value(command, "--data_dir") == "/data/af2"
        assert _flag_value(command, "--max_template_date") == "2024-01-01"
        assert _flag_value(command, "--model_preset") == "monomer_ptm"
        assert _flag_value(command, "--db_preset") == "full_dbs"

    def test_af2_requires_sequence_or_fasta_path(self) -> None:
        with pytest.raises(ValidationError, match="sequence or fasta_path"):
            AlphaFold2LocalJobRequest()


class TestAlphaFold3CommandBuilder:
    def test_json_path_and_output_dir_flags_are_rendered(self) -> None:
        request = AlphaFold3LocalJobRequest(
            json_path="/inputs/af3.json",
            output_dir="/outputs/af3",
        )

        command = build_alphafold3_local_command(request)

        assert _flag_value(command, "--json_path") == "/inputs/af3.json"
        assert _flag_value(command, "--output_dir") == "/outputs/af3"

    def test_input_dir_mode_uses_input_dir_flag(self) -> None:
        request = AlphaFold3LocalJobRequest(
            input_kind="input_dir",
            input_dir="/inputs/af3-batch",
        )

        command = build_alphafold3_local_command(request)

        assert _flag_value(command, "--input_dir") == "/inputs/af3-batch"
        assert "--json_path" not in command

    def test_model_dir_and_db_dir_flags_are_rendered(self) -> None:
        request = AlphaFold3LocalJobRequest(
            json_path="/inputs/af3.json",
            model_dir="/models/af3",
            db_dir="/db/af3",
        )

        command = build_alphafold3_local_command(request)

        assert _flag_value(command, "--model_dir") == "/models/af3"
        assert _flag_value(command, "--db_dir") == "/db/af3"

    def test_inline_af3_input_requires_json_output_path(self) -> None:
        request = AlphaFold3LocalJobRequest(af3_input=_minimal_af3_input())

        with pytest.raises(ValueError, match="json_output_path is required"):
            build_alphafold3_local_command(request)


class TestRemoteAndLookupCommandBuilders:
    def test_alphafold_server_command_renders_upload_acknowledgement(self) -> None:
        request = AlphaFoldServerJobRequest(
            json_path="/inputs/server.json",
            acknowledge_external_upload=True,
        )

        command = build_alphafold_server_command(request)

        assert command == [
            "alphafold_server_submit",
            "--json_path",
            "/inputs/server.json",
            "--acknowledge-external-upload",
        ]

    def test_alphafold_server_requires_json_path(self) -> None:
        with pytest.raises(ValidationError, match="requires json_path"):
            AlphaFoldServerJobRequest()

    def test_alphafold_db_command_uses_accession(self) -> None:
        request = AlphaFoldDbLookupRequest(accession="P12345")

        assert build_alphafold_db_command(request) == ["alphafold_db_lookup", "P12345"]

    def test_alphafold_db_result_contains_reference_links(self) -> None:
        request = AlphaFoldDbLookupRequest(accession="P12345")

        result = build_alphafold_db_result(request)

        structure = result["structure"]
        assert structure["backend"] == "alphafold_db"
        assert structure["status"] == "completed"
        assert structure["accession"] == "P12345"
        assert structure["source_url"] == "https://alphafold.ebi.ac.uk/entry/P12345"
        assert structure["model_cif"] == (
            "https://alphafold.ebi.ac.uk/files/AF-P12345-F1-model_v4.cif"
        )


class TestAlphaFoldRequestDispatcher:
    @pytest.mark.parametrize(
        ("backend_name", "payload", "expected_type"),
        [
            ("colabfold", {"sequence": "MTEYK"}, ColabFoldJobRequest),
            ("local_colabfold", {"sequence": "MTEYK"}, ColabFoldJobRequest),
            (
                "alphafold2_local",
                {"fasta_path": "/inputs/demo.fa"},
                AlphaFold2LocalJobRequest,
            ),
            (
                "alphafold3_local",
                {"json_path": "/inputs/af3.json"},
                AlphaFold3LocalJobRequest,
            ),
            (
                "alphafold_server",
                {"json_path": "/inputs/server.json"},
                AlphaFoldServerJobRequest,
            ),
            ("alphafold_db", {"accession": "P12345"}, AlphaFoldDbLookupRequest),
        ],
    )
    def test_dispatches_to_backend_specific_schema(
        self,
        backend_name: str,
        payload: dict,
        expected_type: type,
    ) -> None:
        request = parse_alphafold_request(backend_name, payload)

        assert isinstance(request, expected_type)

    def test_unknown_backend_falls_back_to_base_schema(self) -> None:
        request = parse_alphafold_request("future_backend", {"job_name": "future"})

        assert isinstance(request, AlphaFoldJobRequestBase)
        assert request.job_name == "future"

    def test_validation_error_is_propagated_for_invalid_backend_payload(self) -> None:
        with pytest.raises(ValidationError, match="fasta input requires sequence"):
            parse_alphafold_request("colabfold", {})


@pytest.mark.parametrize(
    ("backend_name", "payload", "expected_fragment"),
    [
        ("colabfold", {}, "fasta input requires sequence"),
        ("alphafold2_local", {}, "sequence or fasta_path"),
        ("alphafold_server", {}, "requires json_path"),
        ("alphafold_db", {}, "accession"),
    ],
)
def test_alphafold_dry_run_rejects_backend_specific_invalid_payloads(
    client: TestClient,
    backend_name: str,
    payload: dict,
    expected_fragment: str,
) -> None:
    response = client.post(f"/alphafold/backends/{backend_name}/dry-run", json=payload)

    assert response.status_code == 422
    assert expected_fragment in response.json()["detail"]
