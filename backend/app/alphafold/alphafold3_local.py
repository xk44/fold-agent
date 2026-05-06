"""AlphaFold 3 local command builder and JSON input file writer.

Builds CLI commands for running alphafold3 via ``run_alphafold.py`` and
writes structured AF3 JSON input files from AF3InputJSON models.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.alphafold.schemas import (
    AF3InputJSON,
    AlphaFold3LocalJobRequest,
)


def build_af3_json_input_file(
    af3_input: AF3InputJSON,
    output_path: str | Path,
) -> str:
    """Serialize an AF3InputJSON model to a JSON file for ``--json_path``.

    Parameters
    ----------
    af3_input:
        The structured AF3 input model.
    output_path:
        Where to write the JSON file.

    Returns
    -------
    str
        The string path of the written file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = af3_input.to_af3_json_dict()
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return str(output_path)


def build_alphafold3_local_command(
    request: AlphaFold3LocalJobRequest,
    *,
    json_output_path: str | None = None,
) -> list[str]:
    """Build the CLI command for running AlphaFold 3 locally.

    Parameters
    ----------
    request:
        The AF3 local job request.  If ``af3_input`` is populated the
        builder will write the JSON file and use ``--json_path``.
    json_output_path:
        Required when ``request.af3_input`` is set.  Path where the
        AF3 JSON input file will be written.

    Returns
    -------
    list[str]
        The command-line arguments list (argv style).
    """
    command: list[str] = ["alphafold"]

    if request.af3_input is not None:
        if json_output_path is None:
            raise ValueError("json_output_path is required when af3_input is provided")
        build_af3_json_input_file(request.af3_input, json_output_path)
        command.extend(["--json_path", str(json_output_path)])
    elif request.input_kind == "json":
        command.extend(["--json_path", request.json_path])  # type: ignore[arg-type]
    else:
        command.extend(["--input_dir", request.input_dir])  # type: ignore[arg-type]

    if request.model_dir:
        command.extend(["--model_dir", request.model_dir])
    if request.db_dir:
        command.extend(["--db_dir", request.db_dir])
    if request.output_dir:
        command.extend(["--output_dir", request.output_dir])

    return command
