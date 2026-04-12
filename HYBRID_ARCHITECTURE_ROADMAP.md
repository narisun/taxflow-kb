# TaxFlow AI — Hybrid Architecture Analysis & Roadmap

**Date:** April 2026  
**Current baseline:** HR@10 = 69.4%, Generation pass rate = 41.2%, Faithfulness avg = 2.75

---

## Part 1 — Where We Stand Against the Three IRS Data Layers

The research framework describes three structurally distinct IRS data sources, each requiring a different retrieval paradigm. Here is an honest map of what exists in the codebase today versus what is wired into the live query path.

---

### Layer 1 — MeF Business Rules (Structured CSV)

**What it is:** The IRS Modernized e-File (MeF) schema ships as XML/CSV describing every field-level validation rule — data types, required fields, cross-field conditionals, error codes, reject reasons. These are the rules that decide whether a return will be accepted or rejected at submission time. No NLP is needed to query them: a CPA asking "what error code fires when Schedule C Line 7 is blank?" needs an exact lookup, not a cosine similarity.

**What is built:**
- `tax_brain/rules/csv_parser.py` — full MeF CSV parser with column-alias normalization, produces `MeFRule` objects with `rule_id`, `form_family`, `field_path`, `rule_type`, `severity`, `error_code`, `rule_text`, and a parsed AST of the rule expression.
- `tax_brain/rules/neo4j_ingestion.py` — full Neo4j ingestion with `Form`, `FormLine`, `Rule`, `ErrorCode` nodes and `GOVERNED_BY` / `RAISES` / `SUPERSEDES` relationships. Handles schema version diffing.
- Neo4j schema is designed: `(:FormLine)-[:GOVERNED_BY]->(:Rule)-[:RAISES]->(:ErrorCode)`.

**What is NOT wired:**
- `MultiLayerRetriever.retrieve()` has a comment `# TODO: if query references a specific form/field, keyword-search mef_rules` but no implementation.
- No query classifier exists to detect "this question is about a specific form field / error code."
- The Neo4j database may be empty — no CLI command ingests MeF data.

**Gap severity:** High. A substantial fraction of CPA queries are compliance questions ("will this return reject?", "what error fires for X?") that Layer 3 publications cannot answer reliably. The code exists; it just needs wiring.

---

### Layer 2 — HTML Form Instructions (Parseable, Line-Numbered)

**What it is:** IRS.gov publishes HTML instructions for every form — 1040, Schedule A/B/C/D/E/SE, 8889, 8606, etc. These are semi-structured: each line of the form has a dedicated section with cross-references to other lines, schedules, and publications. They sit between Layer 1 (pure rules) and Layer 3 (policy prose) — they are the "how to fill in this line" layer.

**What is built:**
- `tax_brain/instructions/html_parser.py` — full IRS HTML instruction parser, handles both synthetic and real irs.gov HTML. Extracts `InstructionSection` objects with `line_reference`, `field_names`, `cross_refs`, `section_type` (line-instruction, general, definition, cross-reference). Has a `LINE_TO_FIELDS` map covering 1040 lines 1a through 38.
- `tax_brain/instructions/postgres_layer2.py` — PostgreSQL persistence for instruction sections (not pgvector; relational structure).
- `tax_brain/instructions/neo4j_layer2.py` — Neo4j ingestion: `InstructionPage`, `InstructionSection` nodes with `HAS_SECTION`, `EXPLAINS`, `SEE_ALSO`, `REFERENCES_FORM` relationships.
- `tax_brain/instructions/validation/` — structural and link-coverage validators.

**What is NOT wired:**
- `MultiLayerRetriever` has `# TODO: if query references a form line, query Neo4j instruction graph` but no implementation.
- No CLI command ingests HTML instruction data into Neo4j.
- No retrieval path exists that fetches an `InstructionSection` in response to a form-line query.
- Layer 2 and Layer 1 Neo4j sub-graphs are **disconnected** — `FormLine` nodes exist in both but have no cross-layer edges linking them.

**Gap severity:** High. Form-line questions ("what goes on Schedule E line 28?", "how does 1040 line 11 interact with Form 8582?") need the instruction graph — Layer 3 publications give policy context but not precise line-by-line filing guidance.

---

### Layer 3 — IRS Publications (PDF / Policy Layer)

**What it is:** The IRS publishes ~200 guidance documents covering tax law interpretation, eligibility rules, worksheets, and examples. These are the "why" layer — they explain what the rules mean, not just how to fill in a form. This is where most CPAs go for nuanced questions.

**What is built:** This layer is the most complete.

- `tax_brain/publications/pdf_parser.py` — PDF ingestion with **sliding-window chunking** (400-token target, 50-token overlap). Extracts chapter/section metadata.
- `tax_brain/publications/postgres_layer3.py` — PostgreSQL + pgvector store with `irs_kb.publications` and `irs_kb.publication_chunks` tables. `search_similar()` with cosine distance and IVFFlat ANN index.
- `tax_brain/publications/embeddings.py` — OpenAI `text-embedding-3-large` at 1536 dims (Matryoshka truncation).
- `tax_brain/publications/chunk_enrichment.py` — Pre-embedding NL summary prepended to Pub 596 worksheet/table chunks and Pub 525 topic-tagged chunks.
- `tax_brain/agent/retriever.py` — `Layer3Retriever` fully implemented; `MultiLayerRetriever` orchestrator exists but only calls Layer 3.
- `tax_brain/agent/synthesizer.py` — GPT-4o generation with tiered abstention, citation enforcement, and per-source Pub XXX fix.
- `tax_brain/evaluation/` — full evaluation pipeline: gold set (102 questions, 8 publications), retrieval evaluator, generation evaluator with LLM-as-judge.

**Ingested publications:** Pub 17, 501, 525, 550, 590-A, 590-B, 596, 969.

**Current evaluation results:**

| Publication | Hit Rate @10 | Pass Rate | Avg Score | Key Issue |
|-------------|-------------|-----------|-----------|-----------|
| Pub 501     | ~85%        | 75%       | 3.92      | Strong |
| Pub 550     | ~70%        | ~58%      | 3.4       | Good |
| Pub 596     | ~60%        | 60%       | 3.3       | Worksheet retrieval improving |
| Pub 590-A/B | ~75%        | ~55%      | 3.2       | Acceptable |
| Pub 969     | ~65%        | ~53%      | 3.1       | Acceptable |
| Pub 525     | ~40%        | 21%       | 2.5       | Diverse topics — retrieval miss |
| Pub 17      | ~77%        | 23%       | 2.0       | **Knowledge contamination** |
| **Overall** | **69.4%**   | **41.2%** | **3.02**  | Gate: faithfulness AND citation both ≥ 3 |

**Two root causes of the 41.2% ceiling:**

1. **Pub 17 knowledge contamination.** Pub 17 covers the entire federal tax code, so the model's pre-training heavily overlaps with its content. When retrieved excerpts are from Pub 17, the model adds memorized general tax knowledge that the specific excerpt doesn't support, causing faithfulness scores of 1–2.

2. **Retrieval gap before generation.** At HR@10 = 69.4%, 30.6% of questions don't have the answer chunk in the top-10 results. No amount of generation improvement can fix a retrieval miss.

---

## Part 2 — External Analysis: What to Adopt vs. What We Have

An external review of this architecture proposed a "Tax-Brain" approach. This section evaluates each idea against our codebase and classifies it as: **adopt** (genuinely new value), **already built**, or **deprioritize** (real but low impact-to-effort ratio now).

---

### Idea 1 — `FLOWS_TO` Edges Between LineItems [ADOPT — high priority]

**The proposal:** A `(:FormLine)-[:FLOWS_TO*]->(:FormLine)` DAG tracing how values move through the return. Example: K-1 Box 1 → Schedule E Line 1 → Schedule E Line 41 → 1040 Line 5. Enables graph traversal queries using variable-length path matching.

**Why this is genuinely new:** Our current schema has `FormLine` nodes but **zero edges between them**. The Layer 1 graph links FormLine to Rule; the Layer 2 graph links InstructionSection to FormLine — but no graph records how a dollar amount flows from one form to another. This is the core capability needed for multi-hop compliance questions. Vector search fundamentally cannot answer "where does partnership income from a K-1 ultimately land on the 1040?" — the K-1 and 1040 embeddings are far apart in vector space despite being causally connected.

**How to build it:** The flows are not derivable from CSV or HTML; they are structural facts about tax law. The right approach is a curated seed file (`data/flows/form_flows_2024.json`) authored manually for the ~40 highest-frequency flows (K-1, Schedule C, Schedule D, 8889, 8606, etc.), then extended via LLM-assisted extraction from the publication text ("amounts from Schedule C, line 31, go to Form 1040, Schedule 1, line 3"). Cypher MERGE is idempotent, so the seed can be grown incrementally.

```cypher
// Seed example
MERGE (a:FormLine {form_type: 'ScheduleK1', short_field: 'Box1', tax_year: 2024})
MERGE (b:FormLine {form_type: 'ScheduleE',  short_field: 'Line28a', tax_year: 2024})
MERGE (a)-[:FLOWS_TO {description: 'Ordinary business income', condition: 'passive or active'}]->(b)
```

The variable-length `[:FLOWS_TO*1..3]` traversal then enables the "trace the money" query type:

```cypher
MATCH path = (src:FormLine {form_type: $start_form, short_field: $start_line, tax_year: $year})
             -[:FLOWS_TO*1..4]->(dst:FormLine)
RETURN [node in nodes(path) | node.form_type + ' ' + node.short_field] AS flow_path,
       [rel  in rels(path)  | rel.description] AS descriptions
```

**Text-to-Cypher integration:** For "flow" questions, the query classifier detects intent ("where does X flow", "trace X", "how does X get to the 1040") and the `MultiLayerRetriever` generates a Cypher traversal query via GPT-4o rather than doing vector search. The generated Cypher is validated (parameter injection guard) and executed against Neo4j. The result — a structured flow path — is passed to the synthesizer as a `layer=1` context with `source_type="flow_graph"`.

---

### Idea 2 — Cross-Layer Bridge Edges [ADOPT — high priority]

**The proposal:** `(:FormLine)-[:EXPLAINED_BY]->(:InstructionSection)` and `(:InstructionSection)-[:COVERS_TOPIC]->(:Concept)` to make the two disconnected sub-graphs into a single traversable network.

**Why this is genuinely new:** Our Layer 1 and Layer 2 ingestion pipelines both create `FormLine` nodes independently, but they are separate islands. A query retrieving a Layer 1 `Rule` node has no way to automatically pull the Layer 2 instruction text that explains how to satisfy that rule. The bridge edges are the "handshake" that makes the graph multi-layer rather than multi-silo.

**How to build it:** When ingesting Layer 2, add a post-ingestion step that creates `EXPLAINED_BY` relationships by matching on `(form_type, short_field, tax_year)` — the natural join key that already exists on both `FormLine` node types. Since Layer 2 ingestion already extracts `field_names` from each `InstructionSection`, this is a matter of running:

```cypher
MATCH (s:InstructionSection {page_id: $page_id})
WHERE $field IN s.field_names
MATCH (fl:FormLine {form_type: $form_type, short_field: $field, tax_year: $tax_year})
MERGE (fl)-[:EXPLAINED_BY]->(s)
```

The `COVERS_TOPIC` edge (InstructionSection → Concept) requires entity extraction and is part of Phase 5. But `EXPLAINED_BY` can be created during Phase 4 Layer 2 ingestion at zero additional cost.

---

### Idea 3 — Semantic Chunking by Section Type [ADOPT — medium priority]

**The proposal:** Instead of fixed sliding-window chunking (our current 400-token / 50-overlap scheme), chunk IRS publications by semantic section boundaries: "Example N", "Safe Harbor", "Exception", "Worksheet N", "Rule", "Definition."

**Why this is genuinely new:** Our current chunker already extracts chapter/section headings, but it still splits on token count within a section. This means a single "Example 3" narrative can be split across two chunks, with the question context in one chunk and the answer in the next. Our gold set evaluation confirmed this: six gold questions referencing specific named examples ("In Example 28…") had near-zero retrieval hit rate because the example text was split at a token boundary.

**How to build it:** Add a `semantic_chunker()` path to `pdf_parser.py` that detects section-type markers using the existing regex patterns:

```python
_EXAMPLE_RE  = re.compile(r"^Example\s+\d+", re.I | re.M)
_WORKSHEET_RE= re.compile(r"^Worksheet\s+\d+", re.I | re.M)
_EXCEPTION_RE= re.compile(r"^Exception[\.\s]", re.I | re.M)
_SAFEHARBOR_RE = re.compile(r"safe\s+harbor", re.I)
```

When a section-type marker is detected, always start a new chunk at that boundary regardless of token count. Chunks that overflow HARD_MAX (512 tokens) are then split by the existing token-based splitter as a fallback. A new column `chunk_type` (`prose`, `example`, `worksheet`, `exception`, `definition`) is added to `publication_chunks` and used as a retrieval filter: when a question references a specific example, restrict the search to `chunk_type = 'example'`.

This directly fixes the "Example 28" gold set failure and the Pub 596 worksheet retrieval problem without changing the embedding model.

---

### Idea 4 — Chain of Trust Citation Format [ADOPT — medium priority]

**The proposal:** Every answer should include a three-tier citation: Logic source (MeF Rule ID), Instruction source (Form, page), Policy source (Publication, chapter).

**Why this matters:** Our current `citation_accuracy` metric treats all citations equally. For CPAs, the citation hierarchy matters enormously — a MeF Rule citation is authoritative proof that a return will reject, while a Publication citation is interpretive guidance. Showing all three tiers for a single answer (when available) significantly increases professional trust and directly improves our `citation_accuracy` score.

**How to build it:** Add a `CitationChain` model to `models_layer4.py` and populate it in the synthesizer based on which layers contributed context:

```python
class CitationChain(BaseModel):
    mef_rule: Optional[str]       = None  # e.g. "R-1040-001 (MeF v12.3)"
    instruction: Optional[str]   = None  # e.g. "Form 1040 Instructions, p.14"
    publication: Optional[str]   = None  # e.g. "Pub 550, Chapter 2"

class AgentResponse(BaseModel):
    answer: str
    citations: list[CitationChain]   # replaces flat citations list
    confidence: float
    abstained: bool
```

The synthesizer system prompt instructs the model to populate all three tiers when their contexts are provided.

---

### Idea 5 — LLM-Assisted Condition Extraction for Layer 2 [ADOPT — lower priority]

**The proposal:** When parsing HTML instructions, use an LLM pass to extract conditional edges ("If you are a qualifying widow, see page 12") and store them as typed relationships in the instruction graph.

**Why this is new:** Our current `html_parser.py` extracts `cross_refs` as a list of form/section references but doesn't parse their conditions. A conditional edge (`-[:SEE_ALSO {condition: "qualifying_widow"}]->`) enables conditional routing: when the user query mentions "qualifying widow", the retriever follows the conditional branch to retrieve the targeted section.

**Why it's lower priority:** This adds genuine value but requires a post-parsing LLM call for every `InstructionSection` (~500+ sections across all forms). At ~$0.001 per section, this is cheap but adds latency to the ingestion pipeline. The benefit is incremental given that the unconditional graph already surfaces most of the right sections. Planned for Phase 5, after the core graph is built and populated.

---

### Idea 6 — Domain-Specific Embedding Model (ColBERT / fine-tuned RoBERTa) [DEPRIORITIZE]

**The proposal:** Replace `text-embedding-3-large` with a domain-specific model — either late-interaction ColBERT or a fine-tuned RoBERTa on IRS text.

**Why we deprioritize this now:** `text-embedding-3-large` went from HR@10=44% to 69.4% after we upgraded from `text-embedding-3-small`. The remaining retrieval gap is better addressed by BM25 hybrid (Phase 1) and semantic chunking (Phase 3 addition) before we invest in model fine-tuning. Fine-tuning a tax-domain embedding model requires labeled retrieval pairs (question → correct chunk) — our gold set has 102 pairs, which is too few for reliable fine-tuning (typically need 1,000+). Revisit after Phase 1 if BM25 hybrid + semantic chunking leave meaningful retrieval headroom.

---

## Part 3 — Updated Target Architecture

```
CPA Question
     │
     ▼
┌─────────────────────────────────────────────────────┐
│           Query Classifier / Router                  │
│  • Extracts: form numbers, line refs, error codes   │
│  • Detects intent: flow | lookup | policy | filing  │
│  • Tags: layer1_hit | layer2_hit | layer3_hit        │
│  • Detects: "flow/trace" → Text-to-Cypher path      │
└───────┬───────────────┬───────────────┬─────────────┘
        │               │               │
  Flow Query       Form Line        Policy Query
  (Text-to-Cypher) (Layer 2 graph)  (Layer 3 vector+BM25)
        │               │               │
 Neo4j FLOWS_TO    InstructionSection  pgvector cosine
 traversal         -[EXPLAINED_BY]-   + BM25 tsvector
                   FormLine           + chunk_type filter
        │               │               │
        └───────────────┴───────────────┘
                        │
                  ┌─────▼──────┐
                  │    RRF     │  Reciprocal Rank Fusion
                  │  Merger    │  across all result lists
                  └─────┬──────┘
                        │
                  ┌─────▼──────────────────┐
                  │  GPT-4o Synthesizer    │
                  │  • verbatim grounding  │
                  │  • CitationChain model │
                  │  • three-tier citation │
                  └────────────────────────┘
```

The Neo4j graph is now a **unified, cross-layer graph** rather than three disconnected sub-graphs:

```
(:Form)-[:HAS_LINE]->(:FormLine)-[:GOVERNED_BY]->(:Rule)-[:RAISES]->(:ErrorCode)
                         │
                    [:FLOWS_TO]          ← NEW: data flow DAG
                         │
                    (:FormLine)
                         │
                    [:EXPLAINED_BY]      ← NEW: cross-layer bridge
                         │
               (:InstructionSection)-[:COVERS_TOPIC]->(:Concept)
                         │
                    [:SEE_ALSO {condition}]  ← NEW: conditional edges
                         │
               (:InstructionSection)
```

---

## Part 4 — Implementation Roadmap

Phases are ordered by impact-to-effort. Each phase is independently shippable. Phases 1 and 2 require no new infrastructure.

---

### Phase 1 — BM25 Hybrid Retrieval (1–2 days)

**What to build:**

**Step 1.1 — Add tsvector column to `publication_chunks`**

```sql
ALTER TABLE irs_kb.publication_chunks
    ADD COLUMN IF NOT EXISTS text_tsvector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_chunks_fts
    ON irs_kb.publication_chunks USING GIN (text_tsvector);
```

The `GENERATED ALWAYS AS ... STORED` pattern means Postgres maintains the index automatically on every upsert — no application-layer plumbing needed.

**Step 1.2 — `BM25Retriever` class in `tax_brain/agent/retriever.py`**

Uses `plainto_tsquery` for query parsing and `ts_rank_cd` with normalization flag `32` (rank ÷ document length) — the closest Postgres approximation to BM25. Shares the same `Layer3Store` connection pool as the vector retriever.

**Step 1.3 — Reciprocal Rank Fusion in `MultiLayerRetriever`**

RRF score for each candidate: `Σ 1/(60 + rank_i)` across the vector and BM25 result lists. Parameter-free, no tuning required.

**Step 1.4 — CLI migration command:** `python cli.py add-bm25-index --pg-dsn "..."`

**Expected impact:** HR@10 estimated +5–12 pts → ~75–81%. Pub 525 in particular benefits because its diverse income types are exact-string matches.

---

### Phase 2 — Fix Pub 17 Knowledge Contamination (1 day)

**What to build:** A `verbatim_grounding` mode in `Synthesizer` activated when Pub 17 contexts are present. Adds a hard constraint block to the system prompt and drops temperature to 0.0.

```
VERBATIM GROUNDING MODE:
- Every sentence in your answer MUST be directly derivable from the excerpts below.
- Do NOT add tax knowledge you know independently.
- A shorter, fully-grounded answer is better than a longer answer that mixes
  excerpt content with background knowledge.
```

**Expected impact:** Pub 17 pass rate: 23% → estimated 50–60%. Overall: 41.2% → ~49–52%.

---

### Phase 3 — Semantic Chunking (3–4 days)

**What to build:**

**Step 3.1 — Section-type-aware chunker in `pdf_parser.py`**

Detect structural markers (`Example N`, `Worksheet N`, `Exception`, `Safe Harbor`, `Definition`) and always start a new chunk at those boundaries. Add `chunk_type` column to `publication_chunks`.

**Step 3.2 — Re-ingest affected publications**

Pub 596 (worksheets), Pub 525 (examples), Pub 590-B (RMD tables) benefit most. Run `python cli.py ingest-pub --pub 596 --force` etc.

**Step 3.3 — Add `chunk_type` filter to retrieval**

When the query classifier detects an example reference ("In Example X", "in the case where"), restrict `search_similar()` to `chunk_type IN ('example', 'worksheet')`.

**Expected impact:** Fixes the named-example retrieval miss that removed 6 gold set questions. Pub 525 pass rate should improve significantly.

---

### Phase 4 — Layer 1 MeF Rule Integration (1–2 weeks)

**What to build:**

**Step 4.1 — MeF data ingestion CLI command**

`python cli.py ingest-mef --csv data/mef/rules_2024.csv --neo4j-uri bolt://... --tax-year 2024`

Pipes `csv_parser.py → Neo4jIngestion.ingest()`. Already coded; needs CLI wrapper.

**Step 4.2 — Seed `FLOWS_TO` edges** ← *new from external review*

Author `data/flows/form_flows_2024.json` covering the ~50 highest-frequency flows:
- K-1 Box 1 → Schedule E Line 28
- Schedule E Line 41 → 1040 Schedule 1 Line 5
- Schedule C Line 31 → 1040 Schedule 1 Line 3
- 8889 Line 13 → 1040 Schedule 1 Line 13
- 8606 Line 15c → 1040 Line 4b
- etc.

Each flow entry: `{from_form, from_line, to_form, to_line, description, condition}`. Ingestion merges into Neo4j on startup.

**Step 4.3 — Query classifier for Layer 1 routing**

Regex signals for MeF rules: `\berror\s+code\b`, `\breject\b`, `\bMeF\b`, `\be-?file\b.*\bvalidat`. Signals for flow queries: `\bwhere\s+does\b`, `\bflows?\s+to\b`, `\btrace\b`, `\bultimat\w+\s+(?:land|go)\b`.

**Step 4.4 — `Layer1Retriever` with two modes**

Mode A (rule lookup): Cypher exact match on `FormLine → Rule` by form/field extracted from query.

Mode B (flow traversal): Text-to-Cypher for flow questions. GPT-4o mini generates the Cypher given the query and the graph schema. Validated before execution (no `DELETE`/`MERGE`/`SET` allowed in generated queries — read-only guard).

**Expected impact:** Enables a new class of compliance question currently returning "INSUFFICIENT CONTEXT."

---

### Phase 5 — Layer 2 Instruction Graph Integration (1 week)

**What to build:**

**Step 5.1 — HTML instruction ingestion CLI command**

`python cli.py ingest-instructions --html-dir data/instructions/ --neo4j-uri bolt://... --tax-year 2024`

Pipes `html_parser.py → Neo4jLayer2Ingestion.ingest()`.

**Step 5.2 — Cross-layer bridge edges** ← *new from external review*

Post-ingestion step in `Neo4jLayer2Ingestion.ingest()`: after upserting all `InstructionSection` nodes, create `EXPLAINED_BY` relationships to matching `FormLine` nodes using the `(form_type, short_field, tax_year)` join key.

```cypher
MATCH (s:InstructionSection {page_id: $page_id})
UNWIND s.field_names AS field
MATCH (fl:FormLine {form_type: $form_type, short_field: field, tax_year: $tax_year})
MERGE (fl)-[:EXPLAINED_BY]->(s)
```

This unifies the Layer 1 and Layer 2 sub-graphs at zero additional infrastructure cost.

**Step 5.3 — `Layer2Retriever` class**

Queries the instruction graph for form-line questions. Follows `EXPLAINED_BY` from `FormLine`, then optionally follows `SEE_ALSO` edges for related sections. Returns `RetrievedContext` with `layer=2, source_type="instruction_section"`.

**Step 5.4 — Wire into `MultiLayerRetriever`**

Replace the `# TODO: Layer 2` comment with a call to `Layer2Retriever` when the form-line classifier fires.

---

### Phase 6 — Knowledge Graph for Layer 3 (3–4 weeks)

**What to build:**

**Step 6.1 — Entity extraction pipeline**

For each publication chunk: extract Concepts, Form references, Publication cross-references, Dollar thresholds, IRC citations using GPT-4o-mini with structured output. Estimated cost: ~$15–25 for all 8 publications.

**Step 6.2 — Neo4j schema extension**

```
(:Concept {name, canonical_name, pub_number, tax_year})
(:Threshold {concept, amount, currency, year, filing_status})
(:IRSCode {section, title})
(:Chunk)-[:DEFINES]->(:Concept)
(:Chunk)-[:REFERENCES_FORM_LINE]->(:FormLine)    ← bridges to Layers 1 & 2
(:Concept)-[:SUBJECT_TO]->(:IRSCode)
(:InstructionSection)-[:COVERS_TOPIC]->(:Concept) ← NEW from external review
```

**Step 6.3 — Graph-expansion retrieval**

After vector search finds the top-5 chunks, follow outgoing edges (`:REFERENCES_FORM_LINE`, `:DEFINES`, `:REFERENCES_PUB`) to pull first-hop neighbors. This is the "retrieve then expand" GraphRAG pattern.

**Step 6.4 — LLM-assisted condition extraction for Layer 2** ← *from external review*

Post-parse LLM call to extract conditional `SEE_ALSO` edges ("If qualifying widow, see page 12" → `condition: "qualifying_widow"`). Enables conditional routing in graph traversal.

---

### Phase 7 — Chain of Trust Citation Format (1 day, concurrent with Phase 5+)

**What to build:** New `CitationChain` Pydantic model and updated synthesizer system prompt instructing the model to populate all three citation tiers when context from multiple layers is provided.

```python
class CitationChain(BaseModel):
    mef_rule:    Optional[str] = None  # "R-1040-001 (MeF v12.3)"
    instruction: Optional[str] = None  # "Form 1040 Instructions, p.14"
    publication: Optional[str] = None  # "Pub 550, Chapter 2"
```

Meaningful only after Phase 4 (Layer 1 live) but the model can be written earlier and activated then.

---

### Phase 8 — Evaluation Expansion (ongoing)

As each phase ships:

**Layer 1 gold set:** 20 questions about specific form-field validation and error codes. Must be authored by a human CPA — cannot be auto-generated from publications.

**Layer 2 gold set:** 20 form-line questions ("what documentation is required for Schedule C home office deduction?").

**Flow gold set:** 10 multi-hop questions requiring FLOWS_TO traversal ("Where does partnership income from K-1 Box 1 ultimately flow on the 1040?"). These are the ultimate GraphRAG benchmark.

**Graph retrieval evaluator:** Extends the existing `retrieval_evaluator.py` to measure (a) whether the correct concept node was reached, (b) whether the correct FormLine was linked, (c) hop count.

---

## Part 5 — Summary Timeline

| Phase | Deliverable | Effort | Expected Impact |
|-------|-------------|--------|-----------------|
| 1 | BM25 hybrid + RRF | 1–2 days | HR@10: ~75–81% |
| 2 | Pub 17 verbatim grounding | 1 day | Pass rate: ~49–52% |
| 3 | Semantic chunking | 3–4 days | Pub 525 retrieval fix; example chunks |
| 4 | Layer 1 + FLOWS_TO seeds + Text-to-Cypher | 1–2 weeks | New: compliance + flow questions |
| 5 | Layer 2 + EXPLAINED_BY bridge | 1 week | New: form-line questions; unified graph |
| 6 | Layer 3 knowledge graph + COVERS_TOPIC | 3–4 weeks | Multi-hop reasoning |
| 7 | Chain of Trust citations | 1 day (with Phase 5) | CPA trust + citation_accuracy |
| 8 | Expanded gold sets | Ongoing | Honest benchmarking across all layers |

---

## Part 6 — Immediate Next Steps (this sprint)

1. **Phase 1.1** — SQL migration: add `text_tsvector` generated column and GIN index to `publication_chunks`. One SQL statement, zero downtime.
2. **Write `BM25Retriever`** — ~80 lines, same connection pattern as `Layer3Retriever`.
3. **Wire RRF into `MultiLayerRetriever`** — ~30 lines, replaces `all_contexts = l3_contexts`.
4. **Apply Pub 17 verbatim grounding (Phase 2)** — one system prompt addition, one temperature override.
5. **Run full generation eval on gold_set_v4.json** — confirm new baseline before Phase 3.
6. **Author `data/flows/form_flows_2024.json`** — can be started in parallel; seed the 20 most common flow paths manually while Phases 1–2 run.
