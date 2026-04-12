"""
tax_brain/adapters/openai_client.py

Concrete OpenAI embedding and completion client implementations.
"""
from __future__ import annotations

from openai import OpenAI
from pydantic import SecretStr


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
