"""Tax return endpoints — thin HTTP layer delegating to :class:`TaxReturnService`."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user, require_onboarded_user, require_role
from api.auth.models import UserModel
from api.db.engine import get_session
from api.db.models import ManualEntryModel, TaxReturnDraftModel
from api.dependencies import get_tax_return_service
from api.models.tax_return import TaxReturnDraft, ReturnManifest
from api.routers._helpers import get_client_or_404
from api.services.tax import TaxReturnService
from api.tax_engine.advisory.models import AdvisoryItem
from api.tax_engine.comparison.models import ComparisonReport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clients/{client_id}/returns", tags=["tax_returns"])


class ManualEntryRequest(BaseModel):
    form_type: str
    form_index: int = 0
    field_name: str
    value: str


# --- Backwards-compatibility shim -------------------------------------------
# Other routers used to import ``_compute_and_save_draft`` from here. The new
# canonical path is ``TaxReturnService.compute_and_save_draft``; we preserve
# the function so any stragglers still work during the migration.
async def _compute_and_save_draft(
    client_id: str, session: AsyncSession, user: UserModel
) -> TaxReturnDraft:
    from api.services.pii.encryptor import get_pii_encryptor

    service = TaxReturnService(encryptor=get_pii_encryptor())
    return await service.compute_and_save_draft(client_id, session, user)


# --- Draft ------------------------------------------------------------------


@router.post("/draft", response_model=TaxReturnDraft)
async def generate_draft(
    client_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
    service: TaxReturnService = Depends(get_tax_return_service),
):
    return await service.compute_and_save_draft(client_id, session, user)


@router.get("/draft", response_model=TaxReturnDraft)
async def get_draft(
    client_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    await get_client_or_404(client_id, session, user)
    result = await session.execute(
        select(TaxReturnDraftModel).where(
            TaxReturnDraftModel.org_id == user.org_id,
            TaxReturnDraftModel.client_id == client_id,
        )
    )
    db_draft = result.scalar_one_or_none()
    if not db_draft:
        raise HTTPException(status_code=404, detail="No draft found — generate one first")
    return TaxReturnDraft.model_validate_json(db_draft.draft_json)


# --- Manual entries ---------------------------------------------------------


@router.post("/entries")
async def create_manual_entry(
    client_id: str,
    entry: ManualEntryRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
    service: TaxReturnService = Depends(get_tax_return_service),
):
    await get_client_or_404(client_id, session, user)
    result = await session.execute(
        select(ManualEntryModel).where(
            ManualEntryModel.org_id == user.org_id,
            ManualEntryModel.client_id == client_id,
            ManualEntryModel.form_type == entry.form_type,
            ManualEntryModel.form_index == entry.form_index,
            ManualEntryModel.field_name == entry.field_name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = entry.value
    else:
        session.add(
            ManualEntryModel(
                org_id=user.org_id,
                created_by=user.id,
                client_id=client_id,
                form_type=entry.form_type,
                form_index=entry.form_index,
                field_name=entry.field_name,
                value=entry.value,
                entered_by=user.id,
            )
        )
    await session.commit()

    try:
        await service.compute_and_save_draft(client_id, session, user)
    except Exception:
        logger.exception(
            "Draft recompute failed after manual entry (client_id=%s)", client_id
        )

    return {"status": "ok"}


@router.get("/entries")
async def list_manual_entries(
    client_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    await get_client_or_404(client_id, session, user)
    result = await session.execute(
        select(ManualEntryModel).where(
            ManualEntryModel.org_id == user.org_id,
            ManualEntryModel.client_id == client_id,
        )
    )
    entries = result.scalars().all()
    return [
        {
            "id": e.id,
            "form_type": e.form_type,
            "form_index": e.form_index,
            "field_name": e.field_name,
            "value": e.value,
        }
        for e in entries
    ]


@router.delete("/entries/{entry_id}")
async def delete_manual_entry(
    client_id: str,
    entry_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
):
    result = await session.execute(
        select(ManualEntryModel).where(
            ManualEntryModel.id == entry_id,
            ManualEntryModel.org_id == user.org_id,
            ManualEntryModel.client_id == client_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Manual entry not found")
    await session.delete(entry)
    await session.commit()
    return {"status": "deleted"}


# --- Advisory / PDF / Compare / Validate ------------------------------------


@router.get("/advisory", response_model=list[AdvisoryItem])
async def get_advisory(
    client_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
    service: TaxReturnService = Depends(get_tax_return_service),
):
    return await service.get_advisory(client_id, session, user)


@router.get("/pdf")
async def download_pdf(
    client_id: str,
    disposition: str = "attachment",
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
    service: TaxReturnService = Depends(get_tax_return_service),
):
    pdf_bytes, filename = await service.generate_pdf(client_id, session, user)
    disp = "inline" if disposition == "inline" else "attachment"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disp}; filename="{filename}"'},
    )


@router.get("/manifest", response_model=ReturnManifest)
async def get_manifest(
    client_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
    service: TaxReturnService = Depends(get_tax_return_service),
):
    return await service.get_manifest(client_id, session, user)


@router.get("/compare", response_model=ComparisonReport)
async def compare_years(
    client_id: str,
    prior_year: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
    service: TaxReturnService = Depends(get_tax_return_service),
):
    try:
        return await service.compare_years(client_id, prior_year, session, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/validate")
async def validate_return(
    client_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
    service: TaxReturnService = Depends(get_tax_return_service),
):
    return await service.validate(client_id, session, user)
