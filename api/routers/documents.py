"""Document management endpoints."""
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import DocumentModel, ClientModel
from api.models.document import (
    DocumentResponse,
    DocumentListResponse,
    ExtractedField,
    ExtractionResult,
)
from api.auth.dependencies import get_current_user
from api.auth.models import UserModel
from api.services.ocr.mock_extractor import MockOCRExtractor

router = APIRouter(tags=["documents"])

UPLOAD_DIR = Path("uploads")
_ocr = MockOCRExtractor()


def _mock_extract(form_type: str) -> tuple[str, float, str]:
    """Return (extracted_data_json, confidence, flags_json) for mock OCR."""
    if form_type == "W-2":
        fields = [
            {"name": "Box 1 — Wages", "value": "$112,400.00", "confidence": 0.99, "flagged": False, "flag_reason": ""},
            {"name": "Box 2 — Federal Tax Withheld", "value": "$18,750.00", "confidence": 0.99, "flagged": False, "flag_reason": ""},
            {"name": "Employer", "value": "ACME CORPORATION", "confidence": 0.97, "flagged": False, "flag_reason": ""},
        ]
        return json.dumps(fields), 0.99, "[]"
    elif form_type == "1099-INT":
        fields = [
            {"name": "Box 1 — Interest Income", "value": "$3,847.00", "confidence": 0.96, "flagged": False, "flag_reason": ""},
            {"name": "Account Number", "value": "••••8821", "confidence": 0.82, "flagged": True, "flag_reason": "Partially illegible"},
        ]
        return json.dumps(fields), 0.82, json.dumps(["Account number 82% confidence"])
    elif form_type == "1098":
        fields = [
            {"name": "Box 1 — Mortgage Interest", "value": "$14,220.00", "confidence": 0.98, "flagged": False, "flag_reason": ""},
            {"name": "Lender", "value": "FIRST NATIONAL BANK", "confidence": 0.95, "flagged": False, "flag_reason": ""},
        ]
        return json.dumps(fields), 0.95, "[]"
    elif form_type == "1099-B":
        fields = [
            {"name": "1d — Proceeds", "value": "$52,300.00", "confidence": 0.94, "flagged": False, "flag_reason": ""},
            {"name": "1e — Cost Basis", "value": "$48,100.00", "confidence": 0.91, "flagged": False, "flag_reason": ""},
            {"name": "Date Sold", "value": "09/15/2024", "confidence": 0.78, "flagged": True, "flag_reason": "Date partially obscured"},
        ]
        return json.dumps(fields), 0.78, json.dumps(["Date sold 78% confidence"])
    elif form_type == "K-1":
        fields = [
            {"name": "Box 1 — Ordinary Business Income", "value": "$8,400.00", "confidence": 0.93, "flagged": False, "flag_reason": ""},
            {"name": "Partnership Name", "value": "SMITH HOLDINGS LLC", "confidence": 0.90, "flagged": False, "flag_reason": ""},
        ]
        return json.dumps(fields), 0.90, "[]"
    elif form_type == "1099-NEC":
        fields = [
            {"name": "Box 1 — Nonemployee Compensation", "value": "$15,000.00", "confidence": 0.96, "flagged": False, "flag_reason": ""},
            {"name": "Payer Name", "value": "CONSULTING INC", "confidence": 0.94, "flagged": False, "flag_reason": ""},
        ]
        return json.dumps(fields), 0.96, "[]"
    elif form_type == "1099-DIV":
        fields = [
            {"name": "Box 1a — Total Dividends", "value": "$2,450.00", "confidence": 0.97, "flagged": False, "flag_reason": ""},
            {"name": "Box 1b — Qualified Dividends", "value": "$1,800.00", "confidence": 0.95, "flagged": False, "flag_reason": ""},
        ]
        return json.dumps(fields), 0.97, "[]"
    # Generic fallback — returns basic extraction
    fields = [
        {"name": "Document Type", "value": form_type, "confidence": 0.80, "flagged": True, "flag_reason": "Unrecognized form type — manual review recommended"},
    ]
    return json.dumps(fields), 0.80, json.dumps(["Unrecognized form type"])


async def _get_client_or_404(client_id: int, session: AsyncSession, user: UserModel):
    result = await session.execute(
        select(ClientModel).where(ClientModel.id == client_id, ClientModel.org_id == user.org_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get("/api/clients/{client_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    await _get_client_or_404(client_id, session, user)
    result = await session.execute(
        select(DocumentModel).where(DocumentModel.client_id == client_id)
    )
    docs = result.scalars().all()
    count_result = await session.execute(
        select(func.count(DocumentModel.id)).where(DocumentModel.client_id == client_id)
    )
    total = count_result.scalar() or 0
    return DocumentListResponse(items=docs, total=total)


@router.post(
    "/api/clients/{client_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    client_id: int,
    form_type: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    await _get_client_or_404(client_id, session, user)

    # Create document record first to get an ID
    extracted_data, confidence, flags = _mock_extract(form_type)
    has_flags = flags != "[]" and flags != ""
    doc_status = "review" if (has_flags or confidence < 0.90) else "verified"
    doc = DocumentModel(
        client_id=client_id,
        form_type=form_type,
        title=f"{form_type} ({file.filename})" if file.filename else f"{form_type} document",
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

    # Save file to uploads/{doc_id}/
    doc_dir = UPLOAD_DIR / str(doc.id)
    doc_dir.mkdir(parents=True, exist_ok=True)
    file_path = doc_dir / (file.filename or "upload")
    content = await file.read()
    file_path.write_bytes(content)

    doc.file_path = str(file_path)
    await session.commit()
    await session.refresh(doc)
    return doc


@router.get("/api/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    result = await session.execute(
        select(DocumentModel).where(DocumentModel.id == doc_id, DocumentModel.org_id == user.org_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.patch("/api/documents/{doc_id}/approve", response_model=DocumentResponse)
async def approve_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    result = await session.execute(
        select(DocumentModel).where(DocumentModel.id == doc_id, DocumentModel.org_id == user.org_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.status = "approved"
    await session.commit()
    await session.refresh(doc)
    return doc


@router.get("/api/documents/{doc_id}/fields", response_model=list[ExtractedField])
async def get_document_fields(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    result = await session.execute(
        select(DocumentModel).where(DocumentModel.id == doc_id, DocumentModel.org_id == user.org_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        raw = json.loads(doc.extracted_data)
    except (json.JSONDecodeError, TypeError):
        raw = []
    return [ExtractedField(**f) for f in raw]
