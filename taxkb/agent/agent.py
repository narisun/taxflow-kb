"""
taxkb/agent/agent.py

TaxBrainAgent — the CPA query agent.

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

Usage (preferred — via factory):
    from taxkb.factories import create_agent
    agent = create_agent()
    result = agent.query("What is the income limit for the EIC?")

Usage (direct — all deps injected):
    agent = TaxBrainAgent(
        pool=pool, embedding_client=emb, completion_client=comp,
        retriever=retriever, model="gpt-4o",
    )
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from taxkb.agent.models import QueryResult, RetrievedPassage
from taxkb.agent import synthesizer as _syn
from taxkb.agent.reranker import rerank_chunks, apply_positional_optimization
from taxkb.agent.compressor import compress_contexts
from taxkb.agent.classifier import classify_query, QueryMetadata
from taxkb.agent.query_expander import expand_query
from taxkb.protocols import ConnectionPool, EmbeddingClient, CompletionClient, Retriever

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration values the agent needs at query time.

    Extracted as a plain dataclass so tests can create one without
    touching Settings or environment variables.
    """
    retrieval_top_k: int = 10
    synthesis_temperature: float = 0.1
    synthesis_max_tokens: int = 1500
    default_tax_year: int = 2025
    enable_reranking: bool = True
    compression_max_chunks: int = 30
    enable_compression: bool = True
    enable_query_expansion: bool = True

    @classmethod
    def from_settings(cls, settings: Any) -> "AgentConfig":
        """Create from a Settings object."""
        return cls(
            retrieval_top_k=settings.retrieval_top_k,
            synthesis_temperature=settings.synthesis_temperature,
            synthesis_max_tokens=settings.synthesis_max_tokens,
            default_tax_year=settings.default_tax_year,
            enable_reranking=settings.enable_reranking,
            compression_max_chunks=settings.compression_max_chunks,
            enable_compression=settings.enable_compression,
            enable_query_expansion=getattr(settings, 'enable_query_expansion', True),
        )


class TaxBrainAgent:
    """
    Tax research agent for CPAs.

    All dependencies are injected via the constructor. Use
    ``taxkb.factories.create_agent()`` to build a fully wired instance
    from settings, or pass dependencies directly for testing.
    """

    def __init__(
        self,
        pool: ConnectionPool,
        embedding_client: EmbeddingClient,
        completion_client: CompletionClient,
        retriever: Retriever,
        model: str = "gpt-4o",
        config: Optional[AgentConfig] = None,
        # Kept for internal use by synthesizer / retriever sub-methods
        pg_dsn: str = "",
        api_key: str = "",
    ) -> None:
        self._pool = pool
        self._embedding_client = embedding_client
        self._completion_client = completion_client
        self._retriever = retriever
        self.model = model
        self._config = config or AgentConfig()
        self.pg_dsn = pg_dsn
        self.api_key = api_key

    def query(
        self,
        question   : str,
        top_k      : Optional[int]  = None,
        pub_filter : Optional[list[str]] = None,
        tax_year   : Optional[int] = None,
        synthesize : bool = True,
        temperature: Optional[float] = None,
        max_tokens : Optional[int] = None,
    ) -> QueryResult:
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
            QueryResult with answer, contexts, query_intent, and detected_tax_year.
        """
        if not question.strip():
            return QueryResult(
                query  = question,
                answer = "",
                error  = "Empty question.",
            )

        logger.info("TaxBrainAgent.query: %r", question[:80])

        cfg = self._config
        top_k = top_k or cfg.retrieval_top_k
        temperature = temperature if temperature is not None else cfg.synthesis_temperature
        max_tokens = max_tokens or cfg.synthesis_max_tokens

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
            tax_year = cfg.default_tax_year
            logger.debug(
                "No tax year detected or specified; defaulting to %d",
                tax_year,
            )

        # ── Query Expansion ───────────────────────────────────────────────────
        # Use LLM parametric knowledge to add IRC sections, form numbers,
        # and tax terminology synonyms to the query before retrieval.
        # The original question is preserved for synthesis; only retrieval
        # sees the expanded version.
        retrieval_query = question
        if cfg.enable_query_expansion:
            try:
                retrieval_query = expand_query(
                    query=question,
                    completion_client=self._completion_client,
                    api_key=self.api_key,
                )
            except Exception as exc:
                logger.warning("Query expansion failed: %s", exc)

        # ── Retrieval ─────────────────────────────────────────────────────────
        # All strategy selection (cross-year, scoped scenario, hierarchical,
        # flat) is now handled inside the retriever.
        contexts, retrieval_ms, retrieval_metadata = self._retriever.retrieve(
            query      = retrieval_query,
            top_k      = top_k,
            pub_filter = pub_filter,
            tax_year   = tax_year,
            query_meta = query_meta,
        )

        retrieval_mode = retrieval_metadata.get("mode", "flat")
        nav_pubs = retrieval_metadata.get("nav_pubs", [])
        ontology_pubs = retrieval_metadata.get("ontology_pubs", [])

        if not contexts:
            return QueryResult(
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
        if cfg.enable_reranking:
            query_meta_dict = {
                "intent": query_intent,
                "tax_year": detected_tax_year,
            }
            contexts = rerank_chunks(
                query          = question,
                chunks         = contexts,
                nav_pubs       = nav_pubs,
                ontology_pubs  = ontology_pubs,
                max_chunks     = cfg.compression_max_chunks,
                query_metadata = query_meta_dict,
            )
            logger.info(
                "After reranking: %d chunks (max %d)",
                len(contexts), cfg.compression_max_chunks,
            )

        # ── Context Compression ──────────────────────────────────────────────
        if cfg.enable_compression and len(contexts) > 1:
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
            return QueryResult(
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
            return QueryResult(
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

        return QueryResult(
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

