"""
tax_brain/adapters/

Concrete implementations of the protocols defined in tax_brain.protocols.

Separating implementations from interfaces keeps protocols.py free of heavy
dependencies (psycopg2, openai) and allows tests to import only the lightweight
Protocol interfaces.
"""
from tax_brain.adapters.postgres import PgConnectionPool
from tax_brain.adapters.openai_client import OpenAIEmbeddingClient, OpenAICompletionClient

__all__ = ["PgConnectionPool", "OpenAIEmbeddingClient", "OpenAICompletionClient"]
