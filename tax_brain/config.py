"""
tax_brain/config.py

Centralized configuration using Pydantic BaseSettings.

Loads from environment variables and .env file with sensible defaults.
All hardcoded credentials, connection strings, and model parameters
are consolidated here for single-source-of-truth management.

Usage:
    from tax_brain.config import get_settings
    settings = get_settings()    # cached singleton
    dsn = settings.pg_dsn
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

try:
    from pydantic_settings import BaseSettings
except ImportError:
    raise ImportError(
        "pydantic-settings is required for TaxFlow configuration. "
        "Install it with: pip install pydantic-settings"
    )

from pydantic import Field, SecretStr


class Settings(BaseSettings):
    """
    Centralized configuration for TaxFlow AI Knowledge Base.

    Loads from environment variables and .env file. All configuration
    is defined here rather than scattered throughout the codebase.
    """

    # ──────────────────────────────────────────────────────────────────────────
    # PostgreSQL Configuration
    # ──────────────────────────────────────────────────────────────────────────

    pg_dsn: str = Field(
        default="postgresql://taxflow:taxflow_dev@localhost:5432/taxflow",
        description="PostgreSQL connection string (DSN).",
    )

    pool_min_conn: int = Field(
        default=2,
        description="Minimum number of connections in psycopg2 connection pool.",
        ge=1,
    )

    pool_max_conn: int = Field(
        default=10,
        description="Maximum number of connections in psycopg2 connection pool.",
        ge=1,
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Neo4j Configuration
    # ──────────────────────────────────────────────────────────────────────────

    neo4j_uri: str = Field(
        default="bolt://localhost:7687",
        description="Neo4j connection URI.",
    )

    neo4j_user: str = Field(
        default="neo4j",
        description="Neo4j username.",
    )

    neo4j_password: SecretStr = Field(
        default="taxflow_dev",
        description="Neo4j password.",
    )

    # ──────────────────────────────────────────────────────────────────────────
    # OpenAI API Configuration
    # ──────────────────────────────────────────────────────────────────────────

    openai_api_key: SecretStr = Field(
        default="",
        description="OpenAI API key for embeddings and completions.",
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Embedding Model Configuration
    # ──────────────────────────────────────────────────────────────────────────

    embedding_model: str = Field(
        default="text-embedding-3-large",
        description="OpenAI embedding model to use.",
    )

    embedding_dim: int = Field(
        default=1536,
        description="Dimensionality of embeddings (1536 for text-embedding-3-large).",
        ge=1,
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Synthesis & Completion Model Configuration
    # ──────────────────────────────────────────────────────────────────────────

    synthesis_model: str = Field(
        default="gpt-4o",
        description="Model used for synthesis of final answers.",
    )

    judge_model: str = Field(
        default="gpt-4o",
        description="Model used for judging answer quality.",
    )

    synthesis_temperature: float = Field(
        default=0.1,
        description="Temperature parameter for synthesis completions.",
        ge=0.0,
        le=2.0,
    )

    synthesis_max_tokens: int = Field(
        default=1500,
        description="Maximum tokens in synthesis completion response.",
        ge=1,
    )

    synthesis_max_context_chars: int = Field(
        default=12000,
        description="Maximum character count for context passed to synthesis model.",
        ge=100,
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Context Compression Configuration
    # ──────────────────────────────────────────────────────────────────────────

    compression_model: str = Field(
        default="gpt-4o-mini",
        description="Fast model used for query-focused context compression.",
    )

    compression_max_chunks: int = Field(
        default=30,
        description="Maximum chunks to send to the synthesis model after reranking and compression.",
        ge=1,
    )

    enable_reranking: bool = Field(
        default=True,
        description="Enable query-aware chunk reranking before synthesis.",
    )

    enable_compression: bool = Field(
        default=True,
        description="Enable query-focused context compression before synthesis.",
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Retrieval Configuration
    # ──────────────────────────────────────────────────────────────────────────

    retrieval_top_k: int = Field(
        default=10,
        description="Number of top results to retrieve from vector search.",
        ge=1,
    )

    bm25_extras: int = Field(
        default=3,
        description="Number of extra BM25 results to fetch for diversity.",
        ge=0,
    )

    bm25_min_score: float = Field(
        default=0.05,
        description="Minimum BM25 relevance score threshold.",
        ge=0.0,
    )

    merge_strategy: Literal["augment", "rrf"] = Field(
        default="augment",
        description="Strategy for merging vector and BM25 results: 'augment' or 'rrf'.",
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Chunking Configuration
    # ──────────────────────────────────────────────────────────────────────────

    chunk_max_tokens: int = Field(
        default=400,
        description="Target number of tokens per chunk.",
        ge=1,
    )

    chunk_overlap_tokens: int = Field(
        default=50,
        description="Number of overlapping tokens between consecutive chunks.",
        ge=0,
    )

    chunk_hard_max: int = Field(
        default=512,
        description="Hard maximum number of tokens per chunk (safety limit).",
        ge=1,
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Tax Year Configuration
    # ──────────────────────────────────────────────────────────────────────────

    default_tax_year: int = Field(
        default=2025,
        description="Default tax year for queries when not specified.",
        ge=1900,
        le=2100,
    )

    supported_tax_years: list[int] = Field(
        default=[2022, 2023, 2024, 2025],
        description="List of supported tax years in the knowledge base.",
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Pydantic Configuration
    # ──────────────────────────────────────────────────────────────────────────

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Get or create the singleton Settings instance.

    The result is cached using functools.lru_cache to ensure that
    only one Settings instance is created, even across multiple calls.

    Returns:
        Settings: Cached singleton configuration object.

    Example:
        >>> settings = get_settings()
        >>> dsn = settings.pg_dsn
        >>> api_key = settings.openai_api_key.get_secret_value()
    """
    return Settings()
