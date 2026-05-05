"""AlphaFold 2 local command builder."""

from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir

from backend.app.alphafold.schemas import AlphaFold2LocalJobRequest


def build_alphafold2_local_command(request: AlphaFold2LocalJobRequest) -> list[str]:
    fasta_path = request.fasta_path or str(Path(gettempdir()) / f"{request.job_name}.fa")
    output_dir = str(Path(gettempdir()) / f"{request.job_name}_out")
    command = ["run_alphafold", "--fasta_paths", fasta_path, "--output_dir", output_dir]
    if request.data_dir:
        command.extend(["--data_dir", request.data_dir])
    if request.max_template_date:
        command.extend(["--max_template_date", request.max_template_date])
    if request.model_preset:
        command.extend(["--model_preset", request.model_preset])
    if request.db_preset:
        command.extend(["--db_preset", request.db_preset])
    return command
