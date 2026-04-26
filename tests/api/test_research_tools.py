"""Tests for research tool handlers — all taxkb calls mocked."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from api.agent.research_session import ResearchSession


def _make_session() -> ResearchSession:
    return ResearchSession(
        org_id="org-1", user_id="user-1", conversation_id="conv-1",
        db_session=MagicMock(), taxkb_pool=MagicMock(),
    )


class TestFindRelevantPublications:
    @pytest.mark.asyncio
    async def test_returns_publications(self):
        from api.agent.tools.research_tools import find_relevant_publications

        mock_retriever = MagicMock()
        mock_retriever._navigate.return_value = (
            ["590a", "17"],
            [("590a", "Chapter 1: Traditional IRAs"), ("17", "Chapter 5: Deductions")],
            150.0,
        )

        with patch("api.agent.tools.research_tools._get_retriever", return_value=mock_retriever), \
             patch("api.agent.tools.research_tools._expand", side_effect=lambda q: q):
            result = await find_relevant_publications(
                _make_session(), query="IRA contribution limits", tax_year=2025
            )

        assert "publications" in result
        assert len(result["publications"]) == 2
        assert result["publications"][0]["pub_number"] == "590a"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_empty_results(self):
        from api.agent.tools.research_tools import find_relevant_publications

        mock_retriever = MagicMock()
        mock_retriever._navigate.return_value = ([], [], 50.0)

        with patch("api.agent.tools.research_tools._get_retriever", return_value=mock_retriever), \
             patch("api.agent.tools.research_tools._expand", side_effect=lambda q: q):
            result = await find_relevant_publications(_make_session(), query="xyz nothing")

        assert result["publications"] == []
        assert "suggestion" in result


class TestSearchPublicationDetails:
    @pytest.mark.asyncio
    async def test_returns_passages(self):
        from api.agent.tools.research_tools import search_publication_details
        from taxkb.agent.models import RetrievedPassage

        mock_passages = [
            RetrievedPassage(
                title="Contributions to IRAs", text="The maximum contribution is $7,000" + " extra" * 100,
                score=0.92, reference="590a", page=15, chapter="Chapter 1",
                section="Contribution Limits", layer=3,
            ),
        ]
        mock_retriever = MagicMock()
        mock_retriever._search.return_value = (mock_passages, 200.0)

        with patch("api.agent.tools.research_tools._get_retriever", return_value=mock_retriever), \
             patch("api.agent.tools.research_tools._expand", side_effect=lambda q: q):
            result = await search_publication_details(
                _make_session(), query="IRA contribution limits",
                pub_numbers=["590a"], tax_year=2025,
            )

        assert len(result["passages"]) == 1
        assert result["passages"][0]["pub_number"] == "590a"
        assert len(result["passages"][0]["text"]) <= 503  # 500 + "..."

    @pytest.mark.asyncio
    async def test_max_8_passages(self):
        from api.agent.tools.research_tools import search_publication_details
        from taxkb.agent.models import RetrievedPassage

        mock_passages = [
            RetrievedPassage(
                title=f"Passage {i}", text=f"Content {i}", score=0.9 - i * 0.05,
                reference="590a", page=i, layer=3,
            )
            for i in range(15)
        ]
        mock_retriever = MagicMock()
        mock_retriever._search.return_value = (mock_passages, 300.0)

        with patch("api.agent.tools.research_tools._get_retriever", return_value=mock_retriever), \
             patch("api.agent.tools.research_tools._expand", side_effect=lambda q: q):
            result = await search_publication_details(
                _make_session(), query="test", pub_numbers=["590a"],
            )

        assert len(result["passages"]) <= 8


class TestFindCrossReferences:
    @pytest.mark.asyncio
    async def test_returns_related_pubs(self):
        from api.agent.tools.research_tools import find_cross_references

        mock_ontology = MagicMock()
        mock_topic = MagicMock()
        mock_topic.topic_id = "ira-contributions"
        mock_topic.label = "IRA Contributions"
        mock_ontology.find_by_query.return_value = [mock_topic]
        mock_ontology.get_pub_numbers_for_topic.return_value = ["590a", "590b"]

        with patch("api.agent.tools.research_tools._get_ontology", return_value=mock_ontology):
            result = await find_cross_references(
                _make_session(), topic="IRA contributions",
                already_found_pubs=["590a"],
            )

        assert "related_publications" in result
        pub_nums = [p["pub_number"] for p in result["related_publications"]]
        assert "590b" in pub_nums
        assert "590a" not in pub_nums


class TestSearchFormInstructions:
    @pytest.mark.asyncio
    async def test_returns_instructions(self):
        from api.agent.tools.research_tools import search_form_instructions
        from taxkb.agent.models import RetrievedPassage

        mock_passages = [
            RetrievedPassage(
                title="Form 1040 Instructions", text="Line 1a: Enter wages...",
                score=0.95, reference="1040", page=5, layer=2,
                source_type="instruction_section",
            ),
        ]
        mock_searcher = MagicMock()
        mock_searcher.retrieve.return_value = (mock_passages, 80.0)

        with patch("api.agent.tools.research_tools._get_instruction_searcher", return_value=mock_searcher):
            result = await search_form_instructions(
                _make_session(), query="wages line 1a",
                form_number="1040", line_reference="1a",
            )

        assert len(result["instructions"]) == 1


class TestSearchMefRules:
    @pytest.mark.asyncio
    async def test_returns_rules(self):
        from api.agent.tools.research_tools import search_mef_rules
        from taxkb.agent.models import RetrievedPassage

        mock_passages = [
            RetrievedPassage(
                title="MeF Rule", text="If line 1a > 0 then Schedule 1 required",
                score=1.0, reference="F1040", page=0, layer=1,
                source_type="mef_rule",
            ),
        ]
        mock_searcher = MagicMock()
        mock_searcher.retrieve.return_value = (mock_passages, 50.0)

        with patch("api.agent.tools.research_tools._get_rule_searcher", return_value=mock_searcher):
            result = await search_mef_rules(
                _make_session(), query="Schedule 1 attachment",
            )

        assert len(result["rules"]) == 1


class TestCompareTaxYears:
    @pytest.mark.asyncio
    async def test_returns_per_year_passages(self):
        from api.agent.tools.research_tools import compare_tax_years
        from taxkb.agent.models import RetrievedPassage

        mock_passages = [
            RetrievedPassage(
                title="Standard Deduction 2024", text="$14,600 for Single",
                score=0.9, reference="501", page=3, layer=3,
            ),
            RetrievedPassage(
                title="Standard Deduction 2025", text="$15,000 for Single",
                score=0.88, reference="501", page=3, layer=3,
            ),
        ]
        mock_retriever = MagicMock()
        mock_retriever._retrieve_cross_year.return_value = (
            mock_passages, 400.0,
            {"mode": "cross_year_comparison", "nav_pubs": ["501"],
             "ontology_pubs": [], "comparison_years": [2024, 2025]},
        )

        with patch("api.agent.tools.research_tools._get_retriever", return_value=mock_retriever):
            result = await compare_tax_years(
                _make_session(), query="standard deduction", years=[2024, 2025],
            )

        assert "passages" in result
        assert len(result["passages"]) == 2


class TestBuildResearchToolRegistry:
    def test_registers_all_6_tools(self):
        from api.agent.tools.research_tools import build_research_tool_registry

        registry = build_research_tool_registry()
        names = [d["name"] for d in registry.tool_definitions]
        assert "find_relevant_publications" in names
        assert "search_publication_details" in names
        assert "find_cross_references" in names
        assert "search_form_instructions" in names
        assert "search_mef_rules" in names
        assert "compare_tax_years" in names
        assert len(names) == 6
