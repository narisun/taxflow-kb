"""Workflow step transitions — automatically advances client state.

The workflow_step column on ClientModel tracks where a client is in the
tax preparation pipeline:

    intake → documents → review → filing → filed

Transitions are forward-only and conditional:
- intake → documents:  first document uploaded
- documents → review:  all documents approved (none pending/flagged)
- review → filing:     tax return computed
- filing → filed:      (future: e-file submission)

Each transition function is idempotent: calling it when the client is
already past the target step is a no-op.
"""
from __future__ import annotations

import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import ClientModel, DocumentModel

logger = logging.getLogger(__name__)

# Ordered steps — transitions only move forward
_STEP_ORDER = ["intake", "documents", "review", "filing", "filed"]


def _step_index(step: str) -> int:
    try:
        return _STEP_ORDER.index(step)
    except ValueError:
        return 0


async def _advance_to(
    session: AsyncSession, client_id: str, org_id: str, target_step: str,
) -> str | None:
    """Advance client to target_step if currently before it. Returns new step or None."""
    result = await session.execute(
        select(ClientModel).where(
            ClientModel.id == client_id,
            ClientModel.org_id == org_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        return None

    current = client.workflow_step or "intake"
    if _step_index(current) >= _step_index(target_step):
        return None  # already at or past target

    client.workflow_step = target_step
    logger.info(
        "Workflow transition: client %s %s → %s",
        client_id[:8], current, target_step,
    )
    return target_step


async def on_document_uploaded(
    session: AsyncSession, client_id: str, org_id: str,
) -> None:
    """Called after a document is uploaded. Advances intake → documents."""
    await _advance_to(session, client_id, org_id, "documents")


async def on_document_approved(
    session: AsyncSession, client_id: str, org_id: str,
) -> None:
    """Called after a document is approved. If all docs are now approved/verified,
    advances documents → review."""
    # Check if any docs still need review
    pending_count_result = await session.execute(
        select(func.count()).where(
            DocumentModel.client_id == client_id,
            DocumentModel.org_id == org_id,
            DocumentModel.status.in_(["pending", "review", "flagged"]),
        )
    )
    pending = pending_count_result.scalar() or 0

    if pending == 0:
        # All docs approved/verified — advance to review
        await _advance_to(session, client_id, org_id, "review")


async def on_return_computed(
    session: AsyncSession, client_id: str, org_id: str,
) -> None:
    """Called after a tax return is computed. Advances review → filing."""
    await _advance_to(session, client_id, org_id, "filing")
