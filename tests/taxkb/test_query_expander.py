"""
tests/taxkb/test_query_expander.py

Unit tests for LLM-powered query expansion.
All tests use mocks — no API calls are made.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from taxkb.agent.query_expander import expand_query


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _mock_completion_client(response_text: str) -> MagicMock:
    """Create a mock CompletionClient that returns the given text."""
    client = MagicMock()
    client.complete.return_value = (response_text, 50, 30)
    return client


# ── expand_query tests ────────────────────────────────────────────────────────


class TestExpandQuery:
    def test_expands_with_irc_sections(self):
        mock_client = _mock_completion_client(
            "IRC Section 1091 substantially identical securities "
            "Form 8949 Schedule D disallowed loss 61-day window"
        )
        result = expand_query(
            "wash sale rule for options",
            completion_client=mock_client,
        )
        assert "wash sale rule for options" in result
        assert "IRC Section 1091" in result
        assert "Form 8949" in result

    def test_preserves_original_query(self):
        mock_client = _mock_completion_client("IRC Section 121 exclusion")
        result = expand_query(
            "can my client exclude the gain on home sale",
            completion_client=mock_client,
        )
        assert result.startswith("can my client exclude the gain on home sale")

    def test_empty_query_returns_unchanged(self):
        result = expand_query("   ")
        assert result == "   "

    def test_llm_failure_returns_original(self):
        mock_client = MagicMock()
        mock_client.complete.side_effect = RuntimeError("API down")
        result = expand_query(
            "what is the standard deduction",
            completion_client=mock_client,
        )
        assert result == "what is the standard deduction"

    def test_no_useful_expansion_returns_original(self):
        mock_client = _mock_completion_client("No additional terms needed")
        result = expand_query(
            "what is the standard deduction",
            completion_client=mock_client,
        )
        assert result == "what is the standard deduction"

    def test_expansion_appended_not_prepended(self):
        mock_client = _mock_completion_client("Section 179 MACRS Form 4562")
        result = expand_query(
            "depreciation rules for business equipment",
            completion_client=mock_client,
        )
        parts = result.split("depreciation rules for business equipment")
        assert len(parts) == 2
        assert parts[0] == ""  # original is at the start
        assert "Section 179" in parts[1]

    def test_calls_completion_client_correctly(self):
        mock_client = _mock_completion_client("IRC 469 passive activity")
        expand_query(
            "rental property losses",
            completion_client=mock_client,
        )
        mock_client.complete.assert_called_once()
        call_kwargs = mock_client.complete.call_args
        # Should use gpt-4o-mini by default
        assert call_kwargs.kwargs.get("model") or call_kwargs[1].get("model") == "gpt-4o-mini"

    def test_custom_model(self):
        mock_client = _mock_completion_client("terms")
        expand_query(
            "test query",
            completion_client=mock_client,
            model="gpt-4o",
        )
        call_args = mock_client.complete.call_args
        assert "gpt-4o" in str(call_args)


# ── Integration with agent config ────────────────────────────────────────────


class TestQueryExpansionInAgent:
    """Verify that query expansion is wired into the agent correctly."""

    @patch("taxkb.agent.agent.expand_query")
    @patch("taxkb.agent.synthesizer.synthesize")
    def test_agent_calls_expander_when_enabled(self, mock_syn, mock_expand):
        from taxkb.agent.agent import TaxBrainAgent, AgentConfig
        from taxkb.agent.models import RetrievedPassage

        mock_expand.return_value = "EIC income limit IRC 32 earned income credit Publication 596"
        mock_syn.return_value = ("Answer about EIC.", 100, 50, 500.0)

        contexts = [RetrievedPassage(
            title="EIC", text="The EIC limit is...", score=0.8,
            reference="596", layer=3,
        )]
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = (
            contexts, 100.0,
            {"mode": "flat", "nav_pubs": [], "ontology_pubs": []},
        )

        agent = TaxBrainAgent(
            pool=MagicMock(),
            embedding_client=MagicMock(),
            completion_client=MagicMock(),
            retriever=mock_retriever,
            config=AgentConfig(
                enable_query_expansion=True,
                enable_compression=False,
            ),
            api_key="sk-test",
        )
        agent.query("What is the EIC income limit?")

        mock_expand.assert_called_once()
        # Retriever should receive the expanded query
        retriever_call_query = mock_retriever.retrieve.call_args.kwargs.get(
            "query", mock_retriever.retrieve.call_args[1].get("query", "")
        )
        assert "IRC 32" in retriever_call_query or "Publication 596" in retriever_call_query

    @patch("taxkb.agent.agent.expand_query")
    @patch("taxkb.agent.synthesizer.synthesize")
    def test_agent_skips_expander_when_disabled(self, mock_syn, mock_expand):
        from taxkb.agent.agent import TaxBrainAgent, AgentConfig
        from taxkb.agent.models import RetrievedPassage

        mock_syn.return_value = ("Answer.", 100, 50, 500.0)

        contexts = [RetrievedPassage(
            title="EIC", text="The EIC limit is...", score=0.8,
            reference="596", layer=3,
        )]
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = (
            contexts, 100.0,
            {"mode": "flat", "nav_pubs": [], "ontology_pubs": []},
        )

        agent = TaxBrainAgent(
            pool=MagicMock(),
            embedding_client=MagicMock(),
            completion_client=MagicMock(),
            retriever=mock_retriever,
            config=AgentConfig(
                enable_query_expansion=False,
                enable_compression=False,
            ),
            api_key="sk-test",
        )
        agent.query("What is the EIC income limit?")

        mock_expand.assert_not_called()

    @patch("taxkb.agent.agent.expand_query", side_effect=RuntimeError("boom"))
    @patch("taxkb.agent.synthesizer.synthesize")
    def test_agent_survives_expander_failure(self, mock_syn, mock_expand):
        from taxkb.agent.agent import TaxBrainAgent, AgentConfig
        from taxkb.agent.models import RetrievedPassage

        mock_syn.return_value = ("Answer.", 100, 50, 500.0)

        contexts = [RetrievedPassage(
            title="EIC", text="The EIC limit is...", score=0.8,
            reference="596", layer=3,
        )]
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = (
            contexts, 100.0,
            {"mode": "flat", "nav_pubs": [], "ontology_pubs": []},
        )

        agent = TaxBrainAgent(
            pool=MagicMock(),
            embedding_client=MagicMock(),
            completion_client=MagicMock(),
            retriever=mock_retriever,
            config=AgentConfig(enable_compression=False),
            api_key="sk-test",
        )

        # Should not raise — falls back to original query
        result = agent.query("What is the EIC income limit?")
        assert result.answer == "Answer."


# ── BM25 annotation indexing ──────────────────────────────────────────────────


class TestBM25AnnotationIndex:
    """Verify that the BM25 tsvector migration SQL includes context_annotation."""

    def test_add_bm25_index_includes_annotation(self):
        """The migration SQL should reference context_annotation in the tsvector."""
        import inspect
        from taxkb.publications.store import PublicationStore

        source = inspect.getsource(PublicationStore.add_bm25_index)
        assert "context_annotation" in source
        assert "setweight" in source
        # Annotation should be weighted lower than text
        assert "'A'" in source  # text weight
        assert "'B'" in source  # annotation weight
