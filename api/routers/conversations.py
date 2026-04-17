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
from api.agent.service import AgentService
from api.agent.session import AgentSession
from api.dependencies import get_agent_service, get_pii_encryptor_dep
from api.services.pii.encryptor import PIIEncryptor

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
    agent: AgentService = Depends(get_agent_service),
    encryptor: PIIEncryptor = Depends(get_pii_encryptor_dep),
):
    conv = await _get_conversation_or_404(conversation_id, session, user)

    # Update title from first user message (check before adding the new one
    # so the autoflush doesn't inflate the count).
    existing = await session.execute(
        select(func.count()).where(
            ConversationMessageModel.conversation_id == conv.id,
            ConversationMessageModel.role == "user",
        )
    )
    if (existing.scalar() or 0) == 0:
        conv.title = body.content[:80]

    # Persist user message
    user_msg = ConversationMessageModel(
        conversation_id=conv.id,
        role="user",
        content=body.content,
        org_id=user.org_id,
        created_by=user.id,
    )
    session.add(user_msg)
    await session.flush()

    # Build agent session and load history
    agent_session = AgentSession(
        org_id=user.org_id,
        client_id=conv.client_id,
        user_id=user.id,
        conversation_id=conversation_id,
        db_session=session,
        pii_encryptor=encryptor,
    )
    history = await _load_history(session, conversation_id, user.org_id)

    # Call agent
    ai_content = await agent.reply(
        user_message=body.content, session=agent_session, history=history,
    )

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


async def _load_history(
    session: AsyncSession, conversation_id: str, org_id: str, max_chars: int = 32000,
) -> list[dict]:
    """Load conversation history up to token budget. Tool calls from prior turns
    are compressed to save tokens."""
    result = await session.execute(
        select(ConversationMessageModel)
        .where(
            ConversationMessageModel.conversation_id == conversation_id,
            ConversationMessageModel.org_id == org_id,
        )
        .order_by(ConversationMessageModel.created_at.desc())
    )
    all_msgs = result.scalars().all()
    budget = max_chars
    selected = []
    for msg in all_msgs:
        if msg.role in ("user", "assistant"):
            text = msg.content or ""
        elif msg.role == "tool_call":
            text = f"[Used tool: {msg.tool_name}]"
        elif msg.role == "tool_result":
            text = f"[Tool {msg.tool_name} returned data]"
        else:
            continue
        cost = len(text)
        if budget - cost < 0:
            break
        budget -= cost
        selected.append({"role": msg.role if msg.role in ("user", "assistant") else "assistant", "content": text})
    selected.reverse()
    return selected


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
