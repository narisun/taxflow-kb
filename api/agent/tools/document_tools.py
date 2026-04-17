"""Document-scoped agent tools — SSN masking, client isolation."""
from __future__ import annotations

import json
import logging

from sqlalchemy import select

from api.agent.session import AgentSession
from api.auth.models import UserModel
from api.db.models import DocumentModel
from api.services.ocr.field_mapping import get_display_label
from api.services.pii.masking import mask_ssns_in_payload

logger = logging.getLogger(__name__)


async def list_documents(session: AgentSession) -> dict:
    """Return metadata for every document belonging to the current client."""
    db = session.db_session

    stmt = (
        select(DocumentModel)
        .where(DocumentModel.org_id == session.org_id)
        .where(DocumentModel.client_id == session.client_id)
    )
    result = await db.execute(stmt)
    docs: list[DocumentModel] = list(result.scalars().all())

    # Collect unique user ids for name resolution
    user_ids: set[str] = set()
    for doc in docs:
        if doc.created_by:
            user_ids.add(doc.created_by)
        if doc.reviewed_by:
            user_ids.add(doc.reviewed_by)

    user_names: dict[str, str] = {}
    if user_ids:
        user_stmt = (
            select(UserModel.id, UserModel.name)
            .where(UserModel.id.in_(list(user_ids)))
        )
        user_result = await db.execute(user_stmt)
        for uid, uname in user_result.all():
            user_names[uid] = uname

    documents = []
    for doc in docs:
        flags_count = 0
        if doc.flags:
            try:
                flags_count = len(json.loads(doc.flags))
            except (json.JSONDecodeError, TypeError):
                pass

        documents.append({
            "doc_id": doc.id,
            "form_type": doc.form_type,
            "file_name": doc.file_name,
            "title": doc.title,
            "status": doc.status,
            "confidence": doc.confidence,
            "flags_count": flags_count,
            "uploaded_by": user_names.get(doc.created_by, doc.created_by) if doc.created_by else None,
            "uploaded_at": doc.created_at.isoformat() if doc.created_at else None,
            "reviewed_by": user_names.get(doc.reviewed_by, doc.reviewed_by) if doc.reviewed_by else None,
            "reviewed_at": doc.reviewed_at.isoformat() if doc.reviewed_at else None,
        })

    return {"documents": documents, "count": len(documents)}


async def get_document_fields(session: AgentSession, *, doc_id: str) -> dict:
    """Return extracted fields for a single document with SSNs masked.

    Enforces client isolation: the document must belong to session.client_id.
    """
    db = session.db_session

    stmt = (
        select(DocumentModel)
        .where(DocumentModel.org_id == session.org_id)
        .where(DocumentModel.id == doc_id)
    )
    result = await db.execute(stmt)
    doc: DocumentModel | None = result.scalar_one_or_none()

    if doc is None:
        return {"error": "document_not_found"}

    # Client isolation check
    if doc.client_id != session.client_id:
        logger.warning(
            "Client isolation violation: session.client_id=%s tried to access doc %s owned by client_id=%s",
            session.client_id,
            doc_id,
            doc.client_id,
        )
        return {"error": "access_denied", "message": "Document belongs to a different client"}

    # Parse extracted data
    raw_data: dict = {}
    if doc.extracted_data:
        try:
            raw_data = json.loads(doc.extracted_data)
        except (json.JSONDecodeError, TypeError):
            raw_data = {}

    # Mask SSNs
    masked_data = mask_ssns_in_payload(raw_data)

    # Build labelled fields list
    fields = []
    for key, value in masked_data.items():
        fields.append({
            "field_name": key,
            "display_label": get_display_label(doc.form_type, key),
            "value": value,
        })

    return {
        "doc_id": doc.id,
        "form_type": doc.form_type,
        "file_name": doc.file_name,
        "fields": fields,
    }
