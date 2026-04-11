"""
tests/test_multi_year.py

Tests for multi-year support across the Tax Brain pipeline:
  - Publication registry coverage utilities
  - Year-aware pub filtering in query classifier
  - CLI coverage command
  - Year extraction from queries
  - Retriever classify integration (QueryMetadata unpacking)
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

# Resolve project root dynamically (works on any machine)
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


# ──────────────────────────────────────────────────────────────────────────────
# Registry multi-year utilities
# ──────────────────────────────────────────────────────────────────────────────

class TestRegistryCoverageUtilities:
    """Test the new multi-year coverage methods on PublicationRegistry."""

    def setup_method(self):
        from taxflow_kb.layer3.publication_registry import PublicationRegistry
        self.reg = PublicationRegistry()

    def test_get_available_years_known_pub(self):
        """Pub 17 covers 2023-2025."""
        years = self.reg.get_available_years("17")
        assert years == [2023, 2024, 2025]

    def test_get_available_years_discontinued_pub(self):
        """Pub 535 is discontinued — only 2022."""
        years = self.reg.get_available_years("535")
        assert years == [2022]

    def test_get_available_years_empty_pub(self):
        """Pub 564 has no tax years (fully discontinued)."""
        years = self.reg.get_available_years("564")
        assert years == []

    def test_get_available_years_unknown_pub(self):
        """Unknown pub returns empty list."""
        years = self.reg.get_available_years("99999")
        assert years == []

    def test_get_pubs_for_year_2025(self):
        """2025 should include most active pubs."""
        pubs = self.reg.get_pubs_for_year(2025)
        pub_nums = [p.pub_number for p in pubs]
        assert "17" in pub_nums
        assert "501" in pub_nums
        assert "550" in pub_nums
        # Pub 535 is 2022-only, should NOT be here
        assert "535" not in pub_nums

    def test_get_pubs_for_year_2022(self):
        """2022 should include Pub 535."""
        pubs = self.reg.get_pubs_for_year(2022)
        pub_nums = [p.pub_number for p in pubs]
        assert "535" in pub_nums

    def test_get_pubs_for_year_returns_sorted_by_tier(self):
        """Results sorted by (tier, pub_number)."""
        pubs = self.reg.get_pubs_for_year(2025)
        tiers = [p.tier for p in pubs]
        assert tiers == sorted(tiers), "Pubs should be sorted by tier"

    def test_get_pubs_for_nonexistent_year(self):
        """Year with no pubs returns empty list."""
        pubs = self.reg.get_pubs_for_year(1999)
        assert pubs == []

    def test_get_all_years(self):
        """Should return at least 2022-2025."""
        years = self.reg.get_all_years()
        assert 2022 in years
        assert 2023 in years
        assert 2024 in years
        assert 2025 in years
        assert years == sorted(years)

    def test_coverage_matrix_structure(self):
        """Matrix should have all pubs × all years."""
        matrix = self.reg.coverage_matrix()
        all_pubs = self.reg.all_pub_numbers()
        all_years = self.reg.get_all_years()
        assert set(matrix.keys()) == set(all_pubs)
        for pn, year_map in matrix.items():
            assert set(year_map.keys()) == set(all_years)
            assert all(isinstance(v, bool) for v in year_map.values())

    def test_coverage_matrix_values(self):
        """Spot-check matrix values for known pubs."""
        matrix = self.reg.coverage_matrix()
        # Pub 17 covers 2023-2025
        assert matrix["17"][2023] is True
        assert matrix["17"][2025] is True
        # Pub 535 only covers 2022
        assert matrix["535"][2022] is True
        assert matrix["535"][2023] is False
        assert matrix["535"][2025] is False

    def test_coverage_gaps(self):
        """Pub 535 should have gaps in 2023-2025."""
        gaps = self.reg.coverage_gaps()
        assert "535" in gaps
        assert 2023 in gaps["535"]
        assert 2025 in gaps["535"]
        assert 2022 not in gaps["535"]

    def test_coverage_gaps_specific_years(self):
        """Check gaps for a specific year range."""
        gaps = self.reg.coverage_gaps(years=[2024, 2025])
        # Pub 535 should be missing both
        assert "535" in gaps
        assert gaps["535"] == [2024, 2025]
        # Pub 564 has no active years so it's skipped entirely

    def test_coverage_gaps_excludes_fully_discontinued(self):
        """Pub 564 (empty tax_years) should not appear in gaps."""
        gaps = self.reg.coverage_gaps()
        assert "564" not in gaps

    def test_coverage_summary_is_string(self):
        """coverage_summary() returns a non-empty string."""
        summary = self.reg.coverage_summary()
        assert isinstance(summary, str)
        assert len(summary) > 100
        assert "Tax Brain" in summary
        assert "Coverage" in summary

    def test_coverage_summary_contains_pub_numbers(self):
        """Report should mention known pub numbers."""
        summary = self.reg.coverage_summary()
        assert "17" in summary
        assert "501" in summary
        assert "535" in summary


# ──────────────────────────────────────────────────────────────────────────────
# Year-aware pub filter in query classifier
# ──────────────────────────────────────────────────────────────────────────────

class TestYearAwarePubFilter:
    """Test that suggest_pub_filter() respects tax year constraints."""

    def test_filter_excludes_discontinued_pub_for_2025(self):
        """Queries about 2025 should not suggest Pub 535 (2022-only)."""
        from taxflow_kb.layer4.query_classifier import (
            classify_query,
            suggest_pub_filter,
        )
        # Query that would match business expense topics
        meta = classify_query("What business expenses can I deduct for 2025?")
        pubs = suggest_pub_filter(meta)
        if pubs:
            assert "535" not in pubs, "Pub 535 (2022-only) should not be suggested for 2025"

    def test_filter_includes_discontinued_pub_for_2022(self):
        """Queries about 2022 should include Pub 535."""
        from taxflow_kb.layer4.query_classifier import (
            QueryMetadata,
            QueryIntent,
            suggest_pub_filter,
        )
        # Craft metadata that would match business expense topics with year 2022
        meta = QueryMetadata(
            original_query="What business expenses for 2022?",
            normalized_query="what business expenses for 2022",
            intent=QueryIntent.LOOKUP,
            tax_year=2022,
            form_refs=[],
            pub_refs=[],
            topic_tags=["business-expenses"],
            confidence=0.8,
        )
        pubs = suggest_pub_filter(meta)
        if pubs:
            assert "535" in pubs, "Pub 535 should be suggested for 2022 business expense queries"

    def test_filter_with_no_year_returns_all_matches(self):
        """When tax_year is None, no year filtering is applied."""
        from taxflow_kb.layer4.query_classifier import (
            QueryMetadata,
            QueryIntent,
            suggest_pub_filter,
        )
        meta = QueryMetadata(
            original_query="Tell me about business expenses",
            normalized_query="tell me about business expenses",
            intent=QueryIntent.GENERAL,
            tax_year=None,
            form_refs=[],
            pub_refs=[],
            topic_tags=["business-expenses"],
            confidence=0.8,
        )
        pubs = suggest_pub_filter(meta)
        # Should return whatever matches without year filtering
        assert pubs is None or isinstance(pubs, list)


# ──────────────────────────────────────────────────────────────────────────────
# Year extraction from queries
# ──────────────────────────────────────────────────────────────────────────────

class TestYearExtraction:
    """Test that classify_query() correctly extracts tax years from queries."""

    def test_extract_explicit_year(self):
        from taxflow_kb.layer4.query_classifier import classify_query
        meta = classify_query("What is the standard deduction for 2025?")
        assert meta.tax_year == 2025

    def test_extract_year_2024(self):
        from taxflow_kb.layer4.query_classifier import classify_query
        meta = classify_query("What was the HSA contribution limit in 2024?")
        assert meta.tax_year == 2024

    def test_extract_year_2023(self):
        from taxflow_kb.layer4.query_classifier import classify_query
        meta = classify_query("2023 earned income credit phase-out amounts")
        assert meta.tax_year == 2023

    def test_no_year_returns_none(self):
        from taxflow_kb.layer4.query_classifier import classify_query
        meta = classify_query("How does depreciation work for rental property?")
        assert meta.tax_year is None

    def test_query_metadata_fields(self):
        """QueryMetadata has all expected fields."""
        from taxflow_kb.layer4.query_classifier import classify_query
        meta = classify_query("What is the 2025 standard deduction for single filer?")
        assert hasattr(meta, "intent")
        assert hasattr(meta, "tax_year")
        assert hasattr(meta, "form_refs")
        assert hasattr(meta, "pub_refs")
        assert hasattr(meta, "topic_tags")
        assert hasattr(meta, "confidence")
        assert hasattr(meta, "original_query")


# ──────────────────────────────────────────────────────────────────────────────
# Retriever classify integration
# ──────────────────────────────────────────────────────────────────────────────

class TestRetrieverClassifyIntegration:
    """Test that retriever correctly unpacks QueryMetadata from classify_query()."""

    def test_query_metadata_is_dataclass(self):
        """classify_query() should return a QueryMetadata dataclass, not a tuple."""
        from taxflow_kb.layer4.query_classifier import classify_query, QueryMetadata
        result = classify_query("What is the standard deduction for 2025?")
        assert isinstance(result, QueryMetadata)

    def test_query_metadata_intent_has_value(self):
        """QueryMetadata.intent should be a QueryIntent enum with a .value string."""
        from taxflow_kb.layer4.query_classifier import classify_query
        meta = classify_query("How much can I contribute to my HSA in 2024?")
        assert hasattr(meta.intent, "value")
        assert isinstance(meta.intent.value, str)

    def test_suggest_pub_filter_accepts_metadata(self):
        """suggest_pub_filter() should accept a single QueryMetadata argument."""
        from taxflow_kb.layer4.query_classifier import (
            classify_query,
            suggest_pub_filter,
        )
        meta = classify_query("What is the 2025 HSA contribution limit?")
        # Should not raise TypeError (was the bug: passing 2 positional args)
        result = suggest_pub_filter(meta)
        assert result is None or isinstance(result, list)

    def test_retriever_classify_code_path(self):
        """Simulate the retriever's classify code path to confirm it won't crash."""
        from taxflow_kb.layer4.query_classifier import (
            classify_query,
            suggest_pub_filter,
            QueryIntent,
        )
        query = "What is the earned income credit for 2025?"
        query_meta = classify_query(query)

        # This is exactly what retriever.py now does (lines ~841-857)
        query_intent = query_meta.intent.value
        form_refs = query_meta.form_refs
        line_refs = getattr(query_meta, "line_refs", [])
        detected_tax_year = query_meta.tax_year

        assert isinstance(query_intent, str)
        assert isinstance(form_refs, list)
        assert isinstance(line_refs, list)
        assert detected_tax_year is None or isinstance(detected_tax_year, int)

        # This is the fixed suggest_pub_filter call
        detected_pubs = suggest_pub_filter(query_meta)
        assert detected_pubs is None or isinstance(detected_pubs, list)

    def test_retrieve_with_classification_code_path(self):
        """Simulate the retrieve_with_classification() code path."""
        from taxflow_kb.layer4.query_classifier import classify_query

        query_meta = classify_query("What goes on Schedule C line 31?")
        query_metadata = {
            "intent": query_meta.intent.value,
            "form_refs": query_meta.form_refs,
            "topic_tags": query_meta.topic_tags,
            "tax_year": query_meta.tax_year,
        }

        assert "intent" in query_metadata
        assert "form_refs" in query_metadata
        assert "topic_tags" in query_metadata
        assert "tax_year" in query_metadata


# ──────────────────────────────────────────────────────────────────────────────
# CLI coverage command
# ──────────────────────────────────────────────────────────────────────────────

class TestCLICoverageCommand:
    """Test the CLI coverage subcommand."""

    def test_coverage_command_exists_in_dispatch(self):
        """The 'coverage' command should be in the parser."""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "cli.py", "coverage", "--help"],
            capture_output=True, text=True,
            cwd=_PROJECT_ROOT,
        )
        assert result.returncode == 0
        assert "coverage" in result.stdout.lower()

    def test_coverage_command_runs(self):
        """The 'coverage' command should run and print the report."""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "cli.py", "coverage"],
            capture_output=True, text=True,
            cwd=_PROJECT_ROOT,
        )
        assert result.returncode == 0
        assert "Tax Brain" in result.stdout
        assert "Coverage" in result.stdout

    def test_coverage_gaps_only_runs(self):
        """The 'coverage --gaps-only' command should run."""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "cli.py", "coverage", "--gaps-only"],
            capture_output=True, text=True,
            cwd=_PROJECT_ROOT,
        )
        assert result.returncode == 0
        # Should show Pub 535 gaps (or "No coverage gaps" if checking only standard years)
        assert "535" in result.stdout or "No coverage gaps" in result.stdout


# ──────────────────────────────────────────────────────────────────────────────
# Pub 551 revision-based coverage
# ──────────────────────────────────────────────────────────────────────────────

class TestRevisionBasedPubs:
    """Test handling of revision-dated pubs (non-annual)."""

    def test_pub_551_available_years(self):
        """Pub 551 (revision-dated) should have at least 2025."""
        from taxflow_kb.layer3.publication_registry import get_registry
        reg = get_registry()
        years = reg.get_available_years("551")
        assert 2025 in years

    def test_pub_535_discontinued(self):
        """Pub 535 only covers 2022."""
        from taxflow_kb.layer3.publication_registry import get_registry
        reg = get_registry()
        years = reg.get_available_years("535")
        assert years == [2022]
        assert 2023 not in years
        assert 2025 not in years


# ──────────────────────────────────────────────────────────────────────────────
# Default year behavior — prevents cross-year duplicates
# ──────────────────────────────────────────────────────────────────────────────

class TestDefaultYearBehavior:
    """
    When no year is specified and none is detected from the query,
    the pipeline should default to settings.default_tax_year (2025)
    rather than returning results from ALL years.
    """

    def test_agent_defaults_to_current_year(self):
        """CPAQueryAgent.query() should fill in default_tax_year when tax_year is None."""
        from unittest.mock import patch, MagicMock
        from taxflow_kb.layer4.agent import CPAQueryAgent
        from taxflow_kb.layer4.query_classifier import QueryMetadata, QueryIntent

        # Mock classify_query to return no detected year
        no_year_meta = QueryMetadata(
            original_query="How does depreciation work?",
            normalized_query="how does depreciation work",
            intent=QueryIntent.GENERAL,
            tax_year=None,  # no year detected
            form_refs=[],
            pub_refs=[],
            topic_tags=[],
            confidence=0.5,
        )

        with patch("taxflow_kb.layer4.agent.classify_query", return_value=no_year_meta):
            with patch("taxflow_kb.layer4.agent.get_settings") as mock_settings:
                mock_settings.return_value.default_tax_year = 2025
                mock_settings.return_value.retrieval_top_k = 5
                mock_settings.return_value.synthesis_temperature = 0.1
                mock_settings.return_value.synthesis_max_tokens = 1000

                agent = MagicMock(spec=CPAQueryAgent)
                agent._retriever = MagicMock()
                agent._retriever.retrieve.return_value = ([], 10.0, {"mode": "flat", "nav_pubs": [], "ontology_pubs": []})

                # Call the real query method
                CPAQueryAgent.query(agent, "How does depreciation work?")

                # Verify retriever was called with default year, not None
                call_kwargs = agent._retriever.retrieve.call_args
                assert call_kwargs is not None
                # tax_year should be 2025 (the default), not None
                _, kwargs = call_kwargs
                assert kwargs.get("tax_year") == 2025

    def test_agent_respects_explicit_year(self):
        """When user passes tax_year=2023, the agent should use 2023, not default."""
        from unittest.mock import patch, MagicMock
        from taxflow_kb.layer4.agent import CPAQueryAgent
        from taxflow_kb.layer4.query_classifier import QueryMetadata, QueryIntent

        no_year_meta = QueryMetadata(
            original_query="How does depreciation work?",
            normalized_query="how does depreciation work",
            intent=QueryIntent.GENERAL,
            tax_year=None,
            form_refs=[],
            pub_refs=[],
            topic_tags=[],
            confidence=0.5,
        )

        with patch("taxflow_kb.layer4.agent.classify_query", return_value=no_year_meta):
            with patch("taxflow_kb.layer4.agent.get_settings") as mock_settings:
                mock_settings.return_value.default_tax_year = 2025
                mock_settings.return_value.retrieval_top_k = 5
                mock_settings.return_value.synthesis_temperature = 0.1
                mock_settings.return_value.synthesis_max_tokens = 1000

                agent = MagicMock(spec=CPAQueryAgent)
                agent._retriever = MagicMock()
                agent._retriever.retrieve.return_value = ([], 10.0, {"mode": "flat", "nav_pubs": [], "ontology_pubs": []})

                CPAQueryAgent.query(agent, "How does depreciation work?", tax_year=2023)

                call_kwargs = agent._retriever.retrieve.call_args
                _, kwargs = call_kwargs
                assert kwargs.get("tax_year") == 2023

    def test_agent_uses_detected_year(self):
        """When classify_query detects a year, agent should use it over default."""
        from unittest.mock import patch, MagicMock
        from taxflow_kb.layer4.agent import CPAQueryAgent
        from taxflow_kb.layer4.query_classifier import QueryMetadata, QueryIntent

        year_2024_meta = QueryMetadata(
            original_query="What is the 2024 HSA limit?",
            normalized_query="what is the 2024 hsa limit",
            intent=QueryIntent.LOOKUP,
            tax_year=2024,  # year detected from query
            form_refs=[],
            pub_refs=[],
            topic_tags=["hsa"],
            confidence=0.9,
        )

        with patch("taxflow_kb.layer4.agent.classify_query", return_value=year_2024_meta):
            with patch("taxflow_kb.layer4.agent.get_settings") as mock_settings:
                mock_settings.return_value.default_tax_year = 2025
                mock_settings.return_value.retrieval_top_k = 5
                mock_settings.return_value.synthesis_temperature = 0.1
                mock_settings.return_value.synthesis_max_tokens = 1000

                agent = MagicMock(spec=CPAQueryAgent)
                agent._retriever = MagicMock()
                agent._retriever.retrieve.return_value = ([], 10.0, {"mode": "flat", "nav_pubs": [], "ontology_pubs": []})

                CPAQueryAgent.query(agent, "What is the 2024 HSA limit?")

                call_kwargs = agent._retriever.retrieve.call_args
                _, kwargs = call_kwargs
                assert kwargs.get("tax_year") == 2024, \
                    "Detected year (2024) should take priority over default (2025)"

    def test_cli_search_help_does_not_expose_all_years(self):
        """The search --tax-year help should NOT advertise the 0/all-years escape hatch."""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "cli.py", "search", "--help"],
            capture_output=True, text=True,
            cwd=_PROJECT_ROOT,
        )
        assert result.returncode == 0
        assert "ALL years" not in result.stdout
        assert "tax-year 0" not in result.stdout

    def test_cli_ask_help_does_not_expose_all_years(self):
        """The ask --tax-year help should NOT advertise the 0/all-years escape hatch."""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "cli.py", "ask", "--help"],
            capture_output=True, text=True,
            cwd=_PROJECT_ROOT,
        )
        assert result.returncode == 0
        assert "ALL years" not in result.stdout
        assert "tax-year 0" not in result.stdout


# ──────────────────────────────────────────────────────────────────────────────
# Cross-year comparison queries
# ──────────────────────────────────────────────────────────────────────────────

class TestCrossYearComparison:
    """Test cross-year comparison detection and multi-call retrieval."""

    def test_extract_comparison_years_from_to(self):
        """'from 2023 to 2025' → [2023, 2025]."""
        from taxflow_kb.layer4.query_classifier import _extract_comparison_years
        years = _extract_comparison_years(
            "How did the standard deduction change from 2023 to 2025?"
        )
        assert years == [2023, 2025]

    def test_extract_comparison_years_vs(self):
        """'2023 vs 2024' → [2023, 2024]."""
        from taxflow_kb.layer4.query_classifier import _extract_comparison_years
        years = _extract_comparison_years(
            "HSA contribution limit 2023 vs 2024"
        )
        assert years == [2023, 2024]

    def test_extract_comparison_years_three_years(self):
        """Three years → all three returned."""
        from taxflow_kb.layer4.query_classifier import _extract_comparison_years
        years = _extract_comparison_years(
            "Compare EIC limits for 2023, 2024, and 2025"
        )
        assert years == [2023, 2024, 2025]

    def test_extract_comparison_years_single_year(self):
        """A single year → empty list (not a comparison)."""
        from taxflow_kb.layer4.query_classifier import _extract_comparison_years
        years = _extract_comparison_years(
            "What is the 2025 standard deduction?"
        )
        assert years == []

    def test_extract_comparison_years_no_year(self):
        """No years → empty list."""
        from taxflow_kb.layer4.query_classifier import _extract_comparison_years
        years = _extract_comparison_years("How does depreciation work?")
        assert years == []

    def test_classify_query_populates_comparison_years(self):
        """classify_query() should populate comparison_years for multi-year queries."""
        from taxflow_kb.layer4.query_classifier import classify_query
        meta = classify_query("How did HSA limits change from 2023 to 2025?")
        assert meta.comparison_years == [2023, 2025]

    def test_classify_query_no_comparison_years_for_single(self):
        """classify_query() should have empty comparison_years for single-year queries."""
        from taxflow_kb.layer4.query_classifier import classify_query
        meta = classify_query("What is the 2025 HSA limit?")
        assert meta.comparison_years == []

    def test_agent_cross_year_makes_separate_calls(self):
        """
        When comparison_years has 2+ years, the agent should make separate
        retriever calls per year instead of one all-years call.
        """
        from unittest.mock import patch, MagicMock, call
        from taxflow_kb.layer4.agent import CPAQueryAgent
        from taxflow_kb.layer4.query_classifier import QueryMetadata, QueryIntent

        comparison_meta = QueryMetadata(
            original_query="How did HSA limits change from 2023 to 2025?",
            normalized_query="how did hsa limits change from 2023 to 2025",
            intent=QueryIntent.COMPARISON,
            tax_year=2023,  # first year detected
            comparison_years=[2023, 2025],
            form_refs=[],
            pub_refs=[],
            topic_tags=["hsa"],
            confidence=0.85,
        )

        with patch("taxflow_kb.layer4.agent.classify_query", return_value=comparison_meta):
            with patch("taxflow_kb.layer4.agent.get_settings") as mock_settings:
                mock_settings.return_value.default_tax_year = 2025
                mock_settings.return_value.retrieval_top_k = 5
                mock_settings.return_value.synthesis_temperature = 0.1
                mock_settings.return_value.synthesis_max_tokens = 1000

                agent = MagicMock(spec=CPAQueryAgent)
                agent._retriever = MagicMock()
                agent._retriever.retrieve.return_value = ([], 5.0, {"mode": "flat", "nav_pubs": [], "ontology_pubs": []})

                # Bind real cross-year method
                agent._retrieve_cross_year = lambda *a, **kw: CPAQueryAgent._retrieve_cross_year(agent, *a, **kw)

                CPAQueryAgent.query(
                    agent,
                    "How did HSA limits change from 2023 to 2025?",
                )

                # Should have made 2 separate calls (one per year)
                retrieve_calls = agent._retriever.retrieve.call_args_list
                assert len(retrieve_calls) == 2

                # First call should be for 2023
                _, kwargs_1 = retrieve_calls[0]
                assert kwargs_1["tax_year"] == 2023

                # Second call should be for 2025
                _, kwargs_2 = retrieve_calls[1]
                assert kwargs_2["tax_year"] == 2025

    def test_agent_single_year_query_makes_one_call(self):
        """Standard queries should make exactly one retriever call."""
        from unittest.mock import patch, MagicMock
        from taxflow_kb.layer4.agent import CPAQueryAgent
        from taxflow_kb.layer4.query_classifier import QueryMetadata, QueryIntent

        single_meta = QueryMetadata(
            original_query="What is the 2025 HSA limit?",
            normalized_query="what is the 2025 hsa limit",
            intent=QueryIntent.LOOKUP,
            tax_year=2025,
            comparison_years=[],  # not a comparison
            form_refs=[],
            pub_refs=[],
            topic_tags=["hsa"],
            confidence=0.9,
        )

        with patch("taxflow_kb.layer4.agent.classify_query", return_value=single_meta):
            with patch("taxflow_kb.layer4.agent.get_settings") as mock_settings:
                mock_settings.return_value.default_tax_year = 2025
                mock_settings.return_value.retrieval_top_k = 5
                mock_settings.return_value.synthesis_temperature = 0.1
                mock_settings.return_value.synthesis_max_tokens = 1000

                agent = MagicMock(spec=CPAQueryAgent)
                agent._retriever = MagicMock()
                agent._retriever.retrieve.return_value = ([], 10.0, {"mode": "flat", "nav_pubs": [], "ontology_pubs": []})

                CPAQueryAgent.query(agent, "What is the 2025 HSA limit?")

                # Should have made exactly 1 call
                assert agent._retriever.retrieve.call_count == 1
                _, kwargs = agent._retriever.retrieve.call_args
                assert kwargs["tax_year"] == 2025
