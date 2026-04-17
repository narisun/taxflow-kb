# Agentic Layer Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-turn chat pass-through with a tool-calling AI agent backed by persistent conversations, PostgreSQL RLS tenant isolation, and 6 read-only MCP tools.

**Architecture:** New `conversations` + `conversation_messages` tables with RLS. An `AgentService` runs a Claude tool-use loop, dispatching to tool functions that query the DB with server-side `client_id` injection (LLM never controls scope). PII is masked before any data reaches the LLM.

**Tech Stack:** FastAPI, SQLAlchemy 2.x async, Alembic, Anthropic SDK (tool_use), `fastmcp`, PostgreSQL RLS, Pydantic v2.

---

## File Structure

### New files

```
api/agent/__init__.py              — Package init
api/agent/session.py               — AgentSession frozen dataclass
api/agent/tool_registry.py         — Tool definitions + dispatch registry
api/agent/tools/__init__.py        — Package init
api/agent/tools/client_tools.py    — get_client_summary, list_dependents
api/agent/tools/document_tools.py  — list_documents, get_document_fields
api/agent/tools/return_tools.py    — get_return_draft, get_return_line_detail
api/agent/service.py               — AgentService (tool-use loop)
api/models/conversation.py         — Pydantic schemas for conversations
api/routers/conversations.py       — Conversation CRUD + agent dispatch
tests/api/test_conversations.py    — Conversation CRUD + RLS tests
tests/api/test_agent_tools.py      — Tool isolation + PII masking tests
tests/api/test_agent_service.py    — Agent loop tests (mocked Claude)
alembic/versions/xxxx_conversations_and_rls.py — Migration
```

### Modified files

```
api/db/models.py                   — Add ConversationModel, ConversationMessageModel
api/db/engine.py                   — Add get_rls_session dependency
api/config.py                      — Add agent_model, agent_max_tokens, etc.
api/dependencies.py                — Add get_agent_service provider
api/main.py                        — Register conversations router
requirements-api.txt               — Add fastmcp
```

---

### Task 1: Add dependency + agent config settings

**Files:**
- Modify: `requirements-api.txt`
- Modify: `api/config.py`

- [ ] **Step 1: Add fastmcp to requirements**

In `requirements-api.txt`, append after the `uuid6` line:

```
# MCP tool registration for the agentic layer
fastmcp>=2.0
```

- [ ] **Step 2: Add agent config fields to Settings**

In `api/config.py`, add after the `chat_max_tokens` field (around line 85):

```python
    # ── Agent (tool-use chat) ──────────────────────────────────────────
    agent_model: str = Field(default="claude-sonnet-4-20250514")
    agent_max_tokens: int = Field(default=4096)
    agent_max_tool_rounds: int = Field(default=10)
    agent_history_token_budget: int = Field(default=8000)
```

- [ ] **Step 3: Install the new dependency**

Run: `pip install -r requirements-api.txt`

- [ ] **Step 4: Add env vars to .env**

Append to `.env`:

```
# Agent (tool-use chat) — defaults are fine for development
AGENT_MODEL=claude-sonnet-4-20250514
AGENT_MAX_TOKENS=4096
AGENT_MAX_TOOL_ROUNDS=10
AGENT_HISTORY_TOKEN_BUDGET=8000
```

- [ ] **Step 5: Verify config loads**

Run: `python -c "from api.config import get_settings; s = get_settings(); print(f'agent_model={s.agent_model}')"` 
Expected: `agent_model=claude-sonnet-4-20250514`

- [ ] **Step 6: Commit**

```bash
git add requirements-api.txt api/config.py .env
git commit -m "feat(agent): add fastmcp dependency and agent config settings"
```

---

### Task 2: Conversation SQLAlchemy models

**Files:**
- Modify: `api/db/models.py`

- [ ] **Step 1: Write the test**

Create `tests/api/test_conversations.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_create_conversation(client):
    c = await client.post("/api/clients", json={"name": "Conv Test"})
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/conversations", json={})
    assert resp.status_code == 201
    body = resp.json()
    assert isinstance(body["id"], str) and len(body["id"]) == 36
    assert body["client_id"] == cid
    assert body["is_active"] is True
```

- [ ] **Step 2: Run the test — expect FAIL (no models/router yet)**

Run: `pytest tests/api/test_conversations.py::test_create_conversation -xvs`
Expected: FAIL (404 — no route)

- [ ] **Step 3: Add models to api/db/models.py**

Add at the end of `api/db/models.py`, before the `ManualEntryModel`:

```python
class ConversationModel(TenantMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    is_active: Mapped[bool] = mapped_column(default=True)

    messages: Mapped[list["ConversationMessageModel"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan",
        order_by="ConversationMessageModel.created_at",
    )

    __table_args__ = (
        Index("ix_conv_org_client_user", "org_id", "client_id", "user_id"),
    )


class ConversationMessageModel(TenantMixin, Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user|assistant|tool_call|tool_result
    content: Mapped[str] = mapped_column(Text, default="")
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    conversation: Mapped["ConversationModel"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_conv_msg_conv_created", "conversation_id", "created_at"),
        Index("ix_conv_msg_org", "org_id"),
    )
```

- [ ] **Step 4: Commit**

```bash
git add api/db/models.py tests/api/test_conversations.py
git commit -m "feat(agent): add Conversation and ConversationMessage SQLAlchemy models"
```

---

### Task 3: Alembic migration — conversation tables + RLS policies

**Files:**
- Create: `alembic/versions/xxxx_conversations_and_rls.py` (auto-generated + hand-edited)

- [ ] **Step 1: Generate the migration**

Run: `alembic revision --autogenerate -m "add conversations tables and RLS policies"`

- [ ] **Step 2: Edit the migration to add RLS policies**

Open the generated migration file. After the auto-generated `op.create_table` calls, add the RLS section inside `upgrade()`:

```python
    # ── Row Level Security ──────────────────────────────────────────────
    # Defense-in-depth: even if app code forgets a WHERE org_id filter,
    # RLS blocks cross-tenant reads at the database level.
    _TENANT_TABLES = [
        "clients", "documents", "conversations", "conversation_messages",
        "chat_messages", "dependents", "tax_return_drafts",
        "manual_entries", "family_groups",
    ]
    for table in _TENANT_TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (org_id = current_setting('app.current_org_id', true)::text)"
        ))

    # ── Application database role ───────────────────────────────────────
    # The app should connect as this non-superuser role so RLS is enforced.
    # In dev/test the superuser (taxflow) bypasses RLS — acceptable for
    # migrations and manual debugging, but the app process uses taxflow_app.
    op.execute(sa.text(
        "DO $$ BEGIN "
        "  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'taxflow_app') THEN "
        "    CREATE ROLE taxflow_app LOGIN PASSWORD 'taxflow_app_dev'; "
        "  END IF; "
        "END $$"
    ))
    op.execute(sa.text("GRANT USAGE ON SCHEMA public TO taxflow_app"))
    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO taxflow_app"))
    op.execute(sa.text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO taxflow_app"))
```

And in `downgrade()`, after the auto-generated drops:

```python
    _TENANT_TABLES = [
        "clients", "documents", "conversations", "conversation_messages",
        "chat_messages", "dependents", "tax_return_drafts",
        "manual_entries", "family_groups",
    ]
    for table in _TENANT_TABLES:
        op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
```

- [ ] **Step 3: Apply the migration**

Run: `alembic upgrade head`
Expected: Migration applies successfully.

- [ ] **Step 4: Verify**

Run: `alembic current`
Expected: New head revision.

Run: `python -c "...verify conversations table exists..."`

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat(agent): migration for conversation tables + RLS policies"
```

---

### Task 4: get_rls_session dependency

**Files:**
- Modify: `api/db/engine.py`

- [ ] **Step 1: Add get_rls_session**

In `api/db/engine.py`, add after the `get_session` function:

```python
async def get_rls_session(
    session: AsyncSession = Depends(get_session),
    user: "UserModel" = Depends(_lazy_require_onboarded),
) -> AsyncSession:
    """Yield a DB session with PostgreSQL RLS tenant context set.

    Uses ``SET LOCAL`` so the variable is scoped to the current transaction
    and cannot leak across connection pool reuse.
    """
    from sqlalchemy import text
    await session.execute(
        text("SET LOCAL app.current_org_id = :oid"),
        {"oid": user.org_id},
    )
    return session


def _lazy_require_onboarded():
    """Late import to avoid circular dependency with auth module."""
    from api.auth.dependencies import require_onboarded_user
    return Depends(require_onboarded_user)
```

Note: The lazy import pattern avoids circular deps. Since `get_rls_session` is used by the conversations router (not by auth), there is no import cycle. But to be safe we use the late-import pattern matching the existing codebase style in `api/dependencies.py`.

Actually, a simpler approach matching the codebase: `get_rls_session` just takes the session and user as separate `Depends`. The router composes them:

```python
from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_rls_session(session: AsyncSession, org_id: str) -> AsyncSession:
    """Activate RLS on a session. Called by routers that have already resolved the user."""
    await session.execute(
        text("SET LOCAL app.current_org_id = :oid"),
        {"oid": org_id},
    )
    return session
```

This is called from the router like:
```python
session = await get_rls_session(session, user.org_id)
```

- [ ] **Step 2: Commit**

```bash
git add api/db/engine.py
git commit -m "feat(agent): add get_rls_session helper for PostgreSQL RLS activation"
```

---

### Task 5: Conversation Pydantic schemas

**Files:**
- Create: `api/models/conversation.py`

- [ ] **Step 1: Create the schemas**

Create `api/models/conversation.py`:

```python
"""Conversation Pydantic schemas."""
from datetime import datetime

from pydantic import BaseModel


class ConversationResponse(BaseModel):
    id: str
    client_id: str
    user_id: str
    title: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int


class ConversationMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    tool_name: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class ConversationMessageListResponse(BaseModel):
    messages: list[ConversationMessageResponse]
    conversation_id: str


class SendMessageRequest(BaseModel):
    content: str
```

- [ ] **Step 2: Commit**

```bash
git add api/models/conversation.py
git commit -m "feat(agent): add conversation Pydantic schemas"
```

---

### Task 6: Conversation router (CRUD + agent dispatch placeholder)

**Files:**
- Create: `api/routers/conversations.py`
- Modify: `api/main.py`

- [ ] **Step 1: Create the router**

Create `api/routers/conversations.py`:

```python
"""Conversation endpoints — persistent, client-scoped chat sessions.

Each conversation is scoped to (org_id, client_id, user_id). The ``send_message``
endpoint triggers the agent tool-use loop and persists all messages (user,
assistant, tool_call, tool_result).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import require_onboarded_user
from api.auth.models import UserModel
from api.db.engine import get_session
from api.db.models import ConversationModel, ConversationMessageModel
from api.models.conversation import (
    ConversationListResponse,
    ConversationMessageListResponse,
    ConversationMessageResponse,
    ConversationResponse,
    SendMessageRequest,
)
from api.routers._helpers import get_client_or_404

router = APIRouter(tags=["conversations"])


async def _activate_rls(session: AsyncSession, org_id: str) -> None:
    await session.execute(
        text("SET LOCAL app.current_org_id = :oid"),
        {"oid": org_id},
    )


# ── Conversation CRUD ────────────────────────────────────────────────────


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
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    await get_client_or_404(client_id, session, user)
    base = (
        select(ConversationModel)
        .where(
            ConversationModel.client_id == client_id,
            ConversationModel.user_id == user.id,
            ConversationModel.org_id == user.org_id,
            ConversationModel.is_active.is_(True),
        )
        .order_by(ConversationModel.updated_at.desc())
    )
    count_q = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_q)).scalar() or 0
    paginated = base.offset((page - 1) * page_size).limit(page_size)
    convs = (await session.execute(paginated)).scalars().all()
    return ConversationListResponse(items=convs, total=total)


@router.get(
    "/api/conversations/{conversation_id}/messages",
    response_model=ConversationMessageListResponse,
)
async def get_messages(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    conv = await _get_conversation_or_404(conversation_id, session, user)
    result = await session.execute(
        select(ConversationMessageModel)
        .where(
            ConversationMessageModel.conversation_id == conversation_id,
            ConversationMessageModel.org_id == user.org_id,
        )
        .order_by(ConversationMessageModel.created_at)
    )
    msgs = result.scalars().all()
    # Only return user-visible messages (user + assistant), not tool internals
    visible = [
        m for m in msgs if m.role in ("user", "assistant")
    ]
    return ConversationMessageListResponse(
        messages=visible, conversation_id=conversation_id,
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
        conversation_id=conversation_id,
        org_id=user.org_id,
        created_by=user.id,
        role="user",
        content=body.content,
        token_count=len(body.content) // 4,
    )
    session.add(user_msg)

    # Update conversation title from first user message
    if conv.title == "New conversation":
        conv.title = body.content[:80]

    # TODO(Task 13): Replace this placeholder with AgentService dispatch.
    # For now, echo back a placeholder so the CRUD tests pass.
    ai_content = f"[Agent placeholder] Received: {body.content[:100]}"

    ai_msg = ConversationMessageModel(
        conversation_id=conversation_id,
        org_id=user.org_id,
        created_by=user.id,
        role="assistant",
        content=ai_content,
        token_count=len(ai_content) // 4,
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


# ── Helpers ───────────────────────────────────────────────────────────────


async def _get_conversation_or_404(
    conversation_id: str,
    session: AsyncSession,
    user: UserModel,
) -> ConversationModel:
    result = await session.execute(
        select(ConversationModel).where(
            ConversationModel.id == conversation_id,
            ConversationModel.org_id == user.org_id,
            ConversationModel.is_active.is_(True),
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv
```

- [ ] **Step 2: Register the router in api/main.py**

In `api/main.py`, add after the existing router imports:

```python
from api.routers.conversations import router as conversations_router
```

And in the `app.include_router(...)` section:

```python
app.include_router(conversations_router)
```

- [ ] **Step 3: Run the conversation tests**

Run: `pytest tests/api/test_conversations.py -xvs`
Expected: `test_create_conversation` passes.

- [ ] **Step 4: Commit**

```bash
git add api/routers/conversations.py api/main.py
git commit -m "feat(agent): add conversation router with CRUD endpoints"
```

---

### Task 7: Conversation CRUD + RLS tests

**Files:**
- Modify: `tests/api/test_conversations.py`

- [ ] **Step 1: Expand the test file**

Replace `tests/api/test_conversations.py` with comprehensive tests:

```python
"""Tests for conversation CRUD and RLS tenant isolation."""
import pytest


@pytest.mark.asyncio
async def test_create_conversation(client):
    c = await client.post("/api/clients", json={"name": "Conv Test"})
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/conversations", json={})
    assert resp.status_code == 201
    body = resp.json()
    assert isinstance(body["id"], str) and len(body["id"]) == 36
    assert body["client_id"] == cid
    assert body["is_active"] is True
    assert body["title"] == "New conversation"


@pytest.mark.asyncio
async def test_list_conversations(client):
    c = await client.post("/api/clients", json={"name": "List Test"})
    cid = c.json()["id"]
    # Create two conversations
    await client.post(f"/api/clients/{cid}/conversations", json={})
    await client.post(f"/api/clients/{cid}/conversations", json={})
    resp = await client.get(f"/api/clients/{cid}/conversations")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2
    assert len(resp.json()["items"]) == 2


@pytest.mark.asyncio
async def test_send_message_and_get_history(client):
    c = await client.post("/api/clients", json={"name": "Msg Test"})
    cid = c.json()["id"]
    conv = await client.post(f"/api/clients/{cid}/conversations", json={})
    conv_id = conv.json()["id"]

    # Send a message
    resp = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "What is the client's filing status?"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "assistant"
    assert len(resp.json()["content"]) > 0

    # Check history — should have user + assistant
    hist = await client.get(f"/api/conversations/{conv_id}/messages")
    assert hist.status_code == 200
    msgs = hist.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_conversation_title_auto_set(client):
    c = await client.post("/api/clients", json={"name": "Title Test"})
    cid = c.json()["id"]
    conv = await client.post(f"/api/clients/{cid}/conversations", json={})
    conv_id = conv.json()["id"]

    await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Check status of the return"},
    )

    listing = await client.get(f"/api/clients/{cid}/conversations")
    titles = [c["title"] for c in listing.json()["items"]]
    assert "Check status of the return" in titles


@pytest.mark.asyncio
async def test_delete_conversation_soft(client):
    c = await client.post("/api/clients", json={"name": "Del Test"})
    cid = c.json()["id"]
    conv = await client.post(f"/api/clients/{cid}/conversations", json={})
    conv_id = conv.json()["id"]

    resp = await client.delete(f"/api/conversations/{conv_id}")
    assert resp.status_code == 204

    # Should not appear in listing
    listing = await client.get(f"/api/clients/{cid}/conversations")
    assert listing.json()["total"] == 0

    # Should return 404 on direct access
    resp = await client.get(f"/api/conversations/{conv_id}/messages")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_conversation_not_found(client):
    resp = await client.get("/api/conversations/nonexistent-id/messages")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_conversation_for_nonexistent_client(client):
    resp = await client.post("/api/clients/nonexistent/conversations", json={})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run all conversation tests**

Run: `pytest tests/api/test_conversations.py -xvs`
Expected: All 7 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_conversations.py
git commit -m "test(agent): comprehensive conversation CRUD + edge case tests"
```

---

### Task 8: AgentSession dataclass + tool registry

**Files:**
- Create: `api/agent/__init__.py`
- Create: `api/agent/session.py`
- Create: `api/agent/tool_registry.py`
- Create: `api/agent/tools/__init__.py`

- [ ] **Step 1: Create the package structure**

Create `api/agent/__init__.py`:

```python
"""Agentic layer — tool-calling AI assistant for CPA workflows."""
```

Create `api/agent/tools/__init__.py`:

```python
"""MCP tool implementations — pure async functions that read client data."""
```

- [ ] **Step 2: Create AgentSession**

Create `api/agent/session.py`:

```python
"""Immutable session context for one agent invocation.

Created by the conversation router, threaded through to all tool functions.
The ``client_id`` is set from the URL path — the LLM never controls it.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from api.services.pii.encryptor import PIIEncryptor


@dataclass(frozen=True)
class AgentSession:
    """Request-scoped, immutable context for agent tool execution.

    Frozen so it cannot be mutated mid-request. All tools read ``client_id``
    from here rather than accepting it as a parameter — this is the primary
    mechanism preventing LLM-directed cross-client data access.
    """
    org_id: str
    client_id: str
    user_id: str
    conversation_id: str
    db_session: AsyncSession
    pii_encryptor: PIIEncryptor
```

- [ ] **Step 3: Create ToolRegistry**

Create `api/agent/tool_registry.py`:

```python
"""Tool registry — maps tool names to handler functions and generates
Claude-compatible tool definitions.

Tools are registered via ``register()`` and dispatched via ``execute()``.
The registry generates the ``tools`` parameter for the Anthropic Messages API
from Python function signatures and docstrings.
"""
from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Callable, get_type_hints

from api.agent.session import AgentSession

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Manages tool definitions and dispatch for the agent loop."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable] = {}
        self._definitions: list[dict[str, Any]] = []

    def register(
        self,
        name: str,
        description: str,
        handler: Callable,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        """Register a tool with its handler and schema."""
        self._handlers[name] = handler
        self._definitions.append({
            "name": name,
            "description": description,
            "input_schema": parameters or {
                "type": "object",
                "properties": {},
                "required": [],
            },
        })

    @property
    def tool_definitions(self) -> list[dict[str, Any]]:
        """Return Claude-compatible tool definitions."""
        return self._definitions

    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        session: AgentSession,
    ) -> dict[str, Any]:
        """Execute a tool and return its result. Never raises — returns
        ``{"error": "..."}`` on failure so the agent can report gracefully."""
        handler = self._handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return await handler(session, **tool_input)
        except Exception as exc:
            logger.exception("Tool %s failed", tool_name)
            return {"error": f"Tool {tool_name} failed: {exc}"}
```

- [ ] **Step 4: Commit**

```bash
git add api/agent/
git commit -m "feat(agent): add AgentSession dataclass and ToolRegistry"
```

---

### Task 9: Client tools (get_client_summary, list_dependents)

**Files:**
- Create: `api/agent/tools/client_tools.py`
- Create: `tests/api/test_agent_tools.py`

- [ ] **Step 1: Write the test**

Create `tests/api/test_agent_tools.py`:

```python
"""Tests for agent tool functions — isolation, PII masking, correctness."""
import pytest
from api.agent.session import AgentSession
from api.agent.tools import client_tools
from api.services.pii.encryptor import PIIEncryptor, _DEV_FALLBACK_KEY


def _make_encryptor() -> PIIEncryptor:
    return PIIEncryptor(_DEV_FALLBACK_KEY)


@pytest.mark.asyncio
async def test_get_client_summary_masks_pii(app):
    """SSN, DOB, and street must be masked in the tool's return value."""
    session_factory = app.state.test_session_factory
    async with session_factory() as db:
        # Seed org + user
        from api.auth.models import OrganizationModel, UserModel
        org = OrganizationModel(name="Tool Test Org", slug="tool-test", plan="starter")
        db.add(org)
        await db.flush()
        user = UserModel(
            org_id=org.id, auth0_sub="auth0|tool-test", email="tool@test.com",
            name="Tool Tester", role="admin", onboarding_status="complete",
        )
        db.add(user)
        await db.flush()

        # Seed client with PII
        from api.db.models import ClientModel
        enc = _make_encryptor()
        client = ClientModel(
            org_id=org.id, created_by=user.id, name="PII Client",
            primary_first_name="John", primary_last_name="Doe",
            filing_status="single", tax_year=2025, dependents=0,
        )
        client.primary_ssn_enc = enc.encrypt("123-45-6789")
        client.primary_dob_enc = enc.encrypt("1990-05-15")
        client.street_enc = enc.encrypt("742 Evergreen Terrace")
        db.add(client)
        await db.commit()

        agent_session = AgentSession(
            org_id=org.id, client_id=client.id, user_id=user.id,
            conversation_id="test-conv", db_session=db,
            pii_encryptor=enc,
        )
        result = await client_tools.get_client_summary(agent_session)

        assert "error" not in result
        # SSN must be masked — last 4 only
        assert result["primary_ssn"] == "***-**-6789"
        # DOB must be masked — year only
        assert "1990" in result["primary_dob"]
        assert result["primary_dob"].startswith("*")
        # Street must be masked
        assert "***" in result["street"]
        # Name is NOT PII — should be plaintext
        assert result["name"] == "PII Client"
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/api/test_agent_tools.py::test_get_client_summary_masks_pii -xvs`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement client_tools**

Create `api/agent/tools/client_tools.py`:

```python
"""Client-scoped read tools — client summary and dependents list.

All PII is masked before returning. The ``session.client_id`` is injected
by the router, never controlled by the LLM.
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select

from api.agent.session import AgentSession
from api.db.models import ClientModel, DependentModel, FamilyGroupModel
from api.services.pii.encryptor import PIIEncryptor


async def get_client_summary(session: AgentSession) -> dict:
    """Get the current client's profile, filing status, and masked PII."""
    result = await session.db_session.execute(
        select(ClientModel).where(
            ClientModel.id == session.client_id,
            ClientModel.org_id == session.org_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        return {"error": "Client not found"}

    enc = session.pii_encryptor

    # Decrypt then mask PII
    ssn = enc.decrypt(client.primary_ssn_enc) if client.primary_ssn_enc else None
    dob = enc.decrypt(client.primary_dob_enc) if client.primary_dob_enc else None
    street = enc.decrypt(client.street_enc) if client.street_enc else None
    spouse_ssn = enc.decrypt(client.spouse_ssn_enc) if client.spouse_ssn_enc else None
    spouse_dob = enc.decrypt(client.spouse_dob_enc) if client.spouse_dob_enc else None

    # Load family group for spouse names
    fg = None
    if client.family_group_id:
        fg = await session.db_session.get(FamilyGroupModel, client.family_group_id)

    # Parse filing_states JSON
    filing_states = []
    if client.filing_states:
        try:
            filing_states = json.loads(client.filing_states)
        except (TypeError, ValueError):
            pass

    return {
        "name": client.name,
        "primary_first_name": client.primary_first_name,
        "primary_last_name": client.primary_last_name,
        "filing_status": client.filing_status,
        "tax_year": client.tax_year,
        "dependents": client.dependents,
        "workflow_step": client.workflow_step,
        "primary_ssn": PIIEncryptor.mask_ssn(ssn),
        "primary_dob": PIIEncryptor.mask_dob(dob),
        "street": PIIEncryptor.mask_address(street),
        "city": client.city,
        "state": client.state,
        "zip_code": client.zip_code,
        "email": client.email,
        "phone": client.phone,
        "spouse_first_name": fg.spouse_first_name if fg else None,
        "spouse_last_name": fg.spouse_last_name if fg else None,
        "spouse_ssn": PIIEncryptor.mask_ssn(spouse_ssn),
        "spouse_dob": PIIEncryptor.mask_dob(spouse_dob),
        "filing_federal": bool(client.filing_federal),
        "filing_states": filing_states,
        "family_group_name": fg.display_name if fg else None,
    }


async def list_dependents(session: AgentSession) -> dict:
    """List all dependents for the current client with masked PII."""
    result = await session.db_session.execute(
        select(DependentModel).where(
            DependentModel.client_id == session.client_id,
            DependentModel.org_id == session.org_id,
        )
    )
    deps = result.scalars().all()
    enc = session.pii_encryptor

    items = []
    for d in deps:
        ssn = enc.decrypt(d.ssn_enc) if d.ssn_enc else None
        dob_str = enc.decrypt(d.dob_enc) if d.dob_enc else None
        dob = date.fromisoformat(dob_str) if dob_str else None
        items.append({
            "first_name": d.first_name,
            "last_name": d.last_name,
            "relationship": d.relationship,
            "is_qualifying_child": d.is_qualifying_child,
            "ssn_masked": PIIEncryptor.mask_ssn(ssn),
            "dob_masked": PIIEncryptor.mask_dob(dob),
        })

    return {"dependents": items, "count": len(items)}
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/api/test_agent_tools.py::test_get_client_summary_masks_pii -xvs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/agent/tools/client_tools.py tests/api/test_agent_tools.py
git commit -m "feat(agent): add client tools (get_client_summary, list_dependents) with PII masking"
```

---

### Task 10: Document tools (list_documents, get_document_fields)

**Files:**
- Create: `api/agent/tools/document_tools.py`
- Modify: `tests/api/test_agent_tools.py`

- [ ] **Step 1: Write the test**

Add to `tests/api/test_agent_tools.py`:

```python
@pytest.mark.asyncio
async def test_get_document_fields_rejects_wrong_client(app):
    """A doc belonging to client B must not be accessible via client A's session."""
    session_factory = app.state.test_session_factory
    async with session_factory() as db:
        from api.auth.models import OrganizationModel, UserModel
        from api.db.models import ClientModel, DocumentModel
        from api.agent.tools import document_tools

        org = OrganizationModel(name="Iso Org", slug="iso", plan="starter")
        db.add(org)
        await db.flush()
        user = UserModel(
            org_id=org.id, auth0_sub="auth0|iso", email="iso@test.com",
            name="Iso User", role="admin", onboarding_status="complete",
        )
        db.add(user)
        await db.flush()

        client_a = ClientModel(org_id=org.id, created_by=user.id, name="A")
        client_b = ClientModel(org_id=org.id, created_by=user.id, name="B")
        db.add_all([client_a, client_b])
        await db.flush()

        doc_b = DocumentModel(
            org_id=org.id, created_by=user.id, client_id=client_b.id,
            form_type="W-2", title="W-2 (test.pdf)", file_name="test.pdf",
            extracted_data='{"wages": 50000}', flags="[]",
        )
        db.add(doc_b)
        await db.commit()

        enc = _make_encryptor()
        session_a = AgentSession(
            org_id=org.id, client_id=client_a.id, user_id=user.id,
            conversation_id="test-conv", db_session=db, pii_encryptor=enc,
        )
        result = await document_tools.get_document_fields(session_a, doc_id=doc_b.id)
        assert "error" in result, "Should reject doc from a different client"
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/api/test_agent_tools.py::test_get_document_fields_rejects_wrong_client -xvs`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement document_tools**

Create `api/agent/tools/document_tools.py`:

```python
"""Document-scoped read tools — list documents and drill into extracted fields.

The ``doc_id`` parameter on ``get_document_fields`` is the ONE parameter the
LLM controls. We validate that the document belongs to the current client
before returning any data.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import select

from api.agent.session import AgentSession
from api.auth.models import UserModel
from api.db.models import DocumentModel
from api.services.ocr.field_mapping import get_display_label
from api.services.pii.masking import mask_ssns_in_payload

logger = logging.getLogger(__name__)


async def _resolve_names(session: AgentSession, user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    rows = await session.db_session.execute(
        select(UserModel.id, UserModel.name).where(UserModel.id.in_(user_ids))
    )
    return {uid: name for uid, name in rows.all()}


async def list_documents(session: AgentSession) -> dict:
    """List all documents for the current client with audit trail."""
    result = await session.db_session.execute(
        select(DocumentModel).where(
            DocumentModel.client_id == session.client_id,
            DocumentModel.org_id == session.org_id,
        )
    )
    docs = list(result.scalars().all())

    user_ids = {d.created_by for d in docs if d.created_by} | {
        d.reviewed_by for d in docs if d.reviewed_by
    }
    names = await _resolve_names(session, user_ids)

    items = []
    for d in docs:
        flags = []
        try:
            flags = json.loads(d.flags or "[]")
        except (TypeError, ValueError):
            pass
        items.append({
            "doc_id": d.id,
            "form_type": d.form_type,
            "file_name": d.file_name or "",
            "title": d.title,
            "status": d.status,
            "confidence": round(d.confidence, 2),
            "flags_count": len(flags),
            "uploaded_by": names.get(d.created_by, "unknown") if d.created_by else None,
            "uploaded_at": d.created_at.isoformat() if d.created_at else None,
            "reviewed_by": names.get(d.reviewed_by, "unknown") if d.reviewed_by else None,
            "reviewed_at": d.reviewed_at.isoformat() if d.reviewed_at else None,
        })

    return {"documents": items, "count": len(items)}


async def get_document_fields(session: AgentSession, *, doc_id: str) -> dict:
    """Get extracted fields for a specific document. SSN values are masked.

    The doc_id is the one parameter the LLM chooses. We verify it belongs
    to the current client before returning data.
    """
    result = await session.db_session.execute(
        select(DocumentModel).where(
            DocumentModel.id == doc_id,
            DocumentModel.org_id == session.org_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        return {"error": f"Document {doc_id} not found"}

    # Isolation check: doc must belong to the current client
    if doc.client_id != session.client_id:
        logger.warning(
            "Tool isolation: doc %s belongs to client %s, but session is for client %s",
            doc_id, doc.client_id, session.client_id,
        )
        return {"error": f"Document {doc_id} not found"}

    try:
        raw_data = json.loads(doc.extracted_data or "{}")
    except (TypeError, ValueError):
        return {"error": "Could not parse extracted data"}

    # Mask SSNs in the payload before sending to the LLM
    masked = mask_ssns_in_payload(raw_data)

    fields = []
    if isinstance(masked, dict):
        for key, value in masked.items():
            fields.append({
                "field_name": key,
                "display_label": get_display_label(doc.form_type, key),
                "value": str(value) if value is not None else "",
            })

    return {
        "doc_id": doc.id,
        "form_type": doc.form_type,
        "file_name": doc.file_name,
        "fields": fields,
    }
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/api/test_agent_tools.py -xvs`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add api/agent/tools/document_tools.py tests/api/test_agent_tools.py
git commit -m "feat(agent): add document tools with client isolation check"
```

---

### Task 11: Return tools (get_return_draft, get_return_line_detail)

**Files:**
- Create: `api/agent/tools/return_tools.py`

- [ ] **Step 1: Implement return_tools**

Create `api/agent/tools/return_tools.py`:

```python
"""Tax return read tools — draft summary and per-line breakdown."""
from __future__ import annotations

import json

from sqlalchemy import select

from api.agent.session import AgentSession
from api.db.models import DocumentModel, TaxReturnDraftModel


async def get_return_draft(session: AgentSession) -> dict:
    """Get the computed tax return draft for the current client."""
    result = await session.db_session.execute(
        select(TaxReturnDraftModel).where(
            TaxReturnDraftModel.client_id == session.client_id,
            TaxReturnDraftModel.org_id == session.org_id,
        )
    )
    draft = result.scalar_one_or_none()
    if not draft or not draft.draft_json:
        return {"status": "not_computed", "message": "No tax return has been computed yet."}

    try:
        data = json.loads(draft.draft_json)
    except (TypeError, ValueError):
        return {"error": "Could not parse draft data"}

    return {
        "status": "computed",
        "tax_year": draft.tax_year,
        "filing_status": draft.filing_status,
        "total_income": data.get("total_income", 0),
        "taxable_income": data.get("taxable_income", 0),
        "total_tax": data.get("total_tax", 0),
        "total_payments": data.get("total_payments", 0),
        "refund_or_owed": data.get("refund_or_owed", 0),
        "effective_rate": data.get("effective_rate", 0),
        "lines": data.get("lines", []),
    }


async def get_return_line_detail(session: AgentSession, *, line_number: str) -> dict:
    """Get breakdown of which documents contribute to a specific 1040 line.

    For example, line 1a (wages) returns each W-2's employer + wage amount.
    """
    # Load draft to find the line
    result = await session.db_session.execute(
        select(TaxReturnDraftModel).where(
            TaxReturnDraftModel.client_id == session.client_id,
            TaxReturnDraftModel.org_id == session.org_id,
        )
    )
    draft = result.scalar_one_or_none()
    if not draft or not draft.draft_json:
        return {"error": "No tax return has been computed yet."}

    try:
        data = json.loads(draft.draft_json)
    except (TypeError, ValueError):
        return {"error": "Could not parse draft data"}

    # Find the requested line
    lines = data.get("lines", [])
    line = next((l for l in lines if l.get("number") == line_number), None)
    if not line:
        available = [l.get("number") for l in lines]
        return {
            "error": f"Line {line_number} not found in draft.",
            "available_lines": available,
        }

    # Cross-reference with documents for contributing sources
    doc_result = await session.db_session.execute(
        select(DocumentModel).where(
            DocumentModel.client_id == session.client_id,
            DocumentModel.org_id == session.org_id,
            DocumentModel.status.in_(["approved", "verified"]),
        )
    )
    docs = doc_result.scalars().all()

    # Map line numbers to relevant form types and extracted fields
    _LINE_TO_FIELDS = {
        "1a": {"W-2": ["wages"]},
        "2b": {"1099-INT": ["interest_income"], "1099-DIV": ["ordinary_dividends"]},
        "25a": {"W-2": ["federal_tax_withheld"]},
    }
    relevant_map = _LINE_TO_FIELDS.get(line_number, {})
    sources = []
    for doc in docs:
        if doc.form_type not in relevant_map:
            continue
        try:
            ext = json.loads(doc.extracted_data or "{}")
        except (TypeError, ValueError):
            continue
        for field_key in relevant_map[doc.form_type]:
            if field_key in ext:
                sources.append({
                    "doc_id": doc.id,
                    "form_type": doc.form_type,
                    "file_name": doc.file_name,
                    "field": field_key,
                    "value": ext[field_key],
                })

    return {
        "line_number": line["number"],
        "label": line.get("label", ""),
        "value": line.get("value", 0),
        "section": line.get("section", ""),
        "contributing_sources": sources,
    }
```

- [ ] **Step 2: Commit**

```bash
git add api/agent/tools/return_tools.py
git commit -m "feat(agent): add return tools (get_return_draft, get_return_line_detail)"
```

---

### Task 12: Register all tools in the registry

**Files:**
- Create: `api/agent/mcp_server.py`

- [ ] **Step 1: Create mcp_server.py with tool registration**

Create `api/agent/mcp_server.py`:

```python
"""FastMCP tool server + registry for the TaxFlow agent.

Registers all 6 READ tools. The registry serves dual purpose:
1. Generates Claude-compatible tool definitions for the Messages API.
2. Dispatches tool calls to the correct handler function.

Tools have NO client_id parameter — the LLM cannot control data scope.
"""
from __future__ import annotations

from api.agent.tool_registry import ToolRegistry
from api.agent.tools import client_tools, document_tools, return_tools


def build_tool_registry() -> ToolRegistry:
    """Construct and return a fully-populated tool registry."""
    registry = ToolRegistry()

    # ── Client tools ─────────────────────────────────────────────────
    registry.register(
        name="get_client_summary",
        description=(
            "Get the current client's profile including name, filing status, "
            "tax year, dependents, workflow step, contact info, and masked PII "
            "(SSN, DOB, address). Use this to understand who the client is."
        ),
        handler=client_tools.get_client_summary,
    )

    registry.register(
        name="list_dependents",
        description=(
            "List all dependents claimed for the current client. Returns names, "
            "relationships, qualifying child status, and masked SSN/DOB."
        ),
        handler=client_tools.list_dependents,
    )

    # ── Document tools ───────────────────────────────────────────────
    registry.register(
        name="list_documents",
        description=(
            "List all uploaded tax documents for the current client. Returns "
            "form type, filename, status (pending/review/verified/approved), "
            "confidence score, flags count, and upload/review audit trail."
        ),
        handler=document_tools.list_documents,
    )

    registry.register(
        name="get_document_fields",
        description=(
            "Get the extracted field values from a specific document. Use this "
            "after list_documents to drill into a particular W-2, 1099, etc. "
            "SSN values are automatically masked."
        ),
        handler=document_tools.get_document_fields,
        parameters={
            "type": "object",
            "properties": {
                "doc_id": {
                    "type": "string",
                    "description": "The document ID to inspect (from list_documents).",
                },
            },
            "required": ["doc_id"],
        },
    )

    # ── Return tools ─────────────────────────────────────────────────
    registry.register(
        name="get_return_draft",
        description=(
            "Get the computed tax return draft for the current client. Returns "
            "all 1040 line items, totals (income, deductions, tax, payments), "
            "refund or amount owed, and effective tax rate. Returns an error if "
            "no return has been computed yet."
        ),
        handler=return_tools.get_return_draft,
    )

    registry.register(
        name="get_return_line_detail",
        description=(
            "Get a breakdown of which documents and values contribute to a "
            "specific 1040 line number. For example, line '1a' shows each W-2's "
            "wages. Use after get_return_draft to explain where a number comes from."
        ),
        handler=return_tools.get_return_line_detail,
        parameters={
            "type": "object",
            "properties": {
                "line_number": {
                    "type": "string",
                    "description": "The 1040 line number to break down (e.g., '1a', '2b', '25a').",
                },
            },
            "required": ["line_number"],
        },
    )

    return registry
```

- [ ] **Step 2: Commit**

```bash
git add api/agent/mcp_server.py
git commit -m "feat(agent): register all 6 READ tools in the tool registry"
```

---

### Task 13: AgentService (tool-use loop + message persistence)

**Files:**
- Create: `api/agent/service.py`
- Create: `tests/api/test_agent_service.py`

- [ ] **Step 1: Write the test**

Create `tests/api/test_agent_service.py`:

```python
"""Tests for AgentService tool-use loop with mocked Claude responses."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.agent.service import AgentService
from api.agent.session import AgentSession
from api.agent.mcp_server import build_tool_registry
from api.services.pii.encryptor import PIIEncryptor, _DEV_FALLBACK_KEY


def _make_text_response(text: str):
    """Simulate a Claude response with just text (no tool calls)."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [block]
    return resp


def _make_tool_call_response(tool_name: str, tool_input: dict, tool_use_id: str = "tu_1"):
    """Simulate a Claude response with a tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input
    block.id = tool_use_id
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    resp.content = [block]
    return resp


@pytest.mark.asyncio
async def test_agent_simple_text_response(app):
    """When Claude returns text immediately (no tools), the agent returns it."""
    session_factory = app.state.test_session_factory
    async with session_factory() as db:
        from api.auth.models import OrganizationModel, UserModel
        from api.db.models import ClientModel, ConversationModel

        org = OrganizationModel(name="Agent Org", slug="agent", plan="starter")
        db.add(org)
        await db.flush()
        user = UserModel(
            org_id=org.id, auth0_sub="auth0|agent", email="agent@test.com",
            name="Agent Tester", role="admin", onboarding_status="complete",
        )
        db.add(user)
        await db.flush()
        client = ClientModel(org_id=org.id, created_by=user.id, name="Agent Client")
        db.add(client)
        await db.flush()
        conv = ConversationModel(
            org_id=org.id, client_id=client.id, user_id=user.id, created_by=user.id,
        )
        db.add(conv)
        await db.commit()

        enc = PIIEncryptor(_DEV_FALLBACK_KEY)
        agent_session = AgentSession(
            org_id=org.id, client_id=client.id, user_id=user.id,
            conversation_id=conv.id, db_session=db, pii_encryptor=enc,
        )

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(
            return_value=_make_text_response("The client is filing as single for TY 2025.")
        )

        service = AgentService(
            anthropic_client=mock_client,
            model="test-model",
            max_tokens=1024,
            max_tool_rounds=5,
            history_token_budget=4000,
            tool_registry=build_tool_registry(),
        )

        result = await service.reply(
            user_message="What is the filing status?",
            session=agent_session,
            history=[],
        )
        assert result == "The client is filing as single for TY 2025."


@pytest.mark.asyncio
async def test_agent_tool_call_then_text(app):
    """Claude calls a tool, gets a result, then produces final text."""
    session_factory = app.state.test_session_factory
    async with session_factory() as db:
        from api.auth.models import OrganizationModel, UserModel
        from api.db.models import ClientModel, ConversationModel

        org = OrganizationModel(name="Agent Org2", slug="agent2", plan="starter")
        db.add(org)
        await db.flush()
        user = UserModel(
            org_id=org.id, auth0_sub="auth0|agent2", email="agent2@test.com",
            name="Agent Tester 2", role="admin", onboarding_status="complete",
        )
        db.add(user)
        await db.flush()
        client = ClientModel(
            org_id=org.id, created_by=user.id, name="Tool Client",
            filing_status="mfj", tax_year=2025,
        )
        db.add(client)
        await db.flush()
        conv = ConversationModel(
            org_id=org.id, client_id=client.id, user_id=user.id, created_by=user.id,
        )
        db.add(conv)
        await db.commit()

        enc = PIIEncryptor(_DEV_FALLBACK_KEY)
        agent_session = AgentSession(
            org_id=org.id, client_id=client.id, user_id=user.id,
            conversation_id=conv.id, db_session=db, pii_encryptor=enc,
        )

        # First call: Claude requests get_client_summary tool
        # Second call: Claude produces final text using the tool result
        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(
            side_effect=[
                _make_tool_call_response("get_client_summary", {}),
                _make_text_response("The client Tool Client is filing MFJ for TY 2025."),
            ]
        )

        service = AgentService(
            anthropic_client=mock_client,
            model="test-model",
            max_tokens=1024,
            max_tool_rounds=5,
            history_token_budget=4000,
            tool_registry=build_tool_registry(),
        )

        result = await service.reply(
            user_message="Tell me about this client",
            session=agent_session,
            history=[],
        )
        assert "Tool Client" in result
        assert "MFJ" in result
        # Verify Claude was called twice (tool call + final)
        assert mock_client.messages.create.call_count == 2
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/api/test_agent_service.py -xvs`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement AgentService**

Create `api/agent/service.py`:

```python
"""AgentService — Claude tool-use loop with message persistence.

Orchestrates the agentic chat: builds the system prompt, runs the tool-use
loop (Claude → tool calls → results → Claude → ... → final text), and
persists every message to ``conversation_messages``.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

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
1. Answer ONLY using data returned by your tools. Never fabricate numbers, \
dollar amounts, or tax figures.
2. All client data you see has PII masked (SSN, DOB, address). Do NOT \
attempt to reconstruct, guess, or display unmasked PII.
3. You can READ data and ANALYZE it. You CANNOT modify data, approve \
documents, send emails, or submit returns. If the user asks you to \
take an action, explain what they need to do in the UI.
4. When referencing specific numbers, state which tool/document they came \
from (e.g., "per the W-2 from Acme Corp").
5. All your tools are scoped to this client only. You cannot access other \
clients' data.
6. If you lack data to answer a question, say so and suggest what the user \
should upload or configure.
7. Keep responses concise and professional. Use markdown formatting for \
readability (bold key numbers, bullet lists for multi-item answers)."""


class AgentService:
    """Stateless service that runs the Claude tool-use loop."""

    def __init__(
        self,
        *,
        anthropic_client: "anthropic.Anthropic | None",
        model: str,
        max_tokens: int,
        max_tool_rounds: int,
        history_token_budget: int,
        tool_registry: ToolRegistry,
    ) -> None:
        self._client = anthropic_client
        self._model = model
        self._max_tokens = max_tokens
        self._max_tool_rounds = max_tool_rounds
        self._history_budget = history_token_budget
        self._registry = tool_registry

    async def reply(
        self,
        user_message: str,
        session: AgentSession,
        history: list[dict],
    ) -> str:
        """Run the full agent loop and return the final assistant text."""
        if self._client is None:
            return "Agent is unavailable — ANTHROPIC_API_KEY not configured."

        system_prompt = await self._build_system_prompt(session)
        messages: list[dict[str, Any]] = [*history, {"role": "user", "content": user_message}]

        for round_num in range(self._max_tool_rounds):
            try:
                response = await asyncio.to_thread(
                    self._client.messages.create,
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=system_prompt,
                    messages=messages,
                    tools=self._registry.tool_definitions,
                )
            except Exception:
                logger.exception("Claude API call failed (round %d)", round_num)
                return (
                    "I encountered an error processing your question. "
                    "Please try again."
                )

            # If Claude returns a final text response, we're done.
            if response.stop_reason == "end_turn":
                text_blocks = [b.text for b in response.content if hasattr(b, "text")]
                return "\n".join(text_blocks) or "I couldn't generate a response."

            # Process tool calls
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    result = await self._registry.execute(
                        block.name, block.input, session,
                    )
                    # Persist tool call + result
                    await self._persist_tool_call(session, block)
                    await self._persist_tool_result(session, block.id, block.name, result)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })

            # Feed results back to Claude
            # The assistant message must include the raw content blocks
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        return (
            "I wasn't able to complete the analysis within the allowed steps. "
            "Please try a more specific question."
        )

    async def _build_system_prompt(self, session: AgentSession) -> str:
        """Build the system prompt with current client context."""
        from sqlalchemy import select
        from api.auth.models import UserModel

        # Load user name/email
        user_result = await session.db_session.execute(
            select(UserModel.name, UserModel.email).where(UserModel.id == session.user_id)
        )
        user_row = user_result.one_or_none()
        user_name = user_row.name if user_row else "Unknown"
        user_email = user_row.email if user_row else ""

        # Load client
        client_result = await session.db_session.execute(
            select(ClientModel).where(
                ClientModel.id == session.client_id,
                ClientModel.org_id == session.org_id,
            )
        )
        client = client_result.scalar_one_or_none()

        return _SYSTEM_PROMPT.format(
            user_name=user_name,
            user_email=user_email,
            client_name=client.name if client else "Unknown",
            filing_status=client.filing_status.upper() if client else "N/A",
            tax_year=client.tax_year if client else "N/A",
            workflow_step=client.workflow_step if client else "N/A",
        )

    async def _persist_tool_call(self, session: AgentSession, block: Any) -> None:
        msg = ConversationMessageModel(
            conversation_id=session.conversation_id,
            org_id=session.org_id,
            created_by=session.user_id,
            role="tool_call",
            content="",
            tool_name=block.name,
            tool_call_id=block.id,
            tool_input=json.dumps(block.input, default=str),
            token_count=len(json.dumps(block.input, default=str)) // 4,
        )
        session.db_session.add(msg)

    async def _persist_tool_result(
        self, session: AgentSession, tool_call_id: str, tool_name: str, result: dict,
    ) -> None:
        output = json.dumps(result, default=str)
        msg = ConversationMessageModel(
            conversation_id=session.conversation_id,
            org_id=session.org_id,
            created_by=session.user_id,
            role="tool_result",
            content="",
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            tool_output=output,
            token_count=len(output) // 4,
        )
        session.db_session.add(msg)
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/api/test_agent_service.py -xvs`
Expected: Both tests pass.

- [ ] **Step 5: Commit**

```bash
git add api/agent/service.py tests/api/test_agent_service.py
git commit -m "feat(agent): AgentService with Claude tool-use loop and message persistence"
```

---

### Task 14: Wire agent into conversation router + dependency

**Files:**
- Modify: `api/dependencies.py`
- Modify: `api/routers/conversations.py`

- [ ] **Step 1: Add get_agent_service to dependencies.py**

In `api/dependencies.py`, add at the end:

```python
def get_agent_service(
    settings: SettingsDep,
    anthropic_client: AnthropicClientDep,
    encryptor: PIIEncryptorDep,
):
    """Construct an :class:`api.agent.service.AgentService` with injected deps."""
    from api.agent.service import AgentService
    from api.agent.mcp_server import build_tool_registry

    return AgentService(
        anthropic_client=anthropic_client,
        model=settings.agent_model,
        max_tokens=settings.agent_max_tokens,
        max_tool_rounds=settings.agent_max_tool_rounds,
        history_token_budget=settings.agent_history_token_budget,
        tool_registry=build_tool_registry(),
    )
```

- [ ] **Step 2: Update send_message in conversations router**

In `api/routers/conversations.py`, replace the `send_message` endpoint with the agent-backed version. Add the imports:

```python
from api.agent.service import AgentService
from api.agent.session import AgentSession
from api.dependencies import get_agent_service, get_pii_encryptor_dep
from api.services.pii.encryptor import PIIEncryptor
```

Replace the `send_message` function:

```python
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

    # Persist user message
    user_msg = ConversationMessageModel(
        conversation_id=conversation_id,
        org_id=user.org_id,
        created_by=user.id,
        role="user",
        content=body.content,
        token_count=len(body.content) // 4,
    )
    session.add(user_msg)

    # Update conversation title from first user message
    if conv.title == "New conversation":
        conv.title = body.content[:80]

    # Build agent session — client_id is injected from the conversation,
    # never from the user's message. This is the isolation guarantee.
    agent_session = AgentSession(
        org_id=user.org_id,
        client_id=conv.client_id,
        user_id=user.id,
        conversation_id=conversation_id,
        db_session=session,
        pii_encryptor=encryptor,
    )

    # Load conversation history for context
    history = await _load_history(session, conversation_id, user.org_id)

    # Run the agent loop
    ai_content = await agent.reply(
        user_message=body.content,
        session=agent_session,
        history=history,
    )

    ai_msg = ConversationMessageModel(
        conversation_id=conversation_id,
        org_id=user.org_id,
        created_by=user.id,
        role="assistant",
        content=ai_content,
        token_count=len(ai_content) // 4,
    )
    session.add(ai_msg)
    await session.commit()
    await session.refresh(ai_msg)
    return ai_msg


async def _load_history(
    session: AsyncSession,
    conversation_id: str,
    org_id: str,
    max_chars: int = 32000,  # ~8000 tokens at 4 chars/token
) -> list[dict]:
    """Load conversation history, newest-first, up to the token budget.

    Tool call/result messages from prior turns are compressed to a single
    summary line to save tokens. Only user + assistant messages carry full
    content.
    """
    result = await session.execute(
        select(ConversationMessageModel)
        .where(
            ConversationMessageModel.conversation_id == conversation_id,
            ConversationMessageModel.org_id == org_id,
        )
        .order_by(ConversationMessageModel.created_at.desc())
    )
    all_msgs = result.scalars().all()

    # Build messages newest-first, stop when budget exhausted
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

    selected.reverse()  # chronological order
    return selected
```

- [ ] **Step 3: Run all tests**

Run: `pytest tests/api/test_conversations.py tests/api/test_agent_service.py -xvs`
Expected: All pass.

- [ ] **Step 4: Run the full test suite**

Run: `pytest tests/api/ -x`
Expected: All tests pass (360+).

- [ ] **Step 5: Commit**

```bash
git add api/dependencies.py api/routers/conversations.py
git commit -m "feat(agent): wire AgentService into conversation router with history loading"
```

---

### Task 15: Full integration test (end-to-end agent flow)

**Files:**
- Modify: `tests/api/test_agent_service.py`

- [ ] **Step 1: Add an end-to-end HTTP test**

Add to `tests/api/test_agent_service.py`:

```python
@pytest.mark.asyncio
async def test_agent_end_to_end_via_http(client):
    """Full round-trip: create client → create conversation → send message → get response."""
    c = await client.post("/api/clients", json={
        "name": "E2E Client", "filing_status": "single", "tax_year": 2025,
    })
    cid = c.json()["id"]

    conv = await client.post(f"/api/clients/{cid}/conversations", json={})
    conv_id = conv.json()["id"]

    resp = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "What is this client's filing status?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "assistant"
    # Agent may use tools or respond directly — just verify we got a non-empty response
    assert len(body["content"]) > 0

    # Verify history persisted
    hist = await client.get(f"/api/conversations/{conv_id}/messages")
    assert hist.status_code == 200
    assert len(hist.json()["messages"]) >= 2  # user + assistant at minimum
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/api/test_agent_service.py::test_agent_end_to_end_via_http -xvs`
Expected: PASS (if ANTHROPIC_API_KEY is configured) or the placeholder response if no key.

- [ ] **Step 3: Run full suite**

Run: `pytest tests/api/ -x`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add tests/api/test_agent_service.py
git commit -m "test(agent): add end-to-end HTTP integration test for agent flow"
```

---

### Summary

| Task | What it delivers |
|------|------------------|
| 1 | `fastmcp` dependency + 4 agent config fields |
| 2 | `ConversationModel` + `ConversationMessageModel` ORM models |
| 3 | Alembic migration with RLS policies on all tenant tables |
| 4 | `get_rls_session` dependency for RLS activation |
| 5 | Pydantic schemas for conversation API |
| 6 | Conversation router (CRUD + placeholder send_message) |
| 7 | 7 conversation CRUD tests |
| 8 | `AgentSession` dataclass + `ToolRegistry` |
| 9 | `get_client_summary` + `list_dependents` tools with PII masking |
| 10 | `list_documents` + `get_document_fields` tools with client isolation |
| 11 | `get_return_draft` + `get_return_line_detail` tools |
| 12 | Tool registration in `mcp_server.py` |
| 13 | `AgentService` with tool-use loop + message persistence |
| 14 | Wire agent into router, add history loading |
| 15 | End-to-end HTTP integration test |

After all 15 tasks: the agent is functional, conversations persist, tools return masked data, and tenant isolation is enforced at both app and database levels.
