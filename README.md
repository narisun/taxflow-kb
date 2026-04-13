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

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend  (Next.js 16 · React 19 · Tailwind CSS 4)        │
│  http://localhost:3000                                       │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────────────┐
│  Backend API  (FastAPI · SQLAlchemy 2 async · Pydantic v2)  │
│  http://localhost:8000                                       │
│  Routers: /api/health · /api/clients · /api/clients/{id}/   │
│           chat · /api/documents · /api/tax-returns           │
└──────┬───────────────┬──────────────────────────────────────┘
       │               │
┌──────▼───────┐ ┌─────▼─────────────────────────────────────┐
│  SQLite      │ │  Knowledge Base (tax_brain)                │
│  (clients,   │ │  PostgreSQL 16 + pgvector · Neo4j 5.18    │
│   docs,      │ │  OpenAI embeddings · Hybrid search         │
│   chat)      │ │  Agent: retrieve → rerank → synthesize     │
└──────────────┘ └────────────────────────────────────────────┘
```

---

## Project Structure

```
taxflow-kb/
├── api/                                    # FastAPI backend
│   ├── main.py                             # App factory (CORS, lifespan, routers)
│   ├── routers/                            # health, clients, chat, documents, tax_returns
│   ├── models/                             # SQLAlchemy models (Client, Document, ChatMessage)
│   ├── services/                           # Business logic
│   └── db/                                 # Engine, sessions, migrations
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
│   ├── main.py                             # Dispatcher (40+ commands)
│   ├── rules_commands.py                   # Layer 1 commands
│   ├── instructions_commands.py            # Layer 2 commands
│   ├── publications_commands.py            # Layer 3 commands
│   ├── agent_commands.py                   # Layer 4 commands (ask, validate-agent)
│   └── evaluation_commands.py              # Layer 5 commands (gold set, evaluate)
├── data/
│   ├── sample/                             # Synthetic MeF CSV
│   ├── instructions/                       # Synthetic instruction HTML
│   └── publications/                       # IRS PDFs (downloaded separately)
├── schema/
│   ├── postgres_schema.sql                 # Layer 1 DDL
│   ├── postgres_layer2.sql                 # Layer 2 DDL
│   ├── postgres_layer3.sql                 # Layer 3 DDL + pgvector
│   └── neo4j_schema.cypher                 # Neo4j constraints and indexes
├── eval/                                   # Evaluation runner and golden sets
│   ├── golden_set.json
│   └── run_eval.py
├── tests/                                  # 453 pytest tests
│   ├── conftest.py                         # Fixtures, mock factories
│   ├── test_rules.py                       # Layer 1 (24 tests)
│   ├── test_instructions.py                # Layer 2 (23 tests)
│   ├── test_publications.py                # Layer 3 (33 tests)
│   ├── test_agent.py                       # Layer 4
│   ├── test_evaluation.py                  # Layer 5
│   ├── test_retriever.py                   # Retrieval pipeline
│   ├── test_config_and_registry.py         # Config & ontology
│   ├── test_ontology.py                    # Ontology
│   ├── test_multi_year.py                  # Multi-year support
│   ├── test_pipeline_wiring.py             # End-to-end wiring
│   ├── test_irs_download.py                # IRS download
│   └── api/                                # API endpoint tests
├── cli.py                                  # CLI entry point
├── docker-compose.yml                      # Neo4j 5.18 + PostgreSQL 16 (pgvector)
├── requirements.txt                        # Core + KB dependencies
├── requirements-api.txt                    # API dependencies (FastAPI, SQLAlchemy, etc.)
├── pyproject.toml                          # Package metadata, pytest config
└── .env.example                            # Environment variable template
```

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

### 6. Run the test suite

No databases, no API key, and no PDF files are required — all tests run entirely in-memory with mocks.

```bash
pytest tests/ -v
```

Expected: **453 tests passed**.

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

## REST API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/health` | Readiness check |
| GET | `/api/clients` | List all clients |
| POST | `/api/clients` | Create a client |
| GET | `/api/clients/{id}` | Get client details |
| PUT | `/api/clients/{id}` | Update a client |
| DELETE | `/api/clients/{id}` | Delete a client |
| GET | `/api/clients/{id}/chat` | Get chat history |
| POST | `/api/clients/{id}/chat` | Send a message |
| POST | `/api/documents` | Upload a document |
| GET | `/api/documents` | List documents |
| POST | `/api/documents/{id}/extract` | Extract data from document |
| POST | `/api/documents/{id}/approve` | Approve extracted data |
| POST | `/api/tax-returns/{client_id}/generate` | Generate draft return |
| GET | `/api/tax-returns/{client_id}` | Get draft return |

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

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Frontend** | Next.js 16, React 19, TypeScript 5, Tailwind CSS 4 |
| **Backend API** | FastAPI, Uvicorn, SQLAlchemy 2 (async), Pydantic v2 |
| **App Database** | SQLite (clients, documents, chat history) |
| **Knowledge Graph** | Neo4j 5.18 Community |
| **Vector Store** | PostgreSQL 16 + pgvector (IVFFlat ANN, 1536-dim) |
| **Full-Text Search** | PostgreSQL GIN/tsvector (BM25 hybrid search) |
| **Embeddings** | OpenAI text-embedding-3-large (1536 dimensions) |
| **LLM Synthesis** | GPT-4o-mini (answers), GPT-4o (judge/evaluation) |
| **PDF Parsing** | pdfplumber (paragraph-aware chunking) |
| **Token Counting** | tiktoken (cl100k_base) |
| **Testing** | pytest (453 tests, all in-memory, no external deps) |

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Default | Purpose |
|----------|---------|---------|
| `PG_DSN` | `postgresql://taxflow:taxflow_dev@localhost:5432/taxflow` | PostgreSQL connection |
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

### Tear down

```bash
docker compose down -v    # removes containers and volumes (data is lost)
```
