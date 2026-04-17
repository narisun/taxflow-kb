"""AgentService — Claude tool-use loop with message persistence."""
from __future__ import annotations
import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from api.agent.session import AgentSession
from api.agent.tool_registry import ToolRegistry
from api.db.models import ClientModel, ConversationMessageModel

if TYPE_CHECKING:
    import anthropic

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are TaxFlow AI, an assistant for CPAs using TaxFlow to prepare tax returns.

CURRENT CONTEXT:
- CPA: {user_name} ({user_email})
- Client: {client_name} — {filing_status}, TY {tax_year}
- Workflow step: {workflow_step}

RULES:
1. Answer ONLY using data returned by your tools. Never fabricate numbers, dollar amounts, or tax figures.
2. All client data you see has PII masked (SSN, DOB, address). Do NOT attempt to reconstruct, guess, or display unmasked PII.
3. You can READ data and ANALYZE it. You CANNOT modify data, approve documents, send emails, or submit returns. If the user asks you to take an action, explain what they need to do in the UI.
4. When referencing specific numbers, state which tool/document they came from (e.g., "per the W-2 from Acme Corp").
5. All your tools are scoped to this client only. You cannot access other clients' data.
6. If you lack data to answer a question, say so and suggest what the user should upload or configure.
7. Keep responses concise and professional. Use markdown formatting for readability."""


class AgentService:
    """Stateless service that runs the Claude tool-use loop."""

    def __init__(self, *, anthropic_client: "anthropic.Anthropic | None", model: str,
                 max_tokens: int, max_tool_rounds: int, history_token_budget: int,
                 tool_registry: ToolRegistry) -> None:
        self._client = anthropic_client
        self._model = model
        self._max_tokens = max_tokens
        self._max_tool_rounds = max_tool_rounds
        self._history_budget = history_token_budget
        self._registry = tool_registry

    async def reply(self, user_message: str, session: AgentSession, history: list[dict]) -> str:
        if self._client is None:
            return "Agent is unavailable — ANTHROPIC_API_KEY not configured."

        system_prompt = await self._build_system_prompt(session)
        messages: list[dict[str, Any]] = [*history, {"role": "user", "content": user_message}]

        for round_num in range(self._max_tool_rounds):
            try:
                response = await asyncio.to_thread(
                    self._client.messages.create,
                    model=self._model, max_tokens=self._max_tokens,
                    system=system_prompt, messages=messages,
                    tools=self._registry.tool_definitions,
                )
            except Exception:
                logger.exception("Claude API call failed (round %d)", round_num)
                return "I encountered an error processing your question. Please try again."

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

        return "I wasn't able to complete the analysis within the allowed steps. Please try a more specific question."

    async def _build_system_prompt(self, session: AgentSession) -> str:
        from api.auth.models import UserModel
        user_result = await session.db_session.execute(
            select(UserModel.name, UserModel.email).where(UserModel.id == session.user_id)
        )
        user_row = user_result.one_or_none()
        client_result = await session.db_session.execute(
            select(ClientModel).where(ClientModel.id == session.client_id, ClientModel.org_id == session.org_id)
        )
        client = client_result.scalar_one_or_none()
        return _SYSTEM_PROMPT.format(
            user_name=user_row.name if user_row else "Unknown",
            user_email=user_row.email if user_row else "",
            client_name=client.name if client else "Unknown",
            filing_status=client.filing_status.upper() if client else "N/A",
            tax_year=client.tax_year if client else "N/A",
            workflow_step=client.workflow_step if client else "N/A",
        )

    async def _persist_tool_call(self, session: AgentSession, block: Any) -> None:
        msg = ConversationMessageModel(
            conversation_id=session.conversation_id, org_id=session.org_id,
            created_by=session.user_id, role="tool_call", content="",
            tool_name=block.name, tool_call_id=block.id,
            tool_input=json.dumps(block.input, default=str),
            token_count=len(json.dumps(block.input, default=str)) // 4,
        )
        session.db_session.add(msg)

    async def _persist_tool_result(self, session: AgentSession, tool_call_id: str,
                                    tool_name: str, result: dict) -> None:
        output = json.dumps(result, default=str)
        msg = ConversationMessageModel(
            conversation_id=session.conversation_id, org_id=session.org_id,
            created_by=session.user_id, role="tool_result", content="",
            tool_name=tool_name, tool_call_id=tool_call_id, tool_output=output,
            token_count=len(output) // 4,
        )
        session.db_session.add(msg)
