# Multi-Year Draft Storage & YoY Comparison — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store tax return drafts per year (not one per client), support importing prior-year 1040 PDFs, and wire the frontend YoY display to real data.

**Architecture:** Change the TaxReturnDraftModel unique constraint to include tax_year, add source tracking columns (source_type, source_document_id), create a prior-year 1040 extraction pipeline, and replace frontend mock data with real API calls.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy (async), Alembic, Pydantic v2, pdfjs-dist, Next.js/React

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `api/db/models.py` | Add source_type, source_document_id columns; update unique constraint |
| Create | `alembic/versions/xxxx_multi_year_draft.py` | Migration for schema changes |
| Modify | `api/models/tax_return.py` | Add PriorYearResponse schema |
| Modify | `api/services/tax/return_service.py` | Fix upsert, add get_prior_year_draft, import_prior_year |
| Create | `api/tax_engine/prior_year_import.py` | Map extracted 1040 fields to TaxReturnDraft |
| Modify | `api/routers/tax_returns.py` | Add ?tax_year param, /prior-year and /import-prior endpoints |
| Create | `api/services/ocr/prompts_1040_prior.py` | Extraction prompt for prior-year 1040 |
| Modify | `api/services/ocr/prompts.py` | Register 1040-Prior form type |
| Create | `tests/api/test_multi_year_draft.py` | Tests for multi-year storage and import |
| Modify | `frontend/lib/api-client.ts` | Add priorYear(), importPrior() methods and types |
| Modify | `frontend/app/page.tsx` | Replace mock prior-year data with real API call |
| Modify | `frontend/components/returns/return-preview.tsx` | Add source badge (Computed/Imported) |
| Modify | `frontend/components/documents/document-manager-modal.tsx` | Add 1040-Prior form type |

---

### Task 1: Database Schema — Add Multi-Year Columns and Constraint

**Files:**
- Modify: `api/db/models.py:171-188`
- Create: `alembic/versions/` (new migration)

- [ ] **Step 1: Update TaxReturnDraftModel in `api/db/models.py`**

Add `source_type` and `source_document_id` columns, and change the unique constraint. Find the `TaxReturnDraftModel` class (around line 171) and replace its column and constraint definitions:

```python
class TaxReturnDraftModel(TenantMixin, Base):
    __tablename__ = "tax_return_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id"), index=True
    )
    tax_year: Mapped[int] = mapped_column(Integer)
    filing_status: Mapped[str] = mapped_column(String(10))
    draft_json: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="computed")
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("documents.id"), nullable=True
    )

    client: Mapped["ClientModel"] = relationship()

    __table_args__ = (
        UniqueConstraint("org_id", "client_id", "tax_year", name="uq_draft_org_client_year"),
        Index("ix_drafts_org_client", "org_id", "client_id"),
    )
```

- [ ] **Step 2: Generate Alembic migration**

Run: `cd /Users/admin-h26/taxflow-kb && alembic revision --autogenerate -m "multi_year_draft_source_tracking"`

If autogenerate doesn't detect the constraint rename, manually edit the migration to include:

```python
def upgrade() -> None:
    op.add_column("tax_return_drafts", sa.Column("source_type", sa.String(20), nullable=False, server_default="computed"))
    op.add_column("tax_return_drafts", sa.Column("source_document_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_draft_source_doc", "tax_return_drafts", "documents", ["source_document_id"], ["id"])
    op.drop_constraint("uq_draft_org_client", "tax_return_drafts", type_="unique")
    op.create_unique_constraint("uq_draft_org_client_year", "tax_return_drafts", ["org_id", "client_id", "tax_year"])


def downgrade() -> None:
    op.drop_constraint("uq_draft_org_client_year", "tax_return_drafts", type_="unique")
    op.drop_constraint("fk_draft_source_doc", "tax_return_drafts", type_="foreignkey")
    op.drop_column("tax_return_drafts", "source_document_id")
    op.drop_column("tax_return_drafts", "source_type")
    op.create_unique_constraint("uq_draft_org_client", "tax_return_drafts", ["org_id", "client_id"])
```

- [ ] **Step 3: Run tests to verify model change doesn't break existing tests**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_tax_returns.py -v --timeout=30`

Expected: All PASS (in-memory SQLite creates tables from model definitions, so the new columns are picked up automatically).

- [ ] **Step 4: Commit**

```bash
git add api/db/models.py alembic/versions/*.py
git commit -m "feat: multi-year draft schema — add source tracking, per-year unique constraint

Adds source_type (computed/imported) and source_document_id columns to
TaxReturnDraftModel. Changes unique constraint from (org_id, client_id)
to (org_id, client_id, tax_year) so multiple years can coexist.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Pydantic Schema — Add PriorYearResponse

**Files:**
- Modify: `api/models/tax_return.py`

- [ ] **Step 1: Add PriorYearResponse to `api/models/tax_return.py`**

Add at the end of the file, after the existing models:

```python
class PriorYearResponse(BaseModel):
    """Response for GET /prior-year — includes source provenance."""
    draft: TaxReturnDraft | None = None
    source_type: str = "computed"
    source_document_id: str | None = None
```

- [ ] **Step 2: Commit**

```bash
git add api/models/tax_return.py
git commit -m "feat: add PriorYearResponse schema with source provenance

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Service Layer — Fix Upsert and Add Prior-Year Methods

**Files:**
- Modify: `api/services/tax/return_service.py`

- [ ] **Step 1: Write tests for multi-year upsert and prior-year retrieval**

Create `tests/api/test_multi_year_draft.py`:

```python
"""Tests for multi-year draft storage and prior-year retrieval."""
import pytest


@pytest.mark.asyncio
async def test_compute_drafts_for_two_years(authenticated_client, app, seeded_user):
    """Computing drafts for 2024 and 2025 creates two separate rows."""
    # Create a client
    resp = await authenticated_client.post("/api/clients", json={
        "name": "Multi Year Test",
        "primary_first_name": "Test",
        "primary_last_name": "User",
        "filing_status": "single",
        "tax_year": 2025,
    })
    assert resp.status_code == 201
    client_id = resp.json()["id"]

    # Compute current year draft
    resp = await authenticated_client.post(f"/api/clients/{client_id}/returns/draft")
    assert resp.status_code == 200
    draft_2025 = resp.json()
    assert draft_2025["tax_year"] == 2025

    # Change client to 2024 and compute
    await authenticated_client.patch(f"/api/clients/{client_id}", json={"tax_year": 2024})
    resp = await authenticated_client.post(f"/api/clients/{client_id}/returns/draft")
    assert resp.status_code == 200 or resp.status_code == 201
    draft_2024 = resp.json()
    assert draft_2024["tax_year"] == 2024

    # Change back to 2025
    await authenticated_client.patch(f"/api/clients/{client_id}", json={"tax_year": 2025})

    # Both drafts should exist
    resp = await authenticated_client.get(f"/api/clients/{client_id}/returns/draft")
    assert resp.status_code == 200
    assert resp.json()["tax_year"] == 2025

    resp = await authenticated_client.get(f"/api/clients/{client_id}/returns/draft?tax_year=2024")
    assert resp.status_code == 200
    assert resp.json()["tax_year"] == 2024


@pytest.mark.asyncio
async def test_prior_year_returns_null_when_none(authenticated_client):
    """GET /prior-year returns null draft when no prior year exists."""
    resp = await authenticated_client.post("/api/clients", json={
        "name": "No Prior",
        "primary_first_name": "No",
        "primary_last_name": "Prior",
        "filing_status": "single",
        "tax_year": 2025,
    })
    client_id = resp.json()["id"]

    resp = await authenticated_client.get(f"/api/clients/{client_id}/returns/prior-year")
    assert resp.status_code == 200
    body = resp.json()
    assert body["draft"] is None
    assert body["source_type"] == "computed"


@pytest.mark.asyncio
async def test_prior_year_returns_stored_draft(authenticated_client):
    """GET /prior-year returns the stored prior-year draft after computing both years."""
    resp = await authenticated_client.post("/api/clients", json={
        "name": "Prior Test",
        "primary_first_name": "Prior",
        "primary_last_name": "Test",
        "filing_status": "single",
        "tax_year": 2024,
    })
    client_id = resp.json()["id"]

    # Compute 2024 draft
    await authenticated_client.post(f"/api/clients/{client_id}/returns/draft")

    # Switch to 2025
    await authenticated_client.patch(f"/api/clients/{client_id}", json={"tax_year": 2025})

    # Now prior-year should return the 2024 draft
    resp = await authenticated_client.get(f"/api/clients/{client_id}/returns/prior-year")
    assert resp.status_code == 200
    body = resp.json()
    assert body["draft"] is not None
    assert body["draft"]["tax_year"] == 2024
    assert body["source_type"] == "computed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_multi_year_draft.py -v --timeout=30`

Expected: FAIL (endpoints don't exist yet, upsert doesn't filter by tax_year).

- [ ] **Step 3: Fix upsert in `compute_and_save_draft()`**

In `api/services/tax/return_service.py`, find the upsert section (around line 112). Change the SELECT query to include `tax_year`:

```python
        # Upsert
        db_result = await session.execute(
            select(TaxReturnDraftModel).where(
                TaxReturnDraftModel.org_id == user.org_id,
                TaxReturnDraftModel.client_id == client_id,
                TaxReturnDraftModel.tax_year == draft.tax_year,
            )
        )
        existing = db_result.scalar_one_or_none()
        if existing:
            existing.filing_status = draft.filing_status
            existing.draft_json = draft.model_dump_json()
            existing.source_type = "computed"
            existing.source_document_id = None
        else:
            db_draft = TaxReturnDraftModel(
                client_id=client_id,
                org_id=user.org_id,
                created_by=user.id,
                tax_year=draft.tax_year,
                filing_status=draft.filing_status,
                draft_json=draft.model_dump_json(),
                source_type="computed",
            )
            session.add(db_draft)
        await session.commit()
        return draft
```

- [ ] **Step 4: Add `get_prior_year_draft()` method to `TaxReturnService`**

Add after `compute_and_save_draft()`:

```python
    async def get_prior_year_draft(
        self,
        client_id: str,
        session: AsyncSession,
        user: UserModel,
    ) -> dict:
        """Return the prior-year draft with source provenance, or None."""
        from api.db.queries import get_client_or_404

        client = await get_client_or_404(client_id, session, user)
        prior_year = client.tax_year - 1

        result = await session.execute(
            select(TaxReturnDraftModel).where(
                TaxReturnDraftModel.org_id == user.org_id,
                TaxReturnDraftModel.client_id == client_id,
                TaxReturnDraftModel.tax_year == prior_year,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return {"draft": None, "source_type": "computed", "source_document_id": None}

        from api.models.tax_return import TaxReturnDraft
        draft = TaxReturnDraft.model_validate_json(row.draft_json)
        return {
            "draft": draft,
            "source_type": row.source_type,
            "source_document_id": row.source_document_id,
        }
```

- [ ] **Step 5: Add `import_prior_year()` method to `TaxReturnService`**

Add after `get_prior_year_draft()`:

```python
    async def import_prior_year(
        self,
        client_id: str,
        document_id: str,
        tax_year: int,
        lines: list,
        session: AsyncSession,
        user: UserModel,
    ) -> "TaxReturnDraft":
        """Create a draft from imported prior-year 1040 line data."""
        from api.tax_engine.prior_year_import import build_draft_from_lines
        from api.models.tax_return import TaxReturnDraft

        draft = build_draft_from_lines(client_id, tax_year, lines)

        # Upsert by (org_id, client_id, tax_year)
        result = await session.execute(
            select(TaxReturnDraftModel).where(
                TaxReturnDraftModel.org_id == user.org_id,
                TaxReturnDraftModel.client_id == client_id,
                TaxReturnDraftModel.tax_year == tax_year,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.filing_status = draft.filing_status
            existing.draft_json = draft.model_dump_json()
            existing.source_type = "imported"
            existing.source_document_id = document_id
        else:
            row = TaxReturnDraftModel(
                client_id=client_id,
                org_id=user.org_id,
                created_by=user.id,
                tax_year=tax_year,
                filing_status=draft.filing_status,
                draft_json=draft.model_dump_json(),
                source_type="imported",
                source_document_id=document_id,
            )
            session.add(row)
        await session.commit()
        return draft
```

- [ ] **Step 6: Commit**

```bash
git add api/services/tax/return_service.py tests/api/test_multi_year_draft.py
git commit -m "feat: multi-year upsert, get_prior_year_draft, import_prior_year

Fixes upsert to filter by tax_year so multiple years coexist.
Adds methods for retrieving prior-year draft with source provenance
and importing from extracted 1040 line data.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Prior-Year 1040 Import Module

**Files:**
- Create: `api/tax_engine/prior_year_import.py`

- [ ] **Step 1: Create `api/tax_engine/prior_year_import.py`**

```python
"""Build a TaxReturnDraft from extracted prior-year 1040 line items."""
from __future__ import annotations

from api.models.tax_return import ReturnLine, TaxReturnDraft

# Form 1040 lines we extract from prior-year PDFs.
# Maps extracted field key → (line_number, label, section).
_LINE_MAP: dict[str, tuple[str, str, str]] = {
    "line_1a": ("1a", "Wages, salaries, tips", "income"),
    "line_2b": ("2b", "Taxable interest", "income"),
    "line_3b": ("3b", "Qualified dividends", "income"),
    "line_7": ("7", "Capital gain or loss", "income"),
    "line_8": ("8", "Other income", "income"),
    "line_9": ("9", "Total income", "income"),
    "line_12": ("12", "Deductions", "deductions"),
    "line_13a": ("13a", "QBI deduction", "deductions"),
    "line_15": ("15", "Taxable income", "deductions"),
    "line_16": ("16", "Tax", "tax_credits"),
    "line_24": ("24", "Total tax", "tax_credits"),
    "line_25a": ("25a", "W-2 withholding", "payments"),
    "line_25b": ("25b", "1099 withholding", "payments"),
    "line_25c": ("25c", "Other withholding", "payments"),
    "line_26": ("26", "Estimated tax payments", "payments"),
    "line_33": ("33", "Total payments", "payments"),
    "line_35a": ("35a", "Refund", "payments"),
    "line_37": ("37", "Amount owed", "payments"),
}


def _parse_dollar(value: str | int | float | None) -> float:
    """Parse a dollar value from OCR output. Handles commas, $, negatives."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    if not cleaned or cleaned == "-":
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def build_draft_from_lines(
    client_id: str,
    tax_year: int,
    extracted: dict[str, str | int | float | None],
    filing_status: str = "S",
) -> TaxReturnDraft:
    """Convert extracted 1040 field dict into a TaxReturnDraft."""
    lines: list[ReturnLine] = []
    for field_key, (line_num, label, section) in _LINE_MAP.items():
        raw = extracted.get(field_key)
        val = _parse_dollar(raw)
        if val != 0.0 or field_key in ("line_9", "line_15", "line_24", "line_33"):
            lines.append(ReturnLine(
                number=line_num, label=label, value=val, section=section,
            ))

    total_income = _parse_dollar(extracted.get("line_9"))
    total_deductions = _parse_dollar(extracted.get("line_12")) + _parse_dollar(extracted.get("line_13a"))
    taxable_income = _parse_dollar(extracted.get("line_15"))
    total_tax = _parse_dollar(extracted.get("line_24"))
    total_payments = _parse_dollar(extracted.get("line_33"))
    refund = _parse_dollar(extracted.get("line_35a"))
    owed = _parse_dollar(extracted.get("line_37"))
    refund_or_owed = refund if refund > 0 else -owed

    effective_rate = round(total_tax / total_income * 100, 1) if total_income > 0 else 0.0

    return TaxReturnDraft(
        client_id=client_id,
        tax_year=tax_year,
        filing_status=filing_status,
        lines=lines,
        total_income=total_income,
        total_deductions=total_deductions,
        taxable_income=taxable_income,
        total_tax=total_tax,
        total_payments=total_payments,
        refund_or_owed=refund_or_owed,
        effective_rate=effective_rate,
    )
```

- [ ] **Step 2: Write tests for the import module**

Add to `tests/api/test_multi_year_draft.py`:

```python
from api.tax_engine.prior_year_import import build_draft_from_lines, _parse_dollar


class TestParseDollar:
    def test_integer(self):
        assert _parse_dollar(85000) == 85000.0

    def test_string_with_commas(self):
        assert _parse_dollar("85,000") == 85000.0

    def test_string_with_dollar_sign(self):
        assert _parse_dollar("$85,000") == 85000.0

    def test_none_returns_zero(self):
        assert _parse_dollar(None) == 0.0

    def test_empty_returns_zero(self):
        assert _parse_dollar("") == 0.0


class TestBuildDraftFromLines:
    def test_builds_draft_with_lines(self):
        extracted = {
            "line_1a": "85000",
            "line_9": "90000",
            "line_12": "14600",
            "line_15": "75400",
            "line_16": "12000",
            "line_24": "12000",
            "line_25a": "14000",
            "line_33": "14000",
            "line_35a": "2000",
        }
        draft = build_draft_from_lines("client-1", 2024, extracted, "S")

        assert draft.client_id == "client-1"
        assert draft.tax_year == 2024
        assert draft.total_income == 90000.0
        assert draft.total_deductions == 14600.0
        assert draft.taxable_income == 75400.0
        assert draft.total_tax == 12000.0
        assert draft.refund_or_owed == 2000.0
        assert draft.effective_rate == 13.3
        assert len(draft.lines) > 0

    def test_empty_extraction_returns_zero_draft(self):
        draft = build_draft_from_lines("client-1", 2024, {})
        assert draft.total_income == 0.0
        assert draft.refund_or_owed == 0.0
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_multi_year_draft.py::TestParseDollar tests/api/test_multi_year_draft.py::TestBuildDraftFromLines -v --timeout=30`

Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add api/tax_engine/prior_year_import.py tests/api/test_multi_year_draft.py
git commit -m "feat: prior-year 1040 import module — extract lines to TaxReturnDraft

Parses OCR-extracted 1040 line values (18 key lines) into a TaxReturnDraft.
Handles dollar formatting (commas, $, negatives). Includes unit tests.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: API Endpoints — Prior-Year and Import

**Files:**
- Modify: `api/routers/tax_returns.py`

- [ ] **Step 1: Add `tax_year` query param to GET /draft endpoint**

In `api/routers/tax_returns.py`, find the `get_draft` endpoint (around line 61). Add an optional `tax_year` query parameter and filter by it:

```python
@router.get("/draft", response_model=TaxReturnDraft)
async def get_draft(
    client_id: str,
    tax_year: int | None = Query(default=None, ge=2000, le=2100),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    await get_client_or_404(client_id, session, user)
    query = select(TaxReturnDraftModel).where(
        TaxReturnDraftModel.org_id == user.org_id,
        TaxReturnDraftModel.client_id == client_id,
    )
    if tax_year is not None:
        query = query.where(TaxReturnDraftModel.tax_year == tax_year)
    else:
        # Default: latest draft by tax_year
        query = query.order_by(TaxReturnDraftModel.tax_year.desc())
    result = await session.execute(query)
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No draft found")
    return TaxReturnDraft.model_validate_json(row.draft_json)
```

- [ ] **Step 2: Add GET /prior-year endpoint**

Add after the existing GET /draft endpoint:

```python
@router.get("/prior-year")
async def get_prior_year(
    client_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
    service: TaxReturnService = Depends(get_tax_return_service),
):
    """Return the prior-year draft with source provenance."""
    result = await service.get_prior_year_draft(client_id, session, user)
    return result
```

- [ ] **Step 3: Add POST /import-prior endpoint**

Add after /prior-year. Import the needed modules at the top of the file:

```python
@router.post("/import-prior", response_model=TaxReturnDraft)
async def import_prior_year(
    client_id: str,
    body: ImportPriorRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
    service: TaxReturnService = Depends(get_tax_return_service),
):
    """Import a prior-year 1040 — extract lines and create archived draft."""
    # Validate the document exists and belongs to this client
    doc_result = await session.execute(
        select(DocumentModel).where(
            DocumentModel.id == body.document_id,
            DocumentModel.client_id == client_id,
            DocumentModel.org_id == user.org_id,
        )
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    import json
    extracted = json.loads(doc.extracted_data) if doc.extracted_data else {}

    return await service.import_prior_year(
        client_id=client_id,
        document_id=body.document_id,
        tax_year=body.tax_year,
        lines=extracted,
        session=session,
        user=user,
    )
```

Add `ImportPriorRequest` to `api/models/tax_return.py`:

```python
class ImportPriorRequest(BaseModel):
    document_id: str
    tax_year: int = Field(ge=2000, le=2100)
```

Add the necessary imports at the top of `tax_returns.py`:

```python
from api.db.models import DocumentModel
```

- [ ] **Step 4: Run the multi-year tests**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_multi_year_draft.py -v --timeout=30`

Expected: All PASS.

- [ ] **Step 5: Run full tax_returns test suite for regressions**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_tax_returns.py -v --timeout=30`

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add api/routers/tax_returns.py api/models/tax_return.py
git commit -m "feat: add /prior-year and /import-prior endpoints, tax_year filter on /draft

GET /draft accepts ?tax_year=N. GET /prior-year returns stored prior-year
draft with source provenance. POST /import-prior creates draft from
uploaded 1040-Prior document extraction.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: OCR Prompt for Prior-Year 1040

**Files:**
- Create: `api/services/ocr/prompts_1040_prior.py`
- Modify: `api/services/ocr/prompts.py`

- [ ] **Step 1: Create the extraction prompt**

Create `api/services/ocr/prompts_1040_prior.py`:

```python
"""Extraction prompt for prior-year Form 1040 (filed returns)."""

PROMPT_1040_PRIOR = """Extract the following fields from this IRS Form 1040 tax return.
Return a JSON object with these exact keys. Use numeric values (no $ or commas).
If a field is blank or not present, use null.

{
  "tax_year": <4-digit year from the form header>,
  "filing_status": <"S", "MFJ", "MFS", "HOH", or "QSS">,
  "line_1a": <Line 1a - Wages, salaries, tips>,
  "line_2b": <Line 2b - Taxable interest>,
  "line_3b": <Line 3b - Qualified dividends>,
  "line_7": <Line 7 - Capital gain or loss>,
  "line_8": <Line 8 - Other income>,
  "line_9": <Line 9 - Total income>,
  "line_12": <Line 12 - Standard or itemized deduction>,
  "line_13a": <Line 13a - Qualified business income deduction>,
  "line_15": <Line 15 - Taxable income>,
  "line_16": <Line 16 - Tax>,
  "line_24": <Line 24 - Total tax>,
  "line_25a": <Line 25a - Federal tax withheld from W-2>,
  "line_25b": <Line 25b - Federal tax withheld from 1099>,
  "line_25c": <Line 25c - Other withholding>,
  "line_26": <Line 26 - Estimated tax payments>,
  "line_33": <Line 33 - Total payments>,
  "line_35a": <Line 35a - Refund amount>,
  "line_37": <Line 37 - Amount you owe>
}

Return ONLY the JSON object. No markdown, no explanation."""
```

- [ ] **Step 2: Register in prompts.py**

In `api/services/ocr/prompts.py`, add "1040-Prior" to `SUPPORTED_FORM_TYPES` (line 3) and add the prompt mapping. Find the `SUPPORTED_FORM_TYPES` list and the `_PROMPTS` dict:

Add to `SUPPORTED_FORM_TYPES`:
```python
SUPPORTED_FORM_TYPES = ["W-2", "1099-INT", "1099-DIV", "1099-B", "1099-NEC", "1098", "K-1", "1040-Prior"]
```

Add to `_PROMPTS` dict:
```python
from api.services.ocr.prompts_1040_prior import PROMPT_1040_PRIOR

# In the _PROMPTS dict:
"1040-Prior": PROMPT_1040_PRIOR,
```

- [ ] **Step 3: Commit**

```bash
git add api/services/ocr/prompts_1040_prior.py api/services/ocr/prompts.py
git commit -m "feat: add OCR extraction prompt for prior-year 1040

Extracts 18 key Form 1040 lines plus tax_year and filing_status.
Registered as '1040-Prior' form type in the OCR prompt registry.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Frontend — API Client and Types

**Files:**
- Modify: `frontend/lib/api-client.ts`

- [ ] **Step 1: Add PriorYearResponse type and new API methods**

In `frontend/lib/api-client.ts`, add the type after the existing `ComparisonReport` interface:

```typescript
export interface PriorYearResponse {
  draft: TaxReturnDraft | null;
  source_type: string;
  source_document_id: string | null;
}
```

In the `returns` section of the api object, add two new methods and update `get()` to accept optional tax_year:

```typescript
    get: (clientId: string, taxYear?: number): Promise<TaxReturnDraft | null> => {
      const params = taxYear ? `?tax_year=${taxYear}` : "";
      return fetchJson<TaxReturnDraft>(`${API_BASE}/api/clients/${clientId}/returns/draft${params}`)
        .catch(() => null);
    },
    priorYear: (clientId: string): Promise<PriorYearResponse> =>
      fetchJson<PriorYearResponse>(
        `${API_BASE}/api/clients/${clientId}/returns/prior-year`,
      ).catch(() => ({ draft: null, source_type: "computed", source_document_id: null })),
    importPrior: (clientId: string, documentId: string, taxYear: number): Promise<TaxReturnDraft> =>
      fetchJson<TaxReturnDraft>(
        `${API_BASE}/api/clients/${clientId}/returns/import-prior`,
        { method: "POST", body: JSON.stringify({ document_id: documentId, tax_year: taxYear }) },
      ),
```

Also add the same methods to the mock API (in `frontend/lib/mock-api.ts`) so mock mode doesn't break. The mock `priorYear` can return from `mockPriorYearDrafts`.

- [ ] **Step 2: TypeScript check**

Run: `cd /Users/admin-h26/taxflow-kb/frontend && npx tsc --noEmit`

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api-client.ts frontend/lib/mock-api.ts
git commit -m "feat: add priorYear() and importPrior() to frontend API client

Adds PriorYearResponse type with source provenance fields. Updates get()
to accept optional taxYear parameter. Mock API returns from existing
mockPriorYearDrafts.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Frontend — Wire Real YoY Data and Source Badge

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/components/returns/return-preview.tsx`

- [ ] **Step 1: Replace mock prior-year data in `page.tsx`**

Find the mock import (line 40) and remove it:
```typescript
// DELETE: import { mockPriorYearDrafts } from "@/lib/mock-data";
```

Find the state declaration for priorYearDraft (around line 94) and add source tracking:
```typescript
const [priorYearDraft, setPriorYearDraft] = useState<TaxReturnDraft | null>(null);
const [priorYearSource, setPriorYearSource] = useState<{ type: string; documentId: string | null }>({ type: "computed", documentId: null });
```

Replace the mock loading code (around lines 155-158 and 278-279) with:
```typescript
api.returns.priorYear(cid).then((resp) => {
  setPriorYearDraft(resp.draft);
  setPriorYearSource({ type: resp.source_type, documentId: resp.source_document_id });
});
```

Pass source metadata to `ReturnPreview`:
```typescript
priorYearSourceType={priorYearSource.type}
priorYearDocumentId={priorYearSource.documentId}
```

- [ ] **Step 2: Add source badge to `return-preview.tsx`**

Add to the `ReturnPreviewProps` interface:
```typescript
priorYearSourceType?: string;
priorYearDocumentId?: string | null;
onOpenDocument?: (docId: string) => void;
```

In the YoY header area (where the "2025 vs 2024" badge is rendered), add a source badge after it:

```typescript
{priorYearSourceType === "imported" && priorYearDocumentId && (
  <button
    onClick={() => onOpenDocument?.(priorYearDocumentId!)}
    className="inline-flex items-center gap-1 text-[10px] text-secondary hover:text-brand transition-colors cursor-pointer"
    title="View source document"
  >
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
      <path d="M4 2h5l4 4v8a1 1 0 01-1 1H4a1 1 0 01-1-1V3a1 1 0 011-1z" stroke="currentColor" strokeWidth="1.2"/>
      <path d="M9 2v4h4" stroke="currentColor" strokeWidth="1.2"/>
    </svg>
    Imported
  </button>
)}
{priorYearSourceType === "computed" && priorYear && (
  <span className="inline-flex items-center gap-1 text-[10px] text-tertiary">
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.2"/>
      <path d="M5.5 8l2 2 3.5-4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
    Computed
  </span>
)}
```

- [ ] **Step 3: TypeScript check**

Run: `cd /Users/admin-h26/taxflow-kb/frontend && npx tsc --noEmit`

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/page.tsx frontend/components/returns/return-preview.tsx
git commit -m "feat: wire real YoY data and add source provenance badge

Replaces mock prior-year data with real API call to /prior-year.
Shows 'Imported' badge (clickable, opens source doc) or 'Computed'
badge next to the YoY comparison header.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Frontend — Add 1040-Prior to Document Upload

**Files:**
- Modify: `frontend/components/documents/document-manager-modal.tsx`

- [ ] **Step 1: Add 1040-Prior form type and auto-import trigger**

In `document-manager-modal.tsx`, find the `FORM_FIELDS` definition (around line 68). Add an entry for 1040-Prior:

```typescript
"1040-Prior": [
  ["tax_year", "", "Tax Year", "text"],
  ["filing_status", "", "Filing Status", "text"],
  ["line_1a", "1a", "Wages", "money"],
  ["line_9", "9", "Total Income", "money"],
  ["line_12", "12", "Deductions", "money"],
  ["line_15", "15", "Taxable Income", "money"],
  ["line_24", "24", "Total Tax", "money"],
  ["line_33", "33", "Total Payments", "money"],
  ["line_35a", "35a", "Refund", "money"],
  ["line_37", "37", "Amount Owed", "money"],
],
```

In the upload success handler, after a "1040-Prior" document is uploaded and extracted, auto-trigger the import:

```typescript
if (formType === "1040-Prior" && uploadedDoc?.id) {
  const extracted = uploadedDoc.extracted_data ? JSON.parse(uploadedDoc.extracted_data) : {};
  const taxYear = parseInt(extracted.tax_year) || new Date().getFullYear() - 1;
  api.returns.importPrior(clientId, uploadedDoc.id, taxYear).then(() => {
    // Show success toast
  }).catch((err) => console.error("Prior year import failed:", err));
}
```

- [ ] **Step 2: TypeScript check**

Run: `cd /Users/admin-h26/taxflow-kb/frontend && npx tsc --noEmit`

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/documents/document-manager-modal.tsx
git commit -m "feat: add 1040-Prior form type with auto-import on upload

Adds '1040-Prior' to the document upload form type list. After upload
and extraction, auto-calls /import-prior to create the archived
prior-year draft. Extracts tax_year from the document.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/ -v --timeout=60`

Expected: All PASS.

- [ ] **Step 2: TypeScript check**

Run: `cd /Users/admin-h26/taxflow-kb/frontend && npx tsc --noEmit`

Expected: No errors.

- [ ] **Step 3: Verify import cycle free**

Run: `python -c "from api.tax_engine.prior_year_import import build_draft_from_lines; print('OK')"`

Expected: OK
