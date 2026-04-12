"""
tax_brain.publications — IRS publication PDF processing and semantic search.

Parses IRS publication PDFs into chunked passages, generates embeddings
via OpenAI, stores them in PostgreSQL with pgvector, and provides
hybrid vector + BM25 search with a topic ontology for cross-publication
navigation.
"""
from tax_brain.publications.store import PublicationStore
from tax_brain.publications.registry import get_registry
from tax_brain.publications.ontology import get_ontology

__all__ = [
    "PublicationStore",
    "get_registry",
    "get_ontology",
]
