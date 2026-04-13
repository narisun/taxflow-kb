"""Chat endpoints — AI-assisted tax Q&A per client."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import ClientModel, ChatMessageModel
from api.auth.dependencies import get_current_user
from api.auth.models import UserModel
from api.models.chat import ChatMessageCreate, ChatMessageResponse, ChatHistoryResponse

router = APIRouter(prefix="/api/clients/{client_id}/chat", tags=["chat"])


async def _get_client_or_404(
    client_id: int, session: AsyncSession, user: UserModel
) -> ClientModel:
    result = await session.execute(
        select(ClientModel).where(ClientModel.id == client_id, ClientModel.org_id == user.org_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get("", response_model=ChatHistoryResponse)
async def get_chat_history(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    await _get_client_or_404(client_id, session, user)
    result = await session.execute(
        select(ChatMessageModel)
        .where(ChatMessageModel.client_id == client_id)
        .order_by(ChatMessageModel.created_at)
    )
    messages = result.scalars().all()
    return ChatHistoryResponse(messages=messages, client_id=client_id)


@router.post("", response_model=ChatMessageResponse)
async def send_message(
    client_id: int,
    message: ChatMessageCreate,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    await _get_client_or_404(client_id, session, user)

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

    # Generate AI response
    try:
        from tax_brain.factories import create_agent

        agent = create_agent()
        result = agent.query(message.content)
        ai_content = result.answer or "I couldn't find relevant information."
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
