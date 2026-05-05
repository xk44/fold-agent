"""NeoVax-Agent Configuration

Local-first, safety-gated research coordination platform.
"""

from enum import Enum
from typing import Optional

from pydantic_settings import BaseSettings


class SpeciesMode(str, Enum):
    """Operating mode determining safety restrictions and templates."""

    DEMO = "demo"
    DOG = "dog"
    HUMAN = "human"


class AlphaFoldBackendName(str, Enum):
    """Available AlphaFold backend names."""

    MOCK = "mock"
    COLABFOLD = "colabfold"
    LOCAL_COLABFOLD = "local_colabfold"
    ALPHAFOLD2_LOCAL = "alphafold2_local"
    ALPHAFOLD3_LOCAL = "alphafold3_local"
    ALPHAFOLD_SERVER = "alphafold_server"
    ALPHAFOLD_DB = "alphafold_db"


class DbInitMode(str, Enum):
    """How the database schema is initialised at startup.

    - ``create_all``: legacy behaviour – call ``Base.metadata.create_all``.
      Useful for development / testing but **bypasses Alembic** and should
      not be used in production once migrations exist.
    - ``validate``: assert that every table declared in the ORM models is
      present in the database.  Raises ``RuntimeError`` on mismatch.  Use
      this in production where Alembic is responsible for schema changes.
    - ``alembic``: run ``alembic upgrade head`` at startup.  Convenience
      shortcut for single-process deployments that want auto-migration.
    """

    create_all = "create_all"
    validate = "validate"
    alembic = "alembic"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Local runtime ports
    api_port: int = 8010
    dashboard_port: int = 8502
    cors_origins: list[str] = [
        "http://localhost:8502",
        "http://127.0.0.1:8502",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:3000",
    ]

    # Database
    database_url: str = "sqlite:///./neovax.db"
    db_init_mode: DbInitMode = DbInitMode.create_all

    # Optional worker stack
    redis_url: Optional[str] = None
    celery_broker_url: Optional[str] = None
    celery_result_backend: Optional[str] = None
    background_job_backend: str = "auto"  # auto, threadpool, celery
    event_backend: str = "memory"  # memory (default), redis (future)

    # Species mode
    species_mode: SpeciesMode = SpeciesMode.DEMO

    # Cloud upload
    cloud_upload_enabled: bool = False
    cloud_upload_confirmation_required: bool = True

    # Encryption
    encryption_at_rest_enabled: bool = False
    encryption_key: Optional[str] = None

    # AlphaFold
    alphafold_default_backend: AlphaFoldBackendName = AlphaFoldBackendName.MOCK
    alphafold_allowed_backends: list[AlphaFoldBackendName] = [
        AlphaFoldBackendName.MOCK,
        AlphaFoldBackendName.COLABFOLD,
        AlphaFoldBackendName.LOCAL_COLABFOLD,
        AlphaFoldBackendName.ALPHAFOLD2_LOCAL,
        AlphaFoldBackendName.ALPHAFOLD3_LOCAL,
        AlphaFoldBackendName.ALPHAFOLD_SERVER,
        AlphaFoldBackendName.ALPHAFOLD_DB,
    ]
    alphafold_cache_outputs: bool = True
    alphafold_store_confidence_metrics: bool = True

    # Logging
    log_level: str = "INFO"
    structured_logs: bool = True
    audit_log_path: str = "./audit_logs"

    # Safety
    safety_preflight_enabled: bool = True
    unsafe_text_scanner_enabled: bool = True
    require_professional_oversight: bool = True

    # Pipeline
    pipeline_mode: str = "mock"  # mock or real
    pipeline_concurrent_workers: int = 2
    pipeline_retry_max_attempts: int = 3

    # Pipeline adapter defaults (paths are placeholders until local tools are installed)
    pipeline_bwa_reference: str = "/data/reference/hg38.fa"
    pipeline_bwa_index: str | None = None
    pipeline_gatk_reference: str = "/data/reference/hg38.fa"
    pipeline_gatk_panel_of_normals: str | None = None
    pipeline_gatk_germline_resource: str | None = None
    pipeline_vep_cache_dir: str = "/data/vep_cache"
    pipeline_vep_assembly: str = "GRCh38"
    pipeline_vep_fork: int = 4
    pipeline_pvactools_alleles: list[str] = ["HLA-A*02:01"]
    pipeline_pvactools_algorithms: list[str] = ["NetMHC"]
    pipeline_default_threads: int = 4
    pipeline_default_memory_gb: int = 8

    # Reports
    reports_default_format: str = "markdown"
    reports_research_only_label: bool = True
    artifact_root: str = "./artifacts"

    # Secret
    secret_key: str = "changeme-set-a-real-secret-key"

    model_config = {"env_prefix": "NEOVAX_"}


settings = Settings()