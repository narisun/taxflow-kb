#!/usr/bin/env bash
#
# ingest_tier2_remaining.sh — Ingest the 3 remaining Tier-2 publications
# (502, 503, 504) to reach 20/20 on V3.2 validation.
#
# Usage:
#   export OPENAI_API_KEY="sk-..."
#   export PG_DSN="postgresql://taxflow:taxflow_dev@localhost:5432/taxflow"
#   bash taxkb/scripts/ingest_tier2_remaining.sh
#
set -euo pipefail

PG_DSN="${PG_DSN:?Set PG_DSN env var}"
OPENAI_API_KEY="${OPENAI_API_KEY:?Set OPENAI_API_KEY env var}"
DATA_DIR="data/publications"

echo "============================================================"
echo "  Tax Brain — Tier-2 Remaining Publication Ingestion"
echo "  (502, 503, 504)"
echo "============================================================"
echo ""

FAILED=0
for PUB_NUM in 502 503 504; do
    PDF_PATH="${DATA_DIR}/p${PUB_NUM}_2025.pdf"

    if [ ! -f "$PDF_PATH" ]; then
        echo "  SKIP: $PDF_PATH not found"
        FAILED=$((FAILED + 1))
        continue
    fi

    echo "── Ingesting Pub ${PUB_NUM} (2025) ──"
    python cli.py ingest-publications \
        --pdf "$PDF_PATH" \
        --pub-number "$PUB_NUM" \
        --tax-year 2025 \
        --pg-dsn "$PG_DSN" \
        --api-key "$OPENAI_API_KEY" \
        --init-schema \
    || { echo "  FAILED: Pub $PUB_NUM"; FAILED=$((FAILED + 1)); }
    echo ""
done

# Rebuild index to include new chunks
echo "── Rebuilding IVFFlat ANN index ──"
python cli.py build-index --pg-dsn "$PG_DSN" --force || true
echo ""

echo "============================================================"
if [ "$FAILED" -eq 0 ]; then
    echo "  ALL 3 REMAINING TIER-2 PUBLICATIONS INGESTED"
else
    echo "  COMPLETED WITH $FAILED FAILURE(S)"
fi
echo "============================================================"
echo ""
echo "Validate: python cli.py validate-publications --pg-dsn \"$PG_DSN\" --step v3.2"

exit $FAILED
