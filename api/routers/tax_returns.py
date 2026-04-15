"""Tax return draft endpoints — powered by tax calculation engine."""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import ClientModel, TaxReturnDraftModel, ManualEntryModel
from api.auth.dependencies import get_current_user, require_role
from api.auth.models import UserModel
from api.models.tax_return import ReturnLine, TaxReturnDraft
from api.routers._helpers import get_client_or_404
from api.tax_engine.dependencies import get_tax_engine, get_assembler
from api.tax_engine.services.engine import TaxCalculationEngine
from api.tax_engine.assembler import DocumentAssembler
from api.tax_engine.pdf.generator import PDFGenerator

router = APIRouter(prefix="/api/clients/{client_id}/returns", tags=["tax_returns"])


class ManualEntryRequest(BaseModel):
    form_type: str
    form_index: int = 0
    field_name: str
    value: str


async def _compute_and_save_draft(client_id: int, session: AsyncSession, user: UserModel) -> TaxReturnDraft:
    """Compute tax return draft and save to DB. Used by draft endpoint and auto-recompute triggers."""
    from api.db.models import ClientModel
    client = await get_client_or_404(client_id, session, user)

    assembler = DocumentAssembler()
    tax_return = await assembler.assemble(client_id, session)

    import api.tax_engine.constants  # noqa: F401
    from api.tax_engine.constants.registry import get_constants
    constants = get_constants(client.tax_year)
    engine = TaxCalculationEngine(constants)
    result = engine.compute(tax_return)

    # Validation
    from api.tax_engine.validation.engine import ValidationEngine as TaxValidationEngine
    validator = TaxValidationEngine()
    validation_results = [r.model_dump() for r in validator.validate(tax_return)]

    # Convert to TaxReturnDraft
    lines = []
    f1040 = result.form_results.get("1040")
    if f1040:
        for line_num, trace in sorted(f1040.lines.items()):
            section = "income"
            if line_num in ("12", "13a", "15"):
                section = "deductions"
            elif line_num in ("16", "23", "24"):
                section = "tax_credits"
            elif line_num in ("25", "26", "33", "35a", "37"):
                section = "payments"
            lines.append(ReturnLine(
                number=line_num, label=trace.label,
                value=float(trace.value), section=section,
            ))

    total_income = float(result.total_income)
    ded_result = result.form_results.get("deduction")
    total_deductions = float(ded_result.total) if ded_result else 0.0
    effective_rate = round(float(result.total_tax) / total_income * 100, 1) if total_income > 0 else 0.0

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    draft = TaxReturnDraft(
        client_id=client_id,
        tax_year=client.tax_year,
        filing_status=client.filing_status,
        lines=lines,
        total_income=total_income,
        total_deductions=total_deductions,
        taxable_income=float(result.taxable_income),
        total_tax=float(result.total_tax),
        total_payments=float(result.total_payments),
        refund_or_owed=float(result.refund_or_owed),
        effective_rate=effective_rate,
        validation_results=validation_results,
        computed_at=now,
    )

    # Upsert
    db_result = await session.execute(
        select(TaxReturnDraftModel).where(
            TaxReturnDraftModel.org_id == user.org_id,
            TaxReturnDraftModel.client_id == client_id,
        )
    )
    existing = db_result.scalar_one_or_none()
    if existing:
        existing.tax_year = draft.tax_year
        existing.filing_status = draft.filing_status
        existing.draft_json = draft.model_dump_json()
    else:
        db_draft = TaxReturnDraftModel(
            client_id=client_id, org_id=user.org_id, created_by=user.id,
            tax_year=draft.tax_year, filing_status=draft.filing_status,
            draft_json=draft.model_dump_json(),
        )
        session.add(db_draft)
    await session.commit()
    return draft


@router.post("/draft", response_model=TaxReturnDraft)
async def generate_draft(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
):
    return await _compute_and_save_draft(client_id, session, user)


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


@router.post("/entries")
async def create_manual_entry(
    client_id: int,
    entry: ManualEntryRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
):
    """Add or update a manual override for a tax form field."""
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
        me = ManualEntryModel(
            org_id=user.org_id, created_by=user.id, client_id=client_id,
            form_type=entry.form_type, form_index=entry.form_index,
            field_name=entry.field_name, value=entry.value,
            entered_by=user.id,
        )
        session.add(me)
    await session.commit()
    # Auto-recompute draft
    try:
        await _compute_and_save_draft(client_id, session, user)
    except Exception:
        pass
    return {"status": "ok"}


@router.get("/entries")
async def list_manual_entries(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    """List all manual overrides for a client."""
    await get_client_or_404(client_id, session, user)
    result = await session.execute(
        select(ManualEntryModel).where(
            ManualEntryModel.org_id == user.org_id,
            ManualEntryModel.client_id == client_id,
        )
    )
    entries = result.scalars().all()
    return [
        {"id": e.id, "form_type": e.form_type, "form_index": e.form_index,
         "field_name": e.field_name, "value": e.value}
        for e in entries
    ]


@router.delete("/entries/{entry_id}")
async def delete_manual_entry(
    client_id: int,
    entry_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
):
    """Remove a manual override."""
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


from api.tax_engine.advisory.models import AdvisoryItem
from api.tax_engine.advisory.engine import AdvisoryEngine


@router.get("/advisory", response_model=list[AdvisoryItem])
async def get_advisory(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    """Generate personalized tax advisory recommendations."""
    client = await get_client_or_404(client_id, session, user)

    assembler = DocumentAssembler()
    tax_return = await assembler.assemble(client_id, session)

    import api.tax_engine.constants  # noqa: F401
    from api.tax_engine.constants.registry import get_constants
    constants = get_constants(client.tax_year)
    engine = TaxCalculationEngine(constants)
    result = engine.compute(tax_return)

    advisory = AdvisoryEngine()
    return advisory.analyze(tax_return, result, constants)


@router.get("/pdf")
async def download_pdf(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    """Generate and download a filled Form 1040 PDF."""
    client = await get_client_or_404(client_id, session, user)

    assembler = DocumentAssembler()
    tax_return = await assembler.assemble(client_id, session)

    import api.tax_engine.constants  # noqa: F401
    from api.tax_engine.constants.registry import get_constants
    constants = get_constants(client.tax_year)
    engine = TaxCalculationEngine(constants)
    result = engine.compute(tax_return)

    generator = PDFGenerator()
    pdf_bytes = generator.generate(tax_return, result)

    safe_name = client.name.replace(" ", "_") if client.name else "client"
    filename = f"1040_{safe_name}_{client.tax_year}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


from api.tax_engine.comparison.models import ComparisonReport
from api.tax_engine.comparison.engine import ComparisonEngine


@router.get("/compare", response_model=ComparisonReport)
async def compare_years(
    client_id: int,
    prior_year: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    """Compare current tax year against a prior year for the same client."""
    client = await get_client_or_404(client_id, session, user)

    if prior_year == client.tax_year:
        raise HTTPException(status_code=400, detail="Cannot compare a year to itself")

    assembler = DocumentAssembler()

    # Compute current year
    tax_return_current = await assembler.assemble(client_id, session)

    import api.tax_engine.constants  # noqa: F401
    from api.tax_engine.constants.registry import get_constants

    current_constants = get_constants(client.tax_year)
    current_result = TaxCalculationEngine(current_constants).compute(tax_return_current)

    # Compute prior year (assemble with same docs — prior year uses different constants)
    prior_return = await assembler.assemble(client_id, session)
    prior_return.tax_year = prior_year
    try:
        prior_constants = get_constants(prior_year)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Tax year {prior_year} is not supported")
    prior_result = TaxCalculationEngine(prior_constants).compute(prior_return)

    engine = ComparisonEngine()
    return engine.compare(current_result, prior_result, client_id=client_id)


@router.post("/validate")
async def validate_return(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    """Run validation without computing taxes."""
    client = await get_client_or_404(client_id, session, user)
    assembler = DocumentAssembler()
    tax_return = await assembler.assemble(client_id, session)

    import api.tax_engine.constants  # noqa: F401
    from api.tax_engine.constants.registry import get_constants
    from api.tax_engine.validation.engine import ValidationEngine as TaxValidationEngine

    constants = get_constants(client.tax_year)

    validator = TaxValidationEngine()
    results = validator.validate(tax_return)

    return {
        "results": [r.model_dump() for r in results],
        "has_errors": any(r.severity == "ERROR" for r in results),
    }
