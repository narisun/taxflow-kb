"""
taxflow_kb/layer4/agent.py

CPAQueryAgent — the main entry point for Layer 4.

Orchestrates retrieval (hierarchical + ontology-augmented), reranking,
query-focused context compression, positional optimization, and synthesis
(OpenAI GPT-4o) to answer natural-language CPA queries with citations
to IRS publications.

Retrieval modes
───────────────
  HIERARCHICAL (default for GENERAL, LOOKUP, SCENARIO, COMPARISON):
    Stage 1 — Navigate summary chunks to identify relevant pubs/sections
    Stage 2 — Drill into detail chunks scoped to those pubs only
    Stage 3 — Ontology augment with cross-publication topic links

  SCOPED MULTI-PUB (SCENARIO queries touching multiple publications):
    Detects multi-pub scenarios from ontology topic routing, then runs
    separate scoped retrievals per publication group to prevent context
    dilution.  Merges results with deduplication.

  FLAT (FORM_LINE, RULE queries, or when no summaries exist):
    Direct vector + BM25 search across all chunks.  Already narrowly
    scoped by form/line references so hierarchy adds no value.

Usage:
    agent = CPAQueryAgent(
        pg_dsn  = "postgresql://taxflow:taxflow_dev@localhost/taxflow",
        api_key = os.environ["OPENAI_API_KEY"],
    )
    result = agent.query("What is the income limit for the EIC with one qualifying child?")
    result.print_report()
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from taxflow_kb.config import get_settings
from taxflow_kb.layer4.models_layer4 import CPAQueryResult, RetrievedContext
from taxflow_kb.layer4 import synthesizer as _syn
from taxflow_kb.layer4.reranker import rerank_chunks, apply_positional_optimization
from taxflow_kb.layer4.context_compressor import compress_contexts
from taxflow_kb.layer4.query_classifier import classify_query, QueryMetadata
from taxflow_kb.protocols import PgConnectionPool, OpenAIEmbeddingClient, OpenAICompletionClient

logger = logging.getLogger(__name__)


def _get_default_model() -> str:
    """Get the default synthesis model from centralized config."""
    return get_settings().synthesis_model


class CPAQueryAgent:
    """
    Tax research agent for CPAs.

    Uses hierarchical retrieval (navigate → drill → ontology augment) as
    the primary retrieval mode, falling back to flat search when the query
    is already narrowly scoped (FORM_LINE, RULE) or no summary chunks exist.

    For complex SCENARIO queries spanning multiple publications, the agent
    runs scoped sub-retrievals per publication group to prevent context
    dilution, then merges and deduplicates the results.

    Attributes:
        pg_dsn  : PostgreSQL DSN for the Layer 3 database.
        api_key : OpenAI API key used for both embedding and synthesis.
        model   : OpenAI chat model used for synthesis.
    """

    def __init__(
        self,
        pg_dsn  : Optional[str] = None,
        api_key : Optional[str] = None,
        model   : Optional[str] = None,
        neo4j_uri     : Optional[str] = None,
        neo4j_user    : Optional[str] = None,
        neo4j_password: Optional[str] = None,
    ) -> None:
        # Load centralized settings
        settings = get_settings()

        # Resolve pg_dsn: explicit arg > settings > error
        self.pg_dsn = pg_dsn or settings.pg_dsn
        if not self.pg_dsn:
            raise ValueError(
                "PostgreSQL DSN is required. Pass pg_dsn= or set PG_DSN in config."
            )

        # Resolve api_key: explicit arg > env var > settings > error
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "") or settings.openai_api_key.get_secret_value()
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Pass api_key=, set OPENAI_API_KEY, or configure openai_api_key."
            )

        # Resolve model: explicit arg > settings
        self.model = model or settings.synthesis_model

        # Resolve Neo4j settings
        self.neo4j_uri = neo4j_uri or settings.neo4j_uri
        self.neo4j_user = neo4j_user or settings.neo4j_user
        self.neo4j_password = neo4j_password or settings.neo4j_password.get_secret_value()

        # Initialize DI components
        self._pool = PgConnectionPool(dsn=self.pg_dsn)
        self._embedding_client = OpenAIEmbeddingClient(api_key=self.api_key)
        self._completion_client = OpenAICompletionClient(api_key=self.api_key)

        # Initialize hierarchical retriever (wraps MultiLayerRetriever internally)
        from taxflow_kb.layer4.hierarchical_retriever import HierarchicalRetriever

        self._retriever = HierarchicalRetriever(
            pg_dsn           = self.pg_dsn,
            api_key          = self.api_key,
            pool             = self._pool,
            embedding_client = self._embedding_client,
            enable_ontology  = True,
            enable_layer1    = True,
            enable_layer2    = True,
        )

    def query(
        self,
        question   : str,
        top_k      : Optional[int]  = None,
        pub_filter : Optional[list[str]] = None,
        tax_year   : Optional[int] = None,
        synthesize : bool = True,
        temperature: Optional[float] = None,
        max_tokens : Optional[int] = None,
    ) -> CPAQueryResult:
        """
        Answer a CPA question by retrieving from the knowledge base and
        synthesizing a cited response.

        Args:
            question    : Natural-language question from a CPA or tax advisor.
            top_k       : Number of publication chunks to retrieve (default from settings).
            pub_filter  : Optional list of pub numbers to restrict search to
                          (e.g. ["596", "17"]).
            tax_year    : Restrict search to chunks from this tax year.
            synthesize  : If False, return retrieved chunks only (no LLM call).
            temperature : LLM temperature (lower = more deterministic, default from settings).
            max_tokens  : Maximum tokens for the synthesized answer (default from settings).

        Returns:
            CPAQueryResult with answer, contexts, query_intent, and detected_tax_year.
        """
        if not question.strip():
            return CPAQueryResult(
                query  = question,
                answer = "",
                error  = "Empty question.",
            )

        logger.info("CPAQueryAgent.query: %r", question[:80])

        # Load settings for defaults
        settings = get_settings()
        top_k = top_k or settings.retrieval_top_k
        temperature = temperature if temperature is not None else settings.synthesis_temperature
        max_tokens = max_tokens or settings.synthesis_max_tokens

        # ── Query Classification ──────────────────────────────────────────────
        query_meta = classify_query(question)
        query_intent = query_meta.intent.value
        detected_tax_year = query_meta.tax_year
        comparison_years = query_meta.comparison_years
        logger.info(
            "Query classified: intent=%r, detected_tax_year=%r, comparison_years=%r",
            query_intent, detected_tax_year, comparison_years,
        )

        # ── Resolve effective tax year ───────────────────────────────────────
        # Always pin to a single year per retrieval call to avoid duplicates.
        if tax_year is None and detected_tax_year is not None:
            tax_year = detected_tax_year
        if tax_year is None:
            tax_year = settings.default_tax_year
            logger.debug(
                "No tax year detected or specified; defaulting to %d",
                tax_year,
            )

        # ── Retrieval ─────────────────────────────────────────────────────────
        retrieval_metadata: dict = {}

        if comparison_years and len(comparison_years) >= 2:
            # Cross-year comparison: separate single-year retrievals
            contexts, retrieval_ms, retrieval_metadata = (
                self._retrieve_cross_year(
                    question, top_k, pub_filter, comparison_years, query_meta,
                )
            )
        elif query_intent == "scenario" and pub_filter is None:
            # SCENARIO: try scoped multi-pub retrieval via ontology routing
            contexts, retrieval_ms, retrieval_metadata = (
                self._retrieve_scoped_scenario(
                    question, top_k, tax_year, query_meta,
                )
            )
        else:
            # Standard retrieval (hierarchical when summaries exist, flat otherwise)
            contexts, retrieval_ms, retrieval_metadata = self._retriever.retrieve(
                query      = question,
                top_k      = top_k,
                pub_filter = pub_filter,
                tax_year   = tax_year,
                classify   = True,
            )

        retrieval_mode = retrieval_metadata.get("mode", "flat")
        nav_pubs = retrieval_metadata.get("nav_pubs", [])
        ontology_pubs = retrieval_metadata.get("ontology_pubs", [])

        if not contexts:
            return CPAQueryResult(
                query             = question,
                answer            = "",
                contexts          = [],
                retrieval_ms      = retrieval_ms,
                query_intent      = query_intent,
                detected_tax_year = detected_tax_year,
                retrieval_mode    = retrieval_mode,
                nav_pubs          = nav_pubs,
                ontology_pubs     = ontology_pubs,
                error             = "No relevant passages found in the knowledge base.",
            )

        # ── Reranking ─────────────────────────────────────────────────────────
        if settings.enable_reranking:
            query_meta_dict = {
                "intent": query_intent,
                "tax_year": detected_tax_year,
            }
            contexts = rerank_chunks(
                query          = question,
                chunks         = contexts,
                nav_pubs       = nav_pubs,
                ontology_pubs  = ontology_pubs,
                max_chunks     = settings.compression_max_chunks,
                query_metadata = query_meta_dict,
            )
            logger.info(
                "After reranking: %d chunks (max %d)",
                len(contexts), settings.compression_max_chunks,
            )

        # ── Context Compression ──────────────────────────────────────────────
        if settings.enable_compression and len(contexts) > 1:
            query_meta_dict_compress = {
                "intent": query_intent,
                "tax_year": detected_tax_year,
            }
            contexts = compress_contexts(
                query             = question,
                chunks            = contexts,
                api_key           = self.api_key,
                completion_client = self._completion_client,
                query_metadata    = query_meta_dict_compress,
            )
            logger.info("After compression: %d entries", len(contexts))

        # ── Positional Optimization ──────────────────────────────────────────
        contexts = apply_positional_optimization(contexts)

        # ── Synthesis ─────────────────────────────────────────────────────────
        if not synthesize:
            return CPAQueryResult(
                query             = question,
                answer            = "",
                contexts          = contexts,
                retrieval_ms      = retrieval_ms,
                query_intent      = query_intent,
                detected_tax_year = detected_tax_year,
                retrieval_mode    = retrieval_mode,
                nav_pubs          = nav_pubs,
                ontology_pubs     = ontology_pubs,
            )

        try:
            query_metadata = {
                "query_intent": query_intent,
                "detected_tax_year": detected_tax_year,
                "retrieval_mode": retrieval_mode,
            }

            answer, prompt_tok, comp_tok, synthesis_ms = _syn.synthesize(
                query              = question,
                contexts           = contexts,
                api_key            = self.api_key,
                model              = self.model,
                temperature        = temperature,
                max_tokens         = max_tokens,
                completion_client  = self._completion_client,
                query_metadata     = query_metadata,
            )
        except Exception as exc:
            logger.error("Synthesis failed: %s", exc)
            return CPAQueryResult(
                query             = question,
                answer            = "",
                contexts          = contexts,
                retrieval_ms      = retrieval_ms,
                query_intent      = query_intent,
                detected_tax_year = detected_tax_year,
                retrieval_mode    = retrieval_mode,
                nav_pubs          = nav_pubs,
                ontology_pubs     = ontology_pubs,
                error             = f"Synthesis failed: {exc}",
            )

        return CPAQueryResult(
            query             = question,
            answer            = answer,
            contexts          = contexts,
            retrieval_ms      = retrieval_ms,
            synthesis_ms      = synthesis_ms,
            model_used        = self.model,
            prompt_tokens     = prompt_tok,
            completion_tokens = comp_tok,
            query_intent      = query_intent,
            detected_tax_year = detected_tax_year,
            retrieval_mode    = retrieval_mode,
            nav_pubs          = nav_pubs,
            ontology_pubs     = ontology_pubs,
        )

    # ── Scoped multi-pub retrieval for SCENARIO queries ───────────────────────

    def _retrieve_scoped_scenario(
        self,
        question: str,
        top_k: int,
        tax_year: int,
        query_meta: QueryMetadata,
    ) -> tuple[list[RetrievedContext], float, dict]:
        """
        Scoped retrieval for SCENARIO queries that span multiple publications.

        Uses the ontology to identify distinct publication groups touched by
        the query's topics, then runs separate scoped retrievals per group.
        This prevents context dilution — each sub-retrieval gets focused
        chunks from a narrow publication scope.

        Falls back to standard hierarchical retrieval if the ontology doesn't
        find multiple distinct pub groups.
        """
        import time
        t0 = time.perf_counter()
        metadata: dict = {"mode": "scoped_multi_pub", "nav_pubs": [],
                          "ontology_pubs": [], "scoped_groups": []}

        # Use ontology to find publication groups per topic
        pub_groups = self._get_ontology_pub_groups(query_meta)

        if len(pub_groups) < 2:
            # Not enough distinct groups — fall back to standard hierarchical
            logger.debug(
                "Scenario query but only %d pub groups — using hierarchical",
                len(pub_groups),
            )
            return self._retriever.retrieve(
                query    = question,
                top_k    = top_k,
                tax_year = tax_year,
                classify = True,
            )

        # Run scoped sub-retrievals per group
        logger.info(
            "Scoped scenario: %d pub groups: %s",
            len(pub_groups), pub_groups,
        )
        all_contexts: list[RetrievedContext] = []
        total_ms = 0.0
        per_group_k = max(2, top_k // len(pub_groups))
        all_nav_pubs: list[str] = []
        all_ontology_pubs: list[str] = []

        for group_pubs in pub_groups[:4]:  # Cap at 4 groups
            group_contexts, group_ms, group_meta = self._retriever.retrieve(
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
        deduped: list[RetrievedContext] = []
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
        query_meta: QueryMetadata,
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
            from taxflow_kb.layer3.topic_ontology import get_ontology

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

            # Build pub groups — one per topic, deduplicated
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

    # ── Cross-year comparison retrieval ───────────────────────────────────────

    def _retrieve_cross_year(
        self,
        question: str,
        top_k: int,
        pub_filter: Optional[list[str]],
        comparison_years: list[int],
        query_meta: QueryMetadata,
    ) -> tuple[list[RetrievedContext], float, dict]:
        """
        Run separate single-year retrievals for cross-year comparison queries.

        Each retrieval is pinned to a single year so the LLM gets clean,
        distinct content per year.
        """
        import time
        t0 = time.perf_counter()
        metadata: dict = {"mode": "cross_year_comparison", "nav_pubs": [],
                          "ontology_pubs": [], "comparison_years": comparison_years}

        logger.info("Cross-year comparison: %s", comparison_years)

        all_contexts: list[RetrievedContext] = []
        per_year_k = max(2, top_k // len(comparison_years))

        for cy in comparison_years:
            year_contexts, year_ms, year_meta = self._retriever.retrieve(
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
        deduped: list[RetrievedContext] = []
        for ctx in all_contexts:
            sig = ctx.text[:200]
            if sig not in seen_sigs:
                seen_sigs.add(sig)
                deduped.append(ctx)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        return deduped[:top_k], elapsed_ms, metadata
