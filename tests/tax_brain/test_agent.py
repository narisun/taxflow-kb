"""
tests/test_layer4.py

Unit tests for Layer 4: CPA Query Agent.

All tests use mocks — no database or API calls are made.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from tax_brain.agent.models import RetrievedPassage, QueryResult
from tax_brain.agent.agent import TaxBrainAgent, AgentConfig
from tax_brain.agent.validation.agent_probes import validate_agent, V41Result


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_context(
    pub_number  = "596",
    title       = "Earned Income Credit (EIC)",
    text        = "The EIC is a refundable credit for low to moderate income workers.",
    score       = 0.75,
    page        = 10,
    chapter     = "Chapter 2",
    section     = "Who Qualifies",
) -> RetrievedPassage:
    return RetrievedPassage(
        layer       = 3,
        source_type = "publication",
        reference   = pub_number,
        title       = title,
        text        = text,
        score       = score,
        page        = page,
        chapter     = chapter,
        section     = section,
    )


def _make_result(
    query    = "What is the EIC?",
    answer   = "The Earned Income Credit is a refundable tax credit. See IRS Pub 596.",
    contexts = None,
    error    = "",
) -> QueryResult:
    return QueryResult(
        query             = query,
        answer            = answer,
        contexts          = contexts or [_make_context() for _ in range(5)],
        retrieval_ms      = 200.0,
        synthesis_ms      = 1500.0,
        model_used        = "gpt-4o-mini",
        prompt_tokens     = 800,
        completion_tokens = 200,
        error             = error,
    )


def _make_agent(retriever_return=None):
    """Create a TaxBrainAgent with mock deps for testing."""
    mock_retriever = MagicMock()
    if retriever_return is not None:
        mock_retriever.retrieve.return_value = retriever_return

    return TaxBrainAgent(
        pool=MagicMock(),
        embedding_client=MagicMock(),
        completion_client=MagicMock(),
        retriever=mock_retriever,
        model="gpt-4o-test",
        config=AgentConfig(enable_compression=False),
        api_key="sk-test",
    )


# ── RetrievedPassage tests ─────────────────────────────────────────────────────

class TestRetrievedContext:
    def test_citation_with_chapter(self):
        ctx = _make_context(pub_number="596", chapter="Chapter 2 EIC Rules", page=10)
        assert "Pub 596" in ctx.citation
        assert "Chapter 2" in ctx.citation
        assert "p. 10" in ctx.citation

    def test_citation_with_section_no_chapter(self):
        ctx = _make_context(pub_number="969", chapter="", section="HSA Contributions", page=5)
        assert "Pub 969" in ctx.citation
        assert "HSA" in ctx.citation

    def test_citation_no_page(self):
        ctx = _make_context(page=0)
        assert "p. 0" not in ctx.citation

    def test_snippet_truncates(self):
        ctx = _make_context(text="A" * 300)
        assert len(ctx.snippet) <= 203  # 200 + "…"
        assert ctx.snippet.endswith("…")

    def test_snippet_no_truncation_short(self):
        ctx = _make_context(text="Short text.")
        assert ctx.snippet == "Short text."


# ── QueryResult tests ───────────────────────────────────────────────────────

class TestCPAQueryResult:
    def test_total_tokens(self):
        r = _make_result()
        assert r.total_tokens == 1000

    def test_sources_deduplicated(self):
        # Two contexts from same pub/page → one source entry
        ctx = _make_context(pub_number="596", chapter="Chapter 2", page=10)
        r   = QueryResult(query="q", answer="a", contexts=[ctx, ctx])
        assert len(r.sources) == 1

    def test_sources_multiple_pubs(self):
        c1 = _make_context(pub_number="596", chapter="Ch2", page=1)
        c2 = _make_context(pub_number="17",  chapter="Ch3", page=5)
        r  = QueryResult(query="q", answer="a", contexts=[c1, c2])
        assert len(r.sources) == 2

    def test_print_report_no_error(self, capsys):
        r = _make_result()
        r.print_report()
        out = capsys.readouterr().out
        assert "Query:" in out
        assert "Sources" in out

    def test_print_report_with_error(self, capsys):
        r = _make_result(error="Synthesis failed: timeout")
        r.print_report()
        out = capsys.readouterr().out
        assert "error" in out.lower()


# ── TaxBrainAgent tests ────────────────────────────────────────────────────────

class TestCPAQueryAgent:
    """Tests use mocks so no DB or API calls are made."""

    def test_empty_question_returns_error(self):
        agent = _make_agent()
        result = agent.query("   ")
        assert result.error
        assert result.answer == ""

    @patch("tax_brain.agent.synthesizer.synthesize")
    def test_query_full_flow(self, mock_syn):
        # Set up retriever mock — TaxBrainRetriever.retrieve returns 3-tuple
        contexts = [_make_context() for _ in range(5)]

        # Set up synthesizer mock
        mock_syn.return_value = (
            "The EIC income limit for one qualifying child is $46,560. See IRS Pub 596.",
            800,
            150,
            1400.0,
        )

        agent = _make_agent(
            retriever_return=(contexts, 220.0, {"mode": "hierarchical", "nav_pubs": [], "ontology_pubs": []}),
        )
        result = agent.query("What is the EIC income limit?", top_k=5)

        assert result.answer
        assert "596" in result.answer or "EIC" in result.answer
        assert result.retrieval_ms == 220.0
        assert result.synthesis_ms == 1400.0
        assert result.prompt_tokens == 800
        assert result.completion_tokens == 150
        assert len(result.contexts) == 5

    @patch("tax_brain.agent.synthesizer.synthesize")
    def test_no_contexts_returns_error(self, mock_syn):
        agent = _make_agent(
            retriever_return=([], 50.0, {"mode": "flat", "nav_pubs": [], "ontology_pubs": []}),
        )

        result = agent.query("Irrelevant query about nothing tax-related")

        assert result.error
        assert result.answer == ""
        mock_syn.assert_not_called()   # synthesis should not run with no contexts

    @patch("tax_brain.agent.synthesizer.synthesize")
    def test_synthesize_false_skips_llm(self, mock_syn):
        contexts = [_make_context() for _ in range(3)]

        agent = _make_agent(
            retriever_return=(contexts, 100.0, {"mode": "hierarchical", "nav_pubs": [], "ontology_pubs": []}),
        )

        result = agent.query("EIC?", synthesize=False)

        assert result.answer == ""
        assert len(result.contexts) == 3
        mock_syn.assert_not_called()

    @patch("tax_brain.agent.synthesizer.synthesize", side_effect=RuntimeError("timeout"))
    def test_synthesis_error_returns_partial_result(self, _mock_syn):
        contexts = [_make_context() for _ in range(5)]

        agent = _make_agent(
            retriever_return=(contexts, 200.0, {"mode": "hierarchical", "nav_pubs": [], "ontology_pubs": []}),
        )

        result = agent.query("What is the EIC?")

        assert result.error                 # error is reported
        assert len(result.contexts) == 5    # but contexts are still returned
        assert result.retrieval_ms == 200.0


# ── V4.1 validation gate tests ────────────────────────────────────────────────

class TestV41Gate:
    """Tests the validation gate logic against a mock agent."""

    def _make_mock_agent(self, result: QueryResult):
        agent = MagicMock()
        agent.query.return_value = result
        return agent

    def test_passes_with_good_result(self):
        result = _make_result(
            answer="The EIC limit for one qualifying child is $46,560 (IRS Pub 596, p. 15). "
                   "The credit begins to phase out above this amount.",
        )
        agent = self._make_mock_agent(result)
        r = validate_agent(
            agent,
            probes=[("What is the EIC income limit?", "596")],
        )
        assert r.passed
        assert r.passed_probes == 1

    def test_fails_v41a_too_few_contexts(self):
        result = QueryResult(
            query    = "test",
            answer   = "A " * 50 + "Pub 596",
            contexts = [_make_context()],   # only 1 context, minimum is 3
            retrieval_ms=100, synthesis_ms=500,
        )
        agent = self._make_mock_agent(result)
        r = validate_agent(agent, probes=[("test query", "596")])
        assert not r.passed
        assert any("V4.1-A" in f for f in r.failures)

    def test_fails_v41c_short_answer(self):
        result = _make_result(answer="Short.")  # < 80 chars
        agent  = self._make_mock_agent(result)
        r = validate_agent(agent, probes=[("test query", None)])
        assert not r.passed
        assert any("V4.1-C" in f for f in r.failures)

    def test_fails_v41d_missing_citation(self):
        result = _make_result(
            answer="The income limit is $46,560 for 2024.",  # no pub citation
        )
        agent = self._make_mock_agent(result)
        r = validate_agent(agent, probes=[("EIC limit?", "596")])
        assert not r.passed
        assert any("V4.1-D" in f for f in r.failures)

    def test_skips_citation_check_when_no_expected_pub(self):
        result = _make_result(
            answer="The standard deduction for 2024 is $14,600 for single filers "
                   "according to the latest IRS guidance for individual taxpayers.",
        )
        agent = self._make_mock_agent(result)
        r = validate_agent(agent, probes=[("What is the standard deduction?", None)])
        assert r.passed   # no expected pub → no citation check → should pass

    def test_summary_string(self):
        result = _make_result(
            answer="The required minimum distribution rules state that you must begin "
                   "taking RMDs at age 73. See IRS Pub 590b for the full RMD tables.",
        )
        agent = self._make_mock_agent(result)
        r = validate_agent(agent, probes=[("RMD rules?", "590b")])
        assert "PASS" in r.summary
        assert "1/1" in r.summary
