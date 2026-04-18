"""Workflow step management — user-driven status progression.

The workflow_step column on ClientModel tracks where a client is in the
tax preparation pipeline. There are 4 ordered steps:

    intake → documents → tax_return → filed

Each step is marked complete by explicit user action:
- intake:     auto-completed on client creation
- documents:  user clicks "Mark Documents Complete"
- tax_return: user clicks "Mark Tax Return Complete"
- filed:      user clicks "Mark Filed"

Marking a step incomplete cascades: all subsequent steps also become
incomplete.

The workflow_step value represents the LAST COMPLETED step.
"""
from __future__ import annotations

import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import ClientModel, DocumentModel, TaxReturnDraftModel

logger = logging.getLogger(__name__)

# Ordered steps
STEPS = ["intake", "documents", "tax_return", "filed"]


def _step_index(step: str) -> int:
    try:
        return STEPS.index(step)
    except ValueError:
        return 0


def can_complete_step(
    step: str,
    has_documents: bool,
    has_return_draft: bool,
    current_step: str,
) -> bool:
    """Check if a step can be marked complete given current state."""
    idx = _step_index(step)
    current_idx = _step_index(current_step)

    # Can't complete a step if previous step isn't complete
    if idx > 0 and current_idx < idx - 1:
        return False

    # Step-specific gating
    if step == "documents" and not has_documents:
        return False
    if step == "tax_return" and not has_return_draft:
        return False
    if step == "filed" and current_idx < _step_index("tax_return"):
        return False

    return True


async def mark_step_complete(
    session: AsyncSession, client_id: str, org_id: str, step: str,
) -> dict:
    """Mark a workflow step as complete. Returns updated workflow state."""
    if step not in STEPS:
        return {"error": f"Invalid step: {step}"}

    result = await session.execute(
        select(ClientModel).where(
            ClientModel.id == client_id,
            ClientModel.org_id == org_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        return {"error": "Client not found"}

    current = client.workflow_step or "intake"

    # Check gating
    has_docs = await _has_documents(session, client_id, org_id)
    has_draft = await _has_return_draft(session, client_id, org_id)

    if not can_complete_step(step, has_docs, has_draft, current):
        return {"error": f"Cannot complete '{step}' — prerequisites not met"}

    # Advance to this step
    if _step_index(step) > _step_index(current):
        client.workflow_step = step
        logger.info("Workflow: client %s → %s (marked complete)", client_id[:8], step)

    return {"workflow_step": client.workflow_step, "steps": _build_step_status(client.workflow_step)}


async def mark_step_incomplete(
    session: AsyncSession, client_id: str, org_id: str, step: str,
) -> dict:
    """Mark a step incomplete. Cascades: all subsequent steps also become incomplete."""
    if step not in STEPS or step == "intake":
        return {"error": f"Cannot unmark '{step}'"}

    result = await session.execute(
        select(ClientModel).where(
            ClientModel.id == client_id,
            ClientModel.org_id == org_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        return {"error": "Client not found"}

    current = client.workflow_step or "intake"
    step_idx = _step_index(step)
    current_idx = _step_index(current)

    if current_idx < step_idx:
        return {"workflow_step": current, "steps": _build_step_status(current)}

    # Roll back to the step before this one
    new_step = STEPS[step_idx - 1] if step_idx > 0 else "intake"
    client.workflow_step = new_step
    logger.info("Workflow: client %s → %s (unmarked %s)", client_id[:8], new_step, step)

    return {"workflow_step": client.workflow_step, "steps": _build_step_status(client.workflow_step)}


async def get_workflow_status(
    session: AsyncSession, client_id: str, org_id: str,
) -> dict:
    """Get current workflow status with step completion states and gate info."""
    result = await session.execute(
        select(ClientModel).where(
            ClientModel.id == client_id,
            ClientModel.org_id == org_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        return {"error": "Client not found"}

    current = client.workflow_step or "intake"
    has_docs = await _has_documents(session, client_id, org_id)
    has_draft = await _has_return_draft(session, client_id, org_id)

    steps = _build_step_status(current)

    # Add gate info (can this step be completed?)
    for s in steps:
        s["can_complete"] = can_complete_step(s["id"], has_docs, has_draft, current)

    return {"workflow_step": current, "steps": steps}


def _build_step_status(current_step: str) -> list[dict]:
    """Build step status list from current workflow_step."""
    current_idx = _step_index(current_step)
    return [
        {
            "id": step,
            "label": _step_label(step),
            "complete": i <= current_idx,
        }
        for i, step in enumerate(STEPS)
    ]


def _step_label(step: str) -> str:
    return {
        "intake": "Intake",
        "documents": "Documents",
        "tax_return": "Tax Return",
        "filed": "Filed",
    }.get(step, step)


async def _has_documents(session: AsyncSession, client_id: str, org_id: str) -> bool:
    result = await session.execute(
        select(func.count()).where(
            DocumentModel.client_id == client_id,
            DocumentModel.org_id == org_id,
        )
    )
    return (result.scalar() or 0) > 0


async def _has_return_draft(session: AsyncSession, client_id: str, org_id: str) -> bool:
    result = await session.execute(
        select(func.count()).where(
            TaxReturnDraftModel.client_id == client_id,
            TaxReturnDraftModel.org_id == org_id,
        )
    )
    return (result.scalar() or 0) > 0
