-- =============================================================================
-- TaxFlow AI — IRS Knowledge Base — PostgreSQL Schema
-- Layer 1: MeF Business Rules
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- trigram index for text search

-- =============================================================================
-- Domain: irs_kb
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS irs_kb;
SET search_path TO irs_kb, public;

-- ─── Enumerations ─────────────────────────────────────────────────────────────

CREATE TYPE rule_type   AS ENUM ('MATH', 'REJECT', 'ALERT', 'DATABASE');
CREATE TYPE severity_t  AS ENUM ('ERROR', 'WARNING', 'INFO');
CREATE TYPE change_type AS ENUM ('ADDED', 'MODIFIED', 'REMOVED', 'UNCHANGED');

-- ─── CSV Ingestion Log ────────────────────────────────────────────────────────
-- Records every CSV file ingested: hash, row counts, parse statistics.
-- Append-only — never updated after insert.

CREATE TABLE csv_ingestion_log (
    id              BIGSERIAL PRIMARY KEY,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tax_year        SMALLINT    NOT NULL,
    schema_version  VARCHAR(10) NOT NULL,
    form_family     VARCHAR(20) NOT NULL,
    file_path       TEXT        NOT NULL,
    file_hash       CHAR(64)    NOT NULL,   -- SHA-256
    total_rows      INTEGER     NOT NULL,
    parse_success   INTEGER     NOT NULL,
    parse_failed    INTEGER     NOT NULL,
    null_field_rows INTEGER     NOT NULL DEFAULT 0,
    duplicate_ids   TEXT[]      NOT NULL DEFAULT '{}',
    failed_detail   JSONB       NOT NULL DEFAULT '[]',
    notes           TEXT
);

CREATE UNIQUE INDEX uq_ingestion_hash ON csv_ingestion_log(file_hash);

-- ─── Forms ────────────────────────────────────────────────────────────────────

CREATE TABLE irs_forms (
    id                      SERIAL PRIMARY KEY,
    form_type               VARCHAR(20)  NOT NULL,
    tax_year                SMALLINT     NOT NULL,
    form_title              VARCHAR(200),
    efile_schema_version    VARCHAR(10),
    instructions_url        TEXT,
    pdf_url                 TEXT,
    ingested_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_form_year UNIQUE (form_type, tax_year)
);

COMMENT ON TABLE irs_forms IS
    'One row per IRS form per tax year. Populated during Layer 1 ingestion.';

-- ─── Business Rules (current versions) ────────────────────────────────────────

CREATE TABLE irs_business_rules (
    id                  BIGSERIAL PRIMARY KEY,
    rule_id             VARCHAR(50)  NOT NULL,
    tax_year            SMALLINT     NOT NULL,
    schema_version      VARCHAR(10)  NOT NULL,
    rule_type           rule_type    NOT NULL,
    form_family         VARCHAR(20)  NOT NULL,
    field_path          TEXT         NOT NULL,
    short_field         VARCHAR(100) GENERATED ALWAYS AS (
                            SUBSTRING(field_path FROM '[^/]+$')
                        ) STORED,
    rule_text           TEXT         NOT NULL,
    rule_expression     TEXT         NOT NULL,
    expression_ast      JSONB,                       -- Populated by ast_parser
    error_code          VARCHAR(20)  NOT NULL,
    severity            severity_t   NOT NULL,
    parse_success       BOOLEAN      NOT NULL DEFAULT FALSE,
    parse_error_msg     TEXT,
    is_current          BOOLEAN      NOT NULL DEFAULT TRUE,  -- FALSE when superseded
    ingested_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_rule_version UNIQUE (rule_id, tax_year, schema_version)
);

COMMENT ON TABLE irs_business_rules IS
    'One row per rule per schema version per tax year. Superseded rows '
    'remain with is_current = FALSE for prior-year return support.';

-- Indexes for common MCP query patterns
CREATE INDEX idx_rules_form_year     ON irs_business_rules(form_family, tax_year);
CREATE INDEX idx_rules_severity      ON irs_business_rules(severity, tax_year);
CREATE INDEX idx_rules_field_path    ON irs_business_rules USING GIN (field_path gin_trgm_ops);
CREATE INDEX idx_rules_error_code    ON irs_business_rules(error_code);
CREATE INDEX idx_rules_current       ON irs_business_rules(is_current, tax_year, form_family);
CREATE INDEX idx_rules_ast           ON irs_business_rules USING GIN (expression_ast);

-- ─── Rule Version History ─────────────────────────────────────────────────────
-- Tracks what changed between schema versions within a single tax year.

CREATE TABLE rule_version_history (
    id              BIGSERIAL PRIMARY KEY,
    rule_id         VARCHAR(50)  NOT NULL,
    tax_year        SMALLINT     NOT NULL,
    old_version     VARCHAR(10),
    new_version     VARCHAR(10)  NOT NULL,
    change_type     change_type  NOT NULL,
    changed_fields  TEXT[]       NOT NULL DEFAULT '{}',
    old_expression  TEXT,
    new_expression  TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_rvh_rule_year ON rule_version_history(rule_id, tax_year);
CREATE INDEX idx_rvh_version   ON rule_version_history(new_version, tax_year);

-- ─── Append-only: prevent UPDATE/DELETE on version history ────────────────────

CREATE OR REPLACE FUNCTION prevent_history_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'rule_version_history is append-only. UPDATE and DELETE are not permitted.';
END;
$$;

CREATE TRIGGER trg_no_update_rvh
    BEFORE UPDATE OR DELETE ON rule_version_history
    FOR EACH ROW EXECUTE FUNCTION prevent_history_mutation();

-- ─── Validation Results ────────────────────────────────────────────────────────

CREATE TABLE validation_runs (
    id              BIGSERIAL PRIMARY KEY,
    run_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    step            VARCHAR(20)  NOT NULL,   -- V1.1, V1.2, V1.3, V1.4
    tax_year        SMALLINT     NOT NULL,
    schema_version  VARCHAR(10),
    passed          BOOLEAN      NOT NULL,
    total_checked   INTEGER      NOT NULL,
    total_passed    INTEGER      NOT NULL,
    total_failed    INTEGER      NOT NULL,
    pass_rate       NUMERIC(5,4) NOT NULL,
    failures        JSONB        NOT NULL DEFAULT '[]',
    warnings        JSONB        NOT NULL DEFAULT '[]',
    notes           TEXT[]       NOT NULL DEFAULT '{}',
    run_by          VARCHAR(100)           -- user / CI pipeline identifier
);

CREATE INDEX idx_vr_step_year ON validation_runs(step, tax_year, run_at DESC);

-- ─── Test Return Cases (for V1.3 replay) ──────────────────────────────────────

CREATE TABLE test_return_cases (
    id              BIGSERIAL PRIMARY KEY,
    case_id         VARCHAR(50)  NOT NULL UNIQUE,
    description     TEXT         NOT NULL,
    tax_year        SMALLINT     NOT NULL,
    expected_outcome VARCHAR(10) NOT NULL CHECK (expected_outcome IN ('ACCEPTED','REJECTED')),
    expected_errors  TEXT[]      NOT NULL DEFAULT '{}',
    return_data     JSONB        NOT NULL,   -- field → value snapshot
    source          VARCHAR(50)  NOT NULL DEFAULT 'IRS_PUBLISHED',  -- or SYNTHETIC
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE test_return_results (
    id              BIGSERIAL PRIMARY KEY,
    run_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    validation_run_id BIGINT     REFERENCES validation_runs(id),
    case_id         VARCHAR(50)  NOT NULL,
    tax_year        SMALLINT     NOT NULL,
    schema_version  VARCHAR(10),
    actual_outcome  VARCHAR(10)  NOT NULL,
    fired_rules     TEXT[]       NOT NULL DEFAULT '{}',
    fired_errors    TEXT[]       NOT NULL DEFAULT '{}',
    outcome_match   BOOLEAN      NOT NULL,
    error_code_match BOOLEAN     NOT NULL,
    notes           TEXT
);

CREATE INDEX idx_trr_case_id  ON test_return_results(case_id, run_at DESC);
CREATE INDEX idx_trr_match    ON test_return_results(outcome_match, run_at DESC);

-- ─── Convenience view: current rules only ─────────────────────────────────────

CREATE VIEW v_current_rules AS
SELECT
    r.*,
    f.form_title
FROM irs_business_rules r
LEFT JOIN irs_forms f ON f.form_type = r.form_family AND f.tax_year = r.tax_year
WHERE r.is_current = TRUE;

-- ─── Convenience view: recent validation summary ──────────────────────────────

CREATE VIEW v_validation_summary AS
SELECT
    step,
    tax_year,
    schema_version,
    run_at,
    passed,
    total_checked,
    total_passed,
    total_failed,
    ROUND(pass_rate * 100, 1) AS pass_pct
FROM validation_runs
ORDER BY run_at DESC;
