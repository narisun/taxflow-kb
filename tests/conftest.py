"""
Shared test fixtures and configuration for the Tax Brain test suite.

This conftest.py provides:
  - Automatic cache clearing between tests (Settings, registry singletons)
  - Shared mock factories for common test doubles
  - Path constants for sample data files
"""
from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

import pytest


# ── Path constants ───────────────────────────────────────────────────────────

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLE_CSV = PROJECT_ROOT / "data" / "sample" / "mef_1040_2024_v5_2.csv"
SAMPLE_HTML = PROJECT_ROOT / "data" / "instructions" / "i1040gi_2024_synthetic.html"


# ── Singleton cache clearing (autouse) ───────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Clear the Settings singleton cache before and after each test.

    Without this, a test that modifies environment variables or creates
    a Settings with custom values would leak that state to subsequent tests.
    """
    from tax_brain.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    """Clear the publication registry singleton between tests."""
    import tax_brain.publications.registry as reg_module
    reg_module._registry = None
    yield
    reg_module._registry = None


# ── Reusable mock factories ─────────────────────────────────────────────────

@pytest.fixture
def mock_pool():
    """A MagicMock implementing the ConnectionPool protocol."""
    pool = MagicMock()
    pool.getconn.return_value = MagicMock()
    return pool


@pytest.fixture
def mock_embedding_client():
    """A MagicMock implementing the EmbeddingClient protocol."""
    client = MagicMock()
    client.embed_texts.return_value = [[0.1] * 1536]
    client.embed_query.return_value = [0.1] * 1536
    return client


@pytest.fixture
def mock_completion_client():
    """A MagicMock implementing the CompletionClient protocol."""
    client = MagicMock()
    client.complete.return_value = ("Mock answer.", 100, 50)
    return client
