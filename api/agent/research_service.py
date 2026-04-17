"""ResearchService — Claude tool-use loop for IRS knowledge research.

User-scoped (no client data). Supports both non-streaming reply() and
streaming reply_stream() that yields SSE events."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, AsyncGenerator

from api.agent.research_session import ResearchSession
from api.agent.tool_registry import ToolRegistry
from api.db.models import ConversationMessageModel

if TYPE_CHECKING:
    import anthropic

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are TaxFlow Research, an IRS tax research assistant for CPA professionals.
You have access to the IRS knowledge base covering publications, form
instructions, and MeF validation rules.

RESEARCH STRATEGY:
- For general tax questions: use find_relevant_publications first to identify
  which IRS publications apply, then search_publication_details to get specific
  rules from those publications. Use find_cross_references if the topic might
  span multiple publications.
- For form/line questions: use search_form_instructions directly.
- For e-file/validation questions: use search_mef_rules directly.
- For year-over-year comparisons: use compare_tax_years with the specific years.
- If initial results are insufficient, refine your search query and try again
  with different terms or a broader scope.

FALLBACK BEHAVIOR:
- If tools return no results or errors (e.g., knowledge base unavailable), you
  MUST still answer the question using your own knowledge of tax law.
- Clearly state that the answer is from your general knowledge and not verified
  against the IRS knowledge base.
- Prefix such answers with: "**Note:** The IRS knowledge base is currently
  unavailable. The following is based on general tax knowledge and should be
  verified against official IRS sources."
- Never return an empty response. Always provide a helpful answer.

CITATION RULES:
- When citing from the knowledge base, cite the IRS publication number,
  chapter/section, and page when available.
- When stating dollar amounts, thresholds, or percentages from the knowledge
  base, cite the exact source.
- When answering from general knowledge (fallback), note that figures should
  be verified against current IRS publications.

FORMAT:
- Use markdown formatting for readability.
- Bold key figures, thresholds, and important terms.
- Structure complex answers with headers for complex topics.
- End with a "Sources" section listing all cited IRS publications."""

_TOOL_DESCRIPTIONS = {
    "find_relevant_publications": "Searching for relevant IRS publications",
    "search_publication_details": "Searching publication details",
    "find_cross_references": "Checking cross-references",
    "search_form_instructions": "Searching form instructions",
    "search_mef_rules": "Searching MeF validation rules",
    "compare_tax_years": "Comparing across tax years",
}


class ResearchService:
    """Stateless service that runs the Claude tool-use loop for research."""

    def __init__(self, *, anthropic_client: "anthropic.Anthropic | None", model: str,
                 max_tokens: int, max_tool_rounds: int,
                 tool_registry: ToolRegistry) -> None:
        self._client = anthropic_client
        self._model = model
        self._max_tokens = max_tokens
        self._max_tool_rounds = max_tool_rounds
        self._registry = tool_registry

    async def reply(self, user_message: str, session: ResearchSession,
                    history: list[dict]) -> str:
        """Non-streaming reply — returns final answer text."""
        if self._client is None:
            return "Research agent is unavailable — ANTHROPIC_API_KEY not configured."

        messages: list[dict[str, Any]] = [*history, {"role": "user", "content": user_message}]

        for round_num in range(self._max_tool_rounds):
            try:
                response = await asyncio.to_thread(
                    self._client.messages.create,
                    model=self._model, max_tokens=self._max_tokens,
                    system=_SYSTEM_PROMPT, messages=messages,
                    tools=self._registry.tool_definitions,
                )
            except Exception:
                logger.exception("Claude API call failed (round %d)", round_num)
                return "I encountered an error processing your research query. Please try again."

            if response.stop_reason == "end_turn":
                text_blocks = [b.text for b in response.content if hasattr(b, "text")]
                return "\n".join(text_blocks) or "I couldn't generate a response."

            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    result = await self._registry.execute(block.name, block.input, session)
                    await self._persist_tool_call(session, block)
                    await self._persist_tool_result(session, block.id, block.name, result)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        return "I wasn't able to complete the research within the allowed steps. Please try a more specific question."

    async def reply_stream(self, user_message: str, session: ResearchSession,
                           history: list[dict]) -> AsyncGenerator[dict, None]:
        """Streaming reply — yields SSE event dicts."""
        if self._client is None:
            yield {"type": "error", "message": "Research agent unavailable — ANTHROPIC_API_KEY not configured."}
            return

        messages: list[dict[str, Any]] = [*history, {"role": "user", "content": user_message}]

        for round_num in range(self._max_tool_rounds):
            try:
                response = await asyncio.to_thread(
                    self._client.messages.create,
                    model=self._model, max_tokens=self._max_tokens,
                    system=_SYSTEM_PROMPT, messages=messages,
                    tools=self._registry.tool_definitions,
                )
            except Exception:
                logger.exception("Claude API call failed (round %d)", round_num)
                yield {"type": "error", "message": "Research query failed. Please try again."}
                return

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        yield {"type": "text_delta", "text": block.text}
                yield {"type": "done"}
                return

            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    desc = _TOOL_DESCRIPTIONS.get(block.name, f"Running {block.name}")
                    yield {"type": "step_start", "tool": block.name, "description": desc}

                    result = await self._registry.execute(block.name, block.input, session)
                    await self._persist_tool_call(session, block)
                    await self._persist_tool_result(session, block.id, block.name, result)

                    summary = self._summarize_tool_result(block.name, result)
                    yield {"type": "step_complete", "tool": block.name, "summary": summary}

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        yield {"type": "error", "message": "Research could not complete within allowed steps."}

    def _summarize_tool_result(self, tool_name: str, result: dict) -> str:
        """Create a short human-readable summary of a tool result."""
        if "error" in result:
            return f"Error: {result['error']}"
        if tool_name == "find_relevant_publications":
            count = len(result.get("publications", []))
            pubs = ", ".join(p["pub_number"] for p in result.get("publications", [])[:3])
            return f"Found {count} publications: {pubs}" if pubs else "No publications found"
        if tool_name == "search_publication_details":
            count = result.get("total_found", len(result.get("passages", [])))
            return f"Found {count} passages"
        if tool_name == "find_cross_references":
            count = len(result.get("related_publications", []))
            return f"Found {count} related publications"
        if tool_name == "search_form_instructions":
            count = len(result.get("instructions", []))
            return f"Found {count} instruction sections"
        if tool_name == "search_mef_rules":
            count = len(result.get("rules", []))
            return f"Found {count} rules"
        if tool_name == "compare_tax_years":
            years = result.get("years", [])
            return f"Compared {len(years)} tax years"
        return "Done"

    async def _persist_tool_call(self, session: ResearchSession, block: Any) -> None:
        msg = ConversationMessageModel(
            conversation_id=session.conversation_id, org_id=session.org_id,
            created_by=session.user_id, role="tool_call", content="",
            tool_name=block.name, tool_call_id=block.id,
            tool_input=json.dumps(block.input, default=str),
            token_count=len(json.dumps(block.input, default=str)) // 4,
        )
        session.db_session.add(msg)

    async def _persist_tool_result(self, session: ResearchSession, tool_call_id: str,
                                    tool_name: str, result: dict) -> None:
        output = json.dumps(result, default=str)
        msg = ConversationMessageModel(
            conversation_id=session.conversation_id, org_id=session.org_id,
            created_by=session.user_id, role="tool_result", content="",
            tool_name=tool_name, tool_call_id=tool_call_id, tool_output=output,
            token_count=len(output) // 4,
        )
        session.db_session.add(msg)
