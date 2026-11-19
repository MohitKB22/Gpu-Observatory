# Convenience commands. Everything here can also be run directly; see README.md.

.PHONY: up down logs dev-db backend-install frontend-install dev-backend dev-frontend test test-backend test-frontend lint

up:            ## Build and start the full stack (http://localhost:8080)
	docker compose up --build -d

down:          ## Stop the stack (data is kept in the postgres-data volume)
	docker compose down

logs:          ## Follow logs from all services
	docker compose logs -f

dev-db:        ## Start only PostgreSQL in Docker on 127.0.0.1:5432, for local development
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db

backend-install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

frontend-install:
	cd frontend && npm ci

dev-backend:   ## Run the API with auto-reload (needs PostgreSQL; see README "Local development")
	cd backend && .venv/bin/alembic upgrade head && .venv/bin/uvicorn --factory app.main:create_app --reload --port 8000

dev-frontend:  ## Run the Vite dev server on http://localhost:5173 (proxies /api to :8000)
	cd frontend && npm run dev

test: test-backend test-frontend

test-backend:  ## Uses (and creates) observatory_test on the local server; see README "Testing"
	cd backend && .venv/bin/pytest

test-frontend:
	cd frontend && npm test

lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd frontend && npm run lint && npm run typecheck
