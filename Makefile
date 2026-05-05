.PHONY: install install-worker install-dev install-hooks dev worker test test-safety test-e2e test-deployment smoke smoke-verify smoke-redis-live lint lint-maintained clean seed-demo dashboard format ci verify-local ports-check docker-build docker-build-clean docker-prepare-volumes docker-up docker-up-core docker-down docker-logs docker-logs-svc docker-health reset migrate makemigration

API_HOST ?= 127.0.0.1
API_PORT ?= 8010
DASHBOARD_HOST ?= 127.0.0.1
DASHBOARD_PORT ?= 8502
NEOVAX_API_URL ?= http://$(API_HOST):$(API_PORT)

# Install dependencies
install:
	pip install -e ".[dev,frontend]"

install-worker:
	pip install -e ".[dev,frontend,worker]"

# Install pre-commit hooks
install-hooks:
	pre-commit install

# Run development server
dev:
	uvicorn backend.app.main:app --reload --host $(API_HOST) --port $(API_PORT)

# Run Celery worker (requires Redis broker — see docker-compose.yml)
worker:
	celery -A backend.app.worker worker --loglevel=info --concurrency=2

# Run Streamlit dashboard
dashboard:
	NEOVAX_API_URL=$(NEOVAX_API_URL) PYTHONPATH=. streamlit run frontend/app/dashboard.py --server.address $(DASHBOARD_HOST) --server.port $(DASHBOARD_PORT)

# Run all tests
test:
	pytest backend/tests/ -v --cov=backend.app

# Run safety-specific tests
test-safety:
	pytest backend/tests/ -v -m safety

# Run end-to-end workflow tests (lifecycle + synthetic demo + background job flows)
test-e2e:
	pytest backend/tests/test_e2e_core_lifecycle_api.py backend/tests/test_e2e_synthetic_demo_api.py -v

# Validate deployment/runtime scaffold files and wiring
test-deployment:
	@if [ -x ./.venv/bin/pytest ]; then \
		PYTHONPATH=. ./.venv/bin/pytest backend/tests/test_deployment_scaffold.py backend/tests/test_ci_precommit_scaffold.py backend/tests/test_lint_maintained_scaffold.py backend/tests/test_port_consistency.py -q; \
	else \
		PYTHONPATH=. pytest backend/tests/test_deployment_scaffold.py backend/tests/test_ci_precommit_scaffold.py backend/tests/test_lint_maintained_scaffold.py backend/tests/test_port_consistency.py -q; \
	fi

# Quick smoke test — fast sanity check excluding slow/integration/e2e
smoke:
	pytest backend/tests/ -v -m "not slow and not integration and not e2e" -x -q

# Live verification — check running API and dashboard respond correctly.
# Respects API_HOST, API_PORT, DASHBOARD_HOST, DASHBOARD_PORT overrides.
smoke-verify:
	@echo "=== NeoVax Live Verification ==="
	@echo "--- API health ---"
	@tmp=$$(mktemp); code=$$(curl -sS -o $$tmp -w "%{http_code}" http://$(API_HOST):$(API_PORT)/health) || (rm -f $$tmp; echo "FAIL: API /health unreachable at http://$(API_HOST):$(API_PORT)" && exit 1); python3 -m json.tool < $$tmp; echo "  /health HTTP $$code (expected 200 or 503)"; rm -f $$tmp; if [ "$$code" != "200" ] && [ "$$code" != "503" ]; then echo "FAIL: API /health returned HTTP $$code" && exit 1; fi
	@echo ""
	@echo "--- API version ---"
	@curl -sf http://$(API_HOST):$(API_PORT)/version | python3 -m json.tool || (echo "FAIL: API /version unreachable" && exit 1)
	@echo ""
	@echo "--- API cases endpoint ---"
	@curl -sf http://$(API_HOST):$(API_PORT)/cases | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  cases returned: {len(d) if isinstance(d, list) else \"(paginated)\"}')" || echo "WARN: /cases not reachable or no seed data"
	@echo ""
	@echo "--- Dashboard health ---"
	@tmp=$$(mktemp); code=$$(curl -sS -o $$tmp -w "%{http_code}" http://$(DASHBOARD_HOST):$(DASHBOARD_PORT)/_stcore/health) || (rm -f $$tmp; echo "WARN: dashboard unreachable at http://$(DASHBOARD_HOST):$(DASHBOARD_PORT)" && exit 0); cat $$tmp; echo ""; echo "  dashboard health HTTP $$code (expected 200)"; rm -f $$tmp; if [ "$$code" != "200" ]; then echo "WARN: dashboard health returned HTTP $$code"; fi
	@echo ""
	@echo "=== Verification complete ==="

# Opt-in live Redis smoke using the worker-profile Redis container.
# Requires Docker and a free localhost:6379 unless NEOVAX_REDIS_SMOKE_URL is set.
smoke-redis-live:
	NEOVAX_RUN_REDIS_SMOKE=1 PYTHONPATH=. pytest backend/tests/test_event_stream_redis_live_smoke.py backend/tests/test_event_clients_redis_live_smoke.py -v -s

# Run linters
lint:
	ruff check backend/
	mypy backend/
	black --check backend/

# Run lint only on the actively maintained CI/scaffold files
lint-maintained:
	ruff check backend/tests/test_ci_precommit_scaffold.py backend/tests/test_deployment_scaffold.py backend/tests/test_lint_maintained_scaffold.py backend/tests/test_port_consistency.py
	black --check backend/tests/test_ci_precommit_scaffold.py backend/tests/test_deployment_scaffold.py backend/tests/test_lint_maintained_scaffold.py backend/tests/test_port_consistency.py
	@if [ -x ./.venv/bin/mypy ]; then \
		PYTHONPATH=. ./.venv/bin/mypy backend/tests/test_ci_precommit_scaffold.py backend/tests/test_deployment_scaffold.py backend/tests/test_lint_maintained_scaffold.py backend/tests/test_port_consistency.py; \
	else \
		PYTHONPATH=. python -m mypy backend/tests/test_ci_precommit_scaffold.py backend/tests/test_deployment_scaffold.py backend/tests/test_lint_maintained_scaffold.py backend/tests/test_port_consistency.py; \
	fi

# Format code
format:
	ruff check --fix backend/
	black backend/

# Local CI parity
ci:
	pre-commit run --all-files
	make smoke
	make lint-maintained
	make lint || true
	PYTHONPATH=. pytest -q
	PYTHONPATH=. pytest -q backend/tests/test_deployment_scaffold.py backend/tests/test_ci_precommit_scaffold.py backend/tests/test_lint_maintained_scaffold.py backend/tests/test_port_consistency.py

# Fast local verification for the maintained runtime/deployment scaffold.
verify-local:
	make lint-maintained
	make test-deployment
	make ports-check
	make -n smoke-verify
	make -n docker-health
	@echo "verify-local complete"

# Report current listeners on the canonical NeoVax local ports.
ports-check:
	@echo "=== NeoVax canonical port check ==="
	@echo "API: http://$(API_HOST):$(API_PORT)"
	@echo "Dashboard: http://$(DASHBOARD_HOST):$(DASHBOARD_PORT)"
	@if command -v ss >/dev/null 2>&1; then \
		ss -ltnp 2>/dev/null | grep -E ":($(API_PORT)|$(DASHBOARD_PORT))\\b" || echo "No listeners on $(API_PORT) or $(DASHBOARD_PORT)"; \
	elif command -v lsof >/dev/null 2>&1; then \
		lsof -nP -iTCP:$(API_PORT) -iTCP:$(DASHBOARD_PORT) -sTCP:LISTEN || echo "No listeners on $(API_PORT) or $(DASHBOARD_PORT)"; \
	else \
		echo "WARN: neither ss nor lsof is available for port inspection"; \
	fi

# Seed demo data
seed-demo:
	python -m backend.app.seed_demo

# Run database migrations
migrate:
	alembic upgrade head

# Create a new migration
makemigration:
	alembic revision --autogenerate -m "$(MSG)"

# Clean build artifacts
clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

# --- Docker targets ---

# Build Docker images (use --no-cache for a clean build)
docker-build:
	docker compose build

# Build Docker images without cache
docker-build-clean:
	docker compose build --no-cache

# Prepare bind-mounted runtime directories for the non-root container user.
docker-prepare-volumes:
	@mkdir -p data audit_logs artifacts
	@if [ ! -w data ] || [ ! -w audit_logs ] || [ ! -w artifacts ]; then \
		echo "Preparing Docker bind-mount ownership for uid/gid 1000"; \
		docker compose run --rm --no-deps --user root --entrypoint sh app -c 'chown -R 1000:1000 /app/data /app/audit_logs /app/artifacts'; \
	fi

# Start all services in detached mode
docker-up: docker-prepare-volumes
	docker compose up -d

# Start only the core services (app + dashboard, no worker)
docker-up-core: docker-prepare-volumes
	docker compose up -d app dashboard

# Stop all services
docker-down:
	docker compose down

# Follow Docker logs for all services
docker-logs:
	docker compose logs -f

# Follow logs for a specific service (usage: make docker-logs-svc SVC=app)
docker-logs-svc:
	docker compose logs -f $(SVC)

# Check service health
docker-health:
	@echo "=== Service Status ==="
	@docker compose ps
	@echo ""
	@echo "=== Health Checks ==="
	@tmp=$$(mktemp); code=$$(curl -sS -o $$tmp -w "%{http_code}" $(NEOVAX_API_URL)/health) || (rm -f $$tmp; echo "app health: UNREACHABLE" && exit 0); python3 -m json.tool < $$tmp 2>/dev/null || cat $$tmp; echo "app /health HTTP $$code (expected 200 or 503)"; rm -f $$tmp
	@tmp=$$(mktemp); code=$$(curl -sS -o $$tmp -w "%{http_code}" http://$(DASHBOARD_HOST):$(DASHBOARD_PORT)/_stcore/health) || (rm -f $$tmp; echo "dashboard health: UNREACHABLE" && exit 0); cat $$tmp; echo ""; echo "dashboard health HTTP $$code (expected 200)"; rm -f $$tmp

# Full development reset
reset: clean
	rm -f neovax.db
	@echo "Database reset complete. Recreate schema when DB layer lands."
