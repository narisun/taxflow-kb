"""
tests/test_layer5.py

Unit tests for Layer 5: Evaluation framework.

Covers:
  - GoldSetEntry and GoldSet (models_layer5)
  - RetrievalEvalResult metric computation
  - RetrievalReport accumulation and stats
  - evaluate_retrieval() integration (fully mocked)

All tests use mocks — no database or API calls are made.
"""
from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from taxflow_kb.layer5.models_layer5 import GoldSetEntry, GoldSet
from taxflow_kb.layer5.retrieval_evaluator import (
    RetrievalEvalResult,
    RetrievalReport,
    evaluate_retrieval,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_entry(
    question       = "What is the EIC income limit for one qualifying child?",
    ground_truth   = "For tax year 2025, the earned income limit is $46,560.",
    expected_pub   = "596",
    gold_chunk_ids = ["chunk-aaa", "chunk-bbb"],
    difficulty     = "simple",
    topic_tags     = ["EIC", "income-limit"],
) -> GoldSetEntry:
    return GoldSetEntry(
        question       = question,
        ground_truth   = ground_truth,
        expected_pub   = expected_pub,
        gold_chunk_ids = gold_chunk_ids,
        difficulty     = difficulty,
        topic_tags     = topic_tags,
    )


def _make_retrieval_result(
    chunk_ids : list[str],
    pub_numbers: list[str],
    gold_chunks: list[str] = None,
    expected_pub: str = "596",
) -> RetrievalEvalResult:
    r = RetrievalEvalResult(
        entry_id        = "test-001",
        question        = "Sample question",
        expected_pub    = expected_pub,
        difficulty      = "simple",
        gold_chunk_ids  = gold_chunks or ["chunk-aaa"],
        retrieved_chunk_ids   = chunk_ids,
        retrieved_pub_numbers = pub_numbers,
    )
    r.compute(top_k=5)
    return r


# ══════════════════════════════════════════════════════════════════════════════
# GoldSetEntry tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGoldSetEntry:

    def test_short_id_format(self):
        e = _make_entry()
        assert e.short_id.startswith("596-")

    def test_not_verified_by_default(self):
        e = _make_entry()
        assert not e.is_verified

    def test_mark_verified(self):
        e = _make_entry()
        e.mark_verified("CPA Jones", note="Correct per 2025 tables")
        assert e.is_verified
        assert e.verified_by == "CPA Jones"
        assert "2025" in e.notes
        assert e.verified_at is not None

    def test_serialization_roundtrip(self):
        e = _make_entry()
        d = e.to_dict()
        e2 = GoldSetEntry.from_dict(d)
        assert e2.question       == e.question
        assert e2.ground_truth   == e.ground_truth
        assert e2.expected_pub   == e.expected_pub
        assert e2.gold_chunk_ids == e.gold_chunk_ids
        assert e2.difficulty     == e.difficulty


# ══════════════════════════════════════════════════════════════════════════════
# GoldSet tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGoldSet:

    def test_empty_gold_set(self):
        gs = GoldSet.empty()
        assert gs.total == 0
        assert gs.verified_count == 0

    def test_add_entries_and_stats(self):
        gs = GoldSet()
        gs.entries.append(_make_entry(expected_pub="596", difficulty="simple"))
        gs.entries.append(_make_entry(expected_pub="596", difficulty="complex"))
        gs.entries.append(_make_entry(expected_pub="17",  difficulty="medium"))

        assert gs.total == 3
        assert gs.by_pub["596"] == 2
        assert gs.by_pub["17"]  == 1
        assert gs.by_difficulty["simple"]  == 1
        assert gs.by_difficulty["complex"] == 1

    def test_filter_by_pub(self):
        gs = GoldSet()
        gs.entries.append(_make_entry(expected_pub="596"))
        gs.entries.append(_make_entry(expected_pub="17"))
        result = gs.filter(pub="596")
        assert len(result) == 1
        assert result[0].expected_pub == "596"

    def test_filter_by_difficulty(self):
        gs = GoldSet()
        gs.entries.append(_make_entry(difficulty="simple"))
        gs.entries.append(_make_entry(difficulty="complex"))
        result = gs.filter(difficulty="complex")
        assert len(result) == 1

    def test_filter_verified_only(self):
        gs = GoldSet()
        e1 = _make_entry()
        e2 = _make_entry()
        e2.mark_verified("CPA Test")
        gs.entries.extend([e1, e2])
        result = gs.filter(verified_only=True)
        assert len(result) == 1
        assert result[0].is_verified

    def test_save_and_load(self):
        gs = GoldSet(version="2.0.0", description="test set")
        gs.entries.append(_make_entry())
        gs.entries.append(_make_entry(expected_pub="17", difficulty="medium"))

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            gs.save(path)
            gs2 = GoldSet.load(path)
            assert gs2.total  == 2
            assert gs2.version == "2.0.0"
            assert gs2.entries[0].question == gs.entries[0].question
        finally:
            os.unlink(path)

    def test_summary_contains_key_info(self):
        gs = GoldSet()
        gs.entries.append(_make_entry())
        summary = gs.summary()
        assert "1 entries" in summary
        assert "596" in summary


# ══════════════════════════════════════════════════════════════════════════════
# RetrievalEvalResult metric tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRetrievalEvalResult:

    def test_perfect_hit_at_rank1(self):
        r = _make_retrieval_result(
            chunk_ids   = ["chunk-aaa", "chunk-zzz"],
            pub_numbers = ["596", "17"],
            gold_chunks = ["chunk-aaa"],
        )
        assert r.hit            is True
        assert r.first_hit_rank == 1
        assert r.reciprocal_rank == pytest.approx(1.0)
        assert r.recall         == pytest.approx(1.0)
        assert r.pub_hit        is True

    def test_hit_at_rank3(self):
        r = _make_retrieval_result(
            chunk_ids   = ["chunk-zzz", "chunk-yyy", "chunk-aaa"],
            pub_numbers = ["17", "501", "596"],
            gold_chunks = ["chunk-aaa"],
        )
        assert r.hit            is True
        assert r.first_hit_rank == 3
        assert r.reciprocal_rank == pytest.approx(1 / 3)

    def test_miss(self):
        r = _make_retrieval_result(
            chunk_ids   = ["chunk-zzz", "chunk-yyy"],
            pub_numbers = ["17", "501"],
            gold_chunks = ["chunk-aaa"],
        )
        assert r.hit            is False
        assert r.first_hit_rank is None
        assert r.reciprocal_rank == pytest.approx(0.0)
        assert r.recall         == pytest.approx(0.0)

    def test_partial_recall_two_gold_chunks(self):
        """
        gold_chunk_ids = [primary, adjacent].
        Recall is now computed against the PRIMARY chunk only (index 0).
        Hit rate uses the full gold set, so retrieving the adjacent chunk still counts as a hit.
        """
        r = _make_retrieval_result(
            chunk_ids   = ["chunk-bbb", "chunk-zzz"],   # adjacent found, primary not found
            pub_numbers = ["596", "596"],
            gold_chunks = ["chunk-aaa", "chunk-bbb"],   # chunk-aaa = primary
        )
        # Hit = True (chunk-bbb is in gold set)
        assert r.hit    is True
        # Recall = 0.0: primary chunk (chunk-aaa) was NOT retrieved
        assert r.recall == pytest.approx(0.0)

    def test_full_recall_two_gold_chunks(self):
        """Retrieving the primary gold chunk gives recall = 1.0 regardless of adjacent."""
        r = _make_retrieval_result(
            chunk_ids   = ["chunk-aaa", "chunk-bbb", "chunk-zzz"],
            pub_numbers = ["596", "596", "17"],
            gold_chunks = ["chunk-aaa", "chunk-bbb"],   # chunk-aaa = primary
        )
        # Hit = True, Recall = 1.0 (primary chunk-aaa retrieved)
        assert r.hit    is True
        assert r.recall == pytest.approx(1.0)

    def test_pub_hit_false_when_pub_not_in_results(self):
        r = _make_retrieval_result(
            chunk_ids    = ["chunk-zzz"],
            pub_numbers  = ["17"],
            gold_chunks  = ["chunk-aaa"],
            expected_pub = "596",
        )
        assert r.pub_hit is False

    def test_beyond_top_k_chunks_not_counted(self):
        """Chunks beyond top_k should not count as hits."""
        r = RetrievalEvalResult(
            entry_id        = "t",
            question        = "q",
            expected_pub    = "596",
            difficulty      = "simple",
            gold_chunk_ids  = ["chunk-gold"],
            retrieved_chunk_ids   = ["a", "b", "c", "d", "e", "chunk-gold"],  # gold at rank 6
            retrieved_pub_numbers = ["17", "17", "17", "17", "17", "596"],
        )
        r.compute(top_k=5)
        assert r.hit is False  # rank 6 is beyond top-5


# ══════════════════════════════════════════════════════════════════════════════
# RetrievalReport accumulation tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRetrievalReport:

    def _perfect_result(self, pub="596", difficulty="simple"):
        r = _make_retrieval_result(
            chunk_ids   = ["chunk-aaa"],
            pub_numbers = [pub],
            gold_chunks = ["chunk-aaa"],
            expected_pub = pub,
        )
        r.difficulty = difficulty
        return r

    def _miss_result(self, pub="596", difficulty="simple"):
        r = _make_retrieval_result(
            chunk_ids   = ["chunk-zzz"],
            pub_numbers = ["17"],
            gold_chunks = ["chunk-aaa"],
            expected_pub = pub,
        )
        r.difficulty = difficulty
        return r

    def test_all_hits(self):
        report = RetrievalReport(top_k=5)
        for _ in range(4):
            report.add(self._perfect_result())
        assert report.hit_rate  == pytest.approx(1.0)
        assert report.mrr       == pytest.approx(1.0)
        assert report.recall    == pytest.approx(1.0)

    def test_all_misses(self):
        report = RetrievalReport(top_k=5)
        for _ in range(3):
            report.add(self._miss_result())
        assert report.hit_rate == pytest.approx(0.0)
        assert report.mrr      == pytest.approx(0.0)

    def test_mixed_hit_rate(self):
        report = RetrievalReport(top_k=5)
        report.add(self._perfect_result())
        report.add(self._miss_result())
        assert report.hit_rate == pytest.approx(0.5)
        assert report.total    == 2

    def test_slice_by_difficulty(self):
        report = RetrievalReport(top_k=5)
        report.add(self._perfect_result(difficulty="simple"))
        report.add(self._perfect_result(difficulty="simple"))
        report.add(self._miss_result(difficulty="complex"))
        assert report.by_difficulty["simple"][0] == 2   # 2 hits
        assert report.by_difficulty["complex"][0] == 0  # 0 hits

    def test_slice_by_pub(self):
        report = RetrievalReport(top_k=5)
        report.add(self._perfect_result(pub="596"))
        report.add(self._miss_result(pub="17"))
        assert report.by_pub["596"][0] == 1
        assert report.by_pub["17"][0]  == 0

    def test_error_entries_counted_but_not_added_to_metrics(self):
        report = RetrievalReport(top_k=5)
        report.add(self._perfect_result())

        bad = RetrievalEvalResult(
            entry_id="err", question="q", expected_pub="596",
            difficulty="simple", gold_chunk_ids=["x"], error="timeout"
        )
        report.add(bad)

        assert report.total  == 2
        assert report.errors == 1
        assert report.hit_count == 1  # only the good result counted

    def test_to_dict_structure(self):
        report = RetrievalReport(top_k=5)
        report.add(self._perfect_result())
        d = report.to_dict()
        assert "hit_rate" in d
        assert "mrr" in d
        assert "recall" in d
        assert "pub_accuracy" in d
        assert "by_difficulty" in d
        assert "by_pub" in d

    def test_print_report_runs_without_error(self, capsys):
        report = RetrievalReport(top_k=5)
        report.add(self._perfect_result())
        report.add(self._miss_result())
        report.print_report()
        captured = capsys.readouterr()
        assert "Hit Rate" in captured.out
        assert "MRR"      in captured.out


# ══════════════════════════════════════════════════════════════════════════════
# evaluate_retrieval integration (mocked retriever)
# ══════════════════════════════════════════════════════════════════════════════

class TestEvaluateRetrieval:

    def _make_gold_set(self, n: int = 3) -> GoldSet:
        gs = GoldSet()
        for i in range(n):
            gs.entries.append(GoldSetEntry(
                question       = f"Question {i} about tax rules?",
                ground_truth   = f"The rule is X with limit ${i * 1000}.",
                expected_pub   = "596",
                gold_chunk_ids = [f"chunk-{i:03d}"],
                difficulty     = "simple",
                topic_tags     = ["EIC"],
            ))
        return gs

    def _make_context(self, chunk_id: str, pub: str = "596"):
        """Build a mock context object."""
        ctx = MagicMock()
        ctx.chunk_id  = chunk_id
        ctx.reference = pub
        return ctx

    def test_perfect_retrieval(self):
        """All gold chunks are retrieved at rank 1."""
        gs = self._make_gold_set(3)

        mock_retriever = MagicMock()
        def side_effect(question, top_k=5):
            # Return each gold chunk as the first result based on question index
            for i, e in enumerate(gs.entries):
                if f"Question {i}" in question:
                    return [self._make_context(f"chunk-{i:03d}")], 100.0
            return [], 100.0

        mock_retriever.retrieve.side_effect = side_effect

        report = evaluate_retrieval(
            gold_set  = gs,
            retriever = mock_retriever,
            top_k     = 5,
        )
        assert report.hit_rate == pytest.approx(1.0)
        assert report.mrr      == pytest.approx(1.0)
        assert report.total    == 3

    def test_zero_retrieval(self):
        """Retriever returns nothing — all misses."""
        gs = self._make_gold_set(3)

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = ([], 50.0)

        report = evaluate_retrieval(
            gold_set  = gs,
            retriever = mock_retriever,
            top_k     = 5,
        )
        assert report.hit_rate == pytest.approx(0.0)
        assert report.errors   == 0   # no exceptions, just empty results

    def test_retrieval_exception_counted_as_error(self):
        gs = self._make_gold_set(2)

        mock_retriever = MagicMock()
        mock_retriever.retrieve.side_effect = RuntimeError("DB connection lost")

        report = evaluate_retrieval(
            gold_set  = gs,
            retriever = mock_retriever,
            top_k     = 5,
        )
        assert report.errors == 2
        assert report.total  == 2
        assert report.hit_rate == pytest.approx(0.0)

    def test_pub_filter_applied(self):
        """Only entries from the filtered pub are evaluated."""
        gs = GoldSet()
        gs.entries.append(_make_entry(expected_pub="596"))
        gs.entries.append(_make_entry(expected_pub="17"))

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = ([], 50.0)

        report = evaluate_retrieval(
            gold_set   = gs,
            retriever  = mock_retriever,
            top_k      = 5,
            pub_filter = ["596"],
        )
        # Only the Pub 596 entry should be evaluated
        assert report.total == 1


# ══════════════════════════════════════════════════════════════════════════════
# GenerationEvalResult tests
# ══════════════════════════════════════════════════════════════════════════════

from taxflow_kb.layer5.generation_evaluator import (
    GenerationEvalResult,
    GenerationReport,
    evaluate_generation,
)


class TestGenerationEvalResult:

    def _make_result(self, **kwargs) -> GenerationEvalResult:
        defaults = dict(
            entry_id="e1", question="q", expected_pub="596",
            difficulty="simple", ground_truth="The limit is $46,560.",
        )
        defaults.update(kwargs)
        return GenerationEvalResult(**defaults)

    def test_no_scores_overall_is_none(self):
        r = self._make_result()
        assert r.overall_score is None

    def test_overall_score_average(self):
        r = self._make_result(
            ai_answer="The limit is $46,560.",
            faithfulness=4, answer_correctness=4,
            citation_accuracy=4, temporal_accuracy=4, safe_abstention=4,
        )
        assert r.overall_score == pytest.approx(4.0)

    def test_passes_gate_all_4(self):
        r = self._make_result(
            ai_answer="x",
            faithfulness=4, answer_correctness=4,
            citation_accuracy=4, temporal_accuracy=4, safe_abstention=4,
        )
        assert r.passes_gate is True

    def test_fails_gate_low_faithfulness(self):
        r = self._make_result(
            ai_answer="x",
            faithfulness=2, answer_correctness=4,
            citation_accuracy=4, temporal_accuracy=4, safe_abstention=4,
        )
        # overall = (2+4+4+4+4)/5 = 3.6 >= 3.0 but faithfulness < 3
        assert r.passes_gate is False

    def test_fails_gate_low_citation(self):
        r = self._make_result(
            ai_answer="x",
            faithfulness=4, answer_correctness=4,
            citation_accuracy=2, temporal_accuracy=4, safe_abstention=4,
        )
        assert r.passes_gate is False

    def test_fails_gate_low_overall(self):
        r = self._make_result(
            ai_answer="x",
            faithfulness=3, answer_correctness=2,
            citation_accuracy=3, temporal_accuracy=2, safe_abstention=2,
        )
        # overall = (3+2+3+2+2)/5 = 2.4 < 3.0
        assert r.passes_gate is False

    def test_to_dict_keys(self):
        r = self._make_result(
            ai_answer="x",
            faithfulness=3, answer_correctness=3,
            citation_accuracy=3, temporal_accuracy=3, safe_abstention=3,
        )
        d = r.to_dict()
        for key in ("entry_id", "overall_score", "passes_gate",
                    "faithfulness", "answer_correctness", "citation_accuracy"):
            assert key in d


# ══════════════════════════════════════════════════════════════════════════════
# GenerationReport accumulation tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerationReport:

    def _scored_result(self, pub="596", diff="simple", scores=(4,4,4,4,4)):
        r = GenerationEvalResult(
            entry_id="e", question="q", expected_pub=pub,
            difficulty=diff, ground_truth="g", ai_answer="a",
        )
        (r.faithfulness, r.answer_correctness, r.citation_accuracy,
         r.temporal_accuracy, r.safe_abstention) = scores
        return r

    def test_perfect_scores(self):
        report = GenerationReport()
        for _ in range(3):
            report.add(self._scored_result())
        assert report.pass_rate         == pytest.approx(1.0)
        assert report.avg_faithfulness  == pytest.approx(4.0)
        assert report.avg_overall       == pytest.approx(4.0)
        assert report.total             == 3

    def test_mixed_pass_fail(self):
        report = GenerationReport()
        report.add(self._scored_result(scores=(4,4,4,4,4)))  # passes
        report.add(self._scored_result(scores=(2,2,2,2,2)))  # fails (overall 2.0 < 3.0)
        assert report.pass_count == 1
        assert report.pass_rate  == pytest.approx(0.5)

    def test_agent_error_counted_not_scored(self):
        report = GenerationReport()
        good = self._scored_result()
        report.add(good)
        err = GenerationEvalResult(
            entry_id="err", question="q", expected_pub="596",
            difficulty="simple", ground_truth="g",
            agent_error="Connection refused",
        )
        report.add(err)
        assert report.total       == 2
        assert report.agent_errors == 1
        assert report._scored     == 1

    def test_judge_error_counted_not_scored(self):
        report = GenerationReport()
        r = GenerationEvalResult(
            entry_id="je", question="q", expected_pub="596",
            difficulty="simple", ground_truth="g", ai_answer="a",
            judge_error="Rate limit",
        )
        report.add(r)
        assert report.judge_errors == 1
        assert report._scored      == 0

    def test_slice_by_pub(self):
        report = GenerationReport()
        report.add(self._scored_result(pub="596"))
        report.add(self._scored_result(pub="17", scores=(2,2,2,2,2)))
        assert report.by_pub["596"]["pass"] == 1
        assert report.by_pub["17"]["pass"]  == 0

    def test_print_report_no_error(self, capsys):
        report = GenerationReport()
        report.add(self._scored_result())
        report.print_report()
        out = capsys.readouterr().out
        assert "Pass rate" in out
        assert "Faithfulness" in out


# ══════════════════════════════════════════════════════════════════════════════
# evaluate_generation integration (mocked agent + judge)
# ══════════════════════════════════════════════════════════════════════════════

class TestEvaluateGeneration:

    def _make_gold_set(self, n=2):
        gs = GoldSet()
        for i in range(n):
            gs.entries.append(GoldSetEntry(
                question       = f"What is the EIC rule {i}?",
                ground_truth   = f"The rule is X limit {i * 1000}.",
                expected_pub   = "596",
                gold_chunk_ids = [f"chunk-{i:03d}"],
                difficulty     = "simple",
                topic_tags     = [],
            ))
        return gs

    @patch("taxflow_kb.layer5.generation_evaluator._call_judge")
    def test_evaluate_generation_all_pass(self, mock_judge):
        """All entries get perfect scores via mocked judge."""
        def fill_scores(result, contexts, api_key, model):
            result.faithfulness       = 4
            result.answer_correctness = 4
            result.citation_accuracy  = 4
            result.temporal_accuracy  = 4
            result.safe_abstention    = 4
            result.reasoning          = "Correct."

        mock_judge.side_effect = fill_scores

        mock_agent = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.error    = None
        mock_query_result.answer   = "The EIC limit is $46,560 for 2025."
        mock_query_result.contexts = []
        mock_query_result.retrieval_ms = 100.0
        mock_query_result.synthesis_ms = 500.0
        mock_agent.query.return_value  = mock_query_result

        gs = self._make_gold_set(2)
        report = evaluate_generation(
            gold_set         = gs,
            agent            = mock_agent,
            api_key          = "sk-test",
            judge_model      = "gpt-5.4",
            rate_limit_delay = 0,
        )
        assert report.pass_rate   == pytest.approx(1.0)
        assert report.avg_overall == pytest.approx(4.0)
        assert report.total       == 2

    @patch("taxflow_kb.layer5.generation_evaluator._call_judge")
    def test_agent_error_skips_judge(self, mock_judge):
        """If agent errors, judge should not be called for that entry."""
        mock_agent = MagicMock()
        mock_agent.query.side_effect = RuntimeError("DB down")

        gs = self._make_gold_set(1)
        report = evaluate_generation(
            gold_set         = gs,
            agent            = mock_agent,
            api_key          = "sk-test",
            rate_limit_delay = 0,
        )
        assert report.agent_errors == 1
        mock_judge.assert_not_called()

    @patch("taxflow_kb.layer5.generation_evaluator._call_judge")
    def test_pub_filter_respected(self, mock_judge):
        gs = GoldSet()
        gs.entries.append(GoldSetEntry(
            question="q1", ground_truth="a1", expected_pub="596",
            gold_chunk_ids=[], difficulty="simple", topic_tags=[],
        ))
        gs.entries.append(GoldSetEntry(
            question="q2", ground_truth="a2", expected_pub="17",
            gold_chunk_ids=[], difficulty="simple", topic_tags=[],
        ))

        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.error = None
        mock_result.answer = "answer"
        mock_result.contexts = []
        mock_result.retrieval_ms = 100.0
        mock_result.synthesis_ms = 500.0
        mock_agent.query.return_value = mock_result

        def fill_scores(result, contexts, api_key, model):
            result.faithfulness = result.answer_correctness = 4
            result.citation_accuracy = result.temporal_accuracy = 4
            result.safe_abstention = 4
            result.reasoning = ""

        mock_judge.side_effect = fill_scores

        report = evaluate_generation(
            gold_set         = gs,
            agent            = mock_agent,
            api_key          = "sk-test",
            pub_filter       = ["596"],
            rate_limit_delay = 0,
        )
        assert report.total == 1
        assert "596" in report.by_pub
        assert "17"  not in report.by_pub


# ══════════════════════════════════════════════════════════════════════════════
# V5.1 Gold Set Quality Gate tests
# ══════════════════════════════════════════════════════════════════════════════

from taxflow_kb.layer5.validation.v5_1_gold_set import (
    validate_gold_set,
    MIN_ENTRIES, MIN_PER_PUB, EXPECTED_PUBS,
)


class TestV51GoldSetGate:

    PUBS = ["17", "501", "525", "550", "590a", "590b", "596", "969"]
    DIFFS = ["simple", "medium", "complex"]

    def _make_passing_gold_set(self) -> GoldSet:
        """Build a gold set that passes all V5.1 checks."""
        gs = GoldSet()
        # 6 entries per pub (48 total > MIN_ENTRIES=40), cycling difficulty
        for pub in self.PUBS:
            for j in range(6):
                diff = self.DIFFS[j % 3]
                gs.entries.append(GoldSetEntry(
                    question       = f"What is the specific rule for Pub {pub} question {j} regarding income limits and phase-out ranges?",
                    ground_truth   = f"The specific income limit for Pub {pub} scenario {j} is ${10_000 + j * 5_000} for tax year 2025, subject to phase-out rules.",
                    expected_pub   = pub,
                    gold_chunk_ids = [f"chunk-{pub}-{j:03d}"],
                    difficulty     = diff,
                    topic_tags     = ["income"],
                ))
        return gs

    def test_passing_gold_set(self):
        gs = self._make_passing_gold_set()
        result = validate_gold_set(gs)
        assert result.passed, [c for c in result.checks if not c.passed]

    def test_v51_a_too_few_entries(self):
        gs = GoldSet()
        gs.entries.append(_make_entry())  # just 1 entry
        result = validate_gold_set(gs)
        a_check = next(c for c in result.checks if c.code == "V5.1-A")
        assert not a_check.passed

    def test_v51_b_missing_pub(self):
        """Gold set with all pubs except 969 fails V5.1-B."""
        gs = self._make_passing_gold_set()
        gs.entries = [e for e in gs.entries if e.expected_pub != "969"]
        result = validate_gold_set(gs)
        b_check = next(c for c in result.checks if c.code == "V5.1-B")
        assert not b_check.passed
        assert "969" in b_check.detail

    def test_v51_c_missing_difficulty(self):
        """Gold set with only 'simple' and 'medium' fails V5.1-C."""
        gs = self._make_passing_gold_set()
        for e in gs.entries:
            if e.difficulty == "complex":
                e.difficulty = "simple"
        result = validate_gold_set(gs)
        c_check = next(c for c in result.checks if c.code == "V5.1-C")
        assert not c_check.passed
        assert "complex" in c_check.detail

    def test_v51_d_short_questions(self):
        """Single-word questions fail V5.1-D."""
        gs = GoldSet()
        for pub in self.PUBS:
            for j in range(6):
                gs.entries.append(GoldSetEntry(
                    question       = "Who?",
                    ground_truth   = "The income limit is $46,560 for tax year 2025 per IRS Pub 596 EIC tables.",
                    expected_pub   = pub,
                    gold_chunk_ids = [f"chunk-{pub}-{j}"],
                    difficulty     = self.DIFFS[j % 3],
                    topic_tags     = [],
                ))
        result = validate_gold_set(gs)
        d_check = next(c for c in result.checks if c.code == "V5.1-D")
        assert not d_check.passed

    def test_v51_e_short_answers(self):
        """One-word answers fail V5.1-E."""
        gs = GoldSet()
        for pub in self.PUBS:
            for j in range(6):
                gs.entries.append(GoldSetEntry(
                    question       = f"What is the specific rule regarding income limits in Pub {pub} section {j}?",
                    ground_truth   = "Yes.",
                    expected_pub   = pub,
                    gold_chunk_ids = [f"chunk-{pub}-{j}"],
                    difficulty     = self.DIFFS[j % 3],
                    topic_tags     = [],
                ))
        result = validate_gold_set(gs)
        e_check = next(c for c in result.checks if c.code == "V5.1-E")
        assert not e_check.passed

    def test_v51_f_duplicate_questions(self):
        """Two entries with the same question fail V5.1-F."""
        gs = self._make_passing_gold_set()
        # Duplicate the first entry's question on the second entry
        gs.entries[1].question = gs.entries[0].question
        result = validate_gold_set(gs)
        f_check = next(c for c in result.checks if c.code == "V5.1-F")
        assert not f_check.passed
        assert "1 duplicate" in f_check.detail

    def test_print_report_no_error(self, capsys):
        gs = self._make_passing_gold_set()
        result = validate_gold_set(gs)
        result.print_report()
        out = capsys.readouterr().out
        assert "V5.1-A" in out
        assert "PASS"   in out


# ══════════════════════════════════════════════════════════════════════════════
# patch_adjacent_chunks tests
# ══════════════════════════════════════════════════════════════════════════════

from taxflow_kb.layer5.gold_set_patcher import patch_adjacent_chunks
from unittest.mock import MagicMock, patch as mock_patch
import contextlib


class TestPatchAdjacentChunks:

    def _make_store_mock(self, chunk_ids_by_pub: dict[str, list[str]]):
        """Return a mock Layer3Store whose _cursor returns ordered chunk IDs."""
        store = MagicMock()

        @contextlib.contextmanager
        def mock_cursor():
            cur = MagicMock()
            def execute(sql, params):
                pub = params[0]
                ids = chunk_ids_by_pub.get(pub, [])
                cur.fetchall.return_value = [(cid,) for cid in ids]
            cur.execute = execute
            yield cur

        store._cursor = mock_cursor
        return store

    def _gold_set_with_entries(self, entries_spec):
        """entries_spec: list of (expected_pub, primary_chunk_id)"""
        gs = GoldSet()
        for pub, cid in entries_spec:
            gs.entries.append(GoldSetEntry(
                question       = f"Q about {pub} {cid}",
                ground_truth   = "Some answer about tax rules and income limits.",
                expected_pub   = pub,
                gold_chunk_ids = [cid],
                difficulty     = "simple",
                topic_tags     = [],
            ))
        return gs

    def test_adds_adjacent_chunk_both_sides(self):
        """Middle chunk: should get prev and next as adjacent."""
        store = self._make_store_mock({"596": ["c0", "c1", "c2", "c3", "c4"]})
        gs    = self._gold_set_with_entries([("596", "c2")])

        patch_adjacent_chunks(gs, store, window=1)

        ids = gs.entries[0].gold_chunk_ids
        assert "c2" in ids   # primary still there
        assert "c1" in ids   # left neighbour
        assert "c3" in ids   # right neighbour
        assert len(ids) == 3

    def test_first_chunk_only_gets_right_neighbour(self):
        """First chunk has no left neighbour."""
        store = self._make_store_mock({"596": ["c0", "c1", "c2"]})
        gs    = self._gold_set_with_entries([("596", "c0")])

        patch_adjacent_chunks(gs, store, window=1)
        ids = gs.entries[0].gold_chunk_ids

        assert "c0" in ids
        assert "c1" in ids
        assert len(ids) == 2  # no c(-1)

    def test_last_chunk_only_gets_left_neighbour(self):
        """Last chunk has no right neighbour."""
        store = self._make_store_mock({"596": ["c0", "c1", "c2"]})
        gs    = self._gold_set_with_entries([("596", "c2")])

        patch_adjacent_chunks(gs, store, window=1)
        ids = gs.entries[0].gold_chunk_ids

        assert "c2" in ids
        assert "c1" in ids
        assert len(ids) == 2

    def test_window_2_adds_up_to_4_neighbours(self):
        """Window=2 adds ±2 neighbours (up to 4 extra IDs)."""
        store = self._make_store_mock({"596": ["c0","c1","c2","c3","c4","c5","c6"]})
        gs    = self._gold_set_with_entries([("596", "c3")])

        patch_adjacent_chunks(gs, store, window=2)
        ids = gs.entries[0].gold_chunk_ids

        assert set(ids) == {"c1", "c2", "c3", "c4", "c5"}

    def test_already_patched_entries_skipped(self):
        """Entries with >1 gold_chunk_id are skipped (already patched)."""
        store = self._make_store_mock({"596": ["c0","c1","c2"]})
        gs    = GoldSet()
        e     = GoldSetEntry(
            question="Q", ground_truth="A long enough ground truth for testing purposes.",
            expected_pub="596", gold_chunk_ids=["c1", "c0"],  # already has 2
            difficulty="simple", topic_tags=[],
        )
        gs.entries.append(e)

        n_patched, n_already = patch_adjacent_chunks(gs, store, window=1)

        assert n_already == 1
        assert n_patched == 0
        assert gs.entries[0].gold_chunk_ids == ["c1", "c0"]  # unchanged

    def test_multiple_pubs_each_cached_separately(self):
        """Chunks from different pubs are looked up independently."""
        store = self._make_store_mock({
            "596": ["s0", "s1", "s2"],
            "17" : ["p0", "p1", "p2"],
        })
        gs = self._gold_set_with_entries([("596", "s1"), ("17", "p1")])

        patch_adjacent_chunks(gs, store, window=1)

        ids_596 = gs.entries[0].gold_chunk_ids
        ids_17  = gs.entries[1].gold_chunk_ids

        assert set(ids_596) == {"s0", "s1", "s2"}
        assert set(ids_17)  == {"p0", "p1", "p2"}

    def test_primary_chunk_not_found_leaves_entry_unchanged(self):
        """If the primary chunk ID isn't in the DB, entry is left as-is."""
        store = self._make_store_mock({"596": ["c0", "c1", "c2"]})
        gs    = self._gold_set_with_entries([("596", "missing-id")])

        patch_adjacent_chunks(gs, store, window=1)

        # Entry unchanged (primary not found)
        assert gs.entries[0].gold_chunk_ids == ["missing-id"]

    def test_returns_correct_counts(self):
        store = self._make_store_mock({
            "596": ["c0","c1","c2"],
            "17" : ["p0","p1","p2"],
        })
        already = GoldSetEntry(
            question="Q2", ground_truth="Long enough answer to pass quality filter.",
            expected_pub="596", gold_chunk_ids=["c1","c0"],  # already multi
            difficulty="simple", topic_tags=[],
        )
        new = GoldSetEntry(
            question="Q1", ground_truth="Long enough answer to pass quality filter.",
            expected_pub="17", gold_chunk_ids=["p1"],  # single — will be patched
            difficulty="simple", topic_tags=[],
        )
        gs = GoldSet()
        gs.entries.extend([already, new])

        n_patched, n_already = patch_adjacent_chunks(gs, store, window=1)
        assert n_patched == 1
        assert n_already == 1
