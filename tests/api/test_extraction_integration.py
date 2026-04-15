"""Integration test: upload document -> structured extraction -> assembler builds TaxReturn."""
import json
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.base import Base
from api.db.models import ClientModel, DocumentModel
from api.auth.models import OrganizationModel, UserModel
from api.tax_engine.assembler import DocumentAssembler


@pytest.fixture
async def db_with_extracted_doc():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        org = OrganizationModel(name="Test CPA", slug="test-cpa", plan="professional")
        session.add(org)
        await session.flush()
        user = UserModel(org_id=org.id, auth0_sub="dev|test", email="t@t.com", name="Test", role="admin")
        session.add(user)
        await session.flush()
        client = ClientModel(org_id=org.id, created_by=user.id, name="John Doe",
                             filing_status="single", tax_year=2024)
        session.add(client)
        await session.flush()

        structured_data = {
            "employer_name": "ACME CORPORATION",
            "employer_ein": "12-3456789",
            "box1_wages": "112400.00",
            "box2_fed_withheld": "18750.00",
            "box3_ss_wages": "112400.00",
            "box5_medicare_wages": "112400.00",
        }
        doc = DocumentModel(
            org_id=org.id, created_by=user.id, client_id=client.id,
            form_type="W-2", title="W-2 (w2.pdf)",
            status="approved", confidence=0.95,
            extracted_data=json.dumps(structured_data),
        )
        session.add(doc)
        await session.commit()
        yield session, client.id
    await engine.dispose()


@pytest.mark.asyncio
async def test_assembler_reads_structured_data(db_with_extracted_doc):
    session, client_id = db_with_extracted_doc
    assembler = DocumentAssembler()
    tr = await assembler.assemble(client_id, session)

    assert len(tr.w2s) == 1
    w2 = tr.w2s[0]
    assert w2.employer_name == "ACME CORPORATION"
    assert w2.employer_ein == "12-3456789"
    assert str(w2.box1_wages) == "112400.00"
    assert str(w2.box2_fed_withheld) == "18750.00"


@pytest.mark.asyncio
async def test_assembler_handles_legacy_list_format(db_with_extracted_doc):
    session, client_id = db_with_extracted_doc

    result = await session.execute(
        select(DocumentModel).where(DocumentModel.client_id == client_id))
    doc = result.scalar_one()
    doc.extracted_data = json.dumps([
        {"name": "employer_name", "value": "LEGACY CORP"},
        {"name": "employer_ein", "value": "99-8888888"},
        {"name": "box1_wages", "value": "50000.00"},
    ])
    await session.commit()

    assembler = DocumentAssembler()
    tr = await assembler.assemble(client_id, session)
    assert len(tr.w2s) == 1
    assert tr.w2s[0].employer_name == "LEGACY CORP"


@pytest.mark.asyncio
async def test_full_pipeline_upload_to_computation(client):
    """Upload -> extract -> approve -> compute draft — end-to-end via API."""
    c = await client.post("/api/clients", json={"name": "Test User", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]

    doc_resp = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake-pdf", "application/pdf")},
    )
    assert doc_resp.status_code == 201
    did = doc_resp.json()["id"]

    detail = await client.get(f"/api/documents/{did}")
    data = json.loads(detail.json()["extracted_data"])
    assert isinstance(data, dict)
    assert "box1_wages" in data

    await client.patch(f"/api/documents/{did}/approve")

    draft_resp = await client.post(f"/api/clients/{cid}/returns/draft")
    assert draft_resp.status_code == 200
    draft = draft_resp.json()
    assert draft["total_income"] > 0
