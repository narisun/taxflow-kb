"""Tests for agent tool functions — isolation, PII masking, correctness."""
import pytest
from api.agent.session import AgentSession
from api.agent.tools import client_tools, document_tools
from api.services.pii.encryptor import PIIEncryptor, _DEV_FALLBACK_KEY


def _make_encryptor() -> PIIEncryptor:
    return PIIEncryptor(_DEV_FALLBACK_KEY)


@pytest.mark.asyncio
async def test_get_client_summary_masks_pii(app):
    """SSN, DOB, and street must be masked in the tool's return value."""
    session_factory = app.state.test_session_factory
    async with session_factory() as db:
        from api.auth.models import OrganizationModel, UserModel
        from api.db.models import ClientModel
        org = OrganizationModel(name="Tool Test Org", slug="tool-test", plan="starter")
        db.add(org)
        await db.flush()
        user = UserModel(org_id=org.id, auth0_sub="auth0|tool-test", email="tool@test.com",
                         name="Tool Tester", role="admin", onboarding_status="complete")
        db.add(user)
        await db.flush()
        enc = _make_encryptor()
        client = ClientModel(org_id=org.id, created_by=user.id, name="PII Client",
                             primary_first_name="John", primary_last_name="Doe",
                             filing_status="single", tax_year=2025, dependents=0)
        client.primary_ssn_enc = enc.encrypt("123-45-6789")
        client.primary_dob_enc = enc.encrypt("1990-05-15")
        client.street_enc = enc.encrypt("742 Evergreen Terrace")
        db.add(client)
        await db.commit()

        agent_session = AgentSession(org_id=org.id, client_id=client.id, user_id=user.id,
                                     conversation_id="test-conv", db_session=db, pii_encryptor=enc)
        result = await client_tools.get_client_summary(agent_session)
        assert "error" not in result
        assert result["primary_ssn"] == "***-**-6789"
        assert result["primary_dob"].startswith("*")
        assert "***" in result["street"]
        assert result["name"] == "PII Client"


@pytest.mark.asyncio
async def test_get_document_fields_rejects_wrong_client(app):
    """A doc belonging to client B must not be accessible via client A's session."""
    session_factory = app.state.test_session_factory
    async with session_factory() as db:
        from api.auth.models import OrganizationModel, UserModel
        from api.db.models import ClientModel, DocumentModel
        org = OrganizationModel(name="Iso Org", slug="iso", plan="starter")
        db.add(org)
        await db.flush()
        user = UserModel(org_id=org.id, auth0_sub="auth0|iso", email="iso@test.com",
                         name="Iso User", role="admin", onboarding_status="complete")
        db.add(user)
        await db.flush()
        client_a = ClientModel(org_id=org.id, created_by=user.id, name="A")
        client_b = ClientModel(org_id=org.id, created_by=user.id, name="B")
        db.add_all([client_a, client_b])
        await db.flush()
        doc_b = DocumentModel(org_id=org.id, created_by=user.id, client_id=client_b.id,
                              form_type="W-2", title="W-2 (test.pdf)", file_name="test.pdf",
                              extracted_data='{"wages": 50000}', flags="[]")
        db.add(doc_b)
        await db.commit()

        enc = _make_encryptor()
        session_a = AgentSession(org_id=org.id, client_id=client_a.id, user_id=user.id,
                                 conversation_id="test-conv", db_session=db, pii_encryptor=enc)
        result = await document_tools.get_document_fields(session_a, doc_id=doc_b.id)
        assert "error" in result, "Should reject doc from a different client"
