"""
tax_brain/protocols.py

Pure protocol interfaces for dependency injection.

All external dependencies (database connections, API clients, etc.)
are defined as Protocols so that:
  1. Tests can substitute lightweight fakes without mocking internals
  2. Concrete implementations can be swapped without changing callers
  3. Type checkers verify interface conformance statically

Concrete implementations live in tax_brain.adapters.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


# ──────────────────────────────────────────────────────────────────────────────
# Protocols (interfaces)
# ──────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class Retriever(Protocol):
    """
    Protocol for the query retrieval pipeline.

    Any retrieval backend (hierarchical, LightRAG, flat vector, etc.)
    that implements this method can serve as the agent's retriever.

    The metadata dict is backend-specific — callers should treat it as
    opaque except for the "mode" key which is always present.
    """

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        pub_filter: Optional[list[str]] = None,
        tax_year: Optional[int] = None,
        query_meta: Optional[Any] = None,
    ) -> tuple[list[Any], float, dict]:
        """
        Retrieve relevant passages for a query.

        Args:
            query      : Natural-language question.
            top_k      : Maximum number of passages to return.
            pub_filter : Optional publication numbers to restrict search.
            tax_year   : Optional tax year filter.
            query_meta : Optional QueryMetadata from the classifier.

        Returns:
            tuple of (passages, elapsed_ms, metadata_dict)

            metadata_dict always contains:
              - "mode": str identifying the retrieval strategy used
        """
        ...


@runtime_checkable
class ConnectionPool(Protocol):
    """
    Protocol for database connection pooling.

    Any object that provides these methods can serve as a connection pool.
    """

    def getconn(self) -> Any:
        """
        Acquire a connection from the pool.

        Returns:
            Any: A database connection (typically psycopg2 connection).

        Raises:
            Any exception raised by the underlying pool.
        """
        ...

    def putconn(self, conn: Any) -> None:
        """
        Return a connection to the pool for reuse.

        Args:
            conn: The connection to return to the pool.
        """
        ...

    def closeall(self) -> None:
        """Close all connections in the pool."""
        ...


@runtime_checkable
class EmbeddingClient(Protocol):
    """
    Protocol for text embedding generation.

    Implementations should use a service like OpenAI's embedding API.
    """

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            list[list[float]]: List of embedding vectors (one per input text).

        Raises:
            Various exceptions depending on implementation (API errors, etc.).
        """
        ...

    def embed_query(self, query: str) -> list[float]:
        """
        Generate embedding for a single query string.

        Args:
            query: Query text to embed.

        Returns:
            list[float]: Embedding vector.

        Raises:
            Various exceptions depending on implementation.
        """
        ...


@runtime_checkable
class CompletionClient(Protocol):
    """
    Protocol for language model completions.

    Implementations should use a service like OpenAI's chat completion API.
    """

    def complete(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, int, int]:
        """
        Generate a completion for the given messages.

        Args:
            messages: List of message dicts (e.g., [{"role": "user", "content": "..."}]).
            model: Model identifier to use.
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum tokens in the response.

        Returns:
            tuple[str, int, int]: (answer_text, prompt_tokens_used, completion_tokens_generated)

        Raises:
            Various exceptions depending on implementation (API errors, etc.).
        """
        ...


@runtime_checkable
class ChunkEnricher(Protocol):
    """
    Protocol for enriching chunk text with metadata.

    Implementations may add source attribution, publication links, etc.
    """

    def enrich(self, chunk_text: str, pub_number: str, metadata: dict) -> str:
        """
        Enrich a chunk with additional metadata.

        Args:
            chunk_text: The original chunk text.
            pub_number: Publication number or identifier.
            metadata: Additional metadata dict (e.g., tax_year, form_number).

        Returns:
            str: Enriched chunk text.
        """
        ...


@runtime_checkable
class VectorStore(Protocol):
    """
    Protocol for vector and full-text search over chunks.

    Implementations manage both vector embeddings and BM25 indices.
    """

    def search_similar(
        self,
        query_embedding: list[float],
        top_k: int,
        pub_numbers: Optional[list[str]] = None,
        tax_year: Optional[int] = None,
    ) -> list[Any]:
        """
        Search for chunks similar to the query embedding (vector search).

        Args:
            query_embedding: Query embedding vector.
            top_k: Number of results to return.
            pub_numbers: Optional list of publication numbers to filter by.
            tax_year: Optional tax year to filter by.

        Returns:
            list[Any]: List of matching chunks (implementation-dependent structure).
        """
        ...

    def search_bm25(
        self,
        query: str,
        top_k: int,
        pub_numbers: Optional[list[str]] = None,
        tax_year: Optional[int] = None,
    ) -> list[Any]:
        """
        Search for chunks using full-text BM25 ranking.

        Args:
            query: Query text for BM25 ranking.
            top_k: Number of results to return.
            pub_numbers: Optional list of publication numbers to filter by.
            tax_year: Optional tax year to filter by.

        Returns:
            list[Any]: List of matching chunks (implementation-dependent structure).
        """
        ...
