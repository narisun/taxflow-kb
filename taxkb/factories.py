"""Factory functions for creating configured Tax Brain instances.

This is the composition root for the Tax Brain library. It is the ONLY module
that calls :func:`get_settings` — all other modules receive their dependencies
through constructors.

Config precedence for ``api_key`` arguments (highest → lowest):
    1. Explicit ``api_key=`` argument to the factory
    2. ``settings.openai_api_key`` (from ``.env`` or a registered source)

No ``os.getenv`` fallback — Settings IS the source.

Usage:
    from taxkb.factories import create_agent
    agent = create_agent()                      # uses get_settings()
    agent = create_agent(settings=custom)       # explicit override
    agent = create_agent(api_key="sk-...")      # only the key is overridden
"""
from __future__ import annotations

from typing import Any, Optional

from taxkb.config import Settings, get_settings


def _resolve_openai_key(settings: Settings, api_key: Optional[str]) -> str:
    """Resolve the OpenAI key from an explicit override or Settings."""
    if api_key:
        return api_key
    return settings.openai_api_key.get_secret_value()


def create_pool(settings: Optional[Settings] = None) -> "PgConnectionPool":
    """Create a PostgreSQL connection pool from settings."""
    from taxkb.adapters.postgres import PgConnectionPool
    settings = settings or get_settings()
    return PgConnectionPool(
        dsn=settings.pg_dsn,
        min_conn=settings.pool_min_conn,
        max_conn=settings.pool_max_conn,
    )


def create_embedding_client(
    settings: Optional[Settings] = None,
    api_key: Optional[str] = None,
) -> "OpenAIEmbeddingClient":
    """Create an OpenAI embedding client from settings."""
    from taxkb.adapters.openai_client import OpenAIEmbeddingClient
    settings = settings or get_settings()
    return OpenAIEmbeddingClient(
        api_key=_resolve_openai_key(settings, api_key),
        model=settings.embedding_model,
        dimensions=settings.embedding_dim,
    )


def create_completion_client(
    settings: Optional[Settings] = None,
    api_key: Optional[str] = None,
) -> "OpenAICompletionClient":
    """Create an OpenAI completion client from settings."""
    from taxkb.adapters.openai_client import OpenAICompletionClient
    settings = settings or get_settings()
    return OpenAICompletionClient(api_key=_resolve_openai_key(settings, api_key))


def create_retriever(
    settings: Optional[Settings] = None,
    pool: Optional[Any] = None,
    embedding_client: Optional[Any] = None,
    api_key: Optional[str] = None,
) -> "TaxBrainRetriever":
    """Create a TaxBrainRetriever with all leaf retrievers wired."""
    from taxkb.agent.retriever import TaxBrainRetriever
    settings = settings or get_settings()
    key = _resolve_openai_key(settings, api_key)
    _pool = pool or create_pool(settings)
    _emb = embedding_client or create_embedding_client(settings, key)
    return TaxBrainRetriever(
        pg_dsn=settings.pg_dsn,
        api_key=key,
        pool=_pool,
        embedding_client=_emb,
        enable_ontology=True,
        enable_layer1=True,
        enable_layer2=True,
    )


def create_agent(
    settings: Optional[Settings] = None,
    pool: Optional[Any] = None,
    embedding_client: Optional[Any] = None,
    completion_client: Optional[Any] = None,
    retriever: Optional[Any] = None,
    api_key: Optional[str] = None,
) -> "TaxBrainAgent":
    """Create a fully wired :class:`TaxBrainAgent`.

    Recommended entry point. All dependencies are resolved from Settings and
    can be overridden individually.
    """
    from taxkb.agent.agent import TaxBrainAgent
    settings = settings or get_settings()
    key = _resolve_openai_key(settings, api_key)
    _pool = pool or create_pool(settings)
    _emb = embedding_client or create_embedding_client(settings, key)
    _comp = completion_client or create_completion_client(settings, key)
    _ret = retriever or create_retriever(settings, _pool, _emb, key)
    return TaxBrainAgent(
        pool=_pool,
        embedding_client=_emb,
        completion_client=_comp,
        retriever=_ret,
        model=settings.synthesis_model,
        pg_dsn=settings.pg_dsn,
        api_key=key,
    )
