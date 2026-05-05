"""AlphaFold Server dry-run command builder placeholder."""

from __future__ import annotations

from backend.app.alphafold.schemas import AlphaFoldServerJobRequest


def build_alphafold_server_command(request: AlphaFoldServerJobRequest) -> list[str]:
    command = ["alphafold_server_submit", "--json_path", request.json_path]
    if request.acknowledge_external_upload:
        command.append("--acknowledge-external-upload")
    return command
