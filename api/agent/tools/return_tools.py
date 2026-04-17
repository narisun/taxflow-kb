"""Tax-return draft agent tools — read-only access to computed return data."""
from __future__ import annotations

import json

from sqlalchemy import select

from api.agent.session import AgentSession
from api.db.models import DocumentModel, TaxReturnDraftModel

# Maps 1040 line numbers to the form types and field keys that feed them.
_LINE_SOURCE_MAP: dict[str, list[dict]] = {
    "1a": [{"form_type": "W-2", "field": "box1_wages", "label": "W-2 Wages"}],
    "2b": [{"form_type": "1099-INT", "field": "box1_interest", "label": "1099-INT Interest income"}],
    "3a": [{"form_type": "1099-DIV", "field": "box1b_qualified_dividends", "label": "1099-DIV Qualified dividends"}],
    "3b": [{"form_type": "1099-DIV", "field": "box1a_ordinary_dividends", "label": "1099-DIV Ordinary dividends"}],
    "7": [{"form_type": "1099-B", "field": "short_term_proceeds", "label": "1099-B Capital gain/loss"}],
    "8": [{"form_type": "1099-NEC", "field": "nec_compensation", "label": "1099-NEC Other income"}],
    "8a": [{"form_type": "K-1", "field": "box1_ordinary_income", "label": "K-1 Business income"}],
    "10": [{"form_type": "1098", "field": "box1_interest", "label": "1098 Mortgage interest deduction"}],
}


async def get_return_draft(session: AgentSession) -> dict:
    """Load the latest tax return draft for the current client."""
    db = session.db_session

    stmt = (
        select(TaxReturnDraftModel)
        .where(TaxReturnDraftModel.org_id == session.org_id)
        .where(TaxReturnDraftModel.client_id == session.client_id)
    )
    result = await db.execute(stmt)
    draft: TaxReturnDraftModel | None = result.scalar_one_or_none()

    if draft is None:
        return {
            "status": "not_computed",
            "message": "No tax return draft has been computed for this client yet.",
        }

    # Parse the draft JSON
    draft_data: dict = {}
    if draft.draft_json:
        try:
            draft_data = json.loads(draft.draft_json)
        except (json.JSONDecodeError, TypeError):
            draft_data = {}

    return {
        "status": draft_data.get("status", "draft"),
        "tax_year": draft.tax_year,
        "filing_status": draft.filing_status,
        "total_income": draft_data.get("total_income"),
        "taxable_income": draft_data.get("taxable_income"),
        "total_tax": draft_data.get("total_tax"),
        "total_payments": draft_data.get("total_payments"),
        "refund_or_owed": draft_data.get("refund_or_owed"),
        "effective_rate": draft_data.get("effective_rate"),
        "lines": draft_data.get("lines", []),
    }


async def get_return_line_detail(session: AgentSession, *, line_number: str) -> dict:
    """Drill into a specific 1040 line, showing contributing document sources."""
    db = session.db_session

    # Load draft
    draft_stmt = (
        select(TaxReturnDraftModel)
        .where(TaxReturnDraftModel.org_id == session.org_id)
        .where(TaxReturnDraftModel.client_id == session.client_id)
    )
    draft_result = await db.execute(draft_stmt)
    draft: TaxReturnDraftModel | None = draft_result.scalar_one_or_none()

    if draft is None:
        return {"error": "no_draft", "message": "No tax return draft found."}

    draft_data: dict = {}
    if draft.draft_json:
        try:
            draft_data = json.loads(draft.draft_json)
        except (json.JSONDecodeError, TypeError):
            draft_data = {}

    # Find the requested line in the lines array
    lines = draft_data.get("lines", [])
    target_line = None
    for line in lines:
        if str(line.get("number", "")) == line_number:
            target_line = line
            break

    if target_line is None:
        return {"error": "line_not_found", "message": f"Line {line_number} not found in draft."}

    # Load approved documents to cross-reference contributing sources
    doc_stmt = (
        select(DocumentModel)
        .where(DocumentModel.org_id == session.org_id)
        .where(DocumentModel.client_id == session.client_id)
        .where(DocumentModel.status == "approved")
    )
    doc_result = await db.execute(doc_stmt)
    approved_docs: list[DocumentModel] = list(doc_result.scalars().all())

    # Build contributing sources from the line-source map
    contributing_sources: list[dict] = []
    source_mappings = _LINE_SOURCE_MAP.get(line_number, [])

    for mapping in source_mappings:
        for doc in approved_docs:
            if doc.form_type == mapping["form_type"]:
                extracted: dict = {}
                if doc.extracted_data:
                    try:
                        extracted = json.loads(doc.extracted_data)
                    except (json.JSONDecodeError, TypeError):
                        pass
                field_value = extracted.get(mapping["field"])
                contributing_sources.append({
                    "doc_id": doc.id,
                    "form_type": doc.form_type,
                    "file_name": doc.file_name,
                    "field": mapping["field"],
                    "label": mapping["label"],
                    "value": field_value,
                })

    return {
        "line_number": target_line.get("number"),
        "label": target_line.get("label", ""),
        "value": target_line.get("value"),
        "section": target_line.get("section", ""),
        "contributing_sources": contributing_sources,
    }
