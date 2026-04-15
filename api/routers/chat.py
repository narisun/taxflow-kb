"""Chat endpoints — AI-assisted tax Q&A per client using Claude."""
import asyncio
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import ChatMessageModel, ClientModel, DocumentModel
from api.auth.dependencies import get_current_user
from api.auth.models import UserModel
from api.models.chat import ChatMessageCreate, ChatMessageResponse, ChatHistoryResponse
from api.routers._helpers import get_client_or_404

router = APIRouter(prefix="/api/clients/{client_id}/chat", tags=["chat"])


async def _build_client_context(client_id: int, session: AsyncSession, user: UserModel) -> str:
    """Build context about the client's tax situation for Claude."""
    # Load client
    result = await session.execute(
        select(ClientModel).where(ClientModel.id == client_id, ClientModel.org_id == user.org_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        return "No client data available."

    context_parts = [
        f"Client: {client.name}",
        f"Filing status: {client.filing_status}",
        f"Tax year: {client.tax_year}",
        f"Dependents: {client.dependents}",
        f"Workflow step: {client.workflow_step}",
    ]

    # Load documents
    doc_result = await session.execute(
        select(DocumentModel).where(
            DocumentModel.client_id == client_id,
            DocumentModel.org_id == user.org_id,
        )
    )
    docs = doc_result.scalars().all()
    if docs:
        context_parts.append(f"\nDocuments ({len(docs)}):")
        for doc in docs:
            context_parts.append(f"  - {doc.form_type}: status={doc.status}, confidence={doc.confidence}")
            if doc.status == "approved" and doc.extracted_data:
                try:
                    data = json.loads(doc.extracted_data)
                    if isinstance(data, dict):
                        for k, v in data.items():
                            context_parts.append(f"    {k}: {v}")
                except (json.JSONDecodeError, TypeError):
                    pass

    # Try to load draft if exists
    from api.db.models import TaxReturnDraftModel
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
            context_parts.append(f"\nComputed Tax Return:")
            context_parts.append(f"  Total income: ${draft_data.get('total_income', 0):,.2f}")
            context_parts.append(f"  Taxable income: ${draft_data.get('taxable_income', 0):,.2f}")
            context_parts.append(f"  Total tax: ${draft_data.get('total_tax', 0):,.2f}")
            context_parts.append(f"  Total payments: ${draft_data.get('total_payments', 0):,.2f}")
            context_parts.append(f"  Refund/owed: ${draft_data.get('refund_or_owed', 0):,.2f}")
            context_parts.append(f"  Effective rate: {draft_data.get('effective_rate', 0)}%")
        except (json.JSONDecodeError, TypeError):
            pass

    return "\n".join(context_parts)


async def _get_chat_history_context(client_id: int, session: AsyncSession, org_id: str, limit: int = 10) -> list[dict]:
    """Get recent chat messages for conversation context."""
    result = await session.execute(
        select(ChatMessageModel)
        .where(ChatMessageModel.client_id == client_id, ChatMessageModel.org_id == org_id)
        .order_by(ChatMessageModel.created_at.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": msg.role, "content": msg.content} for msg in messages]


def _query_claude(system_prompt: str, messages: list[dict], user_message: str) -> str:
    """Call Claude API synchronously (run in thread)."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return "Chat is unavailable — ANTHROPIC_API_KEY not configured."

    client = anthropic.Anthropic(api_key=api_key)

    # Build conversation for Claude
    claude_messages = []
    for msg in messages:
        claude_messages.append({"role": msg["role"], "content": msg["content"]})
    claude_messages.append({"role": "user", "content": user_message})

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=system_prompt,
        messages=claude_messages,
    )

    return response.content[0].text if response.content else "I couldn't generate a response."


@router.get("", response_model=ChatHistoryResponse)
async def get_chat_history(
    client_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    await get_client_or_404(client_id, session, user)
    base = (
        select(ChatMessageModel)
        .where(
            ChatMessageModel.client_id == client_id,
            ChatMessageModel.org_id == user.org_id,
        )
        .order_by(ChatMessageModel.created_at)
    )
    count_q = select(func.count()).select_from(base.subquery())
    count_result = await session.execute(count_q)
    total = count_result.scalar() or 0

    paginated = base.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(paginated)
    messages = result.scalars().all()
    return ChatHistoryResponse(
        messages=messages, client_id=client_id, page=page, page_size=page_size,
    )


@router.post("", response_model=ChatMessageResponse)
async def send_message(
    client_id: int,
    message: ChatMessageCreate,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    await get_client_or_404(client_id, session, user)

    # Persist user message
    user_msg = ChatMessageModel(
        client_id=client_id,
        role="user",
        content=message.content,
        org_id=user.org_id,
        created_by=user.id,
    )
    session.add(user_msg)
    await session.flush()

    # Build client context and chat history
    client_context = await _build_client_context(client_id, session, user)
    chat_history = await _get_chat_history_context(client_id, session, user.org_id)

    system_prompt = f"""You are a tax assistant AI embedded in a CPA tax preparation platform called TaxFlow AI.
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

    # Call Claude API
    try:
        ai_content = await asyncio.to_thread(
            _query_claude, system_prompt, chat_history, message.content
        )
    except Exception as e:
        ai_content = f"I encountered an error processing your question. Please try again. ({type(e).__name__})"

    ai_msg = ChatMessageModel(
        client_id=client_id,
        role="assistant",
        content=ai_content,
        org_id=user.org_id,
        created_by=user.id,
    )
    session.add(ai_msg)
    await session.commit()
    await session.refresh(ai_msg)
    return ai_msg
