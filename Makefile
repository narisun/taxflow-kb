# ─────────────────────────────────────────────────────────────────────────────
# TaxFlow AI — Monorepo Makefile
# ─────────────────────────────────────────────────────────────────────────────
# Usage:
#   make help          — show all targets
#   make setup         — first-time bootstrap (env, deps, infra, migrations)
#   make dev           — start full local stack (infra + api + frontend)
#   make test          — run all fast tests
#   make build         — production build (frontend)
#
# Subsystem prefixes:
#   api.*       — Python/FastAPI backend
#   fe.*        — Next.js frontend
#   db.*        — Database (Docker + migrations)
#   kb.*        — TaxKB knowledge base
# ─────────────────────────────────────────────────────────────────────────────

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ── Configuration ────────────────────────────────────────────────────────────

PYTHON       ?= python3
PIP          ?= pip
NPM          ?= npm
UVICORN_HOST ?= 0.0.0.0
UVICORN_PORT ?= 8000
FE_PORT      ?= 3000

# Directories
ROOT_DIR     := $(shell pwd)
API_DIR      := $(ROOT_DIR)/api
FE_DIR       := $(ROOT_DIR)/frontend
TEST_DIR     := $(ROOT_DIR)/tests
ALEMBIC_DIR  := $(ROOT_DIR)/alembic

# Virtual environment
VENV         ?= .venv
VENV_BIN     := $(VENV)/bin
VENV_PYTHON  := $(VENV_BIN)/python
VENV_PIP     := $(VENV_BIN)/pip

# Detect if we're inside a virtual env already
ifdef VIRTUAL_ENV
  RUN_PY := $(PYTHON)
  RUN_PIP := $(PIP)
else
  RUN_PY := $(VENV_PYTHON)
  RUN_PIP := $(VENV_PIP)
endif

# ── Formatting helpers ───────────────────────────────────────────────────────

BOLD   := $(shell tput bold 2>/dev/null)
RESET  := $(shell tput sgr0 2>/dev/null)
CYAN   := $(shell tput setaf 6 2>/dev/null)
GREEN  := $(shell tput setaf 2 2>/dev/null)
YELLOW := $(shell tput setaf 3 2>/dev/null)

# ═════════════════════════════════════════════════════════════════════════════
# HELP
# ═════════════════════════════════════════════════════════════════════════════

.PHONY: help
help: ## Show this help
	@echo ""
	@echo "$(BOLD)TaxFlow AI$(RESET) — Monorepo Build Targets"
	@echo ""
	@grep -E '^[a-zA-Z_.%-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-22s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ═════════════════════════════════════════════════════════════════════════════
# SETUP — First-time bootstrap
# ═════════════════════════════════════════════════════════════════════════════

.PHONY: setup
setup: env venv api.deps fe.deps db.up db.migrate ## Full first-time setup
	@echo "$(GREEN)$(BOLD)Setup complete.$(RESET) Run $(CYAN)make dev$(RESET) to start."

.PHONY: env
env: ## Copy .env.example to .env (no-op if exists)
	@test -f .env || (cp .env.example .env && echo "$(GREEN)Created .env from .env.example — edit credentials before starting.$(RESET)")
	@test -f .env && echo "$(YELLOW).env already exists, skipping.$(RESET)" || true

.PHONY: venv
venv: $(VENV)/pyvenv.cfg ## Create Python virtual environment

$(VENV)/pyvenv.cfg:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip

# ═════════════════════════════════════════════════════════════════════════════
# API — Python/FastAPI Backend
# ═════════════════════════════════════════════════════════════════════════════

.PHONY: api.deps
api.deps: venv ## Install Python dependencies (api + kb)
	$(RUN_PIP) install -r requirements.txt

.PHONY: api.dev
api.dev: ## Start API dev server with hot-reload
	$(RUN_PY) -m uvicorn api.main:create_app --factory \
		--host $(UVICORN_HOST) --port $(UVICORN_PORT) \
		--reload --reload-dir api

.PHONY: api.run
api.run: ## Start API server (production mode)
	$(RUN_PY) -m uvicorn api.main:create_app --factory \
		--host $(UVICORN_HOST) --port $(UVICORN_PORT) \
		--workers 4

.PHONY: api.lint
api.lint: ## Lint Python code with ruff
	$(RUN_PY) -m ruff check api/ taxkb/ tests/

.PHONY: api.format
api.format: ## Format Python code with ruff
	$(RUN_PY) -m ruff format api/ taxkb/ tests/
	$(RUN_PY) -m ruff check --fix api/ taxkb/ tests/

.PHONY: api.typecheck
api.typecheck: ## Type-check Python code with mypy
	$(RUN_PY) -m mypy api/ --ignore-missing-imports

# ═════════════════════════════════════════════════════════════════════════════
# FRONTEND — Next.js
# ═════════════════════════════════════════════════════════════════════════════

.PHONY: fe.deps
fe.deps: ## Install frontend dependencies
	cd $(FE_DIR) && $(NPM) install

.PHONY: fe.dev
fe.dev: ## Start frontend dev server
	cd $(FE_DIR) && $(NPM) run dev

.PHONY: fe.build
fe.build: ## Production build of frontend
	cd $(FE_DIR) && $(NPM) run build

.PHONY: fe.start
fe.start: ## Start frontend in production mode (requires fe.build)
	cd $(FE_DIR) && $(NPM) run start

.PHONY: fe.lint
fe.lint: ## Lint frontend code
	cd $(FE_DIR) && $(NPM) run lint

# ═════════════════════════════════════════════════════════════════════════════
# DATABASE — Docker + Migrations
# ═════════════════════════════════════════════════════════════════════════════

.PHONY: db.up
db.up: ## Start infrastructure containers (Neo4j + PostgreSQL)
	docker compose up -d

.PHONY: db.down
db.down: ## Stop infrastructure containers (keep data)
	docker compose down

.PHONY: db.destroy
db.destroy: ## Stop containers and delete volumes (DESTRUCTIVE)
	@echo "$(YELLOW)This will destroy all local database data.$(RESET)"
	docker compose down -v

.PHONY: db.ps
db.ps: ## Show container status
	docker compose ps

.PHONY: db.logs
db.logs: ## Tail infrastructure container logs
	docker compose logs -f --tail=50

.PHONY: db.migrate
db.migrate: ## Run Alembic migrations to head
	$(RUN_PY) -m alembic upgrade head

.PHONY: db.migration
db.migration: ## Create new migration (usage: make db.migration MSG="add foo table")
	$(RUN_PY) -m alembic revision --autogenerate -m "$(MSG)"

.PHONY: db.rollback
db.rollback: ## Rollback one migration
	$(RUN_PY) -m alembic downgrade -1

.PHONY: db.history
db.history: ## Show migration history
	$(RUN_PY) -m alembic history --verbose

.PHONY: db.current
db.current: ## Show current migration revision
	$(RUN_PY) -m alembic current

.PHONY: db.psql
db.psql: ## Open psql shell to local Postgres
	docker compose exec postgres psql -U $${POSTGRES_USER:-taxflow} -d $${POSTGRES_DB:-taxflow}

# ═════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — TaxKB
# ═════════════════════════════════════════════════════════════════════════════

.PHONY: kb.ingest
kb.ingest: ## Run full publication ingestion
	$(RUN_PY) taxkb/scripts/ingest_all_pubs.py

.PHONY: kb.dryrun
kb.dryrun: ## Dry-run tier 1 ingestion (safe preview)
	$(RUN_PY) taxkb/scripts/dryrun_ingest_tier1.py

# ═════════════════════════════════════════════════════════════════════════════
# TESTING
# ═════════════════════════════════════════════════════════════════════════════

.PHONY: test
test: ## Run unit tests (fast, no DB required)
	$(RUN_PY) -m pytest $(TEST_DIR) -v

.PHONY: test.unit
test.unit: ## Run unit tests explicitly
	$(RUN_PY) -m pytest $(TEST_DIR) -m unit -v

.PHONY: test.integration
test.integration: ## Run integration tests (requires running Postgres)
	$(RUN_PY) -m pytest $(TEST_DIR) -m integration -v

.PHONY: test.all
test.all: ## Run full test suite (unit + integration)
	$(RUN_PY) -m pytest $(TEST_DIR) -m "unit or integration" -v

.PHONY: test.cov
test.cov: ## Run tests with coverage report
	$(RUN_PY) -m pytest $(TEST_DIR) --cov=api --cov-report=term-missing --cov-report=html

.PHONY: test.watch
test.watch: ## Run tests in watch mode (requires pytest-watch)
	$(RUN_PY) -m pytest_watch -- $(TEST_DIR) -v

# ═════════════════════════════════════════════════════════════════════════════
# DEVELOPMENT — Compound targets
# ═════════════════════════════════════════════════════════════════════════════

.PHONY: dev
dev: ## Start full dev stack (infra + api + frontend)
	@echo "$(BOLD)Starting TaxFlow AI development stack...$(RESET)"
	$(MAKE) db.up
	@echo "$(GREEN)Infrastructure ready.$(RESET)"
	@echo "$(CYAN)Starting API on :$(UVICORN_PORT) and Frontend on :$(FE_PORT)...$(RESET)"
	@echo "$(YELLOW)Use Ctrl+C to stop. Run 'make db.down' separately to stop containers.$(RESET)"
	@trap 'kill 0' EXIT; \
		$(MAKE) api.dev & \
		$(MAKE) fe.dev & \
		wait

.PHONY: lint
lint: api.lint fe.lint ## Run all linters

.PHONY: format
format: api.format ## Format all code

# ═════════════════════════════════════════════════════════════════════════════
# BUILD — Production artifacts
# ═════════════════════════════════════════════════════════════════════════════

.PHONY: build
build: fe.build ## Build all production artifacts

# ═════════════════════════════════════════════════════════════════════════════
# CLEAN
# ═════════════════════════════════════════════════════════════════════════════

.PHONY: clean
clean: ## Remove build artifacts and caches
	rm -rf $(FE_DIR)/.next $(FE_DIR)/out
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf htmlcov .coverage

.PHONY: clean.all
clean.all: clean ## Remove everything (venv, node_modules, Docker volumes)
	rm -rf $(VENV)
	rm -rf $(FE_DIR)/node_modules
	$(MAKE) db.destroy
