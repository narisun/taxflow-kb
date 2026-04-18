"""Document management endpoints.

Thin HTTP layer. Business logic (extraction, encryption, SSN masking, draft
recompute) lives in services. The router receives collaborators via
``Depends`` from :mod:`api.dependencies`, so endpoints are unit-testable by
swapping dependency overrides.
"""
from __future__ import annotations

import json
import logging
import os
import re

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from api.auth.dependencies import get_current_user, require_onboarded_user, require_role
from api.auth.models import UserModel
from api.db.engine import get_session
from api.db.models import DocumentModel
from api.dependencies import OCRExtractorDep, PIIEncryptorDep
from api.models.document import DocumentListResponse, DocumentResponse, ExtractedField
from api.models.enums import FormType
from api.routers._helpers import get_client_or_404
from api.services.ocr.field_mapping import get_display_label
from api.services.pii.masking import mask_ssns_in_payload

logger = logging.getLogger(__name__)


class FieldEditRequest(PydanticBaseModel):
    field_name: str
    value: str


router = APIRouter(prefix="/api", tags=["documents"])


async def _resolve_user_names(
    session: AsyncSession, user_ids: set[str]
) -> dict[str, str]:
    """Batch-load user.name for a set of user IDs. Single query, used to
    decorate document responses with uploader/reviewer names without N+1s."""
    if not user_ids:
        return {}
    rows = await session.execute(
        select(UserModel.id, UserModel.name).where(UserModel.id.in_(user_ids))
    )
    return {uid: name for uid, name in rows.all()}


def _doc_to_response(
    doc: DocumentModel, name_by_id: dict[str, str]
) -> DocumentResponse:
    """Build a DocumentResponse from a DB row + a pre-resolved name lookup."""
    return DocumentResponse(
        id=doc.id,
        client_id=doc.client_id,
        form_type=doc.form_type,
        title=doc.title,
        status=doc.status,
        confidence=doc.confidence,
        extracted_data=doc.extracted_data,
        flags=doc.flags,
        file_name=doc.file_name or "",
        created_at=doc.created_at,
        created_by=doc.created_by,
        created_by_name=name_by_id.get(doc.created_by) if doc.created_by else None,
        reviewed_at=doc.reviewed_at,
        reviewed_by=doc.reviewed_by,
        reviewed_by_name=name_by_id.get(doc.reviewed_by) if doc.reviewed_by else None,
    )

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
}


def _sanitize_filename(filename: str) -> str:
    name = os.path.basename(filename)
    name = re.sub(r"[^\w.\-]", "_", name)
    return name or "upload"


@router.get("/clients/{client_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    client_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    await get_client_or_404(client_id, session, user)
    base = select(DocumentModel).where(
        DocumentModel.client_id == client_id,
        DocumentModel.org_id == user.org_id,
    )
    count_q = select(func.count()).select_from(base.subquery())
    count_result = await session.execute(count_q)
    total = count_result.scalar() or 0
    paginated = base.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(paginated)
    docs = list(result.scalars().all())
    user_ids = {d.created_by for d in docs if d.created_by} | {
        d.reviewed_by for d in docs if d.reviewed_by
    }
    names = await _resolve_user_names(session, user_ids)
    items = [_doc_to_response(d, names) for d in docs]
    return DocumentListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.post(
    "/clients/{client_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    client_id: str,
    form_type: FormType = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
    ocr: OCRExtractorDep = None,
    encryptor: PIIEncryptorDep = None,
):
    await get_client_or_404(client_id, session, user)

    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File type '{file.content_type}' not allowed. Accepted: PDF, PNG, JPEG, TIFF.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    safe_name = _sanitize_filename(file.filename or "upload")

    # Extract with injected OCR strategy.
    extraction = await ocr.extract(file_bytes, form_type)

    # Encrypted column carries the full extracted data.
    full_payload_json = json.dumps(extraction.structured_data)
    extracted_data_enc = encryptor.fernet.encrypt(full_payload_json.encode("utf-8"))
    file_content_enc = encryptor.fernet.encrypt(file_bytes)

    # Plaintext column carries an SSN-masked variant until Phase C removes it.
    masked_payload = mask_ssns_in_payload(extraction.structured_data)
    masked_payload_json = json.dumps(masked_payload)

    flags = json.dumps(extraction.flags)
    confidence = extraction.overall_confidence
    has_flags = extraction.has_flags
    doc_status = "review" if (has_flags or confidence < 0.90) else "verified"

    doc = DocumentModel(
        client_id=client_id,
        form_type=form_type,
        title=f"{form_type} ({safe_name})",
        status=doc_status,
        confidence=confidence,
        extracted_data=masked_payload_json,
        extracted_data_enc=extracted_data_enc,
        file_content_enc=file_content_enc,
        file_content_type=file.content_type or "application/pdf",
        file_name=safe_name,
        flags=flags,
        org_id=user.org_id,
        created_by=user.id,
    )
    session.add(doc)

    # Advance workflow: intake → documents on first upload
    from api.services.workflow import on_document_uploaded
    await on_document_uploaded(session, client_id, user.org_id)

    await session.commit()
    await session.refresh(doc)
    names = await _resolve_user_names(session, {doc.created_by} if doc.created_by else set())
    return _doc_to_response(doc, names)


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    result = await session.execute(
        select(DocumentModel).where(
            DocumentModel.id == doc_id,
            DocumentModel.org_id == user.org_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    user_ids = {x for x in (doc.created_by, doc.reviewed_by) if x}
    names = await _resolve_user_names(session, user_ids)
    return _doc_to_response(doc, names)


@router.get("/documents/{doc_id}/file")
async def download_document_file(
    doc_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
    encryptor: PIIEncryptorDep = None,
):
    """Download the original uploaded file."""
    result = await session.execute(
        select(DocumentModel).where(
            DocumentModel.id == doc_id, DocumentModel.org_id == user.org_id
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.file_content_enc:
        raise HTTPException(status_code=404, detail="File content not available")

    file_bytes = encryptor.fernet.decrypt(doc.file_content_enc)

    return Response(
        content=file_bytes,
        media_type=doc.file_content_type or "application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{doc.file_name or "document.pdf"}"'
        },
    )


@router.patch("/documents/{doc_id}/approve", response_model=DocumentResponse)
async def approve_document(
    doc_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
    encryptor: PIIEncryptorDep = None,
):
    result = await session.execute(
        select(DocumentModel).where(
            DocumentModel.id == doc_id,
            DocumentModel.org_id == user.org_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.status = "approved"
    # Stamp the review audit fields. Naive UTC to match the rest of the
    # schema (TenantMixin uses naive timestamps as well — see api/db/base.py).
    doc.reviewed_by = user.id
    doc.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)

    # Advance workflow: documents → review when all docs approved
    from api.services.workflow import on_document_approved
    await on_document_approved(session, doc.client_id, user.org_id)

    await session.commit()
    await session.refresh(doc)

    # Auto-recompute draft after approval. Failures are logged but do not
    # fail the approve request — the draft can be regenerated on demand.
    from api.services.tax import TaxReturnService

    service = TaxReturnService(encryptor=encryptor)
    try:
        await service.compute_and_save_draft(doc.client_id, session, user)
    except Exception:
        logger.exception(
            "Draft recompute failed after approving doc_id=%s (client_id=%s)",
            doc.id,
            doc.client_id,
        )

    user_ids = {x for x in (doc.created_by, doc.reviewed_by) if x}
    names = await _resolve_user_names(session, user_ids)
    return _doc_to_response(doc, names)


@router.get("/documents/{doc_id}/fields", response_model=list[ExtractedField])
async def get_document_fields(
    doc_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    result = await session.execute(
        select(DocumentModel).where(
            DocumentModel.id == doc_id,
            DocumentModel.org_id == user.org_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        raw = json.loads(doc.extracted_data)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Malformed extracted_data for doc_id=%s", doc_id)
        raw = {}

    if isinstance(raw, dict):
        fields = []
        for key, value in raw.items():
            label = get_display_label(doc.form_type, key)
            fields.append(
                ExtractedField(
                    name=key,
                    value=str(value),
                    confidence=doc.confidence,
                    label=label,
                )
            )
        return fields
    if isinstance(raw, list):
        return [ExtractedField(**f) for f in raw]
    return []


@router.patch("/documents/{doc_id}/fields")
async def edit_document_field(
    doc_id: str,
    edit: FieldEditRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
):
    """Edit an extracted field and reset document status to review."""
    result = await session.execute(
        select(DocumentModel).where(
            DocumentModel.id == doc_id, DocumentModel.org_id == user.org_id
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        data = json.loads(doc.extracted_data) if doc.extracted_data else {}
    except (json.JSONDecodeError, TypeError):
        logger.warning("Malformed extracted_data on edit for doc_id=%s", doc_id)
        data = {}
    if not isinstance(data, dict):
        data = {}

    # Apply edit, then re-mask (user may paste raw SSN).
    data[edit.field_name] = edit.value
    masked = mask_ssns_in_payload(data)

    doc.extracted_data = json.dumps(masked)
    doc.status = "review"
    await session.commit()
    await session.refresh(doc)
    return {"status": doc.status, "updated_field": edit.field_name}


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
    encryptor: PIIEncryptorDep = None,
):
    """Delete a document. Recomputes the draft afterwards."""
    result = await session.execute(
        select(DocumentModel).where(
            DocumentModel.id == doc_id,
            DocumentModel.org_id == user.org_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    client_id = doc.client_id
    await session.delete(doc)
    await session.commit()

    from api.services.tax import TaxReturnService

    service = TaxReturnService(encryptor=encryptor)
    try:
        await service.compute_and_save_draft(client_id, session, user)
    except Exception:
        logger.exception(
            "Draft recompute failed after deleting doc_id=%s (client_id=%s)",
            doc_id,
            client_id,
        )
