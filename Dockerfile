# NeoVax-Agent Dockerfile
# Multi-stage build: builder installs deps, runtime copies them.
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
COPY pyproject.toml ./
COPY backend/ backend/

# Install the package with all optional extras (dev, frontend, worker)
RUN pip install --no-cache-dir --prefix=/install -e ".[dev,frontend,worker]"

# --- Runtime stage ---
FROM python:3.11-slim AS runtime

# Labels for introspection
LABEL org.opencontainers.image.title="neovax-agent" \
      org.opencontainers.image.description="Local-first, safety-gated research coordination platform" \
      org.opencontainers.image.version="0.1.0-alpha"

# Create non-root user for security
RUN groupadd --gid 1000 neovax && \
    useradd --uid 1000 --gid neovax --shell /bin/bash --create-home neovax

# Copy installed packages from builder
COPY --from=builder /install /usr

# Create application and data directories
WORKDIR /app
RUN mkdir -p /app/data /app/audit_logs /app/artifacts && \
    chown -R neovax:neovax /app

# Copy application source
COPY --chown=neovax:neovax backend/ backend/
COPY --chown=neovax:neovax frontend/ frontend/
COPY --chown=neovax:neovax pyproject.toml ./

# Install the package in runtime stage so entry points are available
RUN pip install --no-cache-dir -e ".[dev,frontend,worker]"

# Default environment (overridable at runtime)
ENV NEOVAX_DATABASE_URL="sqlite:///./data/neovax.db" \
    NEOVAX_SPECIES_MODE="demo" \
    NEOVAX_SAFETY_PREFLIGHT_ENABLED="true" \
    NEOVAX_LOG_LEVEL="INFO" \
    NEOVAX_STRUCTURED_LOGS="true" \
    NEOVAX_AUDIT_LOG_PATH="/app/audit_logs" \
    NEOVAX_ALPHAFOLD_DEFAULT_BACKEND="mock" \
    NEOVAX_PIPELINE_MODE="mock"

USER neovax

EXPOSE 8010 8502

# Health check — the FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8010/health')" || exit 1

# Default entrypoint: run the API server
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8010"]