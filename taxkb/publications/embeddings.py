"""
taxkb/layer3/embeddings.py

OpenAI embedding generation for publication chunks.

Model: text-embedding-3-large (1536 dimensions via Matryoshka truncation)
       Uses the large model's richer semantic space while staying within the
       existing vector(1536) pgvector column — no schema change required.
       The `dimensions=1536` API parameter truncates the 3072-dim output to
       1536 with minimal quality loss (Matryoshka training).
Cost:  ~$0.13 / 1M tokens (vs $0.02 for small, ~6.5x, one-time re-index cost)

IMPORTANT — model consistency: query and document embeddings MUST use the same
model.  embed_query() reads EMBEDDING_MODEL automatically, so switching the
constant here automatically applies to both ingestion and search.

Usage:
    # Preferred: pass an EmbeddingClient produced by :func:`taxkb.factories.create_embedding_client`.
    from taxkb.factories import create_embedding_client
    from taxkb.publications.embeddings import embed_chunks
    chunks = embed_chunks(chunks, embedding_client=create_embedding_client())

    # Or with an explicit api_key; falls back to Settings when omitted.
    chunks = embed_chunks(chunks, api_key="sk-...")
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

from taxkb.publications.models import PublicationChunk

if TYPE_CHECKING:
    from taxkb.protocols import EmbeddingClient

logger = logging.getLogger(__name__)

# Defaults — can be overridden by passing explicit values to functions.
# These are NOT read from get_settings() at import time to avoid coupling
# the module to the config singleton.
EMBEDDING_MODEL    = "text-embedding-3-large"
EMBEDDING_DIM      = 1536
EMBEDDING_DIMS_PARAM = 1536
BATCH_SIZE         = 256
RETRY_ATTEMPTS     = 3
RETRY_DELAY_S      = 5.0


def _resolve_key_from_settings() -> str:
    """Late import to avoid pulling Settings at module-import time."""
    from taxkb.config import get_settings
    return get_settings().openai_api_key.get_secret_value()


def embed_chunks(
    chunks           : list[PublicationChunk],
    api_key          : Optional[str] = None,
    model            : str = EMBEDDING_MODEL,
    batch_size       : int = BATCH_SIZE,
    force            : bool = False,
    embedding_client : Optional[EmbeddingClient] = None,
) -> list[PublicationChunk]:
    """
    Embed a list of PublicationChunks using the OpenAI Embeddings API.

    Sets `chunk.embedding` on each chunk in-place and also returns the list.
    Chunks that already have an embedding are skipped unless force=True.

    When model is ``text-embedding-3-large`` (or any 3-series large model) the
    API call includes ``dimensions=1536`` so the output fits the existing
    vector(1536) pgvector column (Matryoshka truncation).

    Args:
        chunks           : Chunks to embed (mutated in-place).
        api_key          : OpenAI API key. Falls back to env var, then config.
        model            : Embedding model name.
        batch_size       : Number of texts per API call.
        force            : If True, re-embed chunks that already have a vector.
        embedding_client : Optional EmbeddingClient for dependency injection.
                          If provided, uses this client instead of creating a new one.

    Returns:
        The same list with embeddings populated.

    Raises:
        ImportError  : if openai package is not installed (when not using embedding_client).
        ValueError   : if no API key is available.
        RuntimeError : if the API returns unexpected dimension.
    """
    # If embedding_client is provided, use it for all embeddings
    if embedding_client is not None:
        if force:
            for c in chunks:
                c.embedding = None

        pending = [c for c in chunks if c.embedding is None]
        if not pending:
            logger.info("All %d chunks already embedded — skipping.", len(chunks))
            return chunks

        logger.info(
            "Embedding %d chunks with %s (dims=%d) in batches of %d …",
            len(pending), model, EMBEDDING_DIM, batch_size,
        )

        total_embedded = 0
        for batch_start in range(0, len(pending), batch_size):
            batch = pending[batch_start : batch_start + batch_size]
            # Embed raw chunk text — annotations are used at synthesis time
            # only, not in the embedding. Prepending annotations/enrichment
            # to the embedding input was tested and found to DEGRADE retrieval
            # quality by polluting the vector space with generic boilerplate.
            texts = [c.text for c in batch]

            embeddings = embedding_client.embed_texts(texts)

            for chunk, embedding in zip(batch, embeddings):
                if len(embedding) != EMBEDDING_DIM:
                    raise RuntimeError(
                        f"Unexpected embedding dimension {len(embedding)} "
                        f"(expected {EMBEDDING_DIM}) for model {model}"
                    )
                chunk.embedding = embedding

            total_embedded += len(batch)
            logger.info(
                "  Embedded %d/%d chunks …", total_embedded, len(pending)
            )

        logger.info("Embedding complete: %d chunks embedded.", total_embedded)
        return chunks

    # Fallback: create OpenAI client directly (backward compatible path)
    try:
        from openai import OpenAI      # type: ignore
    except ImportError as e:
        raise ImportError(
            "openai package is required for embedding. "
            "Install it with: pip install openai --break-system-packages"
        ) from e

    key = api_key or _resolve_key_from_settings()
    if not key:
        raise ValueError(
            "OpenAI API key required. Pass api_key= or set OPENAI_API_KEY "
            "in .env (consumed by taxkb.config.Settings)."
        )

    client = OpenAI(api_key=key)

    # If force=True, clear existing embeddings so all chunks are re-embedded.
    if force:
        for c in chunks:
            c.embedding = None

    pending = [c for c in chunks if c.embedding is None]
    if not pending:
        logger.info("All %d chunks already embedded — skipping.", len(chunks))
        return chunks

    # Pass dimensions= for large models to stay within the vector(1536) column.
    extra_kwargs: dict = {}
    if "large" in model:
        extra_kwargs["dimensions"] = EMBEDDING_DIMS_PARAM

    logger.info(
        "Embedding %d chunks with %s (dims=%d) in batches of %d …",
        len(pending), model, EMBEDDING_DIMS_PARAM if extra_kwargs else EMBEDDING_DIM, batch_size,
    )
    total_embedded = 0

    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start : batch_start + batch_size]
        texts = [c.text for c in batch]

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                response = client.embeddings.create(
                    input=texts,
                    model=model,
                    **extra_kwargs,
                )
                break
            except Exception as exc:
                # Quota exhaustion is permanent — retrying won't help.
                exc_str = str(exc)
                if "insufficient_quota" in exc_str or "billing" in exc_str.lower():
                    raise RuntimeError(
                        "OpenAI quota exceeded. Add credits at "
                        "https://platform.openai.com/settings/billing — "
                        "text chunks are already saved; re-run after topping up."
                    ) from exc
                if attempt == RETRY_ATTEMPTS:
                    raise
                logger.warning(
                    "Embedding batch %d failed (attempt %d/%d): %s — retrying in %ds",
                    batch_start // batch_size + 1, attempt, RETRY_ATTEMPTS,
                    exc, RETRY_DELAY_S,
                )
                time.sleep(RETRY_DELAY_S)

        for chunk, data in zip(batch, response.data):
            vec = data.embedding
            if len(vec) != EMBEDDING_DIM:
                raise RuntimeError(
                    f"Unexpected embedding dimension {len(vec)} "
                    f"(expected {EMBEDDING_DIM}) for model {model}"
                )
            chunk.embedding = vec

        total_embedded += len(batch)
        logger.info(
            "  Embedded %d/%d chunks …", total_embedded, len(pending)
        )

    logger.info("Embedding complete: %d chunks embedded.", total_embedded)
    return chunks


def embed_query(
    query            : str,
    api_key          : Optional[str] = None,
    model            : str = EMBEDDING_MODEL,
    embedding_client : Optional[EmbeddingClient] = None,
) -> list[float]:
    """
    Embed a single query string for similarity search.

    Returns a 1536-dimensional float list (or EMBEDDING_DIM). When using
    text-embedding-3-large, passes dimensions=1536 to match the stored
    document embeddings.

    Args:
        query            : Query text to embed.
        api_key          : OpenAI API key. Falls back to env var, then config.
        model            : Embedding model name.
        embedding_client : Optional EmbeddingClient for dependency injection.
                          If provided, uses this client instead of creating a new one.

    Returns:
        list[float]: Embedding vector.

    Raises:
        ImportError  : if openai package is not installed (when not using embedding_client).
        ValueError   : if no API key is available.
    """
    # If embedding_client is provided, use it
    if embedding_client is not None:
        return embedding_client.embed_query(query)

    # Fallback: create OpenAI client directly (backward compatible path)
    try:
        from openai import OpenAI      # type: ignore
    except ImportError as e:
        raise ImportError(
            "openai package is required. "
            "Install it with: pip install openai --break-system-packages"
        ) from e

    key = api_key or _resolve_key_from_settings()
    if not key:
        raise ValueError(
            "OpenAI API key required. Pass api_key= or set OPENAI_API_KEY "
            "in .env (consumed by taxkb.config.Settings)."
        )

    extra_kwargs: dict = {}
    if "large" in model:
        extra_kwargs["dimensions"] = EMBEDDING_DIMS_PARAM

    client   = OpenAI(api_key=key)
    response = client.embeddings.create(input=[query], model=model, **extra_kwargs)
    return response.data[0].embedding
