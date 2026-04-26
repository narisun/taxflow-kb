"""ChatService — AI-assisted tax Q&A for a specific client.

The router (``api.routers.chat``) is thin: it only handles HTTP concerns and
delegates to this service. The service knows nothing about FastAPI.

Design notes:
- The Anthropic client is injected, so tests pass a fake. When the client is
  ``None`` (no API key), :meth:`reply` returns a deterministic unavailable
  message rather than raising.
- Context-building is pure, so it can be unit-tested without mocking Claude.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.models import UserModel
from api.db.models import (
    ChatMessageModel,
    ClientModel,
    DocumentModel,
    TaxReturnDraftModel,
)

if TYPE_CHECKING:
    import anthropic

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT_TEMPLATE = """\
You are a tax assistant AI embedded in a CPA tax preparation platform called TaxFlow AI.
You help CPAs with tax questions, return preparation, and client advisory.

You have access to the following client data:

{client_context}

Guidelines:
- Answer tax questions accurately based on the client's data
- Reference specific numbers from the client's documents and computed return when relevant
- If the client's return has been computed, reference the actual tax amounts
- Suggest next steps in the workflow (e.g., "upload remaining documents", "run validation", "generate PDF")
- Keep answers concise and professional
- If you don't have enough data to answer, say so and suggest what's needed
- Never make up numbers — only reference data shown above"""


class ChatService:
    """Stateless service for client-scoped LLM chat."""

    def __init__(
        self,
        *,
        anthropic_client: "anthropic.Anthropic | None",
        model: str,
        max_tokens: int,
        history_window: int = 10,
    ) -> None:
        self._client = anthropic_client
        self._model = model
        self._max_tokens = max_tokens
        self._history_window = history_window

    # ------------------------------------------------------------------ public API

    async def reply(
        self,
        *,
        client_id: str,
        session: AsyncSession,
        user: UserModel,
        user_message: str,
    ) -> str:
        """Generate an assistant response for ``user_message`` within client scope."""
        if self._client is None:
            return "Chat is unavailable — ANTHROPIC_API_KEY not configured."

        context = await self.build_client_context(client_id, session, user)
        history = await self.get_chat_history_context(client_id, session, user.org_id)
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(client_context=context)

        try:
            return await asyncio.to_thread(
                self._query_claude, system_prompt, history, user_message
            )
        except Exception:
            logger.exception("Claude chat request failed for client_id=%s", client_id)
            return (
                "I encountered an error processing your question. "
                "Please try again, or contact support if this persists."
            )

    # ------------------------------------------------------------------ helpers

    async def build_client_context(
        self,
        client_id: str,
        session: AsyncSession,
        user: UserModel,
    ) -> str:
        """Render a string summary of the client's tax situation for Claude."""
        result = await session.execute(
            select(ClientModel).where(
                ClientModel.id == client_id,
                ClientModel.org_id == user.org_id,
            )
        )
        client = result.scalar_one_or_none()
        if not client:
            return "No client data available."

        parts: list[str] = [
            f"Client: {client.name}",
            f"Filing status: {client.filing_status}",
            f"Tax year: {client.tax_year}",
            f"Dependents: {client.dependents}",
            f"Workflow step: {client.workflow_step}",
        ]

        doc_result = await session.execute(
            select(DocumentModel).where(
                DocumentModel.client_id == client_id,
                DocumentModel.org_id == user.org_id,
            )
        )
        docs = doc_result.scalars().all()
        if docs:
            parts.append(f"\nDocuments ({len(docs)}):")
            for doc in docs:
                parts.append(
                    f"  - {doc.form_type}: status={doc.status}, confidence={doc.confidence}"
                )
                if doc.status == "approved" and doc.extracted_data:
                    try:
                        data = json.loads(doc.extracted_data)
                    except (json.JSONDecodeError, TypeError):
                        logger.debug(
                            "Skipping malformed extracted_data for doc_id=%s", doc.id
                        )
                        continue
                    if isinstance(data, dict):
                        for k, v in data.items():
                            parts.append(f"    {k}: {v}")

        draft_result = await session.execute(
            select(TaxReturnDraftModel).where(
                TaxReturnDraftModel.client_id == client_id,
                TaxReturnDraftModel.org_id == user.org_id,
            )
        )
        draft = draft_result.scalar_one_or_none()
        if draft and draft.draft_json:
            try:
                draft_data = json.loads(draft.draft_json)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "Malformed draft_json for client_id=%s (ignored)", client_id
                )
                draft_data = None
            if draft_data:
                parts.append("\nComputed Tax Return:")
                parts.append(
                    f"  Total income: ${draft_data.get('total_income', 0):,.2f}"
                )
                parts.append(
                    f"  Taxable income: ${draft_data.get('taxable_income', 0):,.2f}"
                )
                parts.append(f"  Total tax: ${draft_data.get('total_tax', 0):,.2f}")
                parts.append(
                    f"  Total payments: ${draft_data.get('total_payments', 0):,.2f}"
                )
                parts.append(
                    f"  Refund/owed: ${draft_data.get('refund_or_owed', 0):,.2f}"
                )
                parts.append(
                    f"  Effective rate: {draft_data.get('effective_rate', 0)}%"
                )

        return "\n".join(parts)

    async def get_chat_history_context(
        self,
        client_id: str,
        session: AsyncSession,
        org_id: str,
    ) -> list[dict]:
        """Return the last N messages for a client in chronological order."""
        result = await session.execute(
            select(ChatMessageModel)
            .where(
                ChatMessageModel.client_id == client_id,
                ChatMessageModel.org_id == org_id,
            )
            .order_by(ChatMessageModel.created_at.desc())
            .limit(self._history_window)
        )
        messages = list(reversed(result.scalars().all()))
        return [{"role": m.role, "content": m.content} for m in messages]

    # ------------------------------------------------------------------ sync bridge

    def _query_claude(
        self,
        system_prompt: str,
        history: list[dict],
        user_message: str,
    ) -> str:
        """Call the Anthropic SDK. Runs inside ``asyncio.to_thread``."""
        assert self._client is not None  # guarded by caller
        claude_messages = [
            {"role": m["role"], "content": m["content"]} for m in history
        ]
        claude_messages.append({"role": "user", "content": user_message})

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=claude_messages,
        )
        return (
            response.content[0].text
            if response.content
            else "I couldn't generate a response."
        )
