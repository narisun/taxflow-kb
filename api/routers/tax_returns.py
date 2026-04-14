"""Tax return draft endpoints."""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import ClientModel, TaxReturnDraftModel
from api.auth.dependencies import get_current_user, require_role
from api.auth.models import UserModel
from api.models.tax_return import ReturnLine, TaxReturnDraft
from api.routers._helpers import get_client_or_404

router = APIRouter(prefix="/api/clients/{client_id}/returns", tags=["tax_returns"])


def _compute_tax(taxable_income: float, filing_status: str) -> float:
    """2024 tax brackets (simplified)."""
    if filing_status == "mfj":
        brackets = [
            (23200, 0.10),
            (94300 - 23200, 0.12),
            (201050 - 94300, 0.22),
            (383900 - 201050, 0.24),
        ]
    else:
        brackets = [
            (11600, 0.10),
            (47150 - 11600, 0.12),
            (100525 - 47150, 0.22),
            (191950 - 100525, 0.24),
        ]
    tax = 0.0
    remaining = taxable_income
    for width, rate in brackets:
        chunk = min(remaining, width)
        tax += chunk * rate
        remaining -= chunk
        if remaining <= 0:
            break
    return round(tax, 2)


def _compute_draft(client: ClientModel) -> TaxReturnDraft:
    """Simple 1040 computation from extracted document data."""
    wages = 185200.0  # mock for now
    interest = 3847.0
    total_income = wages + interest
    standard_deduction = 29200.0 if client.filing_status == "mfj" else 14600.0
    taxable_income = max(0, total_income - standard_deduction)
    tax = _compute_tax(taxable_income, client.filing_status)
    child_credit = client.dependents * 2000.0
    total_tax = max(0, tax - child_credit)
    withholding = 29240.0  # mock
    refund = withholding - total_tax

    return TaxReturnDraft(
        client_id=client.id,
        tax_year=client.tax_year,
        filing_status=client.filing_status,
        lines=[
            ReturnLine(number="1a", label="Total wages", value=wages, section="income"),
            ReturnLine(number="2b", label="Taxable interest", value=interest, section="income"),
            ReturnLine(number="9", label="Total income", value=total_income, section="income"),
            ReturnLine(number="12", label="Standard deduction", value=standard_deduction, section="deductions"),
            ReturnLine(number="15", label="Taxable income", value=taxable_income, section="deductions"),
            ReturnLine(number="16", label="Tax", value=tax, section="tax_credits"),
            ReturnLine(number="19", label="Child Tax Credit", value=-child_credit, section="tax_credits"),
            ReturnLine(number="24", label="Total tax", value=total_tax, section="tax_credits"),
            ReturnLine(number="25", label="Withholding", value=withholding, section="payments"),
            ReturnLine(number="35a", label="Refund", value=refund, section="payments"),
        ],
        total_income=total_income,
        total_deductions=standard_deduction,
        taxable_income=taxable_income,
        total_tax=total_tax,
        total_payments=withholding,
        refund_or_owed=refund,
        effective_rate=round(total_tax / total_income * 100, 1) if total_income else 0,
    )


@router.post("/draft", response_model=TaxReturnDraft)
async def generate_draft(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
):
    client = await get_client_or_404(client_id, session, user)
    draft = _compute_draft(client)

    # Upsert draft in database
    result = await session.execute(
        select(TaxReturnDraftModel).where(
            TaxReturnDraftModel.org_id == user.org_id,
            TaxReturnDraftModel.client_id == client_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.tax_year = draft.tax_year
        existing.filing_status = draft.filing_status
        existing.draft_json = draft.model_dump_json()
    else:
        db_draft = TaxReturnDraftModel(
            client_id=client_id,
            org_id=user.org_id,
            created_by=user.id,
            tax_year=draft.tax_year,
            filing_status=draft.filing_status,
            draft_json=draft.model_dump_json(),
        )
        session.add(db_draft)
    await session.commit()
    return draft


@router.get("/draft", response_model=TaxReturnDraft)
async def get_draft(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
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
