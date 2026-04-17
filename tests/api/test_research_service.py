"""Tests for ResearchService — Claude tool-use loop with streaming."""
from __future__ import annotations
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestResearchServiceReply:
    """Test the non-streaming reply() method."""

    @pytest.mark.asyncio
    async def test_returns_text_on_end_turn(self):
        from api.agent.research_service import ResearchService
        from api.agent.research_session import ResearchSession

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_text_block = MagicMock()
        mock_text_block.text = "The standard deduction for 2025 is $15,000."
        mock_text_block.type = "text"
        mock_response.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_response

        service = ResearchService(
            anthropic_client=mock_client, model="claude-sonnet-4-20250514",
            max_tokens=4096, max_tool_rounds=10,
            tool_registry=MagicMock(tool_definitions=[]),
        )

        session = ResearchSession(
            org_id="org-1", user_id="user-1", conversation_id="conv-1",
            db_session=MagicMock(), tax_brain_pool=MagicMock(),
        )

        result = await service.reply("What is the standard deduction?", session, [])
        assert "15,000" in result

    @pytest.mark.asyncio
    async def test_returns_fallback_when_no_client(self):
        from api.agent.research_service import ResearchService

        service = ResearchService(
            anthropic_client=None, model="test", max_tokens=100,
            max_tool_rounds=10, tool_registry=MagicMock(tool_definitions=[]),
        )
        session = MagicMock()
        result = await service.reply("test", session, [])
        assert "unavailable" in result.lower()

    @pytest.mark.asyncio
    async def test_executes_tool_and_loops(self):
        from api.agent.research_service import ResearchService
        from api.agent.research_session import ResearchSession

        mock_client = MagicMock()

        # Round 1: tool_use
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "find_relevant_publications"
        tool_block.id = "tool-1"
        tool_block.input = {"query": "IRA limits"}
        round1_response = MagicMock()
        round1_response.stop_reason = "tool_use"
        round1_response.content = [tool_block]

        # Round 2: end_turn
        text_block = MagicMock()
        text_block.text = "IRA contribution limit is $7,000."
        text_block.type = "text"
        round2_response = MagicMock()
        round2_response.stop_reason = "end_turn"
        round2_response.content = [text_block]

        mock_client.messages.create.side_effect = [round1_response, round2_response]

        mock_registry = MagicMock()
        mock_registry.tool_definitions = []
        mock_registry.execute = AsyncMock(return_value={"publications": [{"pub_number": "590a"}]})

        service = ResearchService(
            anthropic_client=mock_client, model="test", max_tokens=4096,
            max_tool_rounds=10, tool_registry=mock_registry,
        )
        session = ResearchSession(
            org_id="org-1", user_id="user-1", conversation_id="conv-1",
            db_session=MagicMock(), tax_brain_pool=MagicMock(),
        )

        result = await service.reply("IRA limits?", session, [])
        assert "7,000" in result
        mock_registry.execute.assert_called_once()
