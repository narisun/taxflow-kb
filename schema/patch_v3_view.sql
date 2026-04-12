-- =============================================================================
-- Patch: rebuild v_pub_coverage with page_count and avg_token_count columns.
--
-- PostgreSQL cannot rename view columns via CREATE OR REPLACE, so we drop first.
-- v_line_chunks does NOT depend on v_pub_coverage, so CASCADE is safe here.
--
-- Apply with:
--   docker exec -i taxflow-postgres psql -U taxflow -d taxflow < schema/patch_v3_view.sql
-- =============================================================================

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

-- Quick sanity check — should show 8 rows with non-zero page_count and avg_token_count
SELECT pub_number, page_count, chunk_count, embed_pct, avg_token_count
FROM   irs_kb.v_pub_coverage
ORDER BY pub_number;
