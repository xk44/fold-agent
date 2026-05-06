# FoldAgent Dockerfile
# Single-stage dev build — no builder stage needed for a local-first project.
FROM python:3.11-slim

# Labels for introspection
LABEL org.opencontainers.image.title="foldagent" \
      org.opencontainers.image.description="Local-first, safety-gated research coordination platform" \
      org.opencontainers.image.version="0.1.0-alpha"

# Create non-root user for security
RUN groupadd --gid 1000 foldagent && \
    useradd --uid 1000 --gid foldagent --shell /bin/bash --create-home foldagent

# Create application and data directories
WORKDIR /app
RUN mkdir -p /app/data /app/audit_logs /app/artifacts && \
    chown -R foldagent:foldagent /app

# Copy application source
COPY --chown=foldagent:foldagent backend/ backend/
COPY --chown=foldagent:foldagent frontend/ frontend/
COPY --chown=foldagent:foldagent skills/ skills/
COPY --chown=foldagent:foldagent pyproject.toml ./

# Install the package with all optional extras
RUN pip install --no-cache-dir -e ".[dev,frontend,worker]"

# Default environment (overridable at runtime)
ENV FOLDAGENT_DATABASE_URL="sqlite:///./data/foldagent.db" \
    FOLDAGENT_SPECIES_MODE="demo" \
    FOLDAGENT_SAFETY_PREFLIGHT_ENABLED="true" \
    FOLDAGENT_LOG_LEVEL="INFO" \
    FOLDAGENT_STRUCTURED_LOGS="true" \
    FOLDAGENT_AUDIT_LOG_PATH="/app/audit_logs" \
    FOLDAGENT_ALPHAFOLD_DEFAULT_BACKEND="mock" \
    FOLDAGENT_PIPELINE_MODE="mock"

USER foldagent

EXPOSE 8010 8502

# Health check — the FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8010/health')" || exit 1

# Default entrypoint: run the API server
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8010"]
