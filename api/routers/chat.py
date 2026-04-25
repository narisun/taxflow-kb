"""Chat endpoints — unified on AgentService with tool-use."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.agent.service import AgentService
from api.agent.session import AgentSession
from api.auth.dependencies import require_onboarded_user
from api.auth.models import UserModel
from api.db.engine import get_session
from api.db.models import ChatMessageModel, ConversationModel, ConversationMessageModel
from api.dependencies import get_agent_service, get_pii_encryptor_dep
from api.models.chat import ChatHistoryResponse, ChatMessageCreate, ChatMessageResponse
from api.routers._helpers import get_client_or_404
from api.services.pii.encryptor import PIIEncryptor

router = APIRouter(prefix="/api/clients/{client_id}/chat", tags=["chat"])


@router.get("", response_model=ChatHistoryResponse)
async def get_chat_history(
    client_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
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
    total = count_result.scalar() or 0  # noqa: F841

    paginated = base.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(paginated)
    messages = result.scalars().all()
    return ChatHistoryResponse(
        messages=messages, client_id=client_id, page=page, page_size=page_size,
    )


@router.post("", response_model=ChatMessageResponse)
async def send_message(
    client_id: str,
    message: ChatMessageCreate,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
    agent: AgentService = Depends(get_agent_service),
    encryptor: PIIEncryptor = Depends(get_pii_encryptor_dep),
):
    """Send a user message through the AgentService tool-use loop."""
    await get_client_or_404(client_id, session, user)

    # Auto-create or resume a conversation for this client
    conv = await _get_or_create_conversation(session, client_id, user)

    # Build agent session
    agent_session = AgentSession(
        org_id=user.org_id,
        client_id=client_id,
        user_id=user.id,
        conversation_id=conv.id,
        db_session=session,
        pii_encryptor=encryptor,
    )

    # Load conversation history for context
    history = await _load_history(session, conv.id, user.org_id)

    # Get agent reply (tool-use loop)
    ai_content = await agent.reply(
        user_message=message.content,
        session=agent_session,
        history=history,
    )

    # Persist user message (after reply to avoid double-counting in history)
    user_msg = ChatMessageModel(
        client_id=client_id,
        role="user",
        content=message.content,
        org_id=user.org_id,
        created_by=user.id,
    )
    session.add(user_msg)
    await session.flush()

    # Persist assistant message
    ai_msg = ChatMessageModel(
        client_id=client_id,
        role="assistant",
        content=ai_content,
        org_id=user.org_id,
        created_by=user.id,
    )
    session.add(ai_msg)

    # Also persist to conversation messages for agent history
    conv_user_msg = ConversationMessageModel(
        conversation_id=conv.id, role="user", content=message.content,
        org_id=user.org_id, created_by=user.id,
    )
    conv_ai_msg = ConversationMessageModel(
        conversation_id=conv.id, role="assistant", content=ai_content,
        org_id=user.org_id, created_by=user.id,
    )
    session.add(conv_user_msg)
    session.add(conv_ai_msg)

    await session.commit()
    await session.refresh(ai_msg)
    return ai_msg


async def _get_or_create_conversation(
    session: AsyncSession, client_id: str, user: UserModel,
) -> ConversationModel:
    """Get or create a single conversation per client for chat."""
    result = await session.execute(
        select(ConversationModel).where(
            ConversationModel.client_id == client_id,
            ConversationModel.user_id == user.id,
            ConversationModel.org_id == user.org_id,
            ConversationModel.conversation_type == "client",
            ConversationModel.is_active == True,  # noqa: E712
        ).order_by(ConversationModel.created_at.desc()).limit(1)
    )
    conv = result.scalar_one_or_none()
    if conv:
        return conv

    conv = ConversationModel(
        client_id=client_id,
        user_id=user.id,
        org_id=user.org_id,
        created_by=user.id,
        conversation_type="client",
        title="Client chat",
    )
    session.add(conv)
    await session.flush()
    return conv


async def _load_history(
    session: AsyncSession, conversation_id: str, org_id: str, max_chars: int = 32000,
) -> list[dict]:
    """Load conversation history up to token budget."""
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
