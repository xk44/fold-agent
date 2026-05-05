"""ColabFold and LocalColabFold command builders."""

from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir

from backend.app.alphafold.schemas import ColabFoldJobRequest


def _default_input_path(request: ColabFoldJobRequest) -> str:
    return str(Path(gettempdir()) / f"{request.job_name}.fa")


def _default_output_dir(request: ColabFoldJobRequest) -> str:
    return str(Path(gettempdir()) / f"{request.job_name}_out")


def build_colabfold_command(request: ColabFoldJobRequest) -> list[str]:
    input_path = request.input_path or _default_input_path(request)
    output_dir = _default_output_dir(request)
    command = ["colabfold_batch", input_path, output_dir]
    if request.host_url:
        command.extend(["--host-url", request.host_url])
    if request.num_recycle is not None:
        command.extend(["--num-recycle", str(request.num_recycle)])
    if request.num_seeds is not None:
        command.extend(["--num-seeds", str(request.num_seeds)])
    if request.use_templates:
        command.append("--templates")
    if request.use_dropout:
        command.append("--use-dropout")
    if request.custom_template_path:
        command.extend(["--custom-template-path", request.custom_template_path])
    if request.random_seed is not None:
        command.extend(["--random-seed", str(request.random_seed)])
    if request.max_msa:
        command.extend(["--max-msa", request.max_msa])
    if request.overwrite_existing_results:
        command.append("--overwrite-existing-results")
    return command
