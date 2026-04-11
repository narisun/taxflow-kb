-- =============================================================================
-- TaxFlow AI — Layer 3: IRS Publications (pgvector semantic search)
-- =============================================================================
-- Apply after postgres_schema.sql and postgres_layer2.sql:
--   docker exec -i taxflow-postgres psql -U taxflow -d taxflow < schema/postgres_layer3.sql
-- =============================================================================

-- pgvector extension (pre-installed in pgvector/pgvector:pg16 image)
CREATE EXTENSION IF NOT EXISTS vector;

-- Ensure the shared schema exists (also created by postgres_schema.sql,
-- but we guard here so Layer 3 can be applied standalone after a fresh container)
CREATE SCHEMA IF NOT EXISTS irs_kb;

-- =============================================================================
-- Publications registry
-- =============================================================================
CREATE TABLE IF NOT EXISTS irs_kb.publications (
    pub_id          TEXT PRIMARY KEY,           -- "p17-2025"
    pub_number      TEXT        NOT NULL,       -- "17", "550", "590a"
    pub_title       TEXT        NOT NULL,
    tax_year        INT         NOT NULL,
    source_path     TEXT,
    pdf_hash        TEXT,
    page_count      INT,
    chunk_count     INT         DEFAULT 0,
    embedded_count  INT         DEFAULT 0,
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    embedded_at     TIMESTAMPTZ
);

-- =============================================================================
-- Publication chunks (text + vector)
-- =============================================================================
CREATE TABLE IF NOT EXISTS irs_kb.publication_chunks (
    chunk_id        TEXT PRIMARY KEY,           -- "p17-2025::0042"
    pub_id          TEXT        NOT NULL REFERENCES irs_kb.publications(pub_id)
                                ON DELETE CASCADE,
    pub_number      TEXT        NOT NULL,
    tax_year        INT         NOT NULL,
    chunk_index     INT         NOT NULL,
    chapter_title   TEXT,
    section_title   TEXT,
    page_start      INT,
    page_end        INT,
    text            TEXT        NOT NULL,
    token_count     INT,
    form_refs       TEXT[]      DEFAULT '{}',
    line_refs       TEXT[]      DEFAULT '{}',
    chunk_type      TEXT        DEFAULT 'detail'
                                CHECK (chunk_type IN ('pub_summary', 'section_summary', 'detail')),
    topic_ids       TEXT[]      DEFAULT '{}',
    embedding       vector(1536),               -- text-embedding-3-large (1536-dim)
    embedded_at     TIMESTAMPTZ,
    UNIQUE (pub_id, chunk_index)
);

-- =============================================================================
-- Indexes
-- =============================================================================

-- GIN indexes for array filtering (find chunks that mention a specific form/line)
CREATE INDEX IF NOT EXISTS idx_chunks_form_refs
    ON irs_kb.publication_chunks USING GIN(form_refs);

CREATE INDEX IF NOT EXISTS idx_chunks_line_refs
    ON irs_kb.publication_chunks USING GIN(line_refs);

CREATE INDEX IF NOT EXISTS idx_chunks_pub_id
    ON irs_kb.publication_chunks (pub_id);

CREATE INDEX IF NOT EXISTS idx_chunks_pub_chapter
    ON irs_kb.publication_chunks (pub_id, chapter_title);

-- Hierarchical retrieval: filter by chunk_type (pub_summary, section_summary, detail)
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_type
    ON irs_kb.publication_chunks (chunk_type);

-- Composite index for hierarchical nav: pub + chunk_type
CREATE INDEX IF NOT EXISTS idx_chunks_pub_type
    ON irs_kb.publication_chunks (pub_id, chunk_type);

-- Topic ontology: GIN index for topic_ids array filtering
CREATE INDEX IF NOT EXISTS idx_chunks_topic_ids
    ON irs_kb.publication_chunks USING GIN(topic_ids);

-- IVFFlat ANN index for fast cosine similarity search.
-- lists=100 is appropriate for up to ~1M chunks; rebuild with larger lists if
-- chunk_count grows significantly.  Requires at least one row to be inserted
-- before the index can be built — the ingestion CLI handles this automatically.
-- CREATE INDEX idx_chunks_embedding
--     ON irs_kb.publication_chunks USING ivfflat(embedding vector_cosine_ops)
--     WITH (lists = 100);
-- (Uncomment and run AFTER first ingestion batch is complete)

-- =============================================================================
-- Ingestion log
-- =============================================================================
CREATE TABLE IF NOT EXISTS irs_kb.pub_ingestion_log (
    log_id          BIGSERIAL   PRIMARY KEY,
    pub_id          TEXT,
    action          TEXT        NOT NULL,       -- "parse", "embed", "upsert"
    chunk_count     INT         DEFAULT 0,
    duration_ms     INT,
    error_msg       TEXT,
    logged_at       TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- Validation run log
-- =============================================================================
CREATE TABLE IF NOT EXISTS irs_kb.layer3_validation_runs (
    run_id          BIGSERIAL   PRIMARY KEY,
    gate            TEXT        NOT NULL,       -- "V3.1", "V3.2", "V3.3"
    pub_id          TEXT,
    passed          BOOLEAN     NOT NULL,
    total_checked   INT,
    total_passed    INT,
    total_failed    INT,
    notes           JSONB,
    run_at          TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- Convenience views
-- =============================================================================

-- Per-publication chunk and embedding counts
-- DROP + CREATE required: PostgreSQL cannot rename view columns via CREATE OR REPLACE.
DROP VIEW IF EXISTS irs_kb.v_pub_coverage CASCADE;
CREATE VIEW irs_kb.v_pub_coverage AS
SELECT
    p.pub_id,
    p.pub_number,
    p.pub_title,
    p.tax_year,
    p.page_count,
    p.chunk_count,
    p.embedded_count,
    ROUND(
        CASE WHEN p.chunk_count > 0
             THEN p.embedded_count::numeric / p.chunk_count * 100
             ELSE 0 END, 1
    ) AS embed_pct,
    ROUND(COALESCE(
        (SELECT AVG(c.token_count)
         FROM irs_kb.publication_chunks c
         WHERE c.pub_id = p.pub_id), 0
    ), 1) AS avg_token_count,
    p.ingested_at,
    p.embedded_at
FROM irs_kb.publications p
ORDER BY p.pub_number;

-- Chunks that reference a specific form line (for agent retrieval)
CREATE OR REPLACE VIEW irs_kb.v_line_chunks AS
SELECT
    c.chunk_id,
    c.pub_number,
    c.chapter_title,
    c.section_title,
    c.page_start,
    line_ref,
    c.text
FROM irs_kb.publication_chunks c,
     UNNEST(c.line_refs) AS line_ref
WHERE c.embedding IS NOT NULL
ORDER BY c.pub_number, line_ref, c.chunk_index;
