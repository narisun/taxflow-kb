"""taxkb/cli/config_adapter.py

Resolves configuration for a CLI invocation with a single, clear precedence:

    CLI flag  >  Settings (env / .env / registered sources)

No ``os.getenv`` lookups — Settings is the sole source for environment values.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CliConfig:
    """Resolved configuration for a CLI invocation."""
    pg_dsn: str = ""
    api_key: str = ""
    neo4j_uri: str = ""
    neo4j_user: str = ""
    neo4j_password: str = ""

    @classmethod
    def from_args(cls, args, settings=None) -> "CliConfig":
        """Resolve CLI args with Settings as the fallback."""
        if settings is None:
            from taxkb.config import get_settings
            settings = get_settings()
        return cls(
            pg_dsn=getattr(args, 'pg_dsn', None) or settings.pg_dsn,
            api_key=(
                getattr(args, 'api_key', None)
                or settings.openai_api_key.get_secret_value()
            ),
            neo4j_uri=getattr(args, 'neo4j_uri', None) or settings.neo4j_uri,
            neo4j_user=getattr(args, 'neo4j_user', None) or settings.neo4j_user,
            neo4j_password=(
                getattr(args, 'neo4j_password', None)
                or settings.neo4j_password.get_secret_value()
            ),
        )


def resolve_openai_key(args, settings=None) -> Optional[str]:
    """Shorthand for the common "resolve just the OpenAI key" pattern.

    Precedence:
        1. ``args.api_key`` (CLI flag)
        2. ``settings.openai_api_key`` (from Settings)
    """
    if settings is None:
        from taxkb.config import get_settings
        settings = get_settings()
    explicit = getattr(args, "api_key", None)
    if explicit:
        return explicit
    key = settings.openai_api_key.get_secret_value()
    return key or None
