# TaxFlow AI — CPA Tax Preparation Platform

**AI-powered IRS knowledge base and CPA-facing platform with RAG agent, fullstack web UI, and 5-layer knowledge pipeline.**

TaxFlow AI ingests IRS business rules, form instructions, and publications into a queryable knowledge base. When a CPA asks a tax question, the retrieval-augmented agent synthesizes an answer grounded in authoritative IRS sources.

| Layer | Source | Store | Purpose |
|-------|--------|-------|---------|
| **1 — MeF Business Rules** | IRS MeF CSV | Neo4j + PostgreSQL | Machine-readable tax rules parsed into ASTs |
| **2 — Form Instructions** | IRS HTML (irs.gov) | Neo4j + PostgreSQL | Plain-English line-by-line form explanations |
| **3 — Publications** | IRS Publication PDFs | PostgreSQL + pgvector | Semantic search via embeddings (8 publications) |
| **4 — Query Agent** | User questions | In-memory | Retrieval + synthesis pipeline (hybrid search → rerank → synthesize) |
| **5 — Evaluation** | Gold set Q&A | JSON files | Quality gates, retrieval/generation evaluation |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Frontend** | Next.js 16, React 19, TypeScript 5, Tailwind CSS 4 |
| **Backend API** | FastAPI 0.115+, Uvicorn, SQLAlchemy 2 (async), Pydantic v2 |
| **Authentication** | Auth0 (RS256 JWT), RBAC with 4 roles |
| **App Database** | PostgreSQL 16 (async via asyncpg) — multi-tenant |
| **Knowledge Graph** | Neo4j 5.18 Community |
| **Vector Store** | PostgreSQL 16 + pgvector (IVFFlat ANN, 1536-dim) |
| **Full-Text Search** | PostgreSQL GIN/tsvector (BM25 hybrid search) |
| **Embeddings** | OpenAI text-embedding-3-large (1536 dimensions) |
| **LLM Synthesis** | GPT-4o-mini (answers), GPT-4o (judge/evaluation) |
| **PDF Parsing** | pdfplumber (paragraph-aware chunking) |
| **Token Counting** | tiktoken (cl100k_base) |
| **Testing** | pytest + pytest-asyncio (in-memory SQLite, no external deps) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend  (Next.js 16 · React 19 · Tailwind CSS 4)        │
│  http://localhost:3000                                       │
│  Auth0 SPA login · role-aware UI                            │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST API (Bearer JWT)
┌──────────────────────▼──────────────────────────────────────┐
│  Backend API  (FastAPI · SQLAlchemy 2 async · Pydantic v2)  │
│  http://localhost:8000                                       │
│  Auth0 RS256 JWT verification · RBAC (4 roles)              │
│  Routers: auth · health · clients · chat · documents ·      │
│           tax_returns                                        │
└──────┬───────────────┬──────────────────────────────────────┘
       │               │
┌──────▼───────┐ ┌─────▼─────────────────────────────────────┐
│  PostgreSQL  │ │  Knowledge Base (tax_brain)                │
│  (multi-     │ │  PostgreSQL 16 + pgvector · Neo4j 5.18    │
│   tenant     │ │  OpenAI embeddings · Hybrid search         │
│   app data)  │ │  Agent: retrieve → rerank → synthesize     │
└──────────────┘ └────────────────────────────────────────────┘
```

---

## Services

| Service | Port | Purpose |
|---------|------|---------|
| **Frontend** (Next.js dev server) | 3000 | CPA-facing web application |
| **Backend API** (Uvicorn/FastAPI) | 8000 | REST API, auth, business logic |
| **PostgreSQL** (Docker: `taxflow-postgres`) | 5432 | App database + KB vector store |
| **Neo4j** (Docker: `taxflow-neo4j`) | 7474 (browser), 7687 (Bolt) | Knowledge graph for rules/instructions |

---

## Database Tables

### Application Database (PostgreSQL — async via SQLAlchemy)

All data tables use multi-tenant isolation via `org_id` foreign key.

| Table | Key Columns | Purpose |
|-------|-------------|---------|
| `organizations` | id, name, slug, plan, is_active | Tenant root — each CPA firm is an organization |
| `users` | id, org_id, auth0_sub, email, role | Auth0-linked users with RBAC roles |
| `clients` | id, org_id, created_by, name, filing_status, tax_year, workflow_step | Tax preparation clients per firm |
| `documents` | id, org_id, client_id, form_type, status, confidence, extracted_data | Uploaded tax documents with OCR extraction results |
| `chat_messages` | id, org_id, client_id, role, content, message_type | AI chat history per client |
| `tax_return_drafts` | id, org_id, client_id, tax_year, filing_status, draft_json | Persisted tax return draft computations |

### Knowledge Base Tables (PostgreSQL + pgvector)

| Table | Purpose |
|-------|---------|
| `mef_rules` | Layer 1 — parsed MeF business rules |
| `form_instructions` | Layer 2 — parsed form instruction sections |
| `publication_chunks` | Layer 3 — chunked publication text with 1536-dim embeddings |

### Knowledge Graph (Neo4j)

| Node Label | Purpose |
|------------|---------|
| `Rule` | MeF business rule nodes |
| `FormField` | Form field references |
| `InstructionSection` | Form instruction sections |
| `Publication` | Publication metadata |

---

## Auth0 / OAuth Configuration

TaxFlow uses **Auth0** for authentication with RS256 JWT verification.

### Roles (RBAC)

| Role | Permissions |
|------|-------------|
| **admin** | Full access — manage users, view all clients, file returns, approve docs, analytics |
| **supervisor** | View all clients, file returns, approve docs, analytics (no user management) |
| **preparer** | File returns, approve docs (sees only own clients) |
| **analyst** | Read-only access to own clients |

### Auth0 Setup

1. **Create an Auth0 Application** (Single Page Application type) for the frontend
2. **Create an Auth0 API** with identifier `https://api.taxflow.ai`
3. **Add custom claims** to Auth0 tokens via an Action or Rule:
   - `https://taxflow.ai/org_id` — the user's organization ID
   - `https://taxflow.ai/role` — one of: `admin`, `supervisor`, `preparer`, `analyst`
4. **Set callback URLs** in your Auth0 app:
   - Allowed Callback URLs: `http://localhost:3000/`
   - Allowed Logout URLs: `http://localhost:3000/`
   - Allowed Web Origins: `http://localhost:3000`

### Environment Variables

```bash
# .env
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_API_AUDIENCE=https://api.taxflow.ai
AUTH0_CLIENT_ID=your-client-id
AUTH0_REDIRECT_URI=http://localhost:3000/
```

### Dev Mode

When `APP_ENV` is not set to `production` and no JWT token is provided, the API auto-creates a dev admin user (`dev|local`) for local development — no Auth0 setup needed to get started. **This bypass is disabled in production.**

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

### Chat

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/clients/{id}/chat?page=1&page_size=100` | JWT | Get chat history (paginated) |
| POST | `/api/clients/{id}/chat` | JWT | Send message, receive AI response |

### Documents

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/clients/{id}/documents?page=1&page_size=50` | JWT | List documents (paginated) |
| POST | `/api/clients/{id}/documents` | JWT | Upload document (multipart, max 20 MB, PDF/PNG/JPEG/TIFF) |
| GET | `/api/documents/{id}` | JWT | Get document details |
| PATCH | `/api/documents/{id}/approve` | admin, supervisor, preparer | Approve a document |
| GET | `/api/documents/{id}/fields` | JWT | Get extracted fields as JSON |

### Tax Returns

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| POST | `/api/clients/{id}/returns/draft` | admin, supervisor, preparer | Generate tax return draft |
| GET | `/api/clients/{id}/returns/draft` | JWT | Retrieve generated draft |

### System

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/health` | None | Readiness check |

---

## Prerequisites

| Tool | Minimum Version | Purpose |
|------|----------------|---------|
| Python | 3.10+ | Backend runtime |
| Node.js | 18+ | Frontend runtime |
| Docker + Docker Compose | 24+ | Neo4j and PostgreSQL containers |
| pip | any | Python dependencies |
| npm | any | Frontend dependencies |

> **Neo4j edition:** All constraints use standard `IS UNIQUE` syntax — **Neo4j Community Edition** is sufficient.

---

## Quick Start

### 1. Environment configuration

```bash
cp .env.example .env
# Edit .env — set OPENAI_API_KEY and review database credentials
# Auth0 variables are optional for local dev (dev mode auto-creates an admin user)
```

### 2. Install dependencies

```bash
# Backend — core knowledge base
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Backend — API server
pip install -r requirements-api.txt

# Frontend
cd frontend && npm install && cd ..
```

### 3. Start the databases

```bash
docker compose up -d
```

| Container | Port | Credentials |
|-----------|------|-------------|
| `taxflow-neo4j` | 7474 (browser), 7687 (Bolt) | `neo4j / taxflow_dev` |
| `taxflow-postgres` | 5432 | `taxflow / taxflow_dev` |

Wait ~30 seconds, then verify:

```bash
docker compose ps     # both containers should show "healthy"
```

### 4. Apply database schemas (first time only)

The **application tables** (organizations, users, clients, documents, chat_messages, tax_return_drafts) are auto-created on API startup via SQLAlchemy `create_all`.

The **knowledge base tables** must be applied manually:

```bash
# PostgreSQL (all three layers)
docker exec -i taxflow-postgres psql -U taxflow -d taxflow < schema/postgres_schema.sql
docker exec -i taxflow-postgres psql -U taxflow -d taxflow < schema/postgres_layer2.sql
docker exec -i taxflow-postgres psql -U taxflow -d taxflow < schema/postgres_layer3.sql

# Neo4j
docker exec -it taxflow-neo4j cypher-shell \
  -u neo4j -p taxflow_dev \
  --file /var/lib/neo4j/import/neo4j_schema.cypher
```

> **Windows/WSL2 note:** Docker Desktop on Windows mounts host files with permissions the container's `postgres` user cannot read, so `docker-entrypoint-initdb.d` is intentionally disabled. Apply schemas manually as shown above.

### 5. Run the application

```bash
# Terminal 1 — Backend API
uvicorn api.main:create_app --factory --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

In dev mode (default), the API auto-seeds a sample organization ("Chen & Associates CPA"), an admin user, and 5 sample clients.

### 6. Run the test suite

No databases, no API key, and no PDF files are required — all tests run entirely in-memory with mocks.

```bash
pytest tests/ -v
```

---

## Knowledge Base Ingestion

The knowledge base must be populated before the agent can answer questions. Each layer can be ingested independently.

### Layer 1 — MeF Business Rules

```bash
python cli.py ingest \
  --csv data/sample/mef_1040_2024_v5_2.csv \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j --neo4j-password taxflow_dev \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow"

# Validate
python cli.py validate --step all --csv data/sample/mef_1040_2024_v5_2.csv
```

### Layer 2 — Form Instructions

```bash
python cli.py ingest-instructions \
  --html data/instructions/i1040gi_2024_synthetic.html \
  --form-type 1040 --tax-year 2024 \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j --neo4j-password taxflow_dev \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow"

# Validate
python cli.py validate-instructions \
  --html data/instructions/i1040gi_2024_synthetic.html \
  --form-type 1040 --tax-year 2024
```

### Layer 3 — IRS Publications

Download the IRS PDFs first:

```bash
mkdir -p data/publications
for pub in 17 501 525 550 590a 590b 596 969; do
  curl -L "https://www.irs.gov/pub/irs-pdf/p${pub}.pdf" \
    -H "User-Agent: Mozilla/5.0" \
    -o "data/publications/p${pub}.pdf" --retry 3 --retry-delay 5
  sleep 2
done
```

Then ingest and embed:

```bash
export OPENAI_API_KEY="sk-..."

python cli.py ingest-publications \
  --pdf data/publications/p17.pdf   --pub-number 17   \
  --pdf data/publications/p501.pdf  --pub-number 501  \
  --pdf data/publications/p525.pdf  --pub-number 525  \
  --pdf data/publications/p550.pdf  --pub-number 550  \
  --pdf data/publications/p590a.pdf --pub-number 590a \
  --pdf data/publications/p590b.pdf --pub-number 590b \
  --pdf data/publications/p596.pdf  --pub-number 596  \
  --pdf data/publications/p969.pdf  --pub-number 969  \
  --tax-year 2025 \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" \
  --init-schema

# Build the IVFFlat ANN index after initial bulk ingest
python cli.py ingest-publications \
  --pdf data/publications/p17.pdf --pub-number 17 \
  --tax-year 2025 \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" \
  --skip-embedding --build-index

# Validate
python cli.py validate-publications --step all \
  --pdf data/publications/p17.pdf --pub-number 17 \
  --tax-year 2025 \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" \
  --require-embeddings
```

> **Text-only ingest:** Use `--skip-embedding` to ingest without calling the OpenAI API. Embed later by re-running without the flag.

### Layer 4 — Query Agent

Once the knowledge base is populated, ask questions via the CLI:

```bash
python cli.py ask "What is the standard deduction for a single filer?"

# Validate the agent against standard CPA queries
python cli.py validate-agent
```

### Layer 5 — Evaluation

```bash
# Generate a gold set from ingested chunks
python cli.py generate-gold-set

# Evaluate retrieval quality (HR@k, MRR, Recall)
python cli.py evaluate-retrieval

# Evaluate generation quality (LLM-as-judge)
python cli.py evaluate-generation
```

---

## Semantic Search

```bash
# Basic search
python cli.py search "What is the standard deduction for a single filer?" \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" --top-k 5

# Filter by publication
python cli.py search "IRA contribution limits for 2025" \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" \
  --pub-number 590a --pub-number 590b --top-k 3

# Filter by tax year
python cli.py search "Earned Income Credit eligibility" \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" \
  --pub-number 596 --tax-year 2025 --top-k 5
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Default | Purpose |
|----------|---------|---------|
| **Application** | | |
| `APP_ENV` | `development` | Set to `production` to disable dev auth bypass and seed data |
| `APP_DATABASE_URL` | `postgresql+asyncpg://...localhost:5432/taxflow` | Async PostgreSQL connection for app tables |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| **Auth0** | | |
| `AUTH0_DOMAIN` | — | Your Auth0 tenant domain |
| `AUTH0_API_AUDIENCE` | — | Auth0 API identifier |
| `AUTH0_CLIENT_ID` | — | Auth0 SPA client ID |
| `AUTH0_REDIRECT_URI` | `http://localhost:3000/` | Post-login redirect |
| **Knowledge Base** | | |
| `PG_DSN` | `postgresql://taxflow:taxflow_dev@localhost:5432/taxflow` | PostgreSQL connection for KB |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection |
| `NEO4J_USER` / `NEO4J_PASSWORD` | `neo4j` / `changeme` | Neo4j credentials |
| `OPENAI_API_KEY` | — | Required for embeddings and synthesis |
| `EMBEDDING_MODEL` | `text-embedding-3-large` | Embedding model |
| `EMBEDDING_DIM` | `1536` | Embedding dimensions |
| `SYNTHESIS_MODEL` | `gpt-4o-mini` | Answer synthesis model |
| `JUDGE_MODEL` | `gpt-4o` | Evaluation judge model |
| `RETRIEVAL_TOP_K` | `10` | Top-k results for retrieval |
| `CHUNK_MAX_TOKENS` | `400` | Target tokens per chunk |
| `DEFAULT_TAX_YEAR` | `2025` | Default tax year |

---

## Project Structure

```
taxflow-kb/
├── api/                                    # FastAPI backend
│   ├── main.py                             # App factory (CORS, lifespan, routers)
│   ├── auth/                               # Auth0 JWT verification, RBAC, user provisioning
│   │   ├── config.py                       # Auth0 env config (APP_ENV, domain, audience)
│   │   ├── dependencies.py                 # get_current_user, require_role dependencies
│   │   ├── models.py                       # Organization, User ORM models, ROLE_PERMISSIONS
│   │   └── token.py                        # RS256 JWT verification with JWKS TTL cache
│   ├── routers/                            # auth, health, clients, chat, documents, tax_returns
│   │   └── _helpers.py                     # Shared get_client_or_404 helper
│   ├── models/                             # Pydantic request/response schemas
│   │   ├── enums.py                        # Shared Literal types (FilingStatus, FormType, etc.)
│   │   ├── client.py, chat.py, document.py # CRUD schemas with validation
│   │   └── tax_return.py                   # Tax return draft schemas
│   ├── services/ocr/                       # OCR extraction (mock for dev)
│   └── db/                                 # Engine, base models, seed data
│       ├── base.py                         # DeclarativeBase + TenantMixin (org_id, timestamps)
│       ├── models.py                       # Client, Document, ChatMessage, TaxReturnDraft ORM
│       ├── engine.py                       # Async engine, session factory, init_db
│       └── seed.py                         # Dev seed data (org, user, sample clients)
├── frontend/                               # Next.js 16 web application
│   ├── app/                                # App Router (page.tsx entry point)
│   ├── components/                         # React components
│   │   ├── ui/                             # Base: button, card, modal, input, badge, tabs
│   │   ├── chat/                           # Chat: message-list, bubble, input, typing
│   │   ├── layout/                         # Layout: top-bar, sidebar, chat-panel, work-panel
│   │   ├── clients/                        # Client: intake-modal
│   │   ├── forms/                          # Tax forms: W-2, 1099-INT, generic, renderer
│   │   ├── returns/                        # Return preview
│   │   ├── documents/                      # Document viewer modal
│   │   └── dashboard/                      # Dashboard
│   ├── lib/                                # api-client.ts, utils.ts
│   └── styles/                             # globals.css (design tokens)
├── tax_brain/                              # Core Python knowledge base library
│   ├── models.py                           # Pydantic v2 models (MeFRule, ASTNode, etc.)
│   ├── protocols.py                        # DI interfaces (Retriever, EmbeddingClient, etc.)
│   ├── config.py                           # Centralized settings (Pydantic BaseSettings)
│   ├── factories.py                        # Dependency injection wiring
│   ├── rules/                              # Layer 1: CSV parser, AST parser, Neo4j/PG ingest
│   ├── instructions/                       # Layer 2: HTML parser, Neo4j/PG ingest, validation
│   ├── publications/                       # Layer 3: PDF parser, embeddings, pgvector, search
│   ├── agent/                              # Layer 4: retriever, synthesizer, classifier, reranker
│   ├── evaluation/                         # Layer 5: gold set generation, eval metrics
│   └── adapters/                           # Concrete implementations (OpenAI, PG, Neo4j)
├── cli/                                    # CLI command modules
├── data/                                   # Sample data and IRS PDFs
├── schema/                                 # SQL and Cypher schema files
├── eval/                                   # Evaluation runner and golden sets
├── tests/                                  # pytest tests (all in-memory)
│   └── api/                                # API endpoint tests
├── docker-compose.yml                      # Neo4j 5.18 + PostgreSQL 16 (pgvector)
├── requirements.txt                        # Core + KB dependencies
├── requirements-api.txt                    # API dependencies (FastAPI, SQLAlchemy, etc.)
├── pyproject.toml                          # Package metadata, pytest config
└── .env.example                            # Environment variable template
```

---

## CLI Reference

```
# ── Layer 1 — MeF Business Rules ─────────────────────────────────────────────
python cli.py ingest               --csv FILE [--neo4j-uri URI] [--pg-dsn DSN]
python cli.py validate             --csv FILE --step {v1.1 | v1.3 | all}
python cli.py sample               --csv FILE --out OUTPUT_PREFIX
python cli.py score                --annotated ANNOTATED_JSON
python cli.py diff                 --old OLD_CSV --new NEW_CSV [--report-dir DIR]

# ── Layer 2 — Form Instructions ──────────────────────────────────────────────
python cli.py ingest-instructions  --html FILE --form-type FORM --tax-year YEAR
                                   [--neo4j-uri URI] [--pg-dsn DSN]
python cli.py validate-instructions --html FILE --form-type FORM --tax-year YEAR
                                    --step {all | v2.1 | v2.2}

# ── Layer 3 — Publications ───────────────────────────────────────────────────
python cli.py ingest-publications  --pdf FILE --pub-number NUM [repeat pairs]
                                   --tax-year YEAR --pg-dsn DSN
                                   [--skip-embedding] [--build-index] [--init-schema]
python cli.py validate-publications --step {all | v3.1 | v3.2 | v3.3}
                                    [--pg-dsn DSN] [--pdf FILE --pub-number NUM]
                                    [--require-embeddings]
python cli.py search               QUERY --pg-dsn DSN [--top-k N]
                                   [--pub-number NUM] [--tax-year YEAR]
python cli.py download-publications [--output-dir DIR]
python cli.py build-index          --pg-dsn DSN
python cli.py add-bm25-index       --pg-dsn DSN
python cli.py re-embed             --pg-dsn DSN [--model MODEL]

# ── Layer 4 — Agent ──────────────────────────────────────────────────────────
python cli.py ask                  QUESTION
python cli.py validate-agent

# ── Layer 5 — Evaluation ─────────────────────────────────────────────────────
python cli.py generate-gold-set
python cli.py filter-gold-set
python cli.py patch-gold-set
python cli.py validate-gold-set
python cli.py verify-gold-set
python cli.py evaluate-retrieval
python cli.py evaluate-generation
```

---

## Switching to Real IRS Data

### Layer 1 — Real MeF Business Rules

The sample CSV is a realistic synthetic dataset. Real IRS MeF business rules are available from the [MeF Developer Portal](https://www.irs.gov/e-file-providers/modernized-e-file-mef-internet-filing) (requires IRS e-Services registration). The pipeline expects this 10-column header:

```
RULE_ID, RULE_TYPE, FORM_FAMILY, FIELD_PATH, RULE_TEXT,
RULE_EXPRESSION, ERROR_CODE, SEVERITY, TAX_YEAR, SCHEMA_VERSION
```

### Layer 2 — Real IRS Instruction HTML

IRS publishes instruction HTML at `https://www.irs.gov/instructions/{form-code}`. The HTML parser uses only Python's stdlib `html.parser` and works against live IRS pages with no changes.

### Layer 3 — Real IRS Publications

The Layer 3 pipeline is designed for real IRS PDFs — no conversion needed. All 8 publications are free at `https://www.irs.gov/pub/irs-pdf/p{NUMBER}.pdf`. Embedding cost for all 8 publications is under $0.10 total.

---

## Development Notes

- All database writes use **MERGE / upsert** semantics — re-ingesting is idempotent.
- Protocol-driven dependency injection — all external deps injected via Protocols.
- The rule engine in `v1_3_test_replay.py` uses regex-based evaluation, not `eval()`.
- Embedding batches are capped at 512 chunks per API call with exponential backoff.
- Hybrid search combines vector (cosine) + BM25 (keyword) via augment or RRF fusion.
- The IVFFlat index (`lists=100`) should be built once after initial bulk ingest.
- Tests run entirely in-memory with mock vectors — no databases or API keys needed.
- JWKS keys are cached with a 1-hour TTL to handle Auth0 key rotations.
- File uploads are validated: 20 MB max, PDF/PNG/JPEG/TIFF only, filenames sanitized.
- All queries are tenant-scoped via `org_id` for multi-tenant data isolation.

### Tear down

```bash
docker compose down -v    # removes containers and volumes (data is lost)
```
