# TaxFlow AI — Knowledge Base (Layers 1–3)

**IRS MeF Business Rules + Form Instruction Graph + Publication Semantic Search Ingestion, Parsing, and Validation Pipeline**

TaxFlow AI is a CPA-facing agentic platform. Its knowledge base is the foundation every AI agent queries before answering a tax question. This repository implements the first three layers:

| Layer | Source | Store | Status |
|-------|--------|-------|--------|
| **1 — MeF Business Rules** | IRS MeF CSV | Neo4j + PostgreSQL | ✅ Complete |
| **2 — Form Instructions** | IRS HTML (irs.gov/instructions) | Neo4j + PostgreSQL | ✅ Complete |
| **3 — Publications** | IRS Publication PDFs | PostgreSQL + pgvector | ✅ Complete |

---

## What This Does

When a CPA asks "why is line 11 on Form 1040 flagging an error?", the answer comes from here. Layer 1 ingests the machine-readable IRS ruleset and turns it into a queryable, versioned knowledge graph. Layer 2 enriches every FormLine node with the IRS's own plain-English instructions, so agents can explain *why* a rule exists — not just that it does. Layer 3 adds publication-level semantic search: when the CPA asks a nuanced question ("Can I deduct my health insurance premium?"), the agent retrieves the most relevant passage from the appropriate IRS publication.

```
Layer 1 — MeF Business Rules
─────────────────────────────
IRS MeF CSV
    │
    ▼
CSV Parser (normalize · dedup · validate)
    │
    ▼
AST Parser  (If/Then/Else · MATH · IN list · must be attached · matches pattern)
    │
    ├──► Neo4j       Form → FormLine → Rule → ErrorCode
    └──► PostgreSQL  irs_kb schema · version history · audit log
         │
         ▼
    Validation Gates
         V1.1  Structural integrity  (≥ 98% AST parse rate · zero nulls/dupes)
         V1.2  Expert spot-check     (≥ 95% domain-expert accuracy)
         V1.3  Test-return replay    (100% ERROR match · ≥ 95% WARNING match)
         V1.4  Regression            (zero unexpected outcome changes)

Layer 2 — IRS Form Instruction Graph
──────────────────────────────────────
IRS Instruction HTML  (irs.gov/instructions/i1040gi)
    │
    ▼
HTML Parser  (h2 container sections · h3 line sections · cross-references)
    │
    ├──► Neo4j       InstructionPage → InstructionSection → FormLine
    │                                                      → Form (cross-refs)
    └──► PostgreSQL  instruction_pages · instruction_sections · GIN/FTS indexes
         │
         ▼
    Validation Gates
         V2.1  Structural integrity  (≥ 10 sections · ≥ 5 line sections · no empty h3)
         V2.2  FormLine link coverage (≥ 70% of Layer 1 fields explained)

Layer 3 — IRS Publication Semantic Search (pgvector)
──────────────────────────────────────────────────────
IRS Publication PDFs  (Pub 17, 501, 525, 550, 590a/b, 596, 969)
    │
    ▼
PDF Parser  (pdfplumber · heading detection · paragraph-aware chunking)
  · Target ~400 tokens/chunk · 50-token overlap · hard max 512 tokens
  · Extracts form_refs (Form1040, ScheduleA) and line_refs (1a, 12b) per chunk
    │
    ▼
OpenAI Embeddings  (text-embedding-3-small · 1536-dim · cl100k_base)
  · Batched (512 chunks/request) · 3 retries with backoff
    │
    └──► PostgreSQL + pgvector
           irs_kb.publications        — pub metadata + embedding coverage stats
           irs_kb.publication_chunks  — text + embedding vector(1536)
           IVFFlat index              — cosine ANN search (lists=100)
           GIN indexes                — form_refs[], line_refs[] array filtering
         │
         ▼
    Validation Gates
         V3.1  Structural integrity  (≥ 10 chunks · no empty text · correct embedding dim)
         V3.2  Coverage              (all 8 pubs present · avg tokens in [50, 450])
         V3.3  Retrieval quality     (8 probe queries → expected pub at ≥ 0.50 cosine score)
```

---

## Project Structure

```
taxflow-kb/
├── data/
│   ├── sample/
│   │   └── mef_1040_2024_v5_2.csv             # 60 synthetic MeF rules (Form 1040, TY 2024)
│   ├── instructions/
│   │   └── i1040gi_2024_synthetic.html         # Synthetic Form 1040 instruction page
│   └── publications/                           # IRS publication PDFs (downloaded separately)
│       ├── p17.pdf                             # Your Federal Income Tax
│       ├── p501.pdf                            # Dependents, Standard Deduction, Filing Info
│       ├── p525.pdf                            # Taxable and Nontaxable Income
│       ├── p550.pdf                            # Investment Income and Expenses
│       ├── p590a.pdf                           # IRA Contributions
│       ├── p590b.pdf                           # IRA Distributions
│       ├── p596.pdf                            # Earned Income Credit (EIC)
│       └── p969.pdf                            # Health Savings Accounts
├── schema/
│   ├── postgres_schema.sql                     # Layer 1 DDL — irs_kb schema, views, triggers
│   ├── postgres_layer2.sql                     # Layer 2 DDL — instruction tables, GIN/FTS indexes
│   ├── postgres_layer3.sql                     # Layer 3 DDL — publications + chunks + pgvector
│   └── neo4j_schema.cypher                     # Neo4j constraints, indexes, seed nodes
├── tax_brain/
│   ├── models.py                               # Pydantic v2 models (MeFRule, ASTNode, ValidationReport …)
│   ├── ingestion/
│   │   ├── csv_parser.py                       # CSV → list[MeFRule]
│   │   ├── ast_parser.py                       # IRS pseudo-code → typed ASTNode tree
│   │   ├── neo4j_ingestion.py                  # Layer 1 Neo4j MERGE upserts
│   │   └── postgres_ingestion.py               # Layer 1 PostgreSQL writes
│   ├── layer2/
│   │   ├── models_layer2.py                    # Pydantic models (InstructionPage, InstructionSection)
│   │   ├── html_parser.py                      # HTML → Layer2ParseResult (stdlib html.parser only)
│   │   ├── neo4j_layer2.py                     # Layer 2 Neo4j MERGE upserts
│   │   ├── postgres_layer2.py                  # Layer 2 PostgreSQL upserts
│   │   └── validation/
│   │       ├── v2_1_structural.py              # Gate V2.1 — structural integrity
│   │       └── v2_2_link_coverage.py           # Gate V2.2 — FormLine link coverage
│   ├── layer3/
│   │   ├── models_layer3.py                    # Pydantic models (Publication, PublicationChunk, RetrievalResult)
│   │   ├── pdf_parser.py                       # PDF → paragraph-aware chunks (pdfplumber + tiktoken)
│   │   ├── embeddings.py                       # OpenAI text-embedding-3-small (batched, retry)
│   │   ├── postgres_layer3.py                  # pgvector upsert, IVFFlat index, cosine search
│   │   └── validation/
│   │       ├── v3_1_structural.py              # Gate V3.1 — chunk structural integrity
│   │       ├── v3_2_coverage.py                # Gate V3.2 — publication coverage
│   │       └── v3_3_retrieval.py               # Gate V3.3 — retrieval quality probes
│   └── validation/
│       ├── v1_1_structural.py
│       ├── v1_2_spot_check.py
│       ├── v1_3_test_replay.py
│       └── v1_4_regression.py
├── tests/
│   ├── test_layer1.py                          # 24 pytest tests (CSV · AST · V1.1 · V1.3)
│   ├── test_layer2.py                          # 23 pytest tests (HTML parser · V2.1 · V2.2)
│   └── test_layer3.py                          # 33 pytest tests (models · parser · V3.1–V3.3)
├── cli.py                                      # CLI: all Layer 1–3 commands
├── docker-compose.yml                          # Neo4j 5.18 + PostgreSQL 16 (pgvector/pgvector:pg16)
└── requirements.txt
```

---

## Prerequisites

| Tool | Minimum version | Purpose |
|------|----------------|---------|
| Python | 3.10+ | Runtime |
| Docker + Docker Compose | 24+ | Neo4j and PostgreSQL containers |
| pip | any | Python dependencies |

> **Neo4j edition:** All constraints use standard `IS UNIQUE` syntax — **Neo4j Community Edition** is sufficient. Enterprise Edition is not required.

---

## Build and Run Locally

### 1. Clone / open the project

```bash
cd taxflow-kb
```

### 2. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Start the databases

```bash
docker compose up -d
```

| Container | Port | Credentials |
|-----------|------|-------------|
| `taxflow-neo4j` | 7474 (browser), 7687 (Bolt) | `neo4j / taxflow_dev` |
| `taxflow-postgres` | 5432 | `taxflow / taxflow_dev` |

> **Windows/WSL2 note:** The PostgreSQL schemas are NOT auto-applied on startup. Docker Desktop on Windows mounts host files with permissions the container's `postgres` user cannot read, so `docker-entrypoint-initdb.d` is intentionally disabled. Apply both schemas manually in step 5.

Wait ~30 seconds, then verify:

```bash
docker compose ps     # both containers should show "healthy"
```

### 4. Run the full test suite

No databases, no API key, and no PDF files are required — all tests run entirely in-memory against sample data and mock vectors.

```bash
pytest tests/ -v
```

Expected: **80 passed** (24 Layer 1 + 23 Layer 2 + 33 Layer 3).

To run each layer separately:

```bash
pytest tests/test_layer1.py -v    # 24 passed
pytest tests/test_layer2.py -v    # 23 passed
pytest tests/test_layer3.py -v    # 33 passed
```

### 5. Apply schemas (first time only)

**PostgreSQL Layer 1:**

```bash
docker exec -i taxflow-postgres psql -U taxflow -d taxflow < schema/postgres_schema.sql
```

**PostgreSQL Layer 2:**

```bash
docker exec -i taxflow-postgres psql -U taxflow -d taxflow < schema/postgres_layer2.sql
```

Verify both schemas applied:

```bash
docker exec -it taxflow-postgres psql -U taxflow -d taxflow -c "\dt irs_kb.*"
```

Expected tables: `form_lines`, `mef_rules`, `rule_version_history`, `ingestion_log`, `instruction_pages`, `instruction_sections`, `instruction_ingestion_log`, `layer2_validation_runs`.

**Neo4j:**

```bash
docker exec -it taxflow-neo4j cypher-shell \
  -u neo4j -p taxflow_dev \
  --file /var/lib/neo4j/import/neo4j_schema.cypher
```

### 6. Ingest Layer 1 — MeF business rules

```bash
python cli.py ingest \
  --csv data/sample/mef_1040_2024_v5_2.csv \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j \
  --neo4j-password taxflow_dev \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow"
```

### 7. Run Layer 1 validation gates

```bash
python cli.py validate --step all --csv data/sample/mef_1040_2024_v5_2.csv
```

Or individual gates:

```bash
python cli.py validate --step v1.1 --csv data/sample/mef_1040_2024_v5_2.csv
python cli.py validate --step v1.3 --csv data/sample/mef_1040_2024_v5_2.csv
```

### 8. Ingest Layer 2 — Form 1040 instruction HTML

```bash
python cli.py ingest-instructions \
  --html data/instructions/i1040gi_2024_synthetic.html \
  --form-type 1040 \
  --tax-year 2024 \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j \
  --neo4j-password taxflow_dev \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow"
```

### 9. Run Layer 2 validation gates

```bash
python cli.py validate-instructions \
  --html data/instructions/i1040gi_2024_synthetic.html \
  --form-type 1040 \
  --tax-year 2024
```

Both gates run automatically. Expected output:

```
V2.1 PASSED — structural integrity (38 sections, 26 line sections)
V2.2 PASSED — FormLine link coverage (≥ 70% of Layer 1 fields explained)
```

### 10. Layer 3 setup — pgvector schema

Layer 3 uses the `pgvector/pgvector:pg16` Docker image (already in `docker-compose.yml`). Apply the Layer 3 schema once:

```bash
docker exec -i taxflow-postgres psql -U taxflow -d taxflow < schema/postgres_layer3.sql
```

Verify the new tables:

```bash
docker exec -it taxflow-postgres psql -U taxflow -d taxflow \
  -c "\dt irs_kb.*" -c "SELECT extname FROM pg_extension WHERE extname='vector';"
```

Expected: `publication_chunks`, `publications`, `pub_ingestion_log`, `layer3_validation_runs` tables plus `vector` extension.

### 11. Download IRS Publication PDFs

IRS publications are free public documents available at `https://www.irs.gov/pub/irs-pdf/p{NUMBER}.pdf`.

```bash
mkdir -p data/publications

# Download all 8 publications for TY 2024
for pub in 17 501 525 550 590a 590b 596 969; do
  echo "Downloading p${pub}.pdf …"
  curl -L "https://www.irs.gov/pub/irs-pdf/p${pub}.pdf" \
    -H "User-Agent: Mozilla/5.0" \
    -o "data/publications/p${pub}.pdf" --retry 3 --retry-delay 5
  sleep 2    # be a considerate client
done
```

> **Note:** IRS PDF URLs may redirect. If a publication returns a "Page Not Found", try `https://www.irs.gov/pub/irs-prior/p{NUMBER}--2024.pdf` for the prior-year version.

### 12. Ingest Layer 3 — IRS Publications

Set your OpenAI API key before running:

```bash
export OPENAI_API_KEY="sk-..."
```

Ingest all publications in one command (repeat `--pdf`/`--pub-number` pairs):

```bash
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
```

After the first full ingest, build the IVFFlat ANN index for fast cosine search:

```bash
python cli.py ingest-publications \
  --pdf data/publications/p17.pdf --pub-number 17 \
  --tax-year 2025 \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" \
  --skip-embedding --build-index
```

**Text-only ingest (no API key required):** Use `--skip-embedding` to ingest text without calling the OpenAI API. You can embed later by re-running without the flag.

### 13. Run Layer 3 validation gates

```bash
# V3.1 — structural integrity of the parsed PDFs (no DB required)
python cli.py validate-publications \
  --step v3.1 \
  --pdf data/publications/p17.pdf --pub-number 17 \
  --tax-year 2025

# V3.2 — database coverage (all 8 pubs must be present with adequate chunk counts)
python cli.py validate-publications \
  --step v3.2 \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" \
  --require-embeddings

# V3.3 — retrieval quality (8 probe queries, requires OPENAI_API_KEY)
python cli.py validate-publications \
  --step v3.3 \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow"

# Run all three gates at once
python cli.py validate-publications \
  --step all \
  --pdf data/publications/p17.pdf --pub-number 17 \
  --tax-year 2025 \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" \
  --require-embeddings
```

### 14. Semantic search

```bash
# Basic search
python cli.py search "What is the standard deduction for a single filer?" \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" \
  --top-k 5

# Filter by specific publications
python cli.py search "IRA contribution limits for 2025" \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" \
  --pub-number 590a --pub-number 590b --top-k 3

# Filter by tax year
python cli.py search "Earned Income Credit eligibility requirements" \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" \
  --pub-number 596 --tax-year 2025 --top-k 5
```

Example output:
```
Searching for: 'What is the standard deduction for a single filer?'

──────────────────────────────────────────────────────────────────────────
[1] Pub 501 — Dependents, Standard Deduction, and Filing Information
    Chapter: STANDARD DEDUCTION
    Section: Standard Deduction Amounts
    Page: 22  |  Score: 0.8743
    For 2025, the standard deduction for a single filer is $15,000 …
──────────────────────────────────────────────────────────────────────────
```

### 15. Explore the graph (optional)

Open the Neo4j browser at [http://localhost:7474](http://localhost:7474) and try:

**Layer 1 queries:**

```cypher
-- All rules for Form 1040 after ingest
MATCH (fl:FormLine {form_type: '1040', tax_year: 2024})-[:GOVERNED_BY]->(r:Rule)
RETURN fl.field_path, r.rule_id, r.severity, r.rule_text
ORDER BY r.rule_id;

-- Rules that raise a specific error code
MATCH (r:Rule)-[:RAISES]->(e:ErrorCode {code: 'IND-041-01'})
RETURN r.rule_id, r.rule_text, e.code;
```

**Layer 2 queries:**

```cypher
-- All instruction sections for Form 1040
MATCH (p:InstructionPage {form_type: '1040'})-[:HAS_SECTION]->(s:InstructionSection)
RETURN s.section_type, s.heading, s.line_reference
ORDER BY s.sequence;

-- Which instruction section explains a given FormLine field?
MATCH (s:InstructionSection)-[:EXPLAINS]->(fl:FormLine {short_field: 'WagesSalariesTipsAmt'})
RETURN s.section_id, s.heading, s.text_content;

-- Cross-form references from the instruction graph
MATCH (s:InstructionSection)-[:REFERENCES_FORM]->(f:Form)
RETURN s.heading, f.form_type
ORDER BY f.form_type;
```

**Combined query — rule + plain-English explanation for one field:**

```cypher
MATCH (fl:FormLine {form_type: '1040', short_field: 'WagesSalariesTipsAmt'})
OPTIONAL MATCH (fl)-[:GOVERNED_BY]->(r:Rule)
OPTIONAL MATCH (s:InstructionSection)-[:EXPLAINS]->(fl)
RETURN fl.short_field, r.rule_id, r.rule_text, s.heading, s.text_content
LIMIT 5;
```

### Tear down

```bash
docker compose down -v    # removes containers and volumes (data is lost)
```

---

## CLI Reference

```
# ── Layer 1 ──────────────────────────────────────────────────────────────────
python cli.py ingest               --csv FILE
                                   [--neo4j-uri URI --neo4j-user U --neo4j-password P]
                                   [--pg-dsn DSN] [--init-schema]

python cli.py validate             --csv FILE --step {v1.1 | v1.3 | all}

python cli.py sample               --csv FILE --out OUTPUT_PREFIX

python cli.py score                --annotated ANNOTATED_JSON

python cli.py diff                 --old OLD_CSV --new NEW_CSV [--report-dir DIR]

# ── Layer 2 ──────────────────────────────────────────────────────────────────
python cli.py ingest-instructions  --html FILE --form-type FORM --tax-year YEAR
                                   [--neo4j-uri URI --neo4j-user U --neo4j-password P]
                                   [--pg-dsn DSN] [--init-schema]

python cli.py validate-instructions --html FILE --form-type FORM --tax-year YEAR
                                    --step {all | v2.1 | v2.2}

# ── Layer 3 ──────────────────────────────────────────────────────────────────
python cli.py ingest-publications  --pdf FILE --pub-number NUM [repeat for more PDFs]
                                   --tax-year YEAR --pg-dsn DSN
                                   [--api-key KEY] [--skip-embedding]
                                   [--init-schema] [--build-index]

python cli.py validate-publications --step {all | v3.1 | v3.2 | v3.3}
                                    [--pg-dsn DSN]
                                    [--pdf FILE --pub-number NUM]   # required for v3.1
                                    [--api-key KEY]                  # required for v3.3
                                    [--require-embeddings]           # enforces V3.2-C

python cli.py search               QUERY --pg-dsn DSN
                                   [--api-key KEY] [--top-k N]
                                   [--pub-number NUM] [--tax-year YEAR]
```

---

## Switching to Real IRS Data

### Layer 1 — Real MeF Business Rules

The sample CSV (`data/sample/mef_1040_2024_v5_2.csv`) is a realistic synthetic dataset built to match the IRS MeF format exactly. When the actual IRS files become available:

**Where to get them:**

IRS publishes MeF business rules annually as part of the MeF Developer Resources package. Access requires registration with IRS e-Services:

- MeF Developer Portal: [https://www.irs.gov/e-file-providers/modernized-e-file-mef-internet-filing](https://www.irs.gov/e-file-providers/modernized-e-file-mef-internet-filing)
- Business rules are distributed as a ZIP containing one CSV per form family (e.g., `1040_BusinessRules_2024_v5.2.csv`).

**Column mapping:** The pipeline expects this exact 10-column header (case-insensitive):

```
RULE_ID, RULE_TYPE, FORM_FAMILY, FIELD_PATH, RULE_TEXT,
RULE_EXPRESSION, ERROR_CODE, SEVERITY, TAX_YEAR, SCHEMA_VERSION
```

If the IRS file uses different column names, add aliases to `HEADER_ALIASES` in `tax_brain/rules/csv_parser.py`.

**Multi-form ingestion:**

```bash
for f in data/irs_real/1040_*.csv; do
  python cli.py ingest --csv "$f" \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-user neo4j --neo4j-password taxflow_dev \
    --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow"
done
```

---

### Layer 2 — Real IRS Instruction HTML Pages

The synthetic file (`data/instructions/i1040gi_2024_synthetic.html`) mirrors the structure of real IRS instruction pages. The HTML parser uses only Python's stdlib `html.parser` and makes no assumptions about external CSS or JS, so it works against the live IRS pages with no changes.

#### Fetching the real instruction pages

IRS publishes instruction HTML at `https://www.irs.gov/instructions/{form-code}`. The current year's page is always at the root path; prior years redirect to archived PDF or HTML.

| Form | Live HTML URL | Notes |
|------|--------------|-------|
| Form 1040 General Instructions | [https://www.irs.gov/instructions/i1040gi](https://www.irs.gov/instructions/i1040gi) | Main individual return instructions |
| Form 1040 Schedule A (Itemized) | [https://www.irs.gov/instructions/i1040sca](https://www.irs.gov/instructions/i1040sca) | Itemized deductions |
| Form 1040 Schedule B (Interest/Dividends) | [https://www.irs.gov/instructions/i1040sb](https://www.irs.gov/instructions/i1040sb) | Interest and dividend income |
| Form 1040 Schedule C (Business) | [https://www.irs.gov/instructions/i1040sc](https://www.irs.gov/instructions/i1040sc) | Self-employment / sole proprietor |
| Form 1040 Schedule D (Capital Gains) | [https://www.irs.gov/instructions/i1040sd](https://www.irs.gov/instructions/i1040sd) | Capital gains and losses |
| Form 1040 Schedule E (Pass-through) | [https://www.irs.gov/instructions/i1040se](https://www.irs.gov/instructions/i1040se) | Partnerships, S-corps, trusts |
| Form 8960 (Net Investment Income Tax) | [https://www.irs.gov/instructions/i8960](https://www.irs.gov/instructions/i8960) | NIIT — cross-referenced from Line 17 |
| Form 8812 (Child Tax Credit) | [https://www.irs.gov/instructions/i8812](https://www.irs.gov/instructions/i8812) | CTC/ACTC — cross-referenced from Line 19 |
| Form 8949 (Capital Asset Sales) | [https://www.irs.gov/instructions/i8949](https://www.irs.gov/instructions/i8949) | Feeds into Schedule D |
| Schedule SE (Self-Employment Tax) | [https://www.irs.gov/instructions/i1040sse](https://www.irs.gov/instructions/i1040sse) | Self-employment tax calculation |

**Downloading the pages for offline use:**

```bash
mkdir -p data/instructions/real

# Download each page as a single HTML file (curl follows redirects, saves printable version)
curl -L "https://www.irs.gov/instructions/i1040gi" \
  -H "User-Agent: Mozilla/5.0" \
  -o data/instructions/real/i1040gi_2024.html

curl -L "https://www.irs.gov/instructions/i1040sca" \
  -H "User-Agent: Mozilla/5.0" \
  -o data/instructions/real/i1040sca_2024.html

# Repeat for each form above, then ingest each file:
python cli.py ingest-instructions \
  --html data/instructions/real/i1040gi_2024.html \
  --form-type 1040 \
  --tax-year 2024 \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j --neo4j-password taxflow_dev \
  --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow"
```

> **IRS.gov robots.txt:** The IRS permits automated retrieval of public instruction pages. Keep requests to one page at a time and add a `--delay 2` flag (or `sleep 2`) between downloads to be a considerate client. Do not scrape at bulk rates.

#### Parser adaptation for real HTML

The real IRS instruction pages share the same `h2`/`h3` heading structure as the synthetic file. However, real pages may include:

- Navigation sidebars and breadcrumbs (ignored — the parser only processes `h2`, `h3`, `p`, and `ul`/`li` tags)
- Revision dates in `<div class="field--name-changed-date">` elements (ignored)
- JavaScript-rendered content that does not appear in the raw HTML — use `curl` or `requests`, not a headless browser

If the live page's structure differs significantly, check the V2.1 structural report:

```bash
python cli.py validate-instructions \
  --html data/instructions/real/i1040gi_2024.html \
  --form-type 1040 \
  --tax-year 2024
```

If `SECTION_COUNT` or `LINE_SECTIONS` fail, inspect the raw HTML heading structure:

```bash
grep -E "<h[23]" data/instructions/real/i1040gi_2024.html | head -40
```

Adjust the parser's `_classify_section` logic or heading patterns in `tax_brain/instructions/html_parser.py` as needed.

#### V2.2 coverage on real pages

Real instruction pages cover every line of the form, so V2.2 coverage (≥ 70% of Layer 1 fields linked) should pass easily. If it does not, the most likely cause is a mismatch between the line labels in the HTML (`"Line 1a"`) and the keys in `LINE_TO_FIELDS` in `html_parser.py`. Check the V2.2 report for which fields are uncovered, then add or adjust mappings:

```python
# tax_brain/instructions/html_parser.py — LINE_TO_FIELDS
LINE_TO_FIELDS: dict[str, list[str]] = {
    "1a": ["WagesSalariesTipsAmt"],
    ...
    # Add any new lines found in the real instructions here
}
```

#### Prior-year instruction pages

IRS archives prior-year HTML instructions at:

```
https://www.irs.gov/pub/irs-prior/i1040gi--{YEAR}.pdf
```

Note that archived versions are PDF only. To ingest prior-year instructions, download the PDF, extract text with a PDF parser of your choice, convert it to the expected HTML structure, then run `ingest-instructions`. Alternatively, use the IRS's online instructions viewer, which renders HTML for tax years 2021 and later at the same `/instructions/` path after selecting the year via the page's year-picker widget.

---

### Layer 3 — Real IRS Publication PDFs

The Layer 3 pipeline is designed for the real IRS PDFs. No synthetic data or special conversion is needed.

**Download URLs:**

| Publication | Title | URL |
|-------------|-------|-----|
| Pub 17 | Your Federal Income Tax | https://www.irs.gov/pub/irs-pdf/p17.pdf |
| Pub 501 | Dependents, Standard Deduction | https://www.irs.gov/pub/irs-pdf/p501.pdf |
| Pub 525 | Taxable and Nontaxable Income | https://www.irs.gov/pub/irs-pdf/p525.pdf |
| Pub 550 | Investment Income and Expenses | https://www.irs.gov/pub/irs-pdf/p550.pdf |
| Pub 590-A | IRA Contributions | https://www.irs.gov/pub/irs-pdf/p590a.pdf |
| Pub 590-B | IRA Distributions | https://www.irs.gov/pub/irs-pdf/p590b.pdf |
| Pub 596 | Earned Income Credit | https://www.irs.gov/pub/irs-pdf/p596.pdf |
| Pub 969 | Health Savings Accounts | https://www.irs.gov/pub/irs-pdf/p969.pdf |

**Embedding cost estimate:**

IRS publications typically contain 150–500 pages. With ~400 tokens/chunk and ~3 chunks/page, a typical publication produces 500–1500 chunks. At $0.02/1M tokens with text-embedding-3-small, embedding all 8 publications costs under **$0.10 total**.

**Scanned PDF handling:**

Some older IRS publications are image-based scans. If `parse_publication_pdf()` returns `chunks=[]` with an error message containing "scanned/image-only", the PDF cannot be processed without OCR. Use `tesseract` or the OpenAI vision API to extract text first, then re-run the pipeline. Current publications (2024–2025) are all text-based.

**Adding new publications:**

1. Add the new `pub_number → pub_title` entry to `PUB_TITLES` in `tax_brain/publications/models_layer3.py`.
2. Add the pub_number to `EXPECTED_PUBS` in `tax_brain/publications/validation/v3_2_coverage.py`.
3. Add a retrieval probe to `PROBES` in `tax_brain/publications/validation/v3_3_retrieval.py`.
4. Run `ingest-publications` and `validate-publications` to confirm.

---

## Development Notes

- All database writes use **MERGE / upsert** semantics — re-ingesting the same HTML, CSV, or PDF is idempotent.
- The `rule_version_history` table in PostgreSQL has an append-only trigger: `UPDATE` and `DELETE` are blocked at the database level.
- The HTML parser uses only Python's stdlib `html.parser` — no BeautifulSoup, no lxml, no external dependencies beyond `requirements.txt`.
- For range headings like "Lines 3a–3b", the parser follows IRS convention and registers the *last* line of the range as the primary line reference (3b = ordinary dividends), since that is the field with a data entry.
- The rule engine in `v1_3_test_replay.py` evaluates expressions using a regex-based interpreter and does **not** call `eval()`. IRS rule expressions are not safe to execute as arbitrary Python.
- The V1.2 spot-check uses stratified sampling — at least 10 rules per category are included regardless of total count.
- Layer 3 embedding batches are capped at 512 chunks per OpenAI API call (the API allows up to 2048; 512 is a safe default). Chunks already embedded (non-null embedding) are skipped on re-runs.
- The IVFFlat index (`lists=100`) should be built once after the initial bulk ingest, not after every individual publication update. PostgreSQL will use a sequential scan for cosine queries until the index exists; this is fine for < 10,000 chunks but noticeable above ~100,000 chunks.
- The `v3_3_retrieval.py` probes are designed to be conservative (min_score ≥ 0.50–0.60). If a probe fails on a new publication, first verify the publication was fully embedded (`embedded_count == chunk_count` in `v_pub_coverage`), then check whether the probe's `must_contain` substring appears in any real passage of that publication.
