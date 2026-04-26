"""
taxkb.publications — IRS publication PDF processing and semantic search.

Parses IRS publication PDFs into chunked passages, generates embeddings
via OpenAI, stores them in PostgreSQL with pgvector, and provides
hybrid vector + BM25 search with a topic ontology for cross-publication
navigation.
"""
from taxkb.publications.store import PublicationStore
from taxkb.publications.registry import get_registry
from taxkb.publications.ontology import get_ontology

__all__ = [
    "PublicationStore",
    "get_registry",
    "get_ontology",
]
