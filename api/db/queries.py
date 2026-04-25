"""Tenant-scoped DB query helpers.

Shared between routers and services — lives in the data-access layer so
neither routers nor services create a circular import.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import ClientModel
from api.auth.models import UserModel


async def get_client_or_404(
    client_id: str, session: AsyncSession, user: UserModel
) -> ClientModel:
    """Load a client scoped to the user's org, or raise 404."""
    result = await session.execute(
        select(ClientModel).where(
            ClientModel.id == client_id,
            ClientModel.org_id == user.org_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client
