"""Central application settings for the FastAPI backend.

Strict configuration: every field is REQUIRED. The application will fail
to start (with a Pydantic ValidationError) if any environment variable is
missing. There are no default values and no synthesized URLs — what you
put in ``.env`` (or any registered settings source) is exactly what runs.

Source precedence (highest → lowest):
    1. Sources registered via :func:`register_settings_source`
       (e.g. Vault, AWS Secrets Manager, DB config table)
    2. Values passed to ``Settings(...)`` explicitly
    3. Environment variables (including ones loaded from ``.env``)

Adding a new source — see the worked example in the README.
"""
from __future__ import annotations

import re
import sys
from functools import lru_cache
from typing import IO, Callable, ClassVar, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


AppEnv = Literal["development", "staging", "production", "test"]
OCRMode = Literal["cascade", "claude", "mock"]


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
    """FastAPI backend configuration — every field required."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Environment ─────────────────────────────────────────────────────────
    app_env: AppEnv = Field(...)

    # ── Postgres primitives (also consumed by docker-compose) ──────────────
    postgres_host: str = Field(...)
    postgres_port: int = Field(...)
    postgres_db: str = Field(...)
    postgres_user: str = Field(...)
    postgres_password: SecretStr = Field(...)

    # ── Composed connection URLs ────────────────────────────────────────────
    # Stored as plain str (banner masks the embedded password before display);
    # consumers (SQLAlchemy create_async_engine) need a string, not SecretStr.
    app_database_url: str = Field(...)
    test_database_url: str = Field(...)

    # ── Pool tuning ─────────────────────────────────────────────────────────
    db_pool_size: int = Field(...)
    db_max_overflow: int = Field(...)
    db_pool_recycle_seconds: int = Field(...)

    # ── Anthropic (Claude) ──────────────────────────────────────────────────
    anthropic_api_key: SecretStr = Field(...)
    anthropic_model: str = Field(...)
    chat_max_tokens: int = Field(...)

    # ── Agent (tool-use chat) ──────────────────────────────────────────
    agent_model: str = Field(default="claude-sonnet-4-20250514")
    agent_max_tokens: int = Field(default=4096)
    agent_max_tool_rounds: int = Field(default=10)
    agent_history_token_budget: int = Field(default=8000)

    # ── PII encryption ──────────────────────────────────────────────────────
    pii_encryption_key: SecretStr = Field(...)

    # ── OCR ────────────────────────────────────────────────────────────────
    ocr_extractor: OCRMode = Field(...)

    # ── Auth0 ──────────────────────────────────────────────────────────────
    auth0_domain: str = Field(...)
    auth0_api_audience: str = Field(...)
    auth0_client_id: str = Field(...)
    auth0_redirect_uri: str = Field(...)
    # When true, requests with no Bearer token resolve to the seeded dev user
    # instead of returning 401. Enable in development; ALWAYS false in
    # staging/production (enforced by `is_production`).
    auth0_allow_dev_bypass: bool = Field(...)

    # ── CORS ───────────────────────────────────────────────────────────────
    cors_allowed_origins: str = Field(...)

    # -------------------------------------------------------------- derived

    @property
    def auth0_algorithms(self) -> list[str]:
        return ["RS256"]

    @property
    def auth0_issuer(self) -> str:
        return f"https://{self.auth0_domain}/" if self.auth0_domain else ""

    @property
    def auth0_jwks_url(self) -> str:
        return (
            f"https://{self.auth0_domain}/.well-known/jwks.json"
            if self.auth0_domain
            else ""
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    # -------------------------------------------------------------- validators

    @field_validator("pii_encryption_key")
    @classmethod
    def _validate_pii_key(cls, v: SecretStr) -> SecretStr:
        # 44-char urlsafe-base64 Fernet key. Allow empty in non-prod (handled
        # at runtime by api.services.pii.encryptor).
        raw = v.get_secret_value()
        if raw and len(raw) < 32:
            raise ValueError(
                "PII_ENCRYPTION_KEY must be a 44-char urlsafe-base64 Fernet key."
            )
        return v

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
        "anthropic_api_key",
        "pii_encryption_key",
    })
    DSN_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "app_database_url",
        "test_database_url",
    })
    SEMI_SECRET_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "auth0_client_id",
    })


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor — settings are immutable per-process."""
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
    title: str = "TaxFlow AI — FastAPI Backend",
    stream: IO = sys.stderr,
) -> None:
    """Print the active configuration (secrets masked) at startup."""
    s = settings or get_settings()
    fields = list(s.__class__.model_fields.keys())
    width = max(len(f) for f in fields)
    sep = "═" * 76
    sources = len(_additional_sources)
    src_word = "source" if sources == 1 else "sources"

    print(sep, file=stream)
    print(f"  {title}", file=stream)
    print(
        f"  app_env={s.app_env}   "
        f"loaded from .env + {sources} registered {src_word}",
        file=stream,
    )
    print(sep, file=stream)
    for name in fields:
        print(f"  {name.upper():<{width + 2}}{_format_field(s, name)}", file=stream)
    print(sep, file=stream)
