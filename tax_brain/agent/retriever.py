"""
tax_brain/agent/retriever.py

Unified retriever for the CPA query agent.

Combines hierarchical navigation (summary → detail → ontology augment)
with vector + BM25 hybrid search, Layer 1/2 cross-layer retrieval, and
query classification into a single cohesive class.

How it works
────────────
  Stage 1 — NAVIGATE:
    Search pub_summary and section_summary chunks to identify which
    publications and sections are most relevant to the query. This is
    like a CPA scanning their mental index: "This is an IRA question →
    Pub 590a for contributions, Pub 590b for distributions."

  Stage 2 — DRILL:
    Run vector + BM25 hybrid search over detail chunks, scoped to ONLY
    the publications identified in Stage 1. Merges results using augment
    (default) or RRF strategy. Activates Layer 1/2 when classify=True.

  Stage 3 — AUGMENT (optional):
    Use the topic ontology to find additional cross-publication sections
    that Stage 1 might have missed. For example, a question about Roth
    conversions touches both Pub 590a (conversion process) and Pub 590b
    (distribution rules after conversion).

When to use hierarchical vs flat retrieval
──────────────────────────────────────────
  - GENERAL, LOOKUP, SCENARIO, COMPARISON queries → hierarchical
  - FORM_LINE, RULE queries → flat (already narrowly scoped)
  - Explicit pub_filter → flat (user already knows the scope)
  - No summary chunks stored → flat (graceful degradation)
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from tax_brain.agent.models import RetrievedPassage

logger = logging.getLogger(__name__)


class TaxBrainRetriever:
    """
    Unified retriever: hierarchical navigation + vector/BM25 hybrid search.

    Replaces the former two-class pattern (TaxBrainRetriever wrapping
    MultiLayerRetriever). All retrieval logic lives here:

      1. Summary-based navigation (pub_summary / section_summary)
      2. Vector search (pgvector cosine similarity)
      3. BM25 keyword search (Postgres tsvector + ts_rank_cd)
      4. Hybrid merge (augment or RRF strategy)
      5. Layer 1 (MeF rules) and Layer 2 (instruction graph)
      6. Topic ontology augmentation (cross-publication links)

    Falls back to flat retrieval when:
      - No summary chunks are stored yet (graceful degradation)
      - Query intent is FORM_LINE or RULE (already narrowly scoped)
      - pub_filter is explicitly provided (user already knows the scope)
    """

    def __init__(
        self,
        pg_dsn: str = "",
        api_key: str = "",
        enable_bm25: bool = True,
        merge_strategy: str = "augment",
        rrf_k: int = 60,
        bm25_extras: int = 3,
        bm25_min_score: float = 0.05,
        pool: Optional[Any] = None,
        embedding_client: Optional[Any] = None,
        enable_ontology: bool = True,
        max_nav_pubs: int = 6,
        max_nav_sections: int = 8,
        enable_layer1: bool = True,
        enable_layer2: bool = True,
        default_tax_year: int = 2025,
    ) -> None:
        """
        Args:
            pg_dsn          : PostgreSQL DSN (required).
            api_key         : OpenAI API key (required for query embedding).
            enable_bm25     : Enable BM25 keyword search (default True).
            merge_strategy  : "augment" (default) or "rrf".
            rrf_k           : RRF constant for "rrf" strategy (default 60).
            bm25_extras     : Max BM25-only chunks to append for "augment".
            bm25_min_score  : Minimum BM25 score for extras (default 0.05).
            pool            : Optional ConnectionPool for DI.
            embedding_client: Optional EmbeddingClient for DI.
            enable_ontology : Use topic ontology for cross-pub augmentation.
            max_nav_pubs    : Max publications to scope from Stage 1 (default 4).
            max_nav_sections: Max sections to scope from Stage 1 (default 6).
            enable_layer1   : Enable Layer 1 MeF rules retriever.
            enable_layer2   : Enable Layer 2 instruction graph retriever.
            default_tax_year: Default tax year for rule filtering (default 2025).
        """
        from tax_brain.agent.search import (
            PublicationSearcher, KeywordSearcher,
            RuleSearcher, InstructionSearcher,
        )

        # ── Leaf retrievers ──────────────────────────────────────────────
        self._l3_vector = PublicationSearcher(
            pg_dsn=pg_dsn, api_key=api_key,
            pool=pool, embedding_client=embedding_client,
        )
        self._l3_bm25 = KeywordSearcher(pg_dsn=pg_dsn, pool=pool) if enable_bm25 else None
        self._l1_retriever = RuleSearcher(pg_dsn=pg_dsn, pool=pool) if enable_layer1 else None
        self._l2_retriever = InstructionSearcher(pg_dsn=pg_dsn, pool=pool) if enable_layer2 else None

        # ── Merge config ─────────────────────────────────────────────────
        self._enable_bm25 = enable_bm25
        self._merge_strategy = merge_strategy
        self._rrf_k = rrf_k
        self._bm25_extras = bm25_extras
        self._bm25_min_score = bm25_min_score
        self._default_tax_year = default_tax_year

        # ── Hierarchical + ontology config ───────────────────────────────
        self._pg_dsn = pg_dsn
        self._api_key = api_key
        self._pool = pool
        self._embedding_client = embedding_client
        self._enable_ontology = enable_ontology
        self._max_nav_pubs = max_nav_pubs
        self._max_nav_sections = max_nav_sections

    # ═════════════════════════════════════════════════════════════════════
    # Public API
    # ═════════════════════════════════════════════════════════════════════

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        pub_filter: Optional[list[str]] = None,
        tax_year: Optional[int] = None,
        query_meta: Optional[Any] = None,
        classify: bool = True,
        force_flat: bool = False,
    ) -> tuple[list[RetrievedPassage], float, dict]:
        """
        Retrieve relevant contexts for a CPA query.

        Automatically selects hierarchical or flat mode based on query
        characteristics and available data.  When *query_meta* is provided
        (pre-classified by the agent), strategy selection runs first:

          - Cross-year comparison (2+ comparison_years) → per-year retrieval
          - Scoped multi-pub scenario (intent=scenario, no pub_filter) →
            ontology-routed sub-retrievals per publication group

        If neither special strategy applies, falls through to the standard
        hierarchical / flat decision.

        Returns:
            (contexts, elapsed_ms, metadata)

            metadata dict contains:
              - "mode": "hierarchical" | "flat" | "flat_fallback"
                        | "scoped_multi_pub" | "cross_year_comparison"
              - "nav_pubs": list of publication numbers from Stage 1
              - "nav_sections": list of (pub, chapter) from Stage 1
              - "ontology_pubs": additional pubs from ontology augmentation
        """
        t0 = time.perf_counter()
        metadata: dict = {
            "mode": "flat", "nav_pubs": [], "nav_sections": [],
            "ontology_pubs": [],
        }

        # ── Strategy selection based on query metadata ───────────────────
        if query_meta is not None:
            comparison_years = getattr(query_meta, 'comparison_years', [])
            intent = getattr(query_meta, 'intent', None)
            intent_val = intent.value if intent else ""

            if comparison_years and len(comparison_years) >= 2:
                return self._retrieve_cross_year(
                    query, top_k, pub_filter, comparison_years,
                )

            if intent_val == "scenario" and pub_filter is None:
                result = self._retrieve_scoped_scenario(
                    query, top_k, tax_year, query_meta,
                )
                if result is not None:
                    return result  # None means fallback to standard

            # Classification already happened at the agent level —
            # skip re-classification inside _search.
            classify = False

        # ── Decide: hierarchical or flat? ────────────────────────────────
        use_hierarchical = (
            not force_flat
            and pub_filter is None  # User didn't pre-scope
            and self._has_summary_chunks()
        )

        if not use_hierarchical:
            # Flat — direct vector + BM25 search
            contexts, search_ms = self._search(
                query=query, top_k=top_k,
                pub_filter=pub_filter, tax_year=tax_year,
                classify=classify,
            )
            metadata["mode"] = "flat"
            total_ms = (time.perf_counter() - t0) * 1000
            return contexts, total_ms, metadata

        # ── Stage 1: NAVIGATE — search summary chunks ────────────────────
        nav_pubs, nav_sections, nav_ms = self._navigate(
            query=query, tax_year=tax_year,
            top_k=self._max_nav_sections + 2,
        )

        # If navigate found 0 pubs with year filter, retry WITHOUT year
        # filter. Summaries may only exist for the default year, but the
        # publications cover the requested year's detail chunks.
        if not nav_pubs and tax_year is not None:
            logger.info(
                "Navigate found 0 pubs for year %d — retrying without year filter",
                tax_year,
            )
            nav_pubs, nav_sections, retry_ms = self._navigate(
                query=query, tax_year=None,
                top_k=self._max_nav_sections + 2,
            )
            nav_ms += retry_ms

        metadata["nav_pubs"] = nav_pubs
        metadata["nav_sections"] = nav_sections

        # ── Check if navigation found anything useful ────────────────────
        if not nav_pubs:
            logger.info("Hierarchical nav returned 0 pubs — falling back to flat")
            contexts, search_ms = self._search(
                query=query, top_k=top_k,
                pub_filter=None, tax_year=tax_year,
                classify=classify,
            )
            metadata["mode"] = "flat_fallback"
            total_ms = (time.perf_counter() - t0) * 1000
            return contexts, total_ms, metadata

        # ── Stage 2: DRILL — search detail chunks within scoped pubs ─────
        # Truncate to top-N navigate pubs for the drill search.
        scoped_pubs = nav_pubs[:self._max_nav_pubs]

        # ── Stage 1.5: ONTOLOGY AUGMENT — cross-publication links ────────
        # Run ontology AFTER truncation so it checks against scoped_pubs,
        # not the full nav_pubs list. This ensures that pubs which the
        # navigator found (but that fell outside the top-N truncation) AND
        # which the ontology also identifies as relevant get added back.
        # Example: navigator ranks Pub 1-A at position 7 but max_nav_pubs=6;
        # the ontology matches a tip/overtime topic that includes 1-A and
        # re-adds it because 1-A is not in scoped_pubs.
        if self._enable_ontology and nav_pubs:
            ontology_pubs = self._augment_from_ontology(query, scoped_pubs)
            metadata["ontology_pubs"] = ontology_pubs
            for pn in ontology_pubs:
                if pn not in scoped_pubs:
                    scoped_pubs.append(pn)

        # For future tax years (beyond what's ingested), skip year filter
        # entirely in the drill — the data won't exist for that year.
        drill_tax_year = tax_year
        if tax_year is not None and tax_year > self._default_tax_year:
            logger.info(
                "Drill: tax_year %d > default %d — searching without year filter",
                tax_year, self._default_tax_year,
            )
            drill_tax_year = None

        logger.info(
            "Hierarchical Stage 2: drilling into pubs %s (nav took %.0f ms)",
            scoped_pubs, nav_ms,
        )

        # classify=False for drill: pubs are already scoped by navigation
        # and ontology, and the year filter is already handled. Running
        # classification again could override drill_tax_year (e.g. re-detect
        # a future year we deliberately cleared).
        contexts, drill_ms = self._search(
            query=query, top_k=top_k,
            pub_filter=scoped_pubs, tax_year=drill_tax_year,
            classify=False,
        )

        # ── Year-gap backfill: some navigated pubs may only have chunks
        # at a different year (e.g. Pub 535 ingested as 2022, query is
        # 2025).  If a navigated pub returned 0 contexts, retry that pub
        # without the year filter and merge results in.
        #
        # CRITICAL: This also handles the case where drill returned 0
        # contexts entirely (e.g. all data is 2025 but query asks about
        # 2026). In that case, retry ALL scoped pubs without year filter.
        if tax_year is not None:
            retrieved_pub_set = {c.reference for c in contexts} if contexts else set()
            missing_pubs = [p for p in scoped_pubs if p not in retrieved_pub_set]

            if missing_pubs:
                logger.info(
                    "Drill year-gap backfill: pubs %s returned 0 contexts "
                    "for year %d — retrying without year filter",
                    missing_pubs, tax_year,
                )
                backfill_ctx, backfill_ms = self._search(
                    query=query, top_k=max(5, top_k),
                    pub_filter=missing_pubs, tax_year=None,
                    classify=False,
                )
                drill_ms += backfill_ms
                if backfill_ctx:
                    # Append backfill contexts (lower priority than year-matched)
                    existing_ids = {c.chunk_id for c in contexts}
                    for c in backfill_ctx:
                        if c.chunk_id not in existing_ids:
                            contexts.append(c)
                            existing_ids.add(c.chunk_id)
                    logger.info(
                        "Backfill added %d contexts from pubs %s",
                        len(backfill_ctx), missing_pubs,
                    )

        # ── Scoped pub guarantee: ensure all scoped pubs have representation ─
        # When the navigator and ontology identified a pub as relevant but
        # the drill's top-k results don't include any chunks from that pub
        # (e.g. form PDFs like Schedule 1-A whose field-label text embeds
        # poorly against natural language queries), inject their summary
        # chunks directly by pub_number — bypassing vector similarity.
        #
        # Summary chunks are LLM-generated natural language descriptions
        # created during ingestion. They describe what the publication
        # covers in conversational terms, which is exactly what the
        # synthesizer needs to answer the user's question.
        #
        # If no summary chunks exist for a missing pub, fall back to
        # injecting ALL detail chunks (for very small pubs like 2-page
        # forms, this is the entire publication content).
        if scoped_pubs:
            retrieved_pub_set = {c.reference for c in contexts} if contexts else set()
            missing_scoped_pubs = [
                p for p in scoped_pubs
                if p not in retrieved_pub_set
            ]
            if missing_scoped_pubs:
                logger.info(
                    "Scoped pub guarantee: pubs %s scoped but absent from "
                    "drill results — injecting summary chunks directly",
                    missing_scoped_pubs,
                )
                guarantee_contexts = self._inject_summaries_for_pubs(
                    missing_scoped_pubs, tax_year=None,
                )
                if guarantee_contexts:
                    existing_ids = {c.chunk_id for c in contexts}
                    added = 0
                    for c in guarantee_contexts:
                        if c.chunk_id not in existing_ids:
                            contexts.append(c)
                            existing_ids.add(c.chunk_id)
                            added += 1
                    if added:
                        logger.info(
                            "Scoped pub guarantee injected %d summary/detail "
                            "chunks from pubs %s",
                            added, missing_scoped_pubs,
                        )

        # ── Prepend navigation summaries for context ─────────────────────
        # Pass tax_year=None so we also get summaries from year-mismatched
        # pubs (e.g. Pub 535 summaries at year=2022).
        # Only prepend when drill found detail contexts — otherwise we'd
        # return stale summaries for a year that genuinely has no data.
        if contexts:
            nav_summary_contexts = self._get_nav_summaries(
                query=query, scoped_pubs=scoped_pubs, tax_year=None,
            )
            if nav_summary_contexts:
                detail_ids = {c.chunk_id for c in contexts}
                unique_nav = [c for c in nav_summary_contexts if c.chunk_id not in detail_ids]
                contexts = unique_nav[:2] + contexts  # Max 2 summary anchors

        metadata["mode"] = "hierarchical"
        total_ms = (time.perf_counter() - t0) * 1000

        logger.info(
            "TaxBrainRetriever: %d contexts in %.0f ms "
            "(nav=%.0f ms, drill=%.0f ms, pubs=%s)",
            len(contexts), total_ms, nav_ms, drill_ms, scoped_pubs,
        )

        return contexts, total_ms, metadata

    def classify_and_retrieve(
        self,
        query: str,
        top_k: int = 10,
        pub_filter: Optional[list[str]] = None,
        tax_year: Optional[int] = None,
    ) -> tuple[dict, list[RetrievedPassage], float]:
        """
        Retrieve with automatic query classification.

        Convenience method that always runs classification and returns
        both the query metadata (intent, form_refs, etc.) and the results.

        Returns:
            (query_metadata, contexts, total_elapsed_ms)
        """
        from tax_brain.agent.classifier import classify_query

        t0 = time.perf_counter()
        query_meta = classify_query(query)
        query_metadata = {
            "intent": query_meta.intent.value,
            "form_refs": query_meta.form_refs,
            "topic_tags": query_meta.topic_tags,
            "tax_year": query_meta.tax_year,
        }

        contexts, _, metadata = self.retrieve(
            query, top_k=top_k,
            pub_filter=pub_filter, tax_year=tax_year,
            classify=True,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        return query_metadata, contexts, elapsed_ms

    # ═════════════════════════════════════════════════════════════════════
    # Retrieval strategies (moved from agent.py)
    # ═════════════════════════════════════════════════════════════════════

    def _retrieve_scoped_scenario(
        self,
        question: str,
        top_k: int,
        tax_year: int,
        query_meta: Any,
    ) -> Optional[tuple[list[RetrievedPassage], float, dict]]:
        """
        Scoped retrieval for SCENARIO queries that span multiple publications.

        Uses the ontology to identify distinct publication groups touched by
        the query's topics, then runs separate scoped retrievals per group.
        This prevents context dilution -- each sub-retrieval gets focused
        chunks from a narrow publication scope.

        Returns None if the ontology doesn't find multiple distinct pub
        groups, signalling the caller to fall through to standard retrieval.
        """
        t0 = time.perf_counter()
        metadata: dict = {"mode": "scoped_multi_pub", "nav_pubs": [],
                          "ontology_pubs": [], "scoped_groups": []}

        # Use ontology to find publication groups per topic
        pub_groups = self._get_ontology_pub_groups(query_meta)

        if len(pub_groups) < 2:
            # Not enough distinct groups -- signal caller to use standard
            logger.debug(
                "Scenario query but only %d pub groups -- using hierarchical",
                len(pub_groups),
            )
            return None

        # Run scoped sub-retrievals per group
        logger.info(
            "Scoped scenario: %d pub groups: %s",
            len(pub_groups), pub_groups,
        )
        all_contexts: list[RetrievedPassage] = []
        total_ms = 0.0
        per_group_k = max(2, top_k // len(pub_groups))
        all_nav_pubs: list[str] = []
        all_ontology_pubs: list[str] = []

        for group_pubs in pub_groups[:4]:  # Cap at 4 groups
            group_contexts, group_ms, group_meta = self.retrieve(
                query      = question,
                top_k      = per_group_k,
                pub_filter = group_pubs,
                tax_year   = tax_year,
                classify   = False,  # Already classified at the agent level
            )
            all_contexts.extend(group_contexts)
            total_ms += group_ms
            all_nav_pubs.extend(group_meta.get("nav_pubs", []))
            all_ontology_pubs.extend(group_meta.get("ontology_pubs", []))
            metadata["scoped_groups"].append(group_pubs)

        # Deduplicate by chunk text prefix (same chunk from different groups)
        seen_sigs: set[str] = set()
        deduped: list[RetrievedPassage] = []
        for ctx in all_contexts:
            sig = ctx.text[:200]
            if sig not in seen_sigs:
                seen_sigs.add(sig)
                deduped.append(ctx)

        # Sort by score descending and cap at top_k
        deduped.sort(key=lambda c: c.score, reverse=True)
        final = deduped[:top_k]

        elapsed_ms = (time.perf_counter() - t0) * 1000
        metadata["nav_pubs"] = list(dict.fromkeys(all_nav_pubs))  # dedupe, preserve order
        metadata["ontology_pubs"] = list(dict.fromkeys(all_ontology_pubs))

        logger.info(
            "Scoped scenario: %d contexts from %d groups in %.0f ms",
            len(final), len(pub_groups), elapsed_ms,
        )

        return final, elapsed_ms, metadata

    def _get_ontology_pub_groups(
        self,
        query_meta: Any,
    ) -> list[list[str]]:
        """
        Use the ontology to find distinct publication groups for a query.

        Each group is a list of publication numbers covering a single topic.
        A query about "sold rental property, depreciation recapture, Schedule D"
        might produce:
          - Group 1: ["527"] (rental property)
          - Group 2: ["946"] (depreciation)
          - Group 3: ["544", "550"] (capital gains / sales)

        Returns list of pub groups. Empty list if ontology can't help.
        """
        try:
            from tax_brain.publications.ontology import get_ontology

            ontology = get_ontology()

            # Match topics from query
            matched_topics = ontology.find_by_query(query_meta.original_query)
            if not matched_topics:
                # Also try the classifier's topic_tags
                for tag in query_meta.topic_tags:
                    for t in ontology.find_by_term(tag):
                        if t not in matched_topics:
                            matched_topics.append(t)

            if not matched_topics:
                return []

            # Build pub groups -- one per topic, deduplicated
            groups: list[list[str]] = []
            all_seen_pubs: set[str] = set()

            for topic in matched_topics[:5]:  # Top 5 matching topics
                topic_pubs = ontology.get_pub_numbers_for_topic(topic.topic_id)
                # Only keep pubs not already assigned to a prior group
                unique_pubs = [pn for pn in topic_pubs if pn not in all_seen_pubs]
                if unique_pubs:
                    groups.append(unique_pubs[:3])  # Cap group size
                    all_seen_pubs.update(unique_pubs[:3])

            return groups

        except Exception as exc:
            logger.debug("Ontology pub grouping failed: %s", exc)
            return []

    def _retrieve_cross_year(
        self,
        question: str,
        top_k: int,
        pub_filter: Optional[list[str]],
        comparison_years: list[int],
    ) -> tuple[list[RetrievedPassage], float, dict]:
        """
        Run separate single-year retrievals for cross-year comparison queries.

        Each retrieval is pinned to a single year so the LLM gets clean,
        distinct content per year.
        """
        t0 = time.perf_counter()
        metadata: dict = {"mode": "cross_year_comparison", "nav_pubs": [],
                          "ontology_pubs": [], "comparison_years": comparison_years}

        logger.info("Cross-year comparison: %s", comparison_years)

        all_contexts: list[RetrievedPassage] = []
        per_year_k = max(2, top_k // len(comparison_years))

        for cy in comparison_years:
            year_contexts, year_ms, year_meta = self.retrieve(
                question,
                top_k      = per_year_k,
                pub_filter = pub_filter,
                tax_year   = cy,
                classify   = True,
            )
            all_contexts.extend(year_contexts)
            # Accumulate navigation metadata
            for pn in year_meta.get("nav_pubs", []):
                if pn not in metadata["nav_pubs"]:
                    metadata["nav_pubs"].append(pn)
            for pn in year_meta.get("ontology_pubs", []):
                if pn not in metadata["ontology_pubs"]:
                    metadata["ontology_pubs"].append(pn)

        # Deduplicate
        seen_sigs: set[str] = set()
        deduped: list[RetrievedPassage] = []
        for ctx in all_contexts:
            sig = ctx.text[:200]
            if sig not in seen_sigs:
                seen_sigs.add(sig)
                deduped.append(ctx)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        return deduped[:top_k], elapsed_ms, metadata

    # ═════════════════════════════════════════════════════════════════════
    # Core search engine (vector + BM25 + Layer 1/2)
    # ═════════════════════════════════════════════════════════════════════

    def _search(
        self,
        query: str,
        top_k: int = 10,
        pub_filter: Optional[list[str]] = None,
        tax_year: Optional[int] = None,
        classify: bool = False,
    ) -> tuple[list[RetrievedPassage], float]:
        """
        Execute vector + BM25 hybrid search with optional classification.

        This is the core search engine that runs:
          1. Query classification (when classify=True)
          2. Layer 3 vector search (always)
          3. Layer 3 BM25 search (when enabled)
          4. Merge results (augment or RRF strategy)
          5. Layer 1/2 activation (when classify=True and intent matches)

        Returns:
            (contexts, elapsed_ms)
        """
        from tax_brain.agent.search import (
            normalize_query, _rrf_merge, _hybrid_merge_augment,
        )

        t0 = time.perf_counter()

        # ── Query classification (optional) ──────────────────────────────
        layer1_contexts: list[RetrievedPassage] = []
        layer2_contexts: list[RetrievedPassage] = []
        l1_ms = 0.0
        l2_ms = 0.0

        if classify:
            try:
                from tax_brain.agent.classifier import (
                    classify_query, suggest_pub_filter,
                )

                query_meta = classify_query(query)
                query_intent = query_meta.intent.value
                form_refs = query_meta.form_refs
                line_refs = getattr(query_meta, "line_refs", [])
                detected_tax_year = query_meta.tax_year

                # Use detected tax_year if no explicit one was passed
                if tax_year is None and detected_tax_year is not None:
                    tax_year = detected_tax_year
                    logger.debug("Using detected tax_year: %d", tax_year)

                # Fall back to default year to avoid cross-year duplicates
                if tax_year is None:
                    tax_year = self._default_tax_year
                    logger.debug("No tax year detected; defaulting to %d", tax_year)

                # Use suggested pub_filter if no explicit one was passed
                if pub_filter is None:
                    detected_pubs = suggest_pub_filter(query_meta)
                    if detected_pubs:
                        pub_filter = detected_pubs
                        logger.debug("Using suggested pub_filter: %s", pub_filter)

                logger.debug(
                    "Query classified: intent=%s, forms=%s, tax_year=%s",
                    query_intent, form_refs, tax_year,
                )

                # Activate Layer 1 for RULE and FORM_LINE queries
                if self._l1_retriever and query_intent in ("RULE", "FORM_LINE"):
                    try:
                        layer1_contexts, l1_ms = self._l1_retriever.retrieve(
                            query, form_refs=form_refs, top_k=3,
                            tax_year=tax_year or self._default_tax_year,
                        )
                        if layer1_contexts:
                            logger.debug("Layer 1: %d results", len(layer1_contexts))
                    except Exception as exc:
                        logger.warning("Layer 1 retrieval error: %s", exc)

                # Activate Layer 2 for FORM_LINE queries
                if self._l2_retriever and query_intent == "FORM_LINE":
                    try:
                        layer2_contexts, l2_ms = self._l2_retriever.retrieve(
                            query, line_refs=line_refs,
                            form_refs=form_refs, top_k=3,
                        )
                        if layer2_contexts:
                            logger.debug("Layer 2: %d results", len(layer2_contexts))
                    except Exception as exc:
                        logger.warning("Layer 2 retrieval error: %s", exc)

            except ImportError:
                logger.debug("Query classifier not available; proceeding without")
            except Exception as exc:
                logger.warning("Query classification failed: %s", exc)

        # ── Normalise query ──────────────────────────────────────────────
        norm_query = normalize_query(query)

        # ── Layer 3 vector search — always ───────────────────────────────
        vec_contexts, vec_ms = self._l3_vector.retrieve(
            norm_query, top_k=top_k,
            pub_numbers=pub_filter, tax_year=tax_year,
        )

        # ── Layer 3 BM25 — when enabled ─────────────────────────────────
        bm25_contexts: list[RetrievedPassage] = []
        bm25_ms = 0.0
        if self._l3_bm25 is not None:
            bm25_contexts, bm25_ms = self._l3_bm25.retrieve(
                norm_query, top_k=top_k,
                pub_numbers=pub_filter, tax_year=tax_year,
            )

        # ── Merge Layer 3 results ────────────────────────────────────────
        if bm25_contexts:
            if self._merge_strategy == "rrf":
                all_contexts = _rrf_merge(
                    [vec_contexts, bm25_contexts],
                    top_k=top_k, k=self._rrf_k,
                )
            else:
                all_contexts = _hybrid_merge_augment(
                    vec_contexts, bm25_contexts,
                    top_k=top_k,
                    max_bm25_extras=self._bm25_extras,
                    bm25_min_score=self._bm25_min_score,
                )
            mode = "hybrid"
        else:
            all_contexts = vec_contexts[:top_k]
            mode = "vector"

        # ── Prepend Layer 1/2 results as highest-priority ────────────────
        final_contexts: list[RetrievedPassage] = []
        if layer1_contexts:
            final_contexts.extend(layer1_contexts[:3])
        if layer2_contexts:
            final_contexts.extend(layer2_contexts[:3])
        final_contexts.extend(all_contexts)

        max_results = top_k + self._bm25_extras if mode == "hybrid" else top_k
        final_contexts = final_contexts[:max_results]

        elapsed_ms = (time.perf_counter() - t0) * 1000
        strategy_label = f"{mode}:{self._merge_strategy}" if mode == "hybrid" else mode
        layer_info = ""
        if layer1_contexts or layer2_contexts:
            layer_info = f", l1={len(layer1_contexts)}, l2={len(layer2_contexts)}"

        logger.info(
            "Search [%s]: %d contexts in %.0f ms "
            "(vec=%.0f ms, bm25=%.0f ms%s)",
            strategy_label, len(final_contexts), elapsed_ms, vec_ms, bm25_ms, layer_info,
        )
        return final_contexts, elapsed_ms

    # ═════════════════════════════════════════════════════════════════════
    # Hierarchical navigation internals
    # ═════════════════════════════════════════════════════════════════════

    def _has_summary_chunks(self) -> bool:
        """Check if the database contains any summary chunks."""
        try:
            from tax_brain.publications.store import PublicationStore

            if not self._pool:
                return False
            conn = self._pool.getconn()
            try:
                with PublicationStore(conn=conn) as store:
                    return store.has_chunk_type("pub_summary")
            finally:
                self._pool.putconn(conn)
        except Exception:
            return False

    def _navigate(
        self,
        query: str,
        tax_year: Optional[int],
        top_k: int = 8,
    ) -> tuple[list[str], list[tuple[str, str]], float]:
        """
        Stage 1: Search summary chunks to identify relevant pubs and sections.

        Returns:
            (pub_numbers, section_tuples, elapsed_ms)
            where section_tuples = [(pub_number, chapter_title), ...]
        """
        from tax_brain.agent.search import normalize_query

        t0 = time.perf_counter()
        norm_query = normalize_query(query)

        try:
            from tax_brain.publications.store import PublicationStore
            from tax_brain.publications.embeddings import embed_query

            # Embed the query
            if self._embedding_client:
                q_vec = self._embedding_client.embed_query(norm_query)
            else:
                q_vec = embed_query(norm_query, api_key=self._api_key)

            # Search only summary chunks
            if not self._pool:
                raise RuntimeError("No connection pool available for navigation")
            conn = self._pool.getconn()
            try:
                with PublicationStore(conn=conn) as store:
                    results = store.search_summaries(
                        q_vec, top_k=top_k, tax_year=tax_year,
                    )
            finally:
                self._pool.putconn(conn)

            # Extract unique pubs and sections
            nav_pubs: list[str] = []
            nav_sections: list[tuple[str, str]] = []
            seen_pubs: set[str] = set()

            for r in results:
                if r.pub_number not in seen_pubs:
                    seen_pubs.add(r.pub_number)
                    nav_pubs.append(r.pub_number)
                if r.chapter_title and r.chapter_title != "(Publication Summary)":
                    section_key = (r.pub_number, r.chapter_title)
                    if section_key not in nav_sections:
                        nav_sections.append(section_key)

            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.debug(
                "Navigate: %d pubs, %d sections in %.0f ms",
                len(nav_pubs), len(nav_sections), elapsed_ms,
            )
            return nav_pubs, nav_sections, elapsed_ms

        except Exception as exc:
            logger.warning("Navigation failed: %s — falling back to flat", exc)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            return [], [], elapsed_ms

    def _augment_from_ontology(
        self,
        query: str,
        nav_pubs: list[str],
    ) -> list[str]:
        """
        Use the topic ontology to find additional cross-publication sections.

        If the query matches a topic whose pub_sections include pubs NOT
        already in nav_pubs, add those as supplementary scope.
        """
        try:
            from tax_brain.publications.ontology import get_ontology

            ontology = get_ontology()
            matched_topics = ontology.find_by_query(query)

            augment_pubs: list[str] = []
            for topic in matched_topics[:7]:
                for pn in ontology.get_pub_numbers_for_topic(topic.topic_id):
                    if pn not in nav_pubs and pn not in augment_pubs:
                        augment_pubs.append(pn)

            if augment_pubs:
                logger.debug(
                    "Ontology augment: added pubs %s from topics %s",
                    augment_pubs, [t.topic_id for t in matched_topics[:5]],
                )

            return augment_pubs[:10]

        except Exception as exc:
            logger.warning("Ontology augment failed: %s", exc, exc_info=True)
            return []

    def _get_nav_summaries(
        self,
        query: str,
        scoped_pubs: list[str],
        tax_year: Optional[int],
    ) -> list[RetrievedPassage]:
        """
        Retrieve the top pub/section summary chunks for the scoped pubs.

        These are prepended to detail results as anchor context for the
        LLM synthesizer.
        """
        try:
            from tax_brain.publications.store import PublicationStore
            from tax_brain.publications.embeddings import embed_query
            from tax_brain.agent.search import normalize_query

            norm_query = normalize_query(query)

            if self._embedding_client:
                q_vec = self._embedding_client.embed_query(norm_query)
            else:
                q_vec = embed_query(norm_query, api_key=self._api_key)

            if not self._pool:
                return []
            conn = self._pool.getconn()
            try:
                with PublicationStore(conn=conn) as store:
                    results = store.search_summaries(
                        q_vec, top_k=3,
                        pub_numbers=scoped_pubs, tax_year=tax_year,
                    )
            finally:
                self._pool.putconn(conn)

            from tax_brain.publications.models import PUB_TITLES

            contexts = []
            for r in results:
                pub_title = PUB_TITLES.get(r.pub_number, f"Pub {r.pub_number}")
                ctx = RetrievedPassage(
                    layer=3,
                    source_type="publication",
                    reference=r.pub_number,
                    title=pub_title,
                    text=r.text,
                    score=r.score,
                    page=r.page_start,
                    chunk_id=r.chunk_id,
                    chapter=r.chapter_title or "",
                    section=r.section_title or "",
                    retrieval_method="hierarchical_nav",
                    chunk_type=(
                        r.chunk_id.split("::")[-1]
                        if "::" in r.chunk_id else "summary"
                    ),
                )
                contexts.append(ctx)
            return contexts

        except Exception as exc:
            logger.debug("Nav summary retrieval failed: %s", exc)
            return []

    def _inject_summaries_for_pubs(
        self,
        pub_numbers: list[str],
        tax_year: Optional[int] = None,
    ) -> list[RetrievedPassage]:
        """
        Directly fetch summary chunks for pubs by pub_number (no embedding).

        This is the scoped-pub guarantee's workhorse. When vector search
        can't surface a pub's chunks (e.g. Schedule 1-A form text that
        embeds poorly), this bypasses similarity search entirely and
        fetches the LLM-generated summary chunks by direct DB lookup.

        If a pub has no summary chunks (e.g. very small form PDFs that
        weren't summarised during ingestion), falls back to fetching ALL
        detail chunks for that pub — for a 2-page form, this is the
        entire publication content.

        Returns up to 3 chunks per pub (prioritising pub_summary, then
        section_summary, then detail).
        """
        try:
            from tax_brain.publications.store import PublicationStore
            from tax_brain.publications.models import PUB_TITLES

            if not self._pool:
                return []
            conn = self._pool.getconn()
            try:
                with PublicationStore(conn=conn) as store:
                    results = store.get_summary_chunks(
                        pub_numbers=pub_numbers, tax_year=tax_year,
                    )
                    # If no summaries, try fetching detail chunks instead
                    if not results:
                        results = store.get_summary_chunks(
                            pub_numbers=pub_numbers, tax_year=tax_year,
                            chunk_types=["detail"],
                        )
            finally:
                self._pool.putconn(conn)

            if not results:
                logger.info(
                    "Scoped pub guarantee: no summary or detail chunks "
                    "found for pubs %s (tax_year=%s)",
                    pub_numbers, tax_year,
                )
                return []

            # Group by pub_number and take up to 3 chunks per pub
            from collections import defaultdict
            by_pub: dict[str, list] = defaultdict(list)
            for r in results:
                by_pub[r.pub_number].append(r)

            contexts: list[RetrievedPassage] = []
            for pn, chunks in by_pub.items():
                pub_title = PUB_TITLES.get(pn, f"Pub {pn}")
                for r in chunks[:3]:  # Max 3 per pub
                    ctx = RetrievedPassage(
                        layer=3,
                        source_type="publication",
                        reference=r.pub_number,
                        title=pub_title,
                        text=r.text,
                        score=0.5,  # Neutral score — not similarity-ranked
                        page=r.page_start,
                        chunk_id=r.chunk_id,
                        chapter=r.chapter_title or "",
                        section=r.section_title or "",
                        retrieval_method="scoped_pub_guarantee",
                        chunk_type=(
                            r.chunk_id.split("::")[-1]
                            if "::" in r.chunk_id else "detail"
                        ),
                    )
                    contexts.append(ctx)

            logger.info(
                "Scoped pub guarantee: fetched %d chunks for %d pubs %s",
                len(contexts), len(by_pub), list(by_pub.keys()),
            )
            return contexts

        except Exception as exc:
            logger.warning("Scoped pub guarantee summary injection failed: %s", exc)
            return []
