"""Centralized configuration for the TaxFlow RAG/KB subsystem.

Strict configuration: every field is REQUIRED. Missing env vars cause
Pydantic to raise a ValidationError at startup.

Source precedence (highest → lowest):
    1. Sources registered via :func:`register_settings_source`
    2. Values passed to ``Settings(...)`` explicitly
    3. Environment variables (including ones loaded from ``.env``)

Usage:

    from taxkb.config import get_settings
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value()
"""
from __future__ import annotations

import re
import sys
from functools import lru_cache
from typing import IO, Callable, ClassVar, Literal

from pydantic import Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


# -------------------------------------------------------------------- extension

SourceFactory = Callable[[type["Settings"]], PydanticBaseSettingsSource]

_additional_sources: list[SourceFactory] = []


def register_settings_source(factory: SourceFactory) -> None:
    """Register an additional settings source (Vault, secrets manager, DB table)."""
    _additional_sources.append(factory)


def reset_settings_sources() -> None:
    """Clear all registered sources (primarily for tests)."""
    _additional_sources.clear()


# -------------------------------------------------------------------- settings


class Settings(BaseSettings):
    """KB subsystem configuration — every field required."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Postgres primitives ─────────────────────────────────────────────────
    postgres_host: str = Field(...)
    postgres_port: int = Field(...)
    postgres_db: str = Field(...)
    postgres_user: str = Field(...)
    postgres_password: SecretStr = Field(...)

    # ── Composed Postgres DSN ───────────────────────────────────────────────
    # Stored as plain str (banner masks the password); psycopg2 needs a string.
    pg_dsn: str = Field(...)

    pool_min_conn: int = Field(...)
    pool_max_conn: int = Field(...)

    # ── Neo4j ───────────────────────────────────────────────────────────────
    neo4j_host: str = Field(...)
    neo4j_bolt_port: int = Field(...)
    neo4j_browser_port: int = Field(...)
    neo4j_uri: str = Field(...)
    neo4j_user: str = Field(...)
    neo4j_password: SecretStr = Field(...)

    # ── OpenAI ──────────────────────────────────────────────────────────────
    openai_api_key: SecretStr = Field(...)

    # ── Embedding model ─────────────────────────────────────────────────────
    embedding_model: str = Field(...)
    embedding_dim: int = Field(...)

    # ── Synthesis / completion models ──────────────────────────────────────
    synthesis_model: str = Field(...)
    judge_model: str = Field(...)
    synthesis_temperature: float = Field(...)
    synthesis_max_tokens: int = Field(...)
    synthesis_max_context_chars: int = Field(...)

    # ── Context compression ────────────────────────────────────────────────
    compression_model: str = Field(...)
    compression_max_chunks: int = Field(...)
    enable_reranking: bool = Field(...)
    enable_compression: bool = Field(...)

    # ── Retrieval ──────────────────────────────────────────────────────────
    retrieval_top_k: int = Field(...)
    bm25_extras: int = Field(...)
    bm25_min_score: float = Field(...)
    merge_strategy: Literal["augment", "rrf"] = Field(...)
    enable_query_expansion: bool = Field(default=True)

    # ── Chunking ───────────────────────────────────────────────────────────
    chunk_max_tokens: int = Field(...)
    chunk_overlap_tokens: int = Field(...)
    chunk_hard_max: int = Field(...)

    # ── Tax year ───────────────────────────────────────────────────────────
    default_tax_year: int = Field(...)
    supported_tax_years: list[int] = Field(...)

    # -------------------------------------------------------------- sources hook

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        extra = tuple(factory(settings_cls) for factory in _additional_sources)
        return (
            *extra,
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    # -------------------------------------------------------------- banner metadata

    SECRET_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "postgres_password",
        "neo4j_password",
        "openai_api_key",
    })
    DSN_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "pg_dsn",
    })
    SEMI_SECRET_FIELDS: ClassVar[frozenset[str]] = frozenset()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton accessor."""
    return Settings()


# ---------------------------------------------------------------- banner

_DSN_PASSWORD_RE = re.compile(r"://([^:/@]+):([^@]+)@")


def _mask_dsn(url: str) -> str:
    return _DSN_PASSWORD_RE.sub(r"://\1:***@", url)


def _format_field(settings: Settings, name: str) -> str:
    raw = getattr(settings, name)
    val = raw.get_secret_value() if isinstance(raw, SecretStr) else str(raw)
    if name in settings.SECRET_FIELDS:
        return "<set>" if val else "<NOT SET>"
    if name in settings.DSN_FIELDS:
        return _mask_dsn(val) if val else "<NOT SET>"
    if name in settings.SEMI_SECRET_FIELDS and val:
        return val[:7] + "***"
    return val


def print_settings_banner(
    settings: Settings | None = None,
    *,
    title: str = "TaxFlow AI — RAG / Knowledge Base",
    stream: IO = sys.stderr,
) -> None:
    """Print the active KB configuration (secrets masked) at startup."""
    s = settings or get_settings()
    fields = list(s.__class__.model_fields.keys())
    width = max(len(f) for f in fields)
    sep = "═" * 76
    sources = len(_additional_sources)
    src_word = "source" if sources == 1 else "sources"

    print(sep, file=stream)
    print(f"  {title}", file=stream)
    print(
        f"  loaded from .env + {sources} registered {src_word}",
        file=stream,
    )
    print(sep, file=stream)
    for name in fields:
        print(f"  {name.upper():<{width + 2}}{_format_field(s, name)}", file=stream)
    print(sep, file=stream)
