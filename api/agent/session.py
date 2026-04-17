"""Immutable session context for one agent invocation."""
from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from api.services.pii.encryptor import PIIEncryptor


@dataclass(frozen=True)
class AgentSession:
    """Request-scoped, immutable context for agent tool execution.
    Frozen so it cannot be mutated mid-request. All tools read client_id
    from here rather than accepting it as a parameter."""
    org_id: str
    client_id: str
    user_id: str
    conversation_id: str
    db_session: AsyncSession
    pii_encryptor: PIIEncryptor
