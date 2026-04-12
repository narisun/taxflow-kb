"""Tax return draft endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import ClientModel
from api.models.tax_return import ReturnLine, TaxReturnDraft

router = APIRouter(tags=["tax_returns"])

# In-memory store for drafts (keyed by client_id)
_drafts: dict[int, TaxReturnDraft] = {}


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


@router.post("/api/clients/{client_id}/returns/draft", response_model=TaxReturnDraft)
async def generate_draft(client_id: int, session: AsyncSession = Depends(get_session)):
    client = await session.get(ClientModel, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    draft = _compute_draft(client)
    _drafts[client_id] = draft
    return draft


@router.get("/api/clients/{client_id}/returns/draft", response_model=TaxReturnDraft)
async def get_draft(client_id: int, session: AsyncSession = Depends(get_session)):
    client = await session.get(ClientModel, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    draft = _drafts.get(client_id)
    if not draft:
        raise HTTPException(status_code=404, detail="No draft found — generate one first")
    return draft
