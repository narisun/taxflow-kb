"""
taxkb/adapters/

Concrete implementations of the protocols defined in taxkb.protocols.

Separating implementations from interfaces keeps protocols.py free of heavy
dependencies (psycopg2, openai) and allows tests to import only the lightweight
Protocol interfaces.
"""
from taxkb.adapters.postgres import PgConnectionPool
from taxkb.adapters.openai_client import OpenAIEmbeddingClient, OpenAICompletionClient

__all__ = ["PgConnectionPool", "OpenAIEmbeddingClient", "OpenAICompletionClient"]
