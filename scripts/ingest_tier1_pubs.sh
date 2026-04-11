#!/usr/bin/env bash
#
# ingest_tier1_pubs.sh — Ingest all 8 Tier-1 gap publications into PostgreSQL
#
# Prerequisites:
#   1. PostgreSQL with pgvector extension running
#   2. OPENAI_API_KEY environment variable set
#   3. Database created and Layer 3 schema applied
#
# Usage:
#   export OPENAI_API_KEY="sk-..."
#   export PG_DSN="postgresql://taxflow:taxflow_dev@localhost:5432/taxflow"
#   bash scripts/ingest_tier1_pubs.sh
#
set -euo pipefail

PG_DSN="${PG_DSN:?Set PG_DSN env var (e.g. postgresql://taxflow:pw@localhost:5432/taxflow)}"
OPENAI_API_KEY="${OPENAI_API_KEY:?Set OPENAI_API_KEY env var}"
DATA_DIR="data/publications"

echo "============================================================"
echo "  Tax Brain — Tier-1 Gap Publication Ingestion"
echo "============================================================"
echo ""
echo "  Database: $PG_DSN"
echo "  Data dir: $DATA_DIR"
echo ""

# Step 1: Run one-time migrations
echo "── Step 1: Applying schema migrations ──"
python cli.py add-hierarchy-columns --pg-dsn "$PG_DSN"
echo ""

# Step 2: Ingest each publication (latest tax year)
# Using the most recent tax year available for each publication.
# Pub 535 is discontinued — only 2022 is available.

declare -A PUBS=(
    ["334"]=2025
    ["505"]=2025
    ["523"]=2025
    ["527"]=2025
    ["535"]=2022
    ["544"]=2025
    ["551"]=2025
    ["946"]=2025
)

FAILED=0
for PUB_NUM in 334 505 523 527 535 544 551 946; do
    TAX_YEAR=${PUBS[$PUB_NUM]}
    PDF_PATH="${DATA_DIR}/p${PUB_NUM}_${TAX_YEAR}.pdf"

    if [ ! -f "$PDF_PATH" ]; then
        echo "  SKIP: $PDF_PATH not found"
        FAILED=$((FAILED + 1))
        continue
    fi

    echo "── Ingesting Pub ${PUB_NUM} (${TAX_YEAR}) ──"
    python cli.py ingest-publications \
        --pdf "$PDF_PATH" \
        --pub-number "$PUB_NUM" \
        --tax-year "$TAX_YEAR" \
        --pg-dsn "$PG_DSN" \
        --api-key "$OPENAI_API_KEY" \
        --init-schema \
    || { echo "  FAILED: Pub $PUB_NUM"; FAILED=$((FAILED + 1)); }
    echo ""
done

# Step 3: Build IVFFlat index after all publications are ingested
echo "── Step 3: Building IVFFlat ANN index ──"
python cli.py build-index --pg-dsn "$PG_DSN" --force || true
echo ""

# Summary
echo "============================================================"
if [ "$FAILED" -eq 0 ]; then
    echo "  ALL 8 TIER-1 PUBLICATIONS INGESTED SUCCESSFULLY"
else
    echo "  COMPLETED WITH $FAILED FAILURE(S)"
fi
echo "============================================================"
echo ""
echo "Next steps:"
echo "  1. Validate: python cli.py validate-publications --pg-dsn \"$PG_DSN\" --step v3.2"
echo "  2. Test search: python cli.py search \"standard deduction for single filer\" --pg-dsn \"$PG_DSN\""
echo "  3. Test hierarchy: python cli.py search \"rental property depreciation\" --pg-dsn \"$PG_DSN\" --mode hybrid"

exit $FAILED
