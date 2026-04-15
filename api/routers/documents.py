"""Document management endpoints."""
import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi.responses import Response
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import DocumentModel
from api.models.document import (
    DocumentResponse,
    DocumentListResponse,
    ExtractedField,
)
from api.models.enums import FormType
from api.auth.dependencies import get_current_user, require_role
from api.auth.models import UserModel
from api.routers._helpers import get_client_or_404
from api.services.ocr.protocol import OCRExtractor
from api.services.ocr.field_mapping import get_display_label
from api.services.pii.encryptor import get_pii_encryptor


class FieldEditRequest(PydanticBaseModel):
    field_name: str
    value: str

router = APIRouter(prefix="/api", tags=["documents"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
}


def _get_ocr_extractor() -> OCRExtractor:
    """Select extractor based on config.

    Modes:
    - 'cascade' (default): Text layer first → Claude Vision fallback
    - 'claude': Claude Vision only (all docs sent to API)
    - 'mock': Hardcoded mock data (dev/test)
    """
    mode = os.getenv("OCR_EXTRACTOR", "cascade")

    if mode == "claude":
        import anthropic
        from api.services.ocr.claude_extractor import ClaudeVisionExtractor
        return ClaudeVisionExtractor(anthropic.Anthropic())

    if mode == "mock":
        from api.services.ocr.mock_extractor import MockOCRExtractor
        return MockOCRExtractor()

    # Default: cascade (text layer → vision fallback)
    from api.services.ocr.cascading_extractor import CascadingExtractor
    vision = None
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        import anthropic
        from api.services.ocr.claude_extractor import ClaudeVisionExtractor
        vision = ClaudeVisionExtractor(anthropic.Anthropic(api_key=api_key))
    return CascadingExtractor(vision_extractor=vision)


_ocr = _get_ocr_extractor()


def _sanitize_filename(filename: str) -> str:
    name = os.path.basename(filename)
    name = re.sub(r"[^\w.\-]", "_", name)
    return name or "upload"


@router.get("/clients/{client_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    client_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
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
    docs = result.scalars().all()
    return DocumentListResponse(items=docs, total=total, page=page, page_size=page_size)


@router.post(
    "/clients/{client_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    client_id: int,
    form_type: FormType = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
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

    # Run extraction with actual file content
    extraction = await _ocr.extract(file_bytes, form_type)

    # Encrypt extracted data and file content
    enc = get_pii_encryptor()

    extracted_data_json = json.dumps(extraction.structured_data)
    extracted_data_enc = enc.fernet.encrypt(extracted_data_json.encode("utf-8"))
    file_content_enc = enc.fernet.encrypt(file_bytes)

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
        extracted_data=extracted_data_json,  # Keep plaintext for backward compat (fields endpoint)
        extracted_data_enc=extracted_data_enc,
        file_content_enc=file_content_enc,
        file_content_type=file.content_type or "application/pdf",
        file_name=safe_name,
        flags=flags,
        org_id=user.org_id,
        created_by=user.id,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
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
    return doc


@router.get("/documents/{doc_id}/file")
async def download_document_file(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    """Download the original uploaded file."""
    result = await session.execute(
        select(DocumentModel).where(DocumentModel.id == doc_id, DocumentModel.org_id == user.org_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.file_content_enc:
        raise HTTPException(status_code=404, detail="File content not available")

    enc = get_pii_encryptor()
    file_bytes = enc.fernet.decrypt(doc.file_content_enc)

    return Response(
        content=file_bytes,
        media_type=doc.file_content_type or "application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.file_name or "document.pdf"}"'},
    )


@router.patch("/documents/{doc_id}/approve", response_model=DocumentResponse)
async def approve_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
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
    await session.commit()
    await session.refresh(doc)
    return doc


@router.get("/documents/{doc_id}/fields", response_model=list[ExtractedField])
async def get_document_fields(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
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
        raw = {}

    # Handle both structured dict format (new) and list format (legacy)
    if isinstance(raw, dict):
        fields = []
        for key, value in raw.items():
            label = get_display_label(doc.form_type, key)
            fields.append(ExtractedField(
                name=key, value=str(value), confidence=doc.confidence,
                label=label,
            ))
        return fields
    elif isinstance(raw, list):
        return [ExtractedField(**f) for f in raw]
    return []


@router.patch("/documents/{doc_id}/fields")
async def edit_document_field(
    doc_id: int,
    edit: FieldEditRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
):
    """Edit an extracted field and reset document status to review."""
    result = await session.execute(
        select(DocumentModel).where(DocumentModel.id == doc_id, DocumentModel.org_id == user.org_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Parse current extracted data
    try:
        data = json.loads(doc.extracted_data) if doc.extracted_data else {}
    except (json.JSONDecodeError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}

    # Update the field
    data[edit.field_name] = edit.value

    # Save back and reset status
    doc.extracted_data = json.dumps(data)
    doc.status = "review"
    await session.commit()
    await session.refresh(doc)
    return {"status": doc.status, "updated_field": edit.field_name}


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
):
    """Delete a document."""
    result = await session.execute(
        select(DocumentModel).where(
            DocumentModel.id == doc_id,
            DocumentModel.org_id == user.org_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await session.delete(doc)
    await session.commit()
