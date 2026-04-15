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
| **Testing** | pytest + pytest-asyncio (in-memory SQLite, 245+ tests, no external deps) |

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
│  Routers: auth · health · clients · chat · documents ·          │
│           tax_returns (draft, advisory, pdf, compare, entries)   │
└──────┬───────────┬──────────────┬───────────────────────────────┘
       │           │              │
┌──────▼──────┐ ┌──▼────────┐ ┌──▼──────────────────────────────┐
│ PostgreSQL  │ │ Tax Engine│ │ Knowledge Base (tax_brain)      │
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
├── api/                           # FastAPI backend application
│   ├── main.py                    # App factory (CORS, lifespan, routers)
│   ├── auth/                      # Auth0 JWT verification, RBAC, user provisioning
│   │   ├── config.py              # Auth0 env config (APP_ENV, domain, audience)
│   │   ├── dependencies.py        # get_current_user, require_role dependencies
│   │   ├── models.py              # Organization, User ORM models, ROLE_PERMISSIONS
│   │   └── token.py               # RS256 JWT verification with JWKS TTL cache
│   ├── db/                        # Database layer
│   │   ├── base.py                # DeclarativeBase + TenantMixin (org_id, timestamps)
│   │   ├── models.py              # Client, Document, ChatMessage, TaxReturnDraft, ManualEntry ORM
│   │   ├── engine.py              # Async engine, session factory, init_db
│   │   └── seed.py                # Dev seed data (org, user, sample clients)
│   ├── models/                    # Pydantic request/response schemas
│   │   ├── enums.py               # Shared Literal types (FilingStatus, FormType, etc.)
│   │   ├── client.py              # Client CRUD schemas
│   │   ├── chat.py                # Chat message schemas
│   │   ├── document.py            # Document, ExtractedField, ExtractionResult schemas
│   │   └── tax_return.py          # ReturnLine, TaxReturnDraft response schemas
│   ├── routers/                   # FastAPI route handlers
│   │   ├── auth.py                # GET /api/auth/me
│   │   ├── health.py              # GET /health
│   │   ├── clients.py             # Client CRUD endpoints
│   │   ├── chat.py                # Chat history + AI synthesis
│   │   ├── documents.py           # Upload, list, approve, fields (with DI extractor)
│   │   ├── tax_returns.py         # Draft, advisory, PDF, compare, manual entries
│   │   └── _helpers.py            # Shared get_client_or_404 helper
│   ├── services/ocr/              # Document extraction services
│   │   ├── protocol.py            # OCRExtractor protocol definition
│   │   ├── mock_extractor.py      # Mock extractor (structured format, dev/test)
│   │   ├── claude_extractor.py    # Claude Vision API extractor (production)
│   │   ├── prompts.py             # 7 form-specific extraction prompts + fallback
│   │   └── field_mapping.py       # Structured key → display label mapping
│   └── tax_engine/                # Tax calculation engine (Phase 1-3)
│       ├── models/                # Pydantic domain models
│       │   ├── people.py          # Person, Dependent, Address (SSN/zip validation)
│       │   ├── income.py          # W2, 1099-INT/DIV/B/NEC/R, SSA-1099, ScheduleC, K-1
│       │   ├── deductions.py      # ItemizedDeductions, HSA, IRA, StudentLoan, RentalProperty
│       │   ├── credits.py         # DependentCare, Tuition1098T, EnergyImprovement, EstimatedPayment
│       │   └── tax_return.py      # TaxReturn (master container), LineTrace, FormResult, TaxResult
│       ├── constants/             # Year-versioned tax parameters
│       │   ├── registry.py        # TaxYearConstants dataclass + registry (get_constants, register)
│       │   ├── ty2024.py          # TY2024 IRS values (brackets, limits, thresholds)
│       │   └── ty2025.py          # TY2025 IRS values (OBBB changes: CTC, SALT, deductions)
│       ├── calculators/           # One class per IRS form/schedule
│       │   ├── base.py            # BaseCalculator ABC with LineTrace support
│       │   ├── schedule_b.py      # Interest & dividends
│       │   ├── schedule_c.py      # Self-employment income (net profit)
│       │   ├── schedule_d.py      # Capital gains/losses (with loss limit)
│       │   ├── schedule_e.py      # Rental real estate & K-1 passthrough
│       │   ├── schedule_a.py      # Itemized deductions (SALT cap, medical floor)
│       │   ├── schedule_se.py     # Self-employment tax (SS wage cap)
│       │   ├── form_8812.py       # Child Tax Credit + ACTC (phase-out)
│       │   ├── form_8959.py       # Additional Medicare Tax (0.9%)
│       │   ├── form_8960.py       # Net Investment Income Tax (3.8%)
│       │   ├── form_8995.py       # QBI deduction (§199A, SSTB phase-out)
│       │   └── form_1040.py       # Form 1040 final assembly (lines 1–37)
│       ├── services/              # Domain orchestrators
│       │   ├── income.py          # IncomeService (Schedule B/C/D/E)
│       │   ├── deductions.py      # DeductionService (adjustments, standard vs itemized, QBI)
│       │   ├── credits.py         # CreditService (CTC/ACTC)
│       │   ├── liability.py       # LiabilityService (brackets, SE tax, surtaxes)
│       │   └── engine.py          # TaxCalculationEngine (top-level orchestrator)
│       ├── validation/            # Pluggable tax return validation
│       │   ├── base.py            # ValidationRule ABC, ValidationResult
│       │   ├── rules.py           # 7 concrete rules (V001–V008)
│       │   └── engine.py          # ValidationEngine (run all rules, sort by severity)
│       ├── advisory/              # Tax strategy recommendations
│       │   ├── models.py          # AdvisoryItem (matches frontend interface)
│       │   ├── base.py            # AdvisoryRule ABC + marginal_rate helper
│       │   ├── rules.py           # 12 rules (HSA, 401k, Roth, charity, SALT, CTC, etc.)
│       │   └── engine.py          # AdvisoryEngine (run rules, sort by savings)
│       ├── comparison/            # Year-over-year comparison
│       │   ├── models.py          # ComparisonRow, ComparisonSection, ComparisonReport
│       │   └── engine.py          # ComparisonEngine (18-line diff across 4 sections)
│       ├── pdf/                   # IRS PDF form generation
│       │   ├── templates/         # Blank IRS PDF files (TY2024: f1040, schedules, forms)
│       │   ├── field_maps.py      # Per-form AcroForm field mapping functions
│       │   └── generator.py       # PDFGenerator (fill templates, merge active forms)
│       ├── assembler.py           # DocumentAssembler (documents + manual overrides → TaxReturn)
│       └── dependencies.py        # FastAPI Depends providers for engine, validator, assembler
├── frontend/                      # Next.js 16 web application
│   ├── app/                       # App Router (layout.tsx, page.tsx, providers.tsx)
│   ├── components/                # React components
│   │   ├── ui/                    # Base: button, card, modal, input, badge, tabs
│   │   ├── chat/                  # Chat: message-list, bubble, input, typing indicator
│   │   ├── layout/                # Layout: top-bar, sidebar, chat-panel, work-panel
│   │   ├── clients/               # Client: intake-modal
│   │   ├── forms/                 # Tax forms: W-2, 1099-INT, generic, renderer
│   │   ├── returns/               # Return preview + advisory panel
│   │   ├── documents/             # Document card, viewer modal
│   │   ├── dashboard/             # Dashboard overview
│   │   ├── settings/              # User/org settings
│   │   └── research/              # Tax research/knowledge base UI
│   └── lib/                       # api-client.ts, utils.ts, hooks
├── tax_brain/                     # Core Python knowledge base library
│   ├── models.py                  # Pydantic v2 models (MeFRule, ASTNode, etc.)
│   ├── protocols.py               # DI interfaces (Retriever, EmbeddingClient, etc.)
│   ├── config.py                  # Centralized settings (Pydantic BaseSettings)
│   ├── factories.py               # Dependency injection wiring
│   ├── rules/                     # Layer 1: MeF CSV parser, AST parser, Neo4j/PG ingest
│   ├── instructions/              # Layer 2: IRS HTML parser, Neo4j/PG ingest
│   ├── publications/              # Layer 3: PDF parser, embeddings, pgvector, search
│   ├── agent/                     # Layer 4: retriever, synthesizer, classifier, reranker
│   ├── evaluation/                # Layer 5: gold set generation, eval metrics
│   └── adapters/                  # Concrete implementations (OpenAI, PG, Neo4j)
├── ustaxes-master/                # Reference tax codebase (read-only, not modified)
│   ├── engine/                    # Python tax calculator (5,250-line monolith, 40+ dataclasses)
│   ├── web/                       # Next.js frontend (reference only)
│   ├── ts-forms/                  # TypeScript IRS form definitions + PDF templates
│   ├── pipeline/                  # Document extraction pipeline (Claude Vision)
│   ├── cpax/                      # CPA AI research assistant (QBI/§199A)
│   ├── tests/                     # Reference test suite
│   └── docs/                      # Methodology, developer guides
├── tests/                         # pytest test suite (245+ tests, all in-memory)
│   └── api/                       # API + tax engine tests
│       ├── conftest.py            # Test fixtures (in-memory SQLite, AsyncClient)
│       ├── test_clients.py        # Client CRUD tests
│       ├── test_documents.py      # Document upload, extraction, approval tests
│       ├── test_tax_returns.py    # Draft generation, manual entries tests
│       ├── test_advisory_endpoint.py    # Advisory API tests
│       ├── test_pdf_endpoint.py         # PDF download tests
│       ├── test_comparison_endpoint.py  # Year-over-year comparison tests
│       ├── test_extraction_integration.py # End-to-end extraction pipeline tests
│       ├── tax_engine/            # Tax engine unit tests
│       │   ├── test_models.py     # Domain model validation tests
│       │   ├── test_constants.py  # Tax year constants tests
│       │   ├── test_engine.py     # End-to-end TaxReturn → TaxResult tests
│       │   ├── test_validation.py # Validation rule tests
│       │   ├── test_advisory_rules.py   # 12 advisory rule tests
│       │   ├── test_advisory_engine.py  # Marginal rate + engine tests
│       │   ├── test_comparison_engine.py # Comparison engine tests
│       │   ├── test_pdf_field_maps.py   # PDF field mapping tests
│       │   ├── test_pdf_generator.py    # PDF generator tests
│       │   ├── test_assembler.py        # Document assembler tests
│       │   └── calculators/       # Per-calculator unit tests
│       │       ├── test_schedule_b.py through test_schedule_se.py
│       │       └── test_form_8812.py through test_form_8995.py
│       └── services/ocr/          # Extraction service tests
│           ├── test_prompts.py    # Form prompt tests
│           ├── test_field_mapping.py    # Display label tests
│           ├── test_mock_extractor.py   # Mock extractor tests
│           └── test_claude_extractor.py # Claude extractor tests (mocked API)
├── docs/superpowers/              # Design specs and implementation plans
│   ├── specs/                     # Approved design specifications
│   └── plans/                     # Implementation plans with TDD steps
├── cli/                           # CLI command modules
├── data/                          # Sample data and IRS PDFs
├── schema/                        # SQL and Cypher schema files
├── docker-compose.yml             # Neo4j 5.18 + PostgreSQL 16 (pgvector)
├── requirements.txt               # Core + KB dependencies
├── requirements-api.txt           # API dependencies (FastAPI, SQLAlchemy, anthropic, pypdf)
└── .env.example                   # Environment variable template
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

### Chat

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/clients/{id}/chat` | JWT | Get chat history (paginated) |
| POST | `/api/clients/{id}/chat` | JWT | Send message, receive AI response |

### System

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/health` | None | Readiness check |

---

## Tax Engine Overview

The tax engine is a pure-Python computation pipeline with no external tax library dependencies. All calculations follow IRS instructions and IRC citations.

### Computation Pipeline

```
TaxReturn (input data)
    ↓
Phase 1: Income (Schedule B/C/D/E)
    ↓
Phase 2: SE Tax + AGI Adjustments (HSA, IRA, student loan, SE deduction)
    ↓
Phase 3: Deductions (standard vs itemized, QBI)
    ↓
Phase 4: Tax Liability (brackets, Additional Medicare, NIIT)
    ↓
Phase 5: Credits (CTC/ACTC)
    ↓
Phase 6: Form 1040 Assembly (lines 1–37, refund/owed)
    ↓
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

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_ENV` | `development` | Set to `production` to disable dev auth bypass |
| `APP_DATABASE_URL` | `postgresql+asyncpg://...` | Async PostgreSQL for app tables |
| `OCR_EXTRACTOR` | `mock` | `mock` (dev) or `claude` (production) |
| `ANTHROPIC_API_KEY` | — | Required when `OCR_EXTRACTOR=claude` |
| `AUTH0_DOMAIN` | — | Auth0 tenant domain |
| `AUTH0_API_AUDIENCE` | — | Auth0 API identifier |
| `OPENAI_API_KEY` | — | Required for KB embeddings and synthesis |
| `PG_DSN` | `postgresql://...` | PostgreSQL for knowledge base |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection |

See `.env.example` for the full list.

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-api.txt
cd frontend && npm install && cd ..
```

### 2. Start databases

```bash
docker compose up -d
```

### 3. Run the application

```bash
# Terminal 1 — Backend API
uvicorn api.main:create_app --factory --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000). In dev mode, the API auto-seeds sample data.

### 4. Run tests

```bash
pytest tests/ -v    # 245+ tests, all in-memory, no external deps
```

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
| Neo4j graph | Rule → FormField → InstructionSection relationships |

---

## Knowledge Base Ingestion

See the [CLI Reference](#cli-reference) section below for detailed commands to ingest MeF rules, form instructions, and IRS publications.

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

## CLI Reference

```
# ── Layer 1 — MeF Business Rules ─────────────────────────────────────────────
python cli.py ingest               --csv FILE [--neo4j-uri URI] [--pg-dsn DSN]
python cli.py validate             --csv FILE --step {v1.1 | v1.3 | all}

# ── Layer 2 — Form Instructions ──────────────────────────────────────────────
python cli.py ingest-instructions  --html FILE --form-type FORM --tax-year YEAR
python cli.py validate-instructions --html FILE --form-type FORM --tax-year YEAR

# ── Layer 3 — Publications ───────────────────────────────────────────────────
python cli.py ingest-publications  --pdf FILE --pub-number NUM --tax-year YEAR --pg-dsn DSN
python cli.py search               QUERY --pg-dsn DSN [--top-k N] [--pub-number NUM]

# ── Layer 4 — Agent ──────────────────────────────────────────────────────────
python cli.py ask                  QUESTION
python cli.py validate-agent

# ── Layer 5 — Evaluation ─────────────────────────────────────────────────────
python cli.py evaluate-retrieval
python cli.py evaluate-generation
```

---

## Development Notes

- **245+ tests** — all run in-memory with no databases or API keys required.
- **Protocol-driven DI** — all external dependencies injected via Python Protocols.
- **Multi-tenant isolation** — every query scoped by `org_id`.
- **Decimal arithmetic** — all monetary calculations use `Decimal` for precision.
- **Idempotent ingestion** — all KB writes use MERGE/upsert semantics.
- **File upload validation** — 20 MB max, PDF/PNG/JPEG/TIFF only, filenames sanitized.
- **JWKS caching** — Auth0 keys cached with 1-hour TTL for key rotation.

### Tear down

```bash
docker compose down -v    # removes containers and volumes
```
