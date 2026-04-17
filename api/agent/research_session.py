"""Immutable session context for research agent invocations.

Lighter than AgentSession — no client_id, no PII encryptor.
Research is user-scoped: general IRS knowledge, no client data."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ResearchSession:
    """Request-scoped context for research tool execution."""
    org_id: str
    user_id: str
    conversation_id: str
    db_session: AsyncSession
    tax_brain_pool: Any  # psycopg2 ConnectionPool for KB access
