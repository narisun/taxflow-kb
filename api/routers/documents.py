"""Document management endpoints."""
import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
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


class FieldEditRequest(PydanticBaseModel):
    field_name: str
    value: str

router = APIRouter(prefix="/api", tags=["documents"])

UPLOAD_DIR = Path("uploads")
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
}


def _get_ocr_extractor() -> OCRExtractor:
    """Select extractor based on config."""
    if os.getenv("OCR_EXTRACTOR", "mock") == "claude":
        import anthropic
        from api.services.ocr.claude_extractor import ClaudeVisionExtractor
        return ClaudeVisionExtractor(anthropic.Anthropic())
    from api.services.ocr.mock_extractor import MockOCRExtractor
    return MockOCRExtractor()


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

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    safe_name = _sanitize_filename(file.filename or "upload")

    # Run extraction
    extraction = await _ocr.extract("", form_type)

    # Store as structured JSON dict (model-ready)
    extracted_data = json.dumps(extraction.structured_data)
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
        extracted_data=extracted_data,
        flags=flags,
        org_id=user.org_id,
        created_by=user.id,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    doc_dir = UPLOAD_DIR / str(doc.id)
    doc_dir.mkdir(parents=True, exist_ok=True)
    file_path = doc_dir / safe_name
    file_path.write_bytes(content)

    doc.file_path = str(file_path)
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
