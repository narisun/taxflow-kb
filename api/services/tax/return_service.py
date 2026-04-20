"""TaxReturnService — orchestrates draft computation, advisory, PDF, comparison.

Extracted from :mod:`api.routers.tax_returns` so the router can stay purely
HTTP-shaped. The service:

* does not import FastAPI
* takes collaborators (encryptor, and optionally an Assembler factory) in the
  constructor, so tests override them without monkey-patching
* returns domain objects; the router is responsible for HTTP serialization
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.models import UserModel
from api.db.models import TaxReturnDraftModel
from api.models.tax_return import ReturnLine, TaxReturnDraft
from api.services.pii.encryptor import PIIEncryptor
from api.tax_engine.advisory.engine import AdvisoryEngine
from api.tax_engine.advisory.models import AdvisoryItem
from api.tax_engine.assembler import DocumentAssembler
from api.tax_engine.comparison.engine import ComparisonEngine
from api.tax_engine.comparison.models import ComparisonReport
from api.tax_engine.constants.registry import get_constants  # noqa: F401
import api.tax_engine.constants  # noqa: F401 — triggers tax-year registrations
from api.tax_engine.pdf.generator import PDFGenerator
from api.tax_engine.services.engine import TaxCalculationEngine
from api.tax_engine.validation.engine import ValidationEngine

logger = logging.getLogger(__name__)


AssemblerFactory = Callable[[], DocumentAssembler]


def _default_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


class TaxReturnService:
    """High-level orchestrator for tax-return workflows."""

    def __init__(
        self,
        *,
        encryptor: PIIEncryptor,
        assembler_factory: AssemblerFactory | None = None,
        now: Callable[[], str] = _default_now,
    ) -> None:
        self._encryptor = encryptor
        self._assembler_factory = assembler_factory or (
            lambda: DocumentAssembler(encryptor=encryptor)
        )
        self._now = now

    # --------------------------------------------------------------- draft compute

    async def compute_and_save_draft(
        self,
        client_id: str,
        session: AsyncSession,
        user: UserModel,
    ) -> TaxReturnDraft:
        """Assemble, compute, validate, and upsert the draft row."""
        from api.routers._helpers import get_client_or_404

        client = await get_client_or_404(client_id, session, user)

        assembler = self._assembler_factory()
        tax_return = await assembler.assemble(client_id, session)

        constants = get_constants(client.tax_year)
        engine = TaxCalculationEngine(constants)
        result = engine.compute(tax_return)

        validator = ValidationEngine()
        validation_results = [r.model_dump() for r in validator.validate(tax_return)]

        lines = self._extract_lines(result)

        total_income = float(result.total_income)
        ded_result = result.form_results.get("deduction")
        total_deductions = float(ded_result.total) if ded_result else 0.0
        effective_rate = (
            round(float(result.total_tax) / total_income * 100, 1)
            if total_income > 0
            else 0.0
        )

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
            computed_at=self._now(),
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

    # --------------------------------------------------------------- advisory

    async def get_advisory(
        self,
        client_id: str,
        session: AsyncSession,
        user: UserModel,
    ) -> list[AdvisoryItem]:
        from api.routers._helpers import get_client_or_404

        client = await get_client_or_404(client_id, session, user)

        assembler = self._assembler_factory()
        tax_return = await assembler.assemble(client_id, session)

        constants = get_constants(client.tax_year)
        result = TaxCalculationEngine(constants).compute(tax_return)

        return AdvisoryEngine().analyze(tax_return, result, constants)

    # --------------------------------------------------------------- pdf

    async def generate_pdf(
        self,
        client_id: str,
        session: AsyncSession,
        user: UserModel,
    ) -> tuple[bytes, str]:
        """Return ``(pdf_bytes, suggested_filename)``."""
        from api.routers._helpers import get_client_or_404

        client = await get_client_or_404(client_id, session, user)

        assembler = self._assembler_factory()
        tax_return = await assembler.assemble(client_id, session)

        constants = get_constants(client.tax_year)
        result = TaxCalculationEngine(constants).compute(tax_return)

        pdf_bytes = PDFGenerator().generate(tax_return, result)

        safe_name = client.name.replace(" ", "_") if client.name else "client"
        filename = f"1040_{safe_name}_{client.tax_year}.pdf"
        return pdf_bytes, filename

    # --------------------------------------------------------------- manifest

    async def get_manifest(
        self,
        client_id: str,
        session: AsyncSession,
        user: UserModel,
    ) -> "ReturnManifest":
        """Return form activation status and page mapping."""
        from api.routers._helpers import get_client_or_404
        from api.models.tax_return import ReturnManifest

        client = await get_client_or_404(client_id, session, user)

        assembler = self._assembler_factory()
        tax_return = await assembler.assemble(client_id, session)

        constants = get_constants(client.tax_year)
        result = TaxCalculationEngine(constants).compute(tax_return)

        return PDFGenerator().generate_manifest(tax_return, result)

    # --------------------------------------------------------------- comparison

    async def compare_years(
        self,
        client_id: str,
        prior_year: int,
        session: AsyncSession,
        user: UserModel,
    ) -> ComparisonReport:
        from api.routers._helpers import get_client_or_404

        client = await get_client_or_404(client_id, session, user)
        if prior_year == client.tax_year:
            raise ValueError("Cannot compare a year to itself")

        assembler = self._assembler_factory()

        current_return = await assembler.assemble(client_id, session)
        current_constants = get_constants(client.tax_year)
        current_result = TaxCalculationEngine(current_constants).compute(
            current_return
        )

        prior_return = await assembler.assemble(client_id, session)
        prior_return.tax_year = prior_year
        prior_constants = get_constants(prior_year)  # may raise ValueError
        prior_result = TaxCalculationEngine(prior_constants).compute(prior_return)

        return ComparisonEngine().compare(
            current_result, prior_result, client_id=client_id
        )

    # --------------------------------------------------------------- validate

    async def validate(
        self,
        client_id: str,
        session: AsyncSession,
        user: UserModel,
    ) -> dict:
        from api.routers._helpers import get_client_or_404

        await get_client_or_404(client_id, session, user)
        assembler = self._assembler_factory()
        tax_return = await assembler.assemble(client_id, session)

        results = ValidationEngine().validate(tax_return)
        return {
            "results": [r.model_dump() for r in results],
            "has_errors": any(r.severity == "ERROR" for r in results),
        }

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _extract_lines(result) -> list[ReturnLine]:
        lines: list[ReturnLine] = []
        f1040 = result.form_results.get("1040")
        if not f1040:
            return lines
        for line_num, trace in sorted(f1040.lines.items()):
            section = "income"
            if line_num in ("12", "13a", "15"):
                section = "deductions"
            elif line_num in ("16", "23", "24"):
                section = "tax_credits"
            elif line_num in ("25", "26", "33", "35a", "37"):
                section = "payments"
            lines.append(
                ReturnLine(
                    number=line_num,
                    label=trace.label,
                    value=float(trace.value),
                    section=section,
                )
            )
        return lines
