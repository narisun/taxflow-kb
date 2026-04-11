"""
taxflow_kb/protocols.py

Protocol-based abstractions for dependency injection.

All external dependencies (database connections, API clients, etc.)
are defined as Protocols so that:
  1. Tests can substitute lightweight fakes without mocking internals
  2. Concrete implementations can be swapped without changing callers
  3. Type checkers verify interface conformance statically

This module also provides canonical concrete implementations:
  - PgConnectionPool: ThreadedConnectionPool wrapper
  - OpenAIEmbeddingClient: OpenAI embeddings client
  - OpenAICompletionClient: OpenAI completions client
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

import psycopg2.pool
from openai import OpenAI
from pydantic import SecretStr


# ──────────────────────────────────────────────────────────────────────────────
# Protocols (interfaces)
# ──────────────────────────────────────────────────────────────────────────────


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


# ──────────────────────────────────────────────────────────────────────────────
# Concrete Implementations
# ──────────────────────────────────────────────────────────────────────────────


class PgConnectionPool:
    """
    Thread-safe PostgreSQL connection pool wrapper.

    Wraps psycopg2.pool.ThreadedConnectionPool for safe connection reuse
    across threads. Implements the ConnectionPool protocol.
    """

    def __init__(
        self,
        dsn: str,
        min_conn: int = 2,
        max_conn: int = 10,
    ) -> None:
        """
        Initialize the PostgreSQL connection pool.

        Args:
            dsn: PostgreSQL connection string (DSN).
                Example: "postgresql://user:pass@localhost:5432/dbname"
            min_conn: Minimum number of connections to maintain. Defaults to 2.
            max_conn: Maximum number of connections to allow. Defaults to 10.

        Raises:
            psycopg2.Error: If connection pool creation fails.
        """
        self._dsn = dsn
        self._min_conn = min_conn
        self._max_conn = max_conn
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            min_conn,
            max_conn,
            dsn,
        )

    def getconn(self) -> Any:
        """
        Acquire a connection from the pool.

        Returns:
            Any: A psycopg2 connection object.

        Raises:
            psycopg2.pool.PoolError: If no connections are available.
        """
        return self._pool.getconn()

    def putconn(self, conn: Any) -> None:
        """
        Return a connection to the pool for reuse.

        Args:
            conn: The connection to return to the pool.
        """
        self._pool.putconn(conn)

    def closeall(self) -> None:
        """Close all connections in the pool."""
        self._pool.closeall()

    def __del__(self) -> None:
        """Ensure pool is closed when object is garbage collected."""
        try:
            self.closeall()
        except Exception:
            pass


class OpenAIEmbeddingClient:
    """
    OpenAI embedding client with singleton-friendly design.

    Creates one OpenAI client instance at construction time and reuses
    it across all embedding calls. Implements the EmbeddingClient protocol.
    """

    def __init__(
        self,
        api_key: str | SecretStr,
        model: str = "text-embedding-3-large",
        dimensions: int = 1536,
    ) -> None:
        """
        Initialize the OpenAI embedding client.

        Args:
            api_key: OpenAI API key (string or SecretStr).
            model: Embedding model to use. Defaults to "text-embedding-3-large".
            dimensions: Dimensionality of embeddings. Defaults to 1536.

        Raises:
            ValueError: If api_key is empty or invalid.
        """
        # Extract secret value if SecretStr
        if isinstance(api_key, SecretStr):
            key_str = api_key.get_secret_value()
        else:
            key_str = str(api_key)

        if not key_str or key_str.strip() == "":
            raise ValueError("OpenAI API key cannot be empty")

        self._client = OpenAI(api_key=key_str)
        self._model = model
        self._dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            list[list[float]]: List of embedding vectors (one per input text).

        Raises:
            openai.APIError: If the OpenAI API call fails.
        """
        if not texts:
            return []

        response = self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )

        # Sort by index to match input order
        embeddings = sorted(response.data, key=lambda x: x.index)
        return [embedding.embedding for embedding in embeddings]

    def embed_query(self, query: str) -> list[float]:
        """
        Generate embedding for a single query string.

        Args:
            query: Query text to embed.

        Returns:
            list[float]: Embedding vector.

        Raises:
            openai.APIError: If the OpenAI API call fails.
        """
        embeddings = self.embed_texts([query])
        return embeddings[0] if embeddings else []


class OpenAICompletionClient:
    """
    OpenAI completion client with singleton-friendly design.

    Creates one OpenAI client instance at construction time and reuses
    it across all completion calls. Implements the CompletionClient protocol.
    """

    def __init__(self, api_key: str | SecretStr) -> None:
        """
        Initialize the OpenAI completion client.

        Args:
            api_key: OpenAI API key (string or SecretStr).

        Raises:
            ValueError: If api_key is empty or invalid.
        """
        # Extract secret value if SecretStr
        if isinstance(api_key, SecretStr):
            key_str = api_key.get_secret_value()
        else:
            key_str = str(api_key)

        if not key_str or key_str.strip() == "":
            raise ValueError("OpenAI API key cannot be empty")

        self._client = OpenAI(api_key=key_str)

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
            model: Model identifier to use (e.g., "gpt-4", "gpt-4-turbo").
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum tokens in the response.

        Returns:
            tuple[str, int, int]: (answer_text, prompt_tokens_used, completion_tokens_generated)

        Raises:
            openai.APIError: If the OpenAI API call fails.
        """
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        answer_text = response.choices[0].message.content or ""
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens

        return answer_text, prompt_tokens, completion_tokens
