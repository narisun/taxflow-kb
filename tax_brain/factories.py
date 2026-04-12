"""
tax_brain/factories.py

Factory functions for creating configured instances.

This is the composition root for the Tax Brain library. It is the ONLY
module that calls get_settings() — all other modules receive their
dependencies through constructors.

Usage:
    from tax_brain.factories import create_agent
    agent = create_agent()  # uses default settings
    agent = create_agent(settings=custom_settings)  # override
"""
from __future__ import annotations

import os
from typing import Any, Optional

from tax_brain.config import Settings, get_settings


def create_pool(settings: Optional[Settings] = None) -> "PgConnectionPool":
    """Create a PostgreSQL connection pool from settings."""
    from tax_brain.adapters.postgres import PgConnectionPool
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
    from tax_brain.adapters.openai_client import OpenAIEmbeddingClient
    settings = settings or get_settings()
    key = api_key or os.environ.get("OPENAI_API_KEY", "") or settings.openai_api_key.get_secret_value()
    return OpenAIEmbeddingClient(
        api_key=key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dim,
    )


def create_completion_client(
    settings: Optional[Settings] = None,
    api_key: Optional[str] = None,
) -> "OpenAICompletionClient":
    """Create an OpenAI completion client from settings."""
    from tax_brain.adapters.openai_client import OpenAICompletionClient
    settings = settings or get_settings()
    key = api_key or os.environ.get("OPENAI_API_KEY", "") or settings.openai_api_key.get_secret_value()
    return OpenAICompletionClient(api_key=key)


def create_retriever(
    settings: Optional[Settings] = None,
    pool: Optional[Any] = None,
    embedding_client: Optional[Any] = None,
    api_key: Optional[str] = None,
) -> "TaxBrainRetriever":
    """Create a TaxBrainRetriever with all leaf retrievers wired."""
    from tax_brain.agent.retriever import TaxBrainRetriever
    settings = settings or get_settings()
    key = api_key or os.environ.get("OPENAI_API_KEY", "") or settings.openai_api_key.get_secret_value()
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
    """
    Create a fully wired TaxBrainAgent.

    This is the recommended way to create an agent. All dependencies
    are resolved from settings and can be overridden individually.
    """
    from tax_brain.agent.agent import TaxBrainAgent
    settings = settings or get_settings()
    key = api_key or os.environ.get("OPENAI_API_KEY", "") or settings.openai_api_key.get_secret_value()
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
