-- =============================================================================
-- TaxFlow AI — Knowledge Base Layer 2 Schema
-- IRS HTML Instruction Graph — PostgreSQL tables
-- Run via: python cli.py ingest-instructions --init-schema
-- or:      docker exec -i taxflow-postgres psql -U taxflow -d taxflow < schema/postgres_layer2.sql
-- =============================================================================

SET search_path TO irs_kb, public;

-- ─── Instruction pages ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS instruction_pages (
    page_id             TEXT        NOT NULL,
    form_type           TEXT        NOT NULL,
    tax_year            SMALLINT    NOT NULL,
    title               TEXT        NOT NULL,
    source_url          TEXT        NOT NULL DEFAULT '',
    html_hash           CHAR(64)    NOT NULL,          -- SHA-256 hex
    section_count       INTEGER     NOT NULL DEFAULT 0,
    line_section_count  INTEGER     NOT NULL DEFAULT 0,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_instruction_pages PRIMARY KEY (page_id),
    CONSTRAINT uq_instruction_page  UNIQUE (form_type, tax_year)
);

COMMENT ON TABLE instruction_pages IS
  'One row per IRS instruction HTML publication (e.g. i1040gi for TY 2024).';

-- ─── Instruction sections ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS instruction_sections (
    section_id      TEXT        NOT NULL,
    page_id         TEXT        NOT NULL REFERENCES instruction_pages(page_id),
    heading         TEXT        NOT NULL,
    section_type    TEXT        NOT NULL,              -- SectionType enum value
    level           SMALLINT    NOT NULL,              -- 1=h2  2=h3
    sequence        INTEGER     NOT NULL,
    anchor          TEXT,                              -- HTML id attribute
    line_reference  TEXT,                              -- "1a", "2b", "12", etc.
    field_names     TEXT[]      NOT NULL DEFAULT '{}', -- FormLine short_field values
    text_content    TEXT        NOT NULL DEFAULT '',
    cross_refs      TEXT[]      NOT NULL DEFAULT '{}',
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_instruction_sections PRIMARY KEY (section_id),
    CONSTRAINT uq_instruction_section  UNIQUE (page_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_isec_page_id
    ON instruction_sections (page_id);

CREATE INDEX IF NOT EXISTS idx_isec_line_ref
    ON instruction_sections (line_reference)
    WHERE line_reference IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_isec_field_names
    ON instruction_sections USING GIN (field_names);

CREATE INDEX IF NOT EXISTS idx_isec_cross_refs
    ON instruction_sections USING GIN (cross_refs);

-- Full-text search on instruction content
CREATE INDEX IF NOT EXISTS idx_isec_fts
    ON instruction_sections
    USING GIN (to_tsvector('english', heading || ' ' || text_content));

COMMENT ON TABLE instruction_sections IS
  'One row per h2/h3 section parsed from an IRS instruction HTML page.';

-- ─── Instruction ingestion log ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS instruction_ingestion_log (
    log_id          BIGSERIAL   NOT NULL,
    page_id         TEXT        NOT NULL,
    html_hash       CHAR(64)    NOT NULL,
    source_path     TEXT        NOT NULL,
    section_count   INTEGER     NOT NULL,
    explains_count  INTEGER     NOT NULL DEFAULT 0,
    form_refs_count INTEGER     NOT NULL DEFAULT 0,
    parse_success   BOOLEAN     NOT NULL,
    errors          TEXT[]      NOT NULL DEFAULT '{}',
    warnings        TEXT[]      NOT NULL DEFAULT '{}',
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_instruction_log PRIMARY KEY (log_id)
);

COMMENT ON TABLE instruction_ingestion_log IS
  'Audit trail for each instruction HTML ingestion run.';

-- ─── Layer 2 validation runs ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS layer2_validation_runs (
    run_id          BIGSERIAL   NOT NULL,
    step            TEXT        NOT NULL,  -- "V2.1-STRUCTURAL", "V2.2-LINK-COVERAGE"
    page_id         TEXT,
    passed          BOOLEAN     NOT NULL,
    total_checked   INTEGER     NOT NULL DEFAULT 0,
    total_passed    INTEGER     NOT NULL DEFAULT 0,
    total_failed    INTEGER     NOT NULL DEFAULT 0,
    failures        JSONB       NOT NULL DEFAULT '[]',
    notes           TEXT[]      NOT NULL DEFAULT '{}',
    run_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_layer2_validation PRIMARY KEY (run_id)
);

COMMENT ON TABLE layer2_validation_runs IS
  'Layer 2 validation gate results (V2.1 structural, V2.2 link coverage).';

-- ─── Convenience views ────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_line_sections AS
SELECT
    s.section_id,
    s.page_id,
    p.form_type,
    p.tax_year,
    s.line_reference,
    s.field_names,
    s.heading,
    LEFT(s.text_content, 200) AS text_excerpt,
    array_length(s.cross_refs, 1) AS cross_ref_count
FROM instruction_sections s
JOIN instruction_pages     p ON p.page_id = s.page_id
WHERE s.line_reference IS NOT NULL
ORDER BY p.form_type, p.tax_year, s.sequence;

COMMENT ON VIEW v_line_sections IS
  'All instruction sections that map to a Form 1040 line number.';

CREATE OR REPLACE VIEW v_field_instruction_coverage AS
SELECT
    unnest(s.field_names) AS field_name,
    COUNT(*)               AS section_count,
    array_agg(s.section_id ORDER BY s.sequence) AS section_ids
FROM instruction_sections s
GROUP BY 1
ORDER BY 1;

COMMENT ON VIEW v_field_instruction_coverage IS
  'How many instruction sections explain each FormLine field.';
