"""Conversation CRUD endpoints — tenant-scoped."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import ConversationModel, ConversationMessageModel
from api.auth.dependencies import require_onboarded_user
from api.auth.models import UserModel
from api.models.conversation import (
    ConversationResponse,
    ConversationListResponse,
    ConversationMessageResponse,
    ConversationMessageListResponse,
    SendMessageRequest,
)
from api.routers._helpers import get_client_or_404

router = APIRouter(tags=["conversations"])


async def _get_conversation_or_404(
    conversation_id: str, session: AsyncSession, user: UserModel
) -> ConversationModel:
    """Load a conversation scoped to the user's org, or raise 404."""
    result = await session.execute(
        select(ConversationModel).where(
            ConversationModel.id == conversation_id,
            ConversationModel.org_id == user.org_id,
            ConversationModel.is_active == True,  # noqa: E712
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.post(
    "/api/clients/{client_id}/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    client_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    await get_client_or_404(client_id, session, user)

    conv = ConversationModel(
        client_id=client_id,
        user_id=user.id,
        org_id=user.org_id,
        created_by=user.id,
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


@router.get(
    "/api/clients/{client_id}/conversations",
    response_model=ConversationListResponse,
)
async def list_conversations(
    client_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    await get_client_or_404(client_id, session, user)

    base = select(ConversationModel).where(
        ConversationModel.client_id == client_id,
        ConversationModel.user_id == user.id,
        ConversationModel.org_id == user.org_id,
        ConversationModel.is_active == True,  # noqa: E712
    )

    count_result = await session.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = count_result.scalar() or 0

    paginated = base.order_by(ConversationModel.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await session.execute(paginated)
    items = result.scalars().all()

    return ConversationListResponse(items=items, total=total)


@router.get(
    "/api/conversations/{conversation_id}/messages",
    response_model=ConversationMessageListResponse,
)
async def list_messages(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    conv = await _get_conversation_or_404(conversation_id, session, user)

    result = await session.execute(
        select(ConversationMessageModel)
        .where(
            ConversationMessageModel.conversation_id == conv.id,
            ConversationMessageModel.role.in_(["user", "assistant"]),
        )
        .order_by(ConversationMessageModel.created_at)
    )
    messages = result.scalars().all()

    return ConversationMessageListResponse(
        messages=messages, conversation_id=conv.id
    )


@router.post(
    "/api/conversations/{conversation_id}/messages",
    response_model=ConversationMessageResponse,
)
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    conv = await _get_conversation_or_404(conversation_id, session, user)

    # Persist user message
    user_msg = ConversationMessageModel(
        conversation_id=conv.id,
        role="user",
        content=body.content,
        org_id=user.org_id,
        created_by=user.id,
    )
    session.add(user_msg)

    # Update title from first user message
    existing = await session.execute(
        select(func.count()).where(
            ConversationMessageModel.conversation_id == conv.id,
            ConversationMessageModel.role == "user",
        )
    )
    if (existing.scalar() or 0) == 0:
        conv.title = body.content[:80]

    # Placeholder assistant response (real agent wired in Task 14)
    ai_content = f"[Agent placeholder] Received: {body.content[:100]}"
    ai_msg = ConversationMessageModel(
        conversation_id=conv.id,
        role="assistant",
        content=ai_content,
        org_id=user.org_id,
        created_by=user.id,
    )
    session.add(ai_msg)

    await session.commit()
    await session.refresh(ai_msg)
    return ai_msg


@router.delete(
    "/api/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    conv = await _get_conversation_or_404(conversation_id, session, user)
    conv.is_active = False
    await session.commit()
