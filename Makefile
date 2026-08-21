# NVIDIA AI Performance Observatory — developer entry points.
.DEFAULT_GOAL := help
SHELL := /bin/bash

API_DIR := apps/api
WEB_DIR := apps/web
VENV := $(API_DIR)/.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	 | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ─── Setup ───────────────────────────────────────────────────────────────────
.PHONY: setup
setup: setup-api setup-web ## Install all dependencies

.PHONY: setup-api
setup-api: ## Create the backend virtualenv and install dependencies
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r $(API_DIR)/requirements-dev.txt

.PHONY: setup-web
setup-web: ## Install frontend dependencies
	cd $(WEB_DIR) && npm ci --no-audit --no-fund

.PHONY: env
env: ## Create .env from the example if absent
	@test -f .env || (cp .env.example .env && echo "created .env — set SECRET_KEY and BOOTSTRAP_ADMIN_PASSWORD")

# ─── Run ─────────────────────────────────────────────────────────────────────
.PHONY: dev-api
dev-api: ## Run the API with reload
	cd $(API_DIR) && PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload --port 8000

.PHONY: dev-web
dev-web: ## Run the frontend dev server
	cd $(WEB_DIR) && npm run dev

.PHONY: up
up: env ## Start the full stack with Docker Compose
	docker compose up -d --build
	@echo "dashboard  http://localhost:3000"
	@echo "api docs   http://localhost:8000/docs"
	@echo "prometheus http://localhost:9090"
	@echo "grafana    http://localhost:3001"

.PHONY: down
down: ## Stop the stack
	docker compose down

.PHONY: clean-volumes
clean-volumes: ## Stop the stack and delete its volumes (destroys data)
	docker compose down -v

.PHONY: logs
logs: ## Follow stack logs
	docker compose logs -f --tail=100

# ─── Database ────────────────────────────────────────────────────────────────
.PHONY: migrate
migrate: ## Apply migrations
	cd $(API_DIR) && PYTHONPATH=. .venv/bin/alembic upgrade head

.PHONY: migrate-down
migrate-down: ## Roll back one migration
	cd $(API_DIR) && PYTHONPATH=. .venv/bin/alembic downgrade -1

.PHONY: migration
migration: ## Autogenerate a migration (make migration m="message")
	cd $(API_DIR) && PYTHONPATH=. .venv/bin/alembic revision --autogenerate -m "$(m)"

.PHONY: seed-demo
seed-demo: ## Backfill demo telemetry
	cd $(API_DIR) && PYTHONPATH=. .venv/bin/python ../../scripts/seed_demo.py

# ─── Quality ─────────────────────────────────────────────────────────────────
.PHONY: lint
lint: lint-api lint-web ## Lint everything

.PHONY: lint-api
lint-api: ## Lint the backend
	cd $(API_DIR) && .venv/bin/ruff check app tests && .venv/bin/black --check app tests

.PHONY: format
format: ## Auto-format the backend
	cd $(API_DIR) && .venv/bin/black app tests && .venv/bin/ruff check app tests --fix

.PHONY: lint-web
lint-web: ## Lint the frontend
	cd $(WEB_DIR) && npx eslint .

.PHONY: typecheck
typecheck: ## Type-check both applications
	cd $(API_DIR) && PYTHONPATH=. .venv/bin/mypy app --ignore-missing-imports
	cd $(WEB_DIR) && npx tsc --noEmit

.PHONY: test
test: test-api test-web ## Run all tests

.PHONY: test-api
test-api: ## Run backend tests
	cd $(API_DIR) && PYTHONPATH=. .venv/bin/pytest

.PHONY: test-cov
test-cov: ## Run backend tests with coverage
	cd $(API_DIR) && PYTHONPATH=. .venv/bin/pytest --cov=app --cov-report=term-missing --cov-report=html

.PHONY: test-web
test-web: ## Run frontend tests
	cd $(WEB_DIR) && npx vitest run

.PHONY: build-web
build-web: ## Production build of the frontend
	cd $(WEB_DIR) && npm run build

.PHONY: verify
verify: lint typecheck test build-web ## Everything CI runs

# ─── Infrastructure ──────────────────────────────────────────────────────────
.PHONY: helm-lint
helm-lint: ## Lint the Helm chart
	helm lint infra/helm/nvidia-ai-performance-observatory

.PHONY: helm-template
helm-template: ## Render the Helm chart
	helm template nvo infra/helm/nvidia-ai-performance-observatory

.PHONY: k8s-validate
k8s-validate: ## Validate Kubernetes manifests
	kubectl apply --dry-run=client -k infra/kubernetes/base

.PHONY: package
package: ## Build the distributable ZIP
	./scripts/package.sh

.PHONY: clean
clean: ## Remove build artefacts and caches
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(WEB_DIR)/.next $(API_DIR)/htmlcov $(API_DIR)/.coverage
