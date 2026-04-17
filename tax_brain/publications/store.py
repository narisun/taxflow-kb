"""
tax_brain/publications/store.py

PostgreSQL (pgvector) ingestion and retrieval for IRS Publication chunks.

Responsibilities
────────────────
· Upsert publication metadata → irs_kb.publications
· Batch-upsert text + embedding → irs_kb.publication_chunks
· Log every action → irs_kb.pub_ingestion_log
· Optionally create the IVFFlat ANN index after first ingestion
· Provide semantic search via cosine similarity

Usage:
    from tax_brain.publications.store import PublicationStore

    store = PublicationStore(dsn="postgresql://taxflow:taxflow_dev@localhost:5432/taxflow")
    store.upsert_publication(result)      # Layer3ParseResult
    store.upsert_chunks(result.chunks)
    store.finalize_embedding(pub_id, count)
    results = store.search_similar(query_embedding, top_k=5)
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from tax_brain.publications.models import (
    Layer3ParseResult, Publication, PublicationChunk, RetrievalResult,
    PUB_TITLES,
)

logger = logging.getLogger(__name__)

# Number of chunks to upsert per single executemany call
_UPSERT_BATCH = 200


class PublicationStore:
    """
    Thin wrapper around psycopg2 for Layer 3 pgvector operations.

    Args:
        conn       : An existing psycopg2 connection (caller manages lifecycle).
        pool       : A ConnectionPool — the store will call pool.getconn()
                     and return the connection via pool.putconn() on close().
        autocommit : If True, each upsert method commits immediately.

    Either *conn* or *pool* must be provided, but not both.
    """

    def __init__(
        self,
        conn      = None,
        pool      = None,
        dsn       = None,
        autocommit: bool = True,
    ):
        self._pool = None
        if conn is not None:
            self._conn = conn
            self._owns_conn = False
        elif pool is not None:
            self._conn = pool.getconn()
            self._pool = pool
            self._owns_conn = True  # we'll return to pool on close
        elif dsn is not None:
            import psycopg2
            self._conn = psycopg2.connect(dsn)
            self._owns_conn = True
        else:
            raise ValueError("Either conn, pool, or dsn must be provided.")
        if autocommit:
            self._conn.autocommit = True

        self._autocommit = autocommit

    # ── Context manager support ────────────────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        if self._owns_conn and self._conn:
            if self._pool is not None:
                self._pool.putconn(self._conn)
            elif not self._conn.closed:
                self._conn.close()
            self._conn = None

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _cursor(self):
        return self._conn.cursor()

    def _commit(self):
        if self._autocommit:
            self._conn.commit()

    def _log(self, pub_id: str, action: str, chunk_count: int = 0,
             duration_ms: int = 0, error_msg: Optional[str] = None):
        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO irs_kb.pub_ingestion_log
                        (pub_id, action, chunk_count, duration_ms, error_msg)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (pub_id, action, chunk_count, duration_ms, error_msg),
                )
            self._commit()
        except Exception as exc:
            logger.warning("Failed to write ingestion log: %s", exc)

    # ── Schema init ────────────────────────────────────────────────────────────

    def apply_schema(self, sql_path: str) -> None:
        """
        Execute a .sql file against the database.
        Useful for initialising the schema in one call.
        """
        from pathlib import Path
        sql = Path(sql_path).read_text(encoding="utf-8")
        with self._cursor() as cur:
            cur.execute(sql)
        self._commit()
        logger.info("Schema applied from %s", sql_path)

    # ── Publication upsert ─────────────────────────────────────────────────────

    def upsert_publication(self, pub: Publication) -> None:
        """
        Insert or update a row in irs_kb.publications.

        Conflict on pub_id updates all mutable fields so re-ingestion
        reflects a freshly parsed PDF.
        """
        t0 = time.monotonic()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO irs_kb.publications
                    (pub_id, pub_number, pub_title, tax_year,
                     source_path, pdf_hash, page_count, chunk_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pub_id) DO UPDATE SET
                    pub_number  = EXCLUDED.pub_number,
                    pub_title   = EXCLUDED.pub_title,
                    tax_year    = EXCLUDED.tax_year,
                    source_path = EXCLUDED.source_path,
                    pdf_hash    = EXCLUDED.pdf_hash,
                    page_count  = EXCLUDED.page_count,
                    chunk_count = EXCLUDED.chunk_count,
                    ingested_at = NOW()
                """,
                (
                    pub.pub_id, pub.pub_number, pub.pub_title, pub.tax_year,
                    pub.source_path or None, pub.pdf_hash or None,
                    pub.page_count, pub.chunk_count,
                ),
            )
        self._commit()
        ms = int((time.monotonic() - t0) * 1000)
        logger.info("Upserted publication %s (%d ms)", pub.pub_id, ms)
        self._log(pub.pub_id, "parse", chunk_count=pub.chunk_count, duration_ms=ms)

    # ── Chunk upsert ───────────────────────────────────────────────────────────

    def upsert_chunks(self, chunks: list[PublicationChunk]) -> int:
        """
        Batch-upsert publication chunks (text only, no embedding).

        Returns the number of rows inserted/updated.
        """
        if not chunks:
            return 0

        from psycopg2.extras import execute_values  # type: ignore

        t0    = time.monotonic()
        total = 0

        for batch_start in range(0, len(chunks), _UPSERT_BATCH):
            batch = chunks[batch_start : batch_start + _UPSERT_BATCH]
            rows  = [
                (
                    c.chunk_id, c.pub_id, c.pub_number, c.tax_year,
                    c.chunk_index, c.chapter_title or None, c.section_title or None,
                    c.page_start, c.page_end,
                    c.text, c.token_count,
                    c.form_refs or [],
                    c.line_refs or [],
                    c.chunk_type.value if hasattr(c.chunk_type, 'value') else str(c.chunk_type),
                    c.topic_ids or [],
                    getattr(c, 'context_annotation', '') or '',
                )
                for c in batch
            ]
            with self._cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO irs_kb.publication_chunks
                        (chunk_id, pub_id, pub_number, tax_year, chunk_index,
                         chapter_title, section_title, page_start, page_end,
                         text, token_count, form_refs, line_refs,
                         chunk_type, topic_ids, context_annotation)
                    VALUES %s
                    ON CONFLICT (pub_id, chunk_index) DO UPDATE SET
                        chapter_title      = EXCLUDED.chapter_title,
                        section_title      = EXCLUDED.section_title,
                        page_start         = EXCLUDED.page_start,
                        page_end           = EXCLUDED.page_end,
                        text               = EXCLUDED.text,
                        token_count        = EXCLUDED.token_count,
                        form_refs          = EXCLUDED.form_refs,
                        line_refs          = EXCLUDED.line_refs,
                        chunk_type         = EXCLUDED.chunk_type,
                        topic_ids          = EXCLUDED.topic_ids,
                        context_annotation = EXCLUDED.context_annotation
                    """,
                    rows,
                    template=None,
                    page_size=_UPSERT_BATCH,
                )
            self._commit()
            total += len(batch)
            logger.info("  Upserted %d/%d chunks …", total, len(chunks))

        ms = int((time.monotonic() - t0) * 1000)
        pub_id = chunks[0].pub_id if chunks else ""
        logger.info("Chunk upsert complete: %d rows (%d ms)", total, ms)
        self._log(pub_id, "upsert", chunk_count=total, duration_ms=ms)
        return total

    # ── Embedding upsert ───────────────────────────────────────────────────────

    def upsert_embeddings(self, chunks: list[PublicationChunk]) -> int:
        """
        Update embedding vectors for chunks that have been embedded.

        Only processes chunks where chunk.embedding is not None.
        Uses the pgvector `::vector` cast via the `pgvector` Python client
        (falls back to plain Python list if the adapter is not registered).

        Returns the number of rows updated.
        """
        embedded = [c for c in chunks if c.embedding is not None]
        if not embedded:
            return 0

        # Attempt to register pgvector's psycopg2 adapter so we can pass
        # Python lists directly as vector columns.
        try:
            from pgvector.psycopg2 import register_vector  # type: ignore
            register_vector(self._conn)
            _USE_PGVECTOR_ADAPTER = True
        except ImportError:
            _USE_PGVECTOR_ADAPTER = False

        t0    = time.monotonic()
        total = 0

        for batch_start in range(0, len(embedded), _UPSERT_BATCH):
            batch = embedded[batch_start : batch_start + _UPSERT_BATCH]

            with self._cursor() as cur:
                for c in batch:
                    if _USE_PGVECTOR_ADAPTER:
                        import numpy as np  # type: ignore  # optional dep
                        vec = np.array(c.embedding, dtype=np.float32)
                    else:
                        # Fallback: pass as string in pgvector literal format
                        vec_str = "[" + ",".join(f"{v:.8f}" for v in c.embedding) + "]"
                        cur.execute(
                            """
                            UPDATE irs_kb.publication_chunks
                            SET    embedding   = %s::vector,
                                   embedded_at = NOW()
                            WHERE  chunk_id    = %s
                            """,
                            (vec_str, c.chunk_id),
                        )
                        continue

                    cur.execute(
                        """
                        UPDATE irs_kb.publication_chunks
                        SET    embedding   = %s,
                               embedded_at = NOW()
                        WHERE  chunk_id    = %s
                        """,
                        (vec, c.chunk_id),
                    )

            self._commit()
            total += len(batch)
            logger.info("  Embedded %d/%d chunks …", total, len(embedded))

        ms = int((time.monotonic() - t0) * 1000)
        pub_id = embedded[0].pub_id if embedded else ""
        logger.info("Embedding upsert complete: %d rows (%d ms)", total, ms)
        self._log(pub_id, "embed", chunk_count=total, duration_ms=ms)
        return total

    # ── Post-embedding publication update ──────────────────────────────────────

    def finalize_embedding(self, pub_id: str, embedded_count: int) -> None:
        """
        Stamp irs_kb.publications with embedded_count and embedded_at.
        Call after upsert_embeddings() completes for a publication.
        """
        with self._cursor() as cur:
            cur.execute(
                """
                UPDATE irs_kb.publications
                SET    embedded_count = %s,
                       embedded_at    = NOW()
                WHERE  pub_id = %s
                """,
                (embedded_count, pub_id),
            )
        self._commit()
        logger.info("Finalized embedding for %s: %d vectors stored", pub_id, embedded_count)

    # ── ANN index ─────────────────────────────────────────────────────────────

    def create_ivfflat_index(self, lists: int = 100, force: bool = False) -> None:
        """
        Build the IVFFlat index for cosine ANN search.

        IMPORTANT — use force=True after any re-embedding run.  The IVFFlat
        index stores k-means centroids computed at creation time.  If the
        underlying vectors are replaced (e.g. switching from
        text-embedding-3-small to text-embedding-3-large), the old centroids
        route queries into the wrong cluster partitions and HR collapses to
        near-zero.  force=True drops the stale index before recreating.

        Args:
            lists: Number of IVFFlat lists (100 is good for up to ~1M chunks).
            force: If True, drop the existing index before creating a new one.
                   Required after changing the embedding model.
        """
        if force:
            logger.info("Dropping existing IVFFlat index (force rebuild) …")
            with self._cursor() as cur:
                cur.execute(
                    "DROP INDEX IF EXISTS irs_kb.idx_chunks_embedding"
                )
            self._commit()

        logger.info("Creating IVFFlat index with lists=%d …", lists)
        with self._cursor() as cur:
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_chunks_embedding
                ON irs_kb.publication_chunks
                USING ivfflat(embedding vector_cosine_ops)
                WITH (lists = {lists})
                """
            )
        self._commit()
        logger.info("IVFFlat index created.")

    # ── BM25 full-text index ───────────────────────────────────────────────────

    def add_bm25_index(self) -> None:
        """
        Add a stored tsvector column and GIN full-text index to publication_chunks.

        This is a one-time migration — safe to run multiple times
        (ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS).

        The tsvector concatenates text AND context_annotation so BM25 search
        benefits from LLM-generated annotation keywords (IRC section numbers,
        publication references, topic names, dollar amounts).  The annotation
        vector is weighted 'B' (lower than text's default 'A') so raw text
        matches still rank higher, but annotation keywords are discoverable.

        After this runs, search_bm25() becomes available and
        TaxBrainRetriever automatically enables hybrid retrieval.

        Estimated time: 10–30 seconds on a 10k-chunk corpus (GIN build).
        """
        logger.info("BM25 migration — adding text_tsvector column …")
        with self._cursor() as cur:
            # Drop and recreate the generated column to pick up the new
            # expression.  ALTER COLUMN ... SET EXPRESSION is not supported
            # for generated columns in PostgreSQL, so drop-then-add is the
            # only safe migration path.  The GIN index is rebuilt below.
            cur.execute(
                "ALTER TABLE irs_kb.publication_chunks "
                "DROP COLUMN IF EXISTS text_tsvector"
            )
            cur.execute(
                """
                ALTER TABLE irs_kb.publication_chunks
                ADD COLUMN text_tsvector tsvector
                GENERATED ALWAYS AS (
                    setweight(to_tsvector('english', coalesce(text, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(context_annotation, '')), 'B')
                ) STORED
                """
            )
        self._commit()
        logger.info("  text_tsvector column ready (text='A' + annotation='B').")

        logger.info("BM25 migration — creating GIN index …")
        with self._cursor() as cur:
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chunks_fts
                ON irs_kb.publication_chunks
                USING GIN (text_tsvector)
                """
            )
        self._commit()
        logger.info("  GIN index on text_tsvector ready — BM25 search enabled.")

    # ── Hierarchy migration ───────────────────────────────────────────────────

    def add_hierarchy_columns(self) -> None:
        """
        Add chunk_type and topic_ids columns for the three-tier hierarchy.

        This is a one-time migration — safe to run multiple times
        (ADD COLUMN IF NOT EXISTS).
        """
        logger.info("Hierarchy migration — adding chunk_type column …")
        with self._cursor() as cur:
            cur.execute("""
                ALTER TABLE irs_kb.publication_chunks
                ADD COLUMN IF NOT EXISTS chunk_type TEXT DEFAULT 'detail'
            """)
        self._commit()

        logger.info("Hierarchy migration — adding topic_ids column …")
        with self._cursor() as cur:
            cur.execute("""
                ALTER TABLE irs_kb.publication_chunks
                ADD COLUMN IF NOT EXISTS topic_ids TEXT[] DEFAULT '{}'
            """)
        self._commit()

        logger.info("Hierarchy migration — creating indexes …")
        with self._cursor() as cur:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_chunk_type
                    ON irs_kb.publication_chunks (chunk_type)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_pub_type
                    ON irs_kb.publication_chunks (pub_id, chunk_type)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_topic_ids
                    ON irs_kb.publication_chunks USING GIN(topic_ids)
            """)
        self._commit()
        logger.info("  Hierarchy columns and indexes ready.")

    def has_chunk_type(self, chunk_type: str) -> bool:
        """Check if any chunks of a given chunk_type exist in the database."""
        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM irs_kb.publication_chunks
                        WHERE chunk_type = %s
                        LIMIT 1
                    )
                    """,
                    (chunk_type,),
                )
                return cur.fetchone()[0]
        except Exception:
            # Column may not exist yet
            return False

    # ── Summary search (hierarchical retrieval Stage 1) ────────────────────────

    def search_summaries(
        self,
        query_embedding: list[float],
        top_k: int = 8,
        pub_numbers: Optional[list[str]] = None,
        tax_year: Optional[int] = None,
    ) -> list[RetrievalResult]:
        """
        Search only pub_summary and section_summary chunks.

        Used by the hierarchical retriever's Stage 1 (navigate) to identify
        which publications and sections are most relevant to a query.
        """
        vec_str = "[" + ",".join(f"{v:.8f}" for v in query_embedding) + "]"

        where_clauses: list[str] = [
            "c.embedding IS NOT NULL",
            "c.chunk_type IN ('pub_summary', 'section_summary')",
        ]
        filter_params: list = []

        if pub_numbers:
            where_clauses.append("c.pub_number = ANY(%s)")
            filter_params.append(pub_numbers)

        if tax_year is not None:
            where_clauses.append("c.tax_year = %s")
            filter_params.append(tax_year)

        where_sql = " AND ".join(where_clauses)

        sql = f"""
            SELECT
                c.chunk_id,
                c.pub_number,
                p.pub_title,
                c.chapter_title,
                c.section_title,
                c.page_start,
                c.text,
                1 - (c.embedding <=> %s::vector) AS score,
                c.form_refs,
                c.line_refs
            FROM  irs_kb.publication_chunks c
            JOIN  irs_kb.publications       p ON p.pub_id = c.pub_id
            WHERE {where_sql}
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        """

        all_params = [vec_str] + filter_params + [vec_str, top_k]

        try:
            with self._cursor() as cur:
                cur.execute(sql, all_params)
                rows = cur.fetchall()
        except Exception as exc:
            logger.warning("Summary search failed (chunk_type column may not exist): %s", exc)
            return []

        return [
            RetrievalResult(
                chunk_id=row[0],
                pub_number=row[1],
                pub_title=row[2] or "",
                chapter_title=row[3] or "",
                section_title=row[4] or "",
                page_start=row[5] or 0,
                text=row[6],
                score=float(row[7]),
                form_refs=list(row[8] or []),
                line_refs=list(row[9] or []),
            )
            for row in rows
        ]

    # ── Direct summary lookup (no embedding similarity) ─────────────────────────

    def get_summary_chunks(
        self,
        pub_numbers: list[str],
        tax_year: Optional[int] = None,
        chunk_types: Optional[list[str]] = None,
    ) -> list[RetrievalResult]:
        """
        Fetch summary chunks for specific publications by direct lookup.

        Unlike search_summaries(), this does NOT require a query embedding
        and does NOT rank by similarity.  It simply returns all summary
        chunks for the requested pubs, ordered by pub_number and page.

        This is used by the scoped-pub guarantee: when the ontology
        identifies a publication as relevant but the vector search can't
        surface its chunks (e.g. form PDFs whose field-label text embeds
        poorly), we inject the LLM-generated summary chunks directly.

        Args:
            pub_numbers : Publication numbers to fetch summaries for.
            tax_year    : Optional tax year filter.
            chunk_types : Which chunk types to fetch.
                          Default: ['pub_summary', 'section_summary'].
        """
        if not pub_numbers:
            return []

        if chunk_types is None:
            chunk_types = ["pub_summary", "section_summary"]

        # Use COALESCE to handle NULL chunk_type values: chunks inserted
        # before the hierarchy migration have NULL chunk_type, which SQL
        # treats as "not equal to anything".  COALESCE(NULL, 'detail')
        # maps them to 'detail' so they're retrievable by the fallback.
        where_clauses = [
            "c.pub_number = ANY(%s)",
            "COALESCE(c.chunk_type, 'detail') = ANY(%s)",
        ]
        params: list = [pub_numbers, chunk_types]

        if tax_year is not None:
            where_clauses.append("c.tax_year = %s")
            params.append(tax_year)

        where_sql = " AND ".join(where_clauses)

        sql = f"""
            SELECT
                c.chunk_id,
                c.pub_number,
                p.pub_title,
                c.chapter_title,
                c.section_title,
                c.page_start,
                c.text,
                1.0 AS score,
                c.form_refs,
                c.line_refs
            FROM  irs_kb.publication_chunks c
            JOIN  irs_kb.publications       p ON p.pub_id = c.pub_id
            WHERE {where_sql}
            ORDER BY c.pub_number, c.page_start, c.chunk_index
        """

        try:
            with self._cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        except Exception as exc:
            logger.warning("get_summary_chunks failed: %s", exc)
            return []

        return [
            RetrievalResult(
                chunk_id=row[0],
                pub_number=row[1],
                pub_title=row[2] or "",
                chapter_title=row[3] or "",
                section_title=row[4] or "",
                page_start=row[5] or 0,
                text=row[6],
                score=float(row[7]),
                form_refs=list(row[8] or []),
                line_refs=list(row[9] or []),
            )
            for row in rows
        ]

    # ── BM25 keyword search ────────────────────────────────────────────────────

    def search_bm25(
        self,
        query       : str,
        top_k       : int  = 10,
        pub_numbers : Optional[list[str]] = None,
        tax_year    : Optional[int] = None,
    ) -> list[RetrievalResult]:
        """
        Keyword search using Postgres full-text ranking (BM25 approximation).

        Uses plainto_tsquery (handles multi-word phrases without operators) and
        ts_rank_cd with normalization flag 32 (rank ÷ document length), which
        approximates BM25 length normalization.

        Form numbers ("Form 8889"), error codes ("F1040-001"), dollar thresholds
        ("$7,000"), and IRC sections ("§ 72(t)") are exact-token matches where
        this outperforms cosine similarity.

        Args:
            query       : Natural-language or keyword query string.
            top_k       : Maximum results to return.
            pub_numbers : Optionally restrict to specific publication numbers.
            tax_year    : Optionally restrict to a specific tax year.

        Returns:
            List of RetrievalResult ordered by ts_rank_cd score (descending).
            Returns an empty list if the text_tsvector column doesn't exist yet.

        Raises:
            Does NOT raise on missing column — returns [] so TaxBrainRetriever
            can fall back to vector-only without crashing.
        """
        # Build WHERE and filter params
        # Score threshold: only return chunks with meaningful BM25 signal.
        # ts_rank_cd > 0 means at least one query term matched.
        where_clauses: list[str] = ["ts_rank_cd(c.text_tsvector, q.tsq, 32) > 0"]
        filter_params: list      = []

        if pub_numbers:
            where_clauses.append("c.pub_number = ANY(%s)")
            filter_params.append(pub_numbers)

        if tax_year is not None:
            where_clauses.append("c.tax_year = %s")
            filter_params.append(tax_year)

        where_sql = " AND ".join(where_clauses)

        # Build an OR-based tsquery so ANY matching term scores the chunk.
        # Strategy: strip English stop words by running the query through
        # to_tsvector, then reconstruct as a tsquery with | (OR).
        #
        # ts_stat approach: we build the OR query in SQL via:
        #   SELECT array_to_string(
        #       ARRAY(SELECT lexeme FROM unnest(to_tsvector('english', $q))),
        #       ' | '
        #   )
        # Then wrap in to_tsquery so any matching lexeme scores the chunk.
        # This is far more permissive than plainto_tsquery (AND) and matches
        # IRS-style queries that use conceptual language ("contribution limit"
        # might become "contribut | limit" and hit any chunk with either term).
        #
        # Fallback: if the OR query is empty (all stop words), the CTE returns
        # a null tsq and no chunks match — returning [] gracefully.
        sql = f"""
            WITH q AS (
                SELECT
                    CASE
                        WHEN array_length(
                            ARRAY(SELECT lexeme
                                  FROM unnest(to_tsvector('english', %s))),
                            1
                        ) > 0
                        THEN to_tsquery(
                            'english',
                            array_to_string(
                                ARRAY(SELECT lexeme
                                      FROM unnest(to_tsvector('english', %s))),
                                ' | '
                            )
                        )
                        ELSE NULL
                    END AS tsq
            )
            SELECT
                c.chunk_id,
                c.pub_number,
                p.pub_title,
                c.chapter_title,
                c.section_title,
                c.page_start,
                c.text,
                ts_rank_cd(c.text_tsvector, q.tsq, 32) AS score,
                c.form_refs,
                c.line_refs,
                COALESCE(c.context_annotation, '') AS context_annotation
            FROM  irs_kb.publication_chunks c
            CROSS JOIN q
            JOIN  irs_kb.publications       p ON p.pub_id = c.pub_id
            WHERE q.tsq IS NOT NULL
              AND {where_sql}
            ORDER BY score DESC
            LIMIT %s
        """

        # Params: [query twice for CTE (two unnest calls)] + filter_params + [top_k]
        all_params = [query, query] + filter_params + [top_k]

        try:
            with self._cursor() as cur:
                cur.execute(sql, all_params)
                rows = cur.fetchall()
        except Exception as exc:
            # Most likely cause: text_tsvector column not yet added.
            # Caller (TaxBrainRetriever) handles the empty list by falling
            # back to vector-only results.
            logger.warning(
                "BM25 search failed (column may not exist yet — run "
                "`python cli.py add-bm25-index`): %s", exc
            )
            return []

        return [
            RetrievalResult(
                chunk_id           = row[0],
                pub_number         = row[1],
                pub_title          = row[2] or "",
                chapter_title      = row[3] or "",
                section_title      = row[4] or "",
                page_start         = row[5] or 0,
                text               = row[6],
                score              = float(row[7]),
                form_refs          = list(row[8] or []),
                line_refs          = list(row[9] or []),
                context_annotation = row[10] if len(row) > 10 else "",
            )
            for row in rows
        ]

    # ── Semantic search ────────────────────────────────────────────────────────

    def search_similar(
        self,
        query_embedding : list[float],
        top_k           : int  = 5,
        pub_numbers     : Optional[list[str]] = None,
        tax_year        : Optional[int] = None,
        form_ref        : Optional[str] = None,
    ) -> list[RetrievalResult]:
        """
        Find the top-k most similar chunks to the query embedding using
        cosine distance (1 - cosine_similarity → lower = more similar).

        Args:
            query_embedding : 1536-dim float list from embed_query().
            top_k           : Maximum results to return.
            pub_numbers     : Optionally restrict to specific publication numbers.
            tax_year        : Optionally restrict to a specific tax year.
            form_ref        : Optionally restrict to chunks that mention a form/schedule.

        Returns:
            List of RetrievalResult ordered by similarity (most similar first).
        """
        # Build query embedding string for pgvector
        vec_str = "[" + ",".join(f"{v:.8f}" for v in query_embedding) + "]"

        # Build WHERE clause and matching params list (excluding vec_str placeholders).
        where_clauses: list[str] = ["c.embedding IS NOT NULL"]
        filter_params: list      = []

        if pub_numbers:
            where_clauses.append("c.pub_number = ANY(%s)")
            filter_params.append(pub_numbers)

        if tax_year is not None:
            where_clauses.append("c.tax_year = %s")
            filter_params.append(tax_year)

        if form_ref:
            where_clauses.append("%s = ANY(c.form_refs)")
            filter_params.append(form_ref)

        where_sql = " AND ".join(where_clauses)

        # vec_str appears twice: once in SELECT (score) and once in ORDER BY.
        sql = f"""
            SELECT
                c.chunk_id,
                c.pub_number,
                p.pub_title,
                c.chapter_title,
                c.section_title,
                c.page_start,
                c.text,
                1 - (c.embedding <=> %s::vector)  AS score,
                c.form_refs,
                c.line_refs,
                COALESCE(c.context_annotation, '') AS context_annotation
            FROM  irs_kb.publication_chunks c
            JOIN  irs_kb.publications       p ON p.pub_id = c.pub_id
            WHERE {where_sql}
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        """

        # Param order: [vec_str for score] + filter_params + [vec_str for ORDER BY] + [top_k]
        all_params = [vec_str] + filter_params + [vec_str, top_k]

        with self._cursor() as cur:
            cur.execute(sql, all_params)
            rows = cur.fetchall()

        return [
            RetrievalResult(
                chunk_id           = row[0],
                pub_number         = row[1],
                pub_title          = row[2] or "",
                chapter_title      = row[3] or "",
                section_title      = row[4] or "",
                page_start         = row[5] or 0,
                text               = row[6],
                score              = float(row[7]),
                form_refs          = list(row[8] or []),
                line_refs          = list(row[9] or []),
                context_annotation = row[10] if len(row) > 10 else "",
            )
            for row in rows
        ]

    # ── Convenience: full ingest pipeline ─────────────────────────────────────

    def ingest(
        self,
        result         : Layer3ParseResult,
        embed_api_key  : Optional[str] = None,
        skip_embedding : bool = False,
        generate_summaries : bool = True,
    ) -> dict:
        """
        Run the full ingest pipeline for one publication:
          1. Upsert publication metadata
          2. Generate anchor chunks (pub + section summaries) if enabled
          3. Upsert all chunks (detail + anchor, text only)
          4. Generate embeddings (if not skip_embedding)
          5. Upsert embeddings
          6. Finalize publication embedding count

        Args:
            result: Parsed PDF result with publication metadata and detail chunks.
            embed_api_key: OpenAI API key for embedding.
            skip_embedding: Skip embedding step (text-only ingestion).
            generate_summaries: Generate Tier 1/2 anchor chunks (default True).

        Returns a summary dict with counts and timing.
        """
        from tax_brain.publications.embeddings import embed_chunks

        t_start  = time.monotonic()
        pub      = result.publication
        chunks   = list(result.chunks)  # copy to avoid mutating the original

        # ── Generate anchor chunks (three-tier hierarchy) ─────────────────
        anchor_count = 0
        if generate_summaries and chunks:
            try:
                from tax_brain.publications.summary_generator import generate_anchor_chunks
                anchors = generate_anchor_chunks(
                    pub_number=pub.pub_number,
                    pub_title=pub.pub_title,
                    tax_year=pub.tax_year,
                    detail_chunks=chunks,
                )
                chunks.extend(anchors)
                anchor_count = len(anchors)
                logger.info(
                    "Generated %d anchor chunks (1 pub summary + %d section summaries)",
                    anchor_count, anchor_count - 1,
                )
            except Exception as exc:
                logger.warning("Summary generation failed (proceeding without): %s", exc)

        # ── Contextual annotation (LLM-generated) ────────────────────────
        if not skip_embedding and chunks:
            try:
                from tax_brain.publications.context_annotator import annotate_chunks
                annotate_chunks(
                    chunks,
                    pub_title=pub.pub_title,
                    api_key=embed_api_key,
                )
                annotated_n = sum(1 for c in chunks if getattr(c, "context_annotation", ""))
                logger.info("Annotated %d/%d chunks with LLM context", annotated_n, len(chunks))
            except Exception as exc:
                logger.warning("Annotation step failed (proceeding without): %s", exc)

        # Update publication chunk_count to include anchors
        pub.chunk_count = len(chunks)
        self.upsert_publication(pub)
        self.upsert_chunks(chunks)

        embedded_count = 0
        if not skip_embedding and chunks:
            embedded = embed_chunks(chunks, api_key=embed_api_key)
            embedded_count = self.upsert_embeddings(embedded)
            self.finalize_embedding(pub.pub_id, embedded_count)

        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        summary = {
            "pub_id"        : pub.pub_id,
            "chunk_count"   : len(chunks),
            "anchor_count"  : anchor_count,
            "detail_count"  : len(chunks) - anchor_count,
            "embedded_count": embedded_count,
            "elapsed_ms"    : elapsed_ms,
        }
        logger.info("Ingest complete: %s", summary)
        return summary

    # ── Stats helpers ──────────────────────────────────────────────────────────

    def get_pub_coverage(self) -> list[dict]:
        """Return rows from v_pub_coverage view (per-publication stats)."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM irs_kb.v_pub_coverage")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _avg_tokens_for(self, pub_number: str) -> float:
        """Return average token_count for all chunks of a given pub_number."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT AVG(c.token_count)
                FROM irs_kb.publication_chunks c
                WHERE c.pub_number = %s
                """,
                (pub_number,),
            )
            result = cur.fetchone()[0]
            return float(result) if result is not None else 0.0

    def chunk_count_for(self, pub_id: str) -> int:
        """Return number of chunks stored for a given pub_id."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM irs_kb.publication_chunks WHERE pub_id = %s",
                (pub_id,),
            )
            return cur.fetchone()[0]

    def embedded_count_for(self, pub_id: str) -> int:
        """Return number of embedded (non-null vector) chunks for a given pub_id."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM irs_kb.publication_chunks
                WHERE pub_id = %s AND embedding IS NOT NULL
                """,
                (pub_id,),
            )
            return cur.fetchone()[0]

    def load_chunks_for_pub(self, pub_number: str) -> list:
        """
        Load all chunks for a publication as PublicationChunk objects.

        Used by the re-embed command to fetch existing chunk text from the DB
        without re-parsing the original PDF.  Embeddings are NOT loaded (they
        are large and would be discarded anyway before re-embedding).

        Args:
            pub_number: IRS publication number (e.g. "596", "525").

        Returns:
            List of PublicationChunk with text populated, embedding=None.
        """
        from tax_brain.publications.models import PublicationChunk

        with self._cursor() as cur:
            cur.execute(
                """
                SELECT c.chunk_id,
                       c.pub_id,
                       p.pub_number,
                       p.tax_year,
                       c.chunk_index,
                       c.page_start,
                       c.page_end,
                       c.text,
                       c.form_refs,
                       c.line_refs
                FROM   irs_kb.publication_chunks c
                JOIN   irs_kb.publications       p ON p.pub_id = c.pub_id
                WHERE  p.pub_number = %s
                   AND c.text IS NOT NULL
                ORDER  BY c.page_start, c.chunk_index
                """,
                (pub_number,),
            )
            rows = cur.fetchall()

        chunks = []
        for row in rows:
            c = PublicationChunk(
                chunk_id    = str(row[0]),
                pub_id      = str(row[1]),
                pub_number  = row[2],
                tax_year    = row[3] or 2025,
                chunk_index = row[4],
                page_start  = row[5] or 0,
                page_end    = row[6] or 0,
                text        = row[7] or "",
                form_refs   = row[8] or [],
                line_refs   = row[9] or [],
                embedding   = None,          # always clear — will be re-computed
            )
            chunks.append(c)

        logger.info(
            "Loaded %d chunks for Pub %s from DB", len(chunks), pub_number
        )
        return chunks
