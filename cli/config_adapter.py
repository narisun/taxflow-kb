"""
cli/config_adapter.py

Resolves configuration from CLI args -> environment -> Settings.
Single place for the precedence logic that was repeated in every handler.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
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
        """Resolve CLI args with settings fallbacks."""
        if settings is None:
            from tax_brain.config import get_settings
            settings = get_settings()
        return cls(
            pg_dsn=getattr(args, 'pg_dsn', None) or settings.pg_dsn,
            api_key=getattr(args, 'api_key', None) or os.environ.get("OPENAI_API_KEY", "") or settings.openai_api_key.get_secret_value(),
            neo4j_uri=getattr(args, 'neo4j_uri', None) or settings.neo4j_uri,
            neo4j_user=getattr(args, 'neo4j_user', None) or settings.neo4j_user,
            neo4j_password=getattr(args, 'neo4j_password', None) or settings.neo4j_password.get_secret_value(),
        )
