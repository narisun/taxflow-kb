"""Research Agent endpoints — user-scoped IRS knowledge research."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import ConversationModel, ConversationMessageModel
from api.auth.dependencies import require_onboarded_user
from api.auth.models import UserModel
from api.models.research import (
    ResearchThreadResponse,
    ResearchThreadListResponse,
    ResearchMessageResponse,
    ResearchMessageListResponse,
    SendResearchMessageRequest,
)
from api.agent.research_service import ResearchService
from api.agent.research_session import ResearchSession
from api.dependencies import get_research_service, get_taxkb_pool

router = APIRouter(tags=["research"])


@router.post(
    "/api/research/conversations",
    response_model=ResearchThreadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_research_thread(
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    conv = ConversationModel(
        client_id=None,
        user_id=user.id,
        org_id=user.org_id,
        created_by=user.id,
        conversation_type="research",
        title="New research",
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


@router.get(
    "/api/research/conversations",
    response_model=ResearchThreadListResponse,
)
async def list_research_threads(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    base = select(ConversationModel).where(
        ConversationModel.conversation_type == "research",
        ConversationModel.user_id == user.id,
        ConversationModel.org_id == user.org_id,
        ConversationModel.is_active == True,  # noqa: E712
    )
    count_result = await session.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar() or 0

    paginated = base.order_by(ConversationModel.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await session.execute(paginated)
    items = result.scalars().all()

    return ResearchThreadListResponse(items=items, total=total)


@router.get(
    "/api/research/conversations/{conversation_id}/messages",
    response_model=ResearchMessageListResponse,
)
async def list_research_messages(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    conv = await _get_research_thread_or_404(conversation_id, session, user)

    result = await session.execute(
        select(ConversationMessageModel)
        .where(
            ConversationMessageModel.conversation_id == conv.id,
            ConversationMessageModel.role.in_(["user", "assistant"]),
        )
        .order_by(ConversationMessageModel.created_at)
    )
    messages = result.scalars().all()
    return ResearchMessageListResponse(messages=messages, conversation_id=conv.id)


@router.post("/api/research/conversations/{conversation_id}/messages")
async def send_research_message(
    conversation_id: str,
    body: SendResearchMessageRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
    service: ResearchService = Depends(get_research_service),
    taxkb_pool=Depends(get_taxkb_pool),
):
    conv = await _get_research_thread_or_404(conversation_id, session, user)

    # Auto-set title from first user message
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
        conversation_id=conv.id, role="user", content=body.content,
        org_id=user.org_id, created_by=user.id,
    )
    session.add(user_msg)
    await session.flush()

    # Build research session
    research_session = ResearchSession(
        org_id=user.org_id, user_id=user.id,
        conversation_id=conversation_id,
        db_session=session, taxkb_pool=taxkb_pool,
    )
    history = await _load_history(session, conversation_id, user.org_id)

    async def event_stream():
        full_text = []
        async for event in service.reply_stream(body.content, research_session, history):
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") == "text_delta":
                full_text.append(event["text"])

        # Persist assistant message after stream completes
        ai_msg = ConversationMessageModel(
            conversation_id=conv.id, role="assistant",
            content="".join(full_text),
            org_id=user.org_id, created_by=user.id,
        )
        session.add(ai_msg)
        await session.commit()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.delete(
    "/api/research/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_research_thread(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    conv = await _get_research_thread_or_404(conversation_id, session, user)
    conv.is_active = False
    await session.commit()


async def _get_research_thread_or_404(
    conversation_id: str, session: AsyncSession, user: UserModel,
) -> ConversationModel:
    result = await session.execute(
        select(ConversationModel).where(
            ConversationModel.id == conversation_id,
            ConversationModel.org_id == user.org_id,
            ConversationModel.conversation_type == "research",
            ConversationModel.is_active == True,  # noqa: E712
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Research thread not found")
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
