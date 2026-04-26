#!/usr/bin/env python3
"""
Diagnose what's actually in the Tax Brain database.

Run this BEFORE e2e tests to understand what pubs/years/chunks are available.

Usage:
    python taxkb/scripts/diagnose_db.py
"""
import sys
sys.path.insert(0, ".")

import psycopg2
from taxkb.config import get_settings

settings = get_settings()
dsn = settings.pg_dsn

print("=" * 72)
print("  TAX BRAIN — Database Diagnostic")
print(f"  DSN: {dsn}")
print("=" * 72)

conn = psycopg2.connect(dsn)
cur = conn.cursor()

# 1. Total chunks
cur.execute("SELECT COUNT(*) FROM irs_kb.publication_chunks")
total = cur.fetchone()[0]
print(f"\nTotal chunks: {total}")

# 2. Chunks by pub_number
print("\n── Chunks per Publication ──────────────────────────────────────")
cur.execute("""
    SELECT pub_number, COUNT(*) as cnt,
           COUNT(*) FILTER (WHERE embedding IS NOT NULL) as embedded
    FROM irs_kb.publication_chunks
    GROUP BY pub_number
    ORDER BY pub_number
""")
rows = cur.fetchall()
print(f"  {'Pub':<8} {'Chunks':>8} {'Embedded':>10}")
print(f"  {'---':<8} {'------':>8} {'--------':>10}")
for pub, cnt, emb in rows:
    print(f"  {pub:<8} {cnt:>8} {emb:>10}")
print(f"\n  Total pubs: {len(rows)}")

# 3. Chunks by tax_year
print("\n── Chunks per Tax Year ─────────────────────────────────────────")
cur.execute("""
    SELECT tax_year, COUNT(*) as cnt
    FROM irs_kb.publication_chunks
    GROUP BY tax_year
    ORDER BY tax_year
""")
for year, cnt in cur.fetchall():
    print(f"  {year}: {cnt} chunks")

# 4. Chunks by chunk_type
print("\n── Chunks by Type ──────────────────────────────────────────────")
cur.execute("""
    SELECT chunk_type, COUNT(*) as cnt
    FROM irs_kb.publication_chunks
    GROUP BY chunk_type
    ORDER BY chunk_type
""")
for ctype, cnt in cur.fetchall():
    print(f"  {ctype or 'NULL':<20} {cnt:>6}")

# 5. Pub × Year matrix
print("\n── Publication × Year Matrix ───────────────────────────────────")
cur.execute("""
    SELECT pub_number, tax_year, COUNT(*) as cnt
    FROM irs_kb.publication_chunks
    GROUP BY pub_number, tax_year
    ORDER BY pub_number, tax_year
""")
matrix = {}
all_years = set()
for pub, year, cnt in cur.fetchall():
    matrix.setdefault(pub, {})[year] = cnt
    all_years.add(year)

years_sorted = sorted(all_years)
header = f"  {'Pub':<8}" + "".join(f"{y:>8}" for y in years_sorted)
print(header)
print(f"  {'---':<8}" + "".join(f"{'------':>8}" for _ in years_sorted))
for pub in sorted(matrix.keys()):
    row = f"  {pub:<8}"
    for y in years_sorted:
        cnt = matrix[pub].get(y, 0)
        row += f"{cnt or '-':>8}"
    print(row)

# 6. Summary chunks specifically
print("\n── Summary Chunks ──────────────────────────────────────────────")
cur.execute("""
    SELECT pub_number, chunk_type, COUNT(*)
    FROM irs_kb.publication_chunks
    WHERE chunk_type IN ('pub_summary', 'section_summary', 'PUB_SUMMARY', 'SECTION_SUMMARY')
    GROUP BY pub_number, chunk_type
    ORDER BY pub_number, chunk_type
""")
summary_rows = cur.fetchall()
if summary_rows:
    for pub, ctype, cnt in summary_rows:
        print(f"  {pub:<8} {ctype:<20} {cnt}")
else:
    print("  ** NO summary chunks found **")
    print("  (Hierarchical retrieval will fall back to flat mode)")

# 7. Sample chunk for top pub
print("\n── Sample Chunk (first pub) ────────────────────────────────────")
cur.execute("""
    SELECT pub_number, chunk_type, tax_year, section_title,
           LEFT(text, 200) as preview
    FROM irs_kb.publication_chunks
    ORDER BY pub_number, chunk_id
    LIMIT 3
""")
for pub, ctype, year, section, preview in cur.fetchall():
    print(f"  Pub {pub} | type={ctype} | year={year} | section={section}")
    print(f"  Preview: {preview[:150]}...")
    print()

# 8. Check column existence
print("── Schema Check ────────────────────────────────────────────────")
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_schema = 'irs_kb' AND table_name = 'publication_chunks'
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print(f"  Columns: {', '.join(cols)}")

conn.close()
print("\n" + "=" * 72)
print("  Diagnostic complete. Use this to calibrate e2e_test_taxkb.py")
print("=" * 72)
