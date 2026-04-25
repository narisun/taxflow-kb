"""Tax computation and validation tools for the client agent.

These tools wrap TaxReturnService methods, making them callable by Claude
through the AgentService tool-use loop. All tools receive AgentSession
and use session.client_id for scoping.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.agent.session import AgentSession
from api.db.models import ClientModel, DocumentModel

logger = logging.getLogger(__name__)


async def _load_client(session: AgentSession) -> ClientModel | None:
    result = await session.db_session.execute(
        select(ClientModel).where(
            ClientModel.id == session.client_id,
            ClientModel.org_id == session.org_id,
        )
    )
    return result.scalar_one_or_none()


async def _load_approved_docs(session: AgentSession) -> list[DocumentModel]:
    result = await session.db_session.execute(
        select(DocumentModel).where(
            DocumentModel.client_id == session.client_id,
            DocumentModel.org_id == session.org_id,
            DocumentModel.status.in_(["approved", "verified"]),
        )
    )
    return list(result.scalars().all())


def _get_tax_service(session: AgentSession):
    from api.services.tax import TaxReturnService
    return TaxReturnService(encryptor=session.pii_encryptor)


async def _get_user(session: AgentSession):
    from api.auth.models import UserModel
    result = await session.db_session.execute(
        select(UserModel).where(UserModel.id == session.user_id)
    )
    return result.scalar_one_or_none()


def _ssn_last4(ssn: str) -> str:
    """Extract last 4 digits from an SSN, whether masked or unmasked."""
    digits = re.sub(r"\D", "", ssn)
    return digits[-4:] if len(digits) >= 4 else ""


async def validate_intake_vs_documents(session: AgentSession) -> dict:
    """Cross-check intake form data against extracted document data."""
    client = await _load_client(session)
    if not client:
        return {"error": "Client not found"}

    docs = await _load_approved_docs(session)
    if not docs:
        return {"mismatches": [], "summary": "No approved documents to validate against."}

    enc = session.pii_encryptor
    intake_ssn = enc.decrypt(client.primary_ssn_enc) if client.primary_ssn_enc else None
    intake_name = f"{client.primary_first_name or ''} {client.primary_last_name or ''}".strip()
    intake_city = (client.city or "").strip().lower()
    intake_state = (client.state or "").strip().upper()

    mismatches = []

    for doc in docs:
        extracted: dict = {}
        if doc.extracted_data:
            try:
                extracted = json.loads(doc.extracted_data)
            except (json.JSONDecodeError, TypeError):
                continue

        doc_ref = f"{doc.form_type} ({doc.file_name or doc.id[:8]})"

        # SSN check — compare last 4 digits only. Document SSNs may be
        # stored masked (***-**-6789) while intake SSNs are decrypted to
        # full plaintext, so a direct string comparison would false-positive.
        doc_ssn = extracted.get("employee_ssn") or extracted.get("recipient_ssn")
        intake_last4 = _ssn_last4(intake_ssn) if intake_ssn else ""
        doc_last4 = _ssn_last4(doc_ssn) if doc_ssn else ""
        if intake_last4 and doc_last4 and intake_last4 != doc_last4:
            mismatches.append({
                "field": "ssn",
                "intake_value": f"***-**-{intake_ssn[-4:]}",
                "document_value": f"***-**-{doc_ssn[-4:]}",
                "document": doc_ref,
                "document_id": doc.id,
                "form_type": doc.form_type,
                "severity": "critical",
            })

        # Name check
        doc_name = extracted.get("employee_name", "").strip()
        if not doc_name:
            first = extracted.get("employee_first_name", "")
            last = extracted.get("employee_last_name", "")
            doc_name = f"{first} {last}".strip()
        if intake_name and doc_name and intake_name.lower() != doc_name.lower():
            mismatches.append({
                "field": "name",
                "intake_value": intake_name,
                "document_value": doc_name,
                "document": doc_ref,
                "document_id": doc.id,
                "form_type": doc.form_type,
                "severity": "warning",
            })

        # Address — state check
        doc_state = extracted.get("box15_state", "").strip().upper()
        doc_addr = extracted.get("employee_address", "")
        if intake_state and doc_state and intake_state != doc_state:
            mismatches.append({
                "field": "state",
                "intake_value": intake_state,
                "document_value": doc_state,
                "document": doc_ref,
                "document_id": doc.id,
                "form_type": doc.form_type,
                "severity": "warning",
            })
        elif intake_city and doc_addr:
            if intake_city not in doc_addr.lower():
                mismatches.append({
                    "field": "city",
                    "intake_value": client.city,
                    "document_value": doc_addr,
                    "document": doc_ref,
                    "document_id": doc.id,
                    "form_type": doc.form_type,
                    "severity": "info",
                })

    critical = sum(1 for m in mismatches if m["severity"] == "critical")
    warnings = sum(1 for m in mismatches if m["severity"] == "warning")

    if not mismatches:
        summary = f"All {len(docs)} document(s) match the intake data. No discrepancies found."
    else:
        summary = f"Found {len(mismatches)} discrepancy(ies) across {len(docs)} document(s): {critical} critical, {warnings} warnings."

    return {"mismatches": mismatches, "summary": summary, "documents_checked": len(docs)}


async def compute_tax_return(session: AgentSession) -> dict:
    """Run full tax computation, save draft, return results."""
    service = _get_tax_service(session)
    user = await _get_user(session)
    if not user:
        return {"error": "User not found"}

    try:
        draft = await service.compute_and_save_draft(
            client_id=session.client_id, session=session.db_session, user=user,
        )
    except Exception as exc:
        logger.warning("compute_tax_return failed: %s", exc)
        return {"error": f"Computation failed: {exc}"}

    return {
        "status": "computed",
        "tax_year": draft.tax_year,
        "filing_status": draft.filing_status,
        "total_income": draft.total_income,
        "total_deductions": getattr(draft, "total_deductions", 0),
        "taxable_income": draft.taxable_income,
        "total_tax": draft.total_tax,
        "total_payments": draft.total_payments,
        "refund_or_owed": draft.refund_or_owed,
        "effective_rate": draft.effective_rate,
    }


async def run_advisory_analysis(session: AgentSession) -> dict:
    """Run 12 advisory rules and return tax-saving recommendations."""
    service = _get_tax_service(session)
    user = await _get_user(session)
    if not user:
        return {"error": "User not found"}

    try:
        items = await service.get_advisory(
            client_id=session.client_id, session=session.db_session, user=user,
        )
    except Exception as exc:
        logger.warning("run_advisory_analysis failed: %s", exc)
        return {"error": f"Advisory analysis failed: {exc}"}

    recommendations = [
        {
            "title": item.title,
            "detail": item.detail,
            "estimated_savings": float(item.estimated_savings) if hasattr(item, "estimated_savings") else 0,
        }
        for item in items
    ]

    total_savings = sum(r["estimated_savings"] for r in recommendations)

    return {
        "recommendations": recommendations,
        "total_potential_savings": total_savings,
        "count": len(recommendations),
    }


async def compare_prior_year(session: AgentSession, *, prior_year: int | None = None) -> dict:
    """Year-over-year comparison of key tax return lines."""
    service = _get_tax_service(session)
    user = await _get_user(session)
    if not user:
        return {"error": "User not found"}

    client = await _load_client(session)
    if not client:
        return {"error": "Client not found"}

    year = prior_year or (client.tax_year - 1)

    try:
        report = await service.compare_years(
            client_id=session.client_id, prior_year=year,
            session=session.db_session, user=user,
        )
    except Exception as exc:
        logger.warning("compare_prior_year failed: %s", exc)
        return {"error": f"Year comparison failed: {exc}"}

    sections = []
    for section in report.sections:
        rows = [
            {
                "label": row.label,
                "current": float(row.current) if row.current else 0,
                "prior": float(row.prior) if row.prior else 0,
                "change": float(row.change) if row.change else 0,
                "pct_change": float(row.pct_change) if row.pct_change else 0,
            }
            for row in section.rows
        ]
        sections.append({"name": section.title, "rows": rows})

    summary = {
        "current_refund": float(report.summary.current) if report.summary else 0,
        "prior_refund": float(report.summary.prior) if report.summary else 0,
        "change": float(report.summary.change) if report.summary else 0,
    }

    return {"sections": sections, "summary": summary, "current_year": client.tax_year, "prior_year": year}


async def run_validation_rules(session: AgentSession) -> dict:
    """Run structural validation rules on the tax return."""
    service = _get_tax_service(session)
    user = await _get_user(session)
    if not user:
        return {"error": "User not found"}

    try:
        result = await service.validate(
            client_id=session.client_id, session=session.db_session, user=user,
        )
    except Exception as exc:
        logger.warning("run_validation_rules failed: %s", exc)
        return {"error": f"Validation failed: {exc}"}

    return result
