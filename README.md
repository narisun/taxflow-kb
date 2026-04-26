# TaxFlow AI — CPA Tax Preparation Platform

**AI-powered tax preparation platform with a full calculation engine, document extraction, advisory system, and IRS knowledge base.**

TaxFlow AI provides CPAs with an end-to-end tax workflow: upload client documents, extract data (via Claude Vision or mock), compute federal tax returns with auditable line traces, generate advisory recommendations, produce filled IRS PDFs, and compare returns year-over-year — all backed by a RAG-powered IRS knowledge base.

---

## What It Does

| Capability | Description |
|-----------|-------------|
| **Document Upload & Extraction** | Upload PDF/image tax documents (W-2, 1099s, K-1, 1098). Extracted via Claude Vision API or mock extractor. Structured data stored for engine consumption. |
| **Tax Calculation Engine** | Full Form 1040 computation with 11 calculator classes (Schedules A/B/C/D/E/SE, Forms 8812/8959/8960/8995). Every value produces an auditable `LineTrace`. |
| **Validation** | 7 pluggable cross-form validation rules (S-Corp W-2 match, SSN format, MFJ spouse required, HSA match, duplicate SSN, HOH dependent, withholding check). |
| **Tax Advisory** | 12 strategy rules analyze the computed return and estimate savings using the taxpayer's marginal rate (HSA, 401k, Roth, charitable bunching, CTC, EITC, etc.). |
| **PDF Generation** | Fill official IRS PDF templates with computed values using pypdf. Merges only active forms (Form 1040 + relevant schedules). |
| **Year-over-Year Comparison** | Compare a client's current and prior year returns across 18 Form 1040 lines grouped by income, deductions, tax, and payments. |
| **IRS Knowledge Base** | 5-layer RAG pipeline: MeF business rules, form instructions, IRS publications with vector search, query agent, and evaluation framework. |
| **Multi-Tenant CPA Platform** | Auth0 JWT auth, RBAC (4 roles), per-organization data isolation, client management, chat with AI synthesis. |

---

## Quick Start

```bash
# 1. Clone and set up everything (venv, deps, Docker, migrations)
make setup

# 2. Edit .env with your API keys
$EDITOR .env

# 3. Start the full stack (API + Frontend + Docker infra)
make dev
```

Open [http://localhost:3000](http://localhost:3000). In dev mode, the API auto-seeds sample data.

### Make Targets

Run `make help` for the full list. Key targets:

| Target | Description |
|--------|-------------|
| `make setup` | One-command bootstrap: `.env`, venv, deps, Docker, migrations |
| `make dev` | Start full stack (infra + API with hot-reload + frontend) |
| `make test` | Run unit tests (fast, no DB required) |
| `make test.cov` | Run tests with coverage report |
| `make test.integration` | Run integration tests (requires Postgres) |
| `make build` | Production build (frontend) |
| `make lint` | Run all linters (Python + frontend) |
| `make format` | Format Python code with ruff |
| `make clean` | Remove build artifacts and caches |

#### Subsystem Targets

Targets are namespaced by subsystem using dot notation:

| Prefix | Examples |
|--------|----------|
| `api.*` | `api.dev`, `api.run`, `api.deps`, `api.lint`, `api.format`, `api.typecheck` |
| `fe.*` | `fe.dev`, `fe.build`, `fe.start`, `fe.deps`, `fe.lint` |
| `db.*` | `db.up`, `db.down`, `db.destroy`, `db.migrate`, `db.migration MSG="..."`, `db.rollback`, `db.psql`, `db.logs` |
| `kb.*` | `kb.ingest`, `kb.dryrun` |
| `test.*` | `test.unit`, `test.integration`, `test.all`, `test.cov`, `test.watch` |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Frontend** | Next.js 16, React 19, TypeScript 5, Tailwind CSS 4 |
| **Backend API** | FastAPI 0.115+, Uvicorn, SQLAlchemy 2 (async), Pydantic v2 |
| **Tax Engine** | Pure Python (Decimal arithmetic), OOP with DI, year-agnostic constants registry |
| **Document Extraction** | Claude Vision API (Anthropic SDK), form-specific prompts, mock extractor for dev |
| **PDF Generation** | pypdf 4.0+ (AcroForm field filling, form merging) |
| **Authentication** | Auth0 (RS256 JWT), RBAC with 4 roles |
| **App Database** | PostgreSQL 16 (async via asyncpg) — multi-tenant |
| **Knowledge Graph** | Neo4j 5.18 Community |
| **Vector Store** | PostgreSQL 16 + pgvector (IVFFlat ANN, 1536-dim) |
| **Embeddings** | OpenAI text-embedding-3-large (1536 dimensions) |
| **LLM Synthesis** | GPT-4o-mini (answers), GPT-4o (judge/evaluation) |
| **Testing** | pytest + pytest-asyncio + pytest-cov + pytest-timeout (in-memory SQLite, 800+ unit tests; optional Postgres-backed integration suite) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend  (Next.js 16 · React 19 · Tailwind CSS 4)            │
│  http://localhost:3000                                           │
│  Auth0 SPA login · role-aware UI · advisory panel               │
└──────────────────────┬──────────────────────────────────────────┘
                       │ REST API (Bearer JWT)
┌──────────────────────▼──────────────────────────────────────────┐
│  Backend API  (FastAPI · SQLAlchemy 2 async · Pydantic v2)      │
│  http://localhost:8000                                           │
│  Routers: auth · health · clients · chat · conversations ·      │
│           documents · tax_returns · dependents · research        │
└──────┬───────────┬──────────────┬───────────────────────────────┘
       │           │              │
┌──────▼──────┐ ┌──▼────────┐ ┌──▼──────────────────────────────┐
│ PostgreSQL  │ │ Tax Engine│ │ Knowledge Base (taxkb/)          │
│ (multi-     │ │ Models    │ │ PostgreSQL + pgvector · Neo4j   │
│  tenant     │ │ Constants │ │ OpenAI embeddings · Hybrid      │
│  app data)  │ │ Calcs     │ │ Agent: retrieve → rerank →     │
│             │ │ Advisory  │ │        synthesize               │
│             │ │ PDF Gen   │ │                                 │
│             │ │ Compare   │ │                                 │
└─────────────┘ └───────────┘ └─────────────────────────────────┘
```

---

## Project Structure

```
taxflow-kb/
├── Makefile                           # Build, dev, test, deploy targets (run: make help)
├── api/                               # FastAPI backend application
│   ├── main.py                        # App factory (CORS, lifespan, routers)
│   ├── config.py                      # Settings (pydantic-settings) — single source of env vars
│   ├── dependencies.py                # FastAPI DI providers
│   ├── auth/                          # Auth0 JWT verification, RBAC, user provisioning
│   ├── db/                            # Database layer (ORM models, engine, migrations)
│   ├── models/                        # Pydantic request/response schemas
│   ├── routers/                       # HTTP handlers (auth, clients, chat, documents, etc.)
│   ├── services/                      # Business logic (chat, OCR, PII, tax)
│   ├── agent/                         # Agentic layer (research tools, sessions)
│   └── tax_engine/                    # Pure tax calculation engine (no FastAPI deps)
│       ├── models/                    # Domain models (people, income, deductions, credits)
│       ├── constants/                 # Year-versioned tax parameters (TY2024, TY2025)
│       ├── calculators/               # One class per IRS form/schedule
│       ├── services/                  # Orchestrators (income, deductions, credits, liability)
│       ├── validation/                # Pluggable cross-form validation rules
│       ├── advisory/                  # Tax strategy recommendations
│       ├── comparison/                # Year-over-year comparison engine
│       ├── pdf/                       # IRS PDF generation (templates + field maps)
│       ├── assembler.py               # Documents + manual overrides → TaxReturn
│       └── dependencies.py            # FastAPI Depends providers
├── frontend/                          # Next.js 16 web application
│   ├── app/                           # App Router (layout, page, providers)
│   ├── components/                    # React components (ui, chat, clients, returns, etc.)
│   └── lib/                           # API client, utils, hooks
├── taxkb/                             # IRS Knowledge Base — RAG subsystem
│   ├── __main__.py                    # CLI entry point (python -m taxkb)
│   ├── config.py                      # KB settings (pydantic-settings)
│   ├── models.py                      # Domain models (MeFRule, ASTNode, etc.)
│   ├── protocols.py                   # DI interfaces (Retriever, EmbeddingClient, etc.)
│   ├── factories.py                   # Dependency injection wiring
│   ├── rules/                         # Layer 1: MeF CSV parser, AST parser, Neo4j/PG ingest
│   ├── instructions/                  # Layer 2: IRS HTML parser, Neo4j/PG ingest
│   ├── publications/                  # Layer 3: PDF parser, embeddings, pgvector, search
│   ├── agent/                         # Layer 4: retriever, synthesizer, classifier, reranker
│   ├── evaluation/                    # Layer 5: gold-set generation + retrieval/generation scorers
│   ├── adapters/                      # Concrete implementations (OpenAI, PG, Neo4j)
│   ├── cli/                           # CLI commands for ingestion/validation/search
│   ├── eval/                          # End-to-end eval harness
│   ├── schema/                        # PostgreSQL / Neo4j DDL
│   └── scripts/                       # Batch ingestion, diagnostics, utilities
├── tests/                             # pytest suite — 800+ unit tests
│   ├── conftest.py                    # Root config: loads tests/.env.test before imports
│   ├── .env.test                      # Deterministic test environment (mock secrets)
│   ├── fixtures/                      # Test data (sample W-2 PDF, etc.)
│   ├── api/                           # API + tax engine unit tests (in-memory SQLite)
│   ├── taxkb/                         # Knowledge base subsystem tests
│   └── integration/                   # Postgres-backed tests (pytest -m integration)
├── alembic/                           # Database migration scripts
├── data/                              # IRS PDFs, CSVs, evaluation datasets
├── docker-compose.yml                 # Neo4j 5.18 + PostgreSQL 16 (pgvector)
├── requirements.txt                   # All Python dependencies (api + kb + dev)
├── pyproject.toml                     # Package config, pytest settings, coverage
└── .env.example                       # Environment variable template (145 vars)
```

---

## REST API Endpoints

All endpoints except `/health` require a valid Auth0 Bearer token (or dev mode).

### Authentication

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/auth/me` | JWT | Current user, organization, and permissions |

### Clients

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/clients?page=1&page_size=50` | JWT | List clients (tenant-scoped, paginated) |
| POST | `/api/clients` | JWT | Create a client |
| GET | `/api/clients/{id}` | JWT | Get client details |
| PATCH | `/api/clients/{id}` | JWT | Update client fields |
| DELETE | `/api/clients/{id}` | admin, supervisor | Delete a client |

### Documents

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/clients/{id}/documents` | JWT | List documents (paginated) |
| POST | `/api/clients/{id}/documents` | JWT | Upload document (multipart, max 20 MB) |
| GET | `/api/documents/{id}` | JWT | Get document details |
| PATCH | `/api/documents/{id}/approve` | admin, supervisor, preparer | Approve a document |
| GET | `/api/documents/{id}/fields` | JWT | Get extracted fields with display labels |

### Tax Returns

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| POST | `/api/clients/{id}/returns/draft` | admin, supervisor, preparer | Compute tax return via engine |
| GET | `/api/clients/{id}/returns/draft` | JWT | Retrieve computed draft |
| POST | `/api/clients/{id}/returns/entries` | admin, supervisor, preparer | Add/update manual data entry |
| GET | `/api/clients/{id}/returns/entries` | JWT | List manual entries for client |
| DELETE | `/api/clients/{id}/returns/entries/{eid}` | admin, supervisor, preparer | Delete a manual entry |
| GET | `/api/clients/{id}/returns/advisory` | JWT | Get advisory recommendations |
| GET | `/api/clients/{id}/returns/pdf` | JWT | Download filled Form 1040 PDF |
| GET | `/api/clients/{id}/returns/compare?prior_year=N` | JWT | Year-over-year comparison |

### Chat & Conversations

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/clients/{id}/chat` | JWT | Get chat history (paginated) |
| POST | `/api/clients/{id}/chat` | JWT | Send message, receive AI response |

### Research

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| POST | `/api/research/query` | JWT | Query the IRS knowledge base |

### System

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/health` | None | Readiness check |

---

## Database & Migrations

### Schema versioning — Alembic

All schema changes flow through [Alembic](https://alembic.sqlalchemy.org/).
The migration history lives in `alembic/versions/`.

```bash
# Common workflow using make targets:
make db.migration MSG="add foo table"   # Generate migration from ORM diff
make db.migrate                         # Apply migrations to head
make db.rollback                        # Roll back one step
make db.current                         # Show current revision
make db.history                         # Full migration history
make db.psql                            # Open psql shell
```

`api/db/engine.py:init_db()` runs `alembic upgrade head` programmatically at
FastAPI startup, so deployments stay in lock-step with the schema.

### Identity policy — UUIDv7 everywhere

Every domain entity uses **UUIDv7** as its primary key, stored as `String(36)`.
Generation is centralized in `api/db/ids.py`. UUIDv7 provides time-ordered,
globally unique IDs with B-tree locality on inserts, no PK enumeration, and
safe cross-environment merges.

---

## Tax Engine Overview

The tax engine is a pure-Python computation pipeline with no external tax library dependencies. All calculations follow IRS instructions and IRC citations.

### Computation Pipeline

```
TaxReturn (input data)
    |
Phase 1: Income (Schedule B/C/D/E)
    |
Phase 2: SE Tax + AGI Adjustments (HSA, IRA, student loan, SE deduction)
    |
Phase 3: Deductions (standard vs itemized, QBI)
    |
Phase 4: Tax Liability (brackets, Additional Medicare, NIIT)
    |
Phase 5: Credits (CTC/ACTC)
    |
Phase 6: Form 1040 Assembly (lines 1-37, refund/owed)
    |
TaxResult (with LineTrace audit trail)
```

### Key Design Decisions

- **LineTrace audit trail** — every computed value records form, line, label, value, formula, inputs, constants used, and IRS citation
- **Year-agnostic constants** — `TaxYearConstants` registry keyed by year; adding TY2026 is just a new data file
- **Constructor injection** — calculators receive `TaxYearConstants` via constructor for testability
- **Manual + automatic assembly** — `DocumentAssembler` merges OCR-extracted document data with CPA manual overrides
- **Pluggable validation** — add rules by implementing `ValidationRule` ABC
- **Pluggable advisory** — add strategies by implementing `AdvisoryRule` ABC

---

## Configuration

The application uses strict `pydantic-settings` — every variable is required,
no defaults. It **refuses to start** if any environment variable is missing.

Two independent Settings classes read the same `.env`:

| Component | Settings class | File |
|---|---|---|
| FastAPI backend | `api.config.Settings` | `api/config.py` |
| Knowledge base | `taxkb.config.Settings` | `taxkb/config.py` |

See `.env.example` for the full annotated variable list. Key variables:

| Variable | Purpose |
|---|---|
| `APP_ENV` | `development` / `staging` / `production` / `test` |
| `APP_DATABASE_URL` | Async SQLAlchemy URL for FastAPI |
| `ANTHROPIC_API_KEY` | Chat + document extraction (Claude) |
| `OPENAI_API_KEY` | KB embeddings + synthesis |
| `PII_ENCRYPTION_KEY` | Fernet key for PII encryption |
| `AUTH0_DOMAIN` / `AUTH0_API_AUDIENCE` / `AUTH0_CLIENT_ID` | Auth0 tenant |
| `OCR_EXTRACTOR` | `cascade` / `claude` / `mock` |

### Generating a production PII key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## CLI Reference

The KB CLI is invoked as a Python module:

```bash
python -m taxkb <command>
```

```
# Layer 1 — MeF Business Rules
python -m taxkb ingest               --csv FILE [--neo4j-uri URI] [--pg-dsn DSN]
python -m taxkb validate             --csv FILE --step {v1.1 | v1.3 | all}

# Layer 2 — Form Instructions
python -m taxkb ingest-instructions  --html FILE --form-type FORM --tax-year YEAR
python -m taxkb validate-instructions --html FILE --form-type FORM --tax-year YEAR

# Layer 3 — Publications
python -m taxkb ingest-publications  --pdf FILE --pub-number NUM --tax-year YEAR --pg-dsn DSN
python -m taxkb search               QUERY --pg-dsn DSN [--top-k N] [--pub-number NUM]

# Layer 4 — Agent
python -m taxkb ask                  QUESTION
python -m taxkb validate-agent

# Layer 5 — Evaluation
python -m taxkb evaluate-retrieval
python -m taxkb evaluate-generation
```

---

## Auth0 / RBAC

| Role | Permissions |
|------|-------------|
| **admin** | Full access — manage users, all clients, file returns, approve docs |
| **supervisor** | All clients, file returns, approve docs (no user management) |
| **preparer** | File returns, approve docs (own clients only) |
| **analyst** | Read-only access to own clients |

In dev mode (`APP_ENV != production`), a dev admin user is auto-created — no Auth0 setup needed.

---

## Architecture: Dependency Injection & Service Layer

The backend follows a strict router -> service -> repository/engine layering. All
process-wide collaborators are wired through FastAPI `Depends`. Tests swap
them via `app.dependency_overrides`.

**Rules of the road:**

1. **No `os.getenv()` in library code.** All env vars are typed fields on
   `Settings` (`api/config.py`).
2. **No module-level clients or caches in routers.** Collaborators are acquired
   via `Depends(...)` providers defined in `api/dependencies.py`.
3. **Routers don't hold business logic.** If a handler does more than "parse,
   call service, serialize, return," push the logic into a service.
4. **Services take collaborators via constructor.** The constructor is the seam
   for tests.
5. **Catch exceptions where you can act on them.** Blanket
   `except Exception: pass` is banned.

---

## Database Tables

### Application Database (multi-tenant via org_id)

| Table | Purpose |
|-------|---------|
| `organizations` | Tenant root — each CPA firm |
| `users` | Auth0-linked users with RBAC roles |
| `clients` | Tax preparation clients per firm |
| `documents` | Uploaded documents with structured extraction data |
| `chat_messages` | AI chat history per client |
| `tax_return_drafts` | Persisted computed tax return drafts |
| `manual_entries` | CPA manual data overrides (field-level) |

### Knowledge Base (PostgreSQL + pgvector + Neo4j)

| Store | Purpose |
|-------|---------|
| `mef_rules` (PG) | Layer 1 — parsed MeF business rules |
| `form_instructions` (PG) | Layer 2 — form instruction sections |
| `publication_chunks` (PG + pgvector) | Layer 3 — chunked text with 1536-dim embeddings |
| Neo4j graph | Rule -> FormField -> InstructionSection relationships |

---

## Testing

```bash
make test                 # Fast unit tests (800+, in-memory SQLite)
make test.cov             # With coverage report
make test.integration     # Postgres-backed integration suite
make test.all             # Unit + integration
make test.watch           # Watch mode (requires pytest-watch)
```

`pytest-timeout` is configured with a 60s per-test ceiling. Tests use a
separate `tests/.env.test` with deterministic dummy values, loaded by the
root `conftest.py` before any application imports.

---

## Development Notes

- **Decimal arithmetic** — all monetary calculations use `Decimal` for precision.
- **Idempotent ingestion** — all KB writes use MERGE/upsert semantics.
- **File upload validation** — 20 MB max, PDF/PNG/JPEG/TIFF only, filenames sanitized.
- **JWKS caching** — Auth0 keys cached with 1-hour TTL for key rotation.
- **PII encryption** — Fernet symmetric encryption; plaintext `extracted_data` is SSN-masked before storage.
- **Constructor-injected services** — all services take collaborators in the constructor for testability.
- **Protocol-driven extractors** — OCR extractors implement the `OCRExtractor` Protocol; strategy selected by `OCRExtractorFactory`.

### Tear down

```bash
make db.down              # Stop containers (keep data)
make db.destroy           # Stop containers and delete volumes
make clean                # Remove build artifacts and caches
make clean.all            # Remove everything (venv, node_modules, volumes)
```
