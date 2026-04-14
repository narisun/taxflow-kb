"""Chat endpoints — AI-assisted tax Q&A per client."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import ChatMessageModel
from api.auth.dependencies import get_current_user
from api.auth.models import UserModel
from api.models.chat import ChatMessageCreate, ChatMessageResponse, ChatHistoryResponse
from api.routers._helpers import get_client_or_404

router = APIRouter(prefix="/api/clients/{client_id}/chat", tags=["chat"])


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

    # Generate AI response — run sync agent in thread to avoid blocking event loop
    try:
        from tax_brain.factories import create_agent

        def _query_agent(content: str) -> str:
            agent = create_agent()
            result = agent.query(content)
            return result.answer or "I couldn't find relevant information."

        ai_content = await asyncio.to_thread(_query_agent, message.content)
    except Exception:
        ai_content = f"[Mock] I received your question about: {message.content[:100]}"

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
