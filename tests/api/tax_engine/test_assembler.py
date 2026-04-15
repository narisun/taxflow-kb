"""Tests for DocumentAssembler."""
import json
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from api.db.base import Base
from api.db.models import ClientModel, DocumentModel, ManualEntryModel
from api.auth.models import OrganizationModel, UserModel
from api.tax_engine.assembler import DocumentAssembler


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        org = OrganizationModel(name="Test CPA", slug="test-cpa", plan="professional")
        session.add(org)
        await session.flush()
        user = UserModel(org_id=org.id, auth0_sub="dev|test", email="test@test.com", name="Test", role="admin")
        session.add(user)
        await session.flush()
        client = ClientModel(org_id=org.id, created_by=user.id, name="Smith Family", filing_status="mfj", tax_year=2024, dependents=2)
        session.add(client)
        await session.flush()
        yield session, client.id, org.id, user.id
    await engine.dispose()


@pytest.mark.asyncio
async def test_assemble_from_approved_docs(db_session):
    session, client_id, org_id, user_id = db_session
    doc = DocumentModel(org_id=org_id, created_by=user_id, client_id=client_id, form_type="W-2", title="W-2 from Acme",
                        status="approved", confidence=0.95,
                        extracted_data=json.dumps({"employer_name": "Acme Corp", "employer_ein": "12-3456789", "box1_wages": "85000", "box2_fed_withheld": "15000"}))
    session.add(doc)
    await session.commit()
    tr = await DocumentAssembler().assemble(client_id, session)
    assert len(tr.w2s) == 1
    assert tr.w2s[0].employer_name == "Acme Corp"
    assert str(tr.w2s[0].box1_wages) == "85000"


@pytest.mark.asyncio
async def test_manual_override(db_session):
    session, client_id, org_id, user_id = db_session
    doc = DocumentModel(org_id=org_id, created_by=user_id, client_id=client_id, form_type="W-2", title="W-2",
                        status="approved", confidence=0.95,
                        extracted_data=json.dumps({"employer_name": "Acme Corp", "employer_ein": "12-3456789", "box1_wages": "85000"}))
    session.add(doc)
    override = ManualEntryModel(org_id=org_id, created_by=user_id, client_id=client_id,
                                form_type="W-2", form_index=0, field_name="box1_wages", value="90000", entered_by=user_id)
    session.add(override)
    await session.commit()
    tr = await DocumentAssembler().assemble(client_id, session)
    assert str(tr.w2s[0].box1_wages) == "90000"


@pytest.mark.asyncio
async def test_pending_docs_excluded(db_session):
    session, client_id, org_id, user_id = db_session
    doc = DocumentModel(org_id=org_id, created_by=user_id, client_id=client_id, form_type="W-2", title="W-2 pending",
                        status="pending", confidence=0.50,
                        extracted_data=json.dumps({"employer_name": "Pending Corp", "employer_ein": "99-9999999"}))
    session.add(doc)
    await session.commit()
    tr = await DocumentAssembler().assemble(client_id, session)
    assert len(tr.w2s) == 0


@pytest.mark.asyncio
async def test_assemble_with_real_client_pii(db_session):
    session, client_id, org_id, user_id = db_session
    from api.services.pii.encryptor import get_pii_encryptor
    from sqlalchemy import select

    enc = get_pii_encryptor()
    result = await session.execute(select(ClientModel).where(ClientModel.id == client_id))
    client = result.scalar_one()
    client.primary_ssn_enc = enc.encrypt("123456789")
    client.primary_dob_enc = enc.encrypt("1985-03-15")
    client.street_enc = enc.encrypt("123 Main St")
    client.city = "Springfield"
    client.state = "IL"
    client.zip_code = "62701"
    await session.commit()

    assembler = DocumentAssembler()
    tr = await assembler.assemble(client_id, session)
    assert tr.primary.ssn == "123456789"
    assert str(tr.primary.date_of_birth) == "1985-03-15"
    assert tr.address.street == "123 Main St"
    assert tr.address.city == "Springfield"


@pytest.mark.asyncio
async def test_assemble_tracks_skipped_documents(db_session):
    session, client_id, org_id, user_id = db_session
    doc = DocumentModel(
        org_id=org_id, created_by=user_id, client_id=client_id,
        form_type="W-2", title="Bad W-2", status="approved", confidence=0.95,
        extracted_data=json.dumps({"invalid_field_only": "bad data"}),
    )
    session.add(doc)
    await session.commit()

    assembler = DocumentAssembler()
    tr = await assembler.assemble(client_id, session)
    assert len(assembler.skipped_documents) >= 1
    assert assembler.skipped_documents[0]["form_type"] == "W-2"
