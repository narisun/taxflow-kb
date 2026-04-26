-- Migration: Add context_annotation column for LLM-generated chunk context
-- Run this BEFORE re-ingesting publications with the annotation pipeline.
--
-- Usage:
--   psql -U taxflow -d taxflow -f scripts/add_context_annotation.sql

-- Add the column (no-op if already exists)
ALTER TABLE irs_kb.publication_chunks
ADD COLUMN IF NOT EXISTS context_annotation TEXT DEFAULT '';

-- Verify
SELECT 'context_annotation column added successfully' AS status;
SELECT COUNT(*) AS total_chunks,
       COUNT(NULLIF(context_annotation, '')) AS annotated_chunks
FROM irs_kb.publication_chunks;
