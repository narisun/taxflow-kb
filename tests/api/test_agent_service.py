"""Tests for AgentService tool-use loop with mocked Claude responses."""
from unittest.mock import MagicMock
import pytest
from api.agent.service import AgentService
from api.agent.session import AgentSession
from api.agent.mcp_server import build_tool_registry
from api.services.pii.encryptor import PIIEncryptor, _DEV_FALLBACK_KEY


def _make_text_response(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [block]
    return resp


def _make_tool_call_response(tool_name: str, tool_input: dict, tool_use_id: str = "tu_1"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input
    block.id = tool_use_id
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    resp.content = [block]
    return resp


@pytest.mark.asyncio
async def test_agent_simple_text_response(app):
    session_factory = app.state.test_session_factory
    async with session_factory() as db:
        from api.auth.models import OrganizationModel, UserModel
        from api.db.models import ClientModel, ConversationModel
        org = OrganizationModel(name="Agent Org", slug="agent", plan="starter")
        db.add(org); await db.flush()
        user = UserModel(org_id=org.id, auth0_sub="auth0|agent", email="agent@test.com",
                         name="Agent Tester", role="admin", onboarding_status="complete")
        db.add(user); await db.flush()
        client = ClientModel(org_id=org.id, created_by=user.id, name="Agent Client")
        db.add(client); await db.flush()
        conv = ConversationModel(org_id=org.id, client_id=client.id, user_id=user.id, created_by=user.id)
        db.add(conv); await db.commit()

        enc = PIIEncryptor(_DEV_FALLBACK_KEY)
        agent_session = AgentSession(org_id=org.id, client_id=client.id, user_id=user.id,
                                     conversation_id=conv.id, db_session=db, pii_encryptor=enc)
        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(
            return_value=_make_text_response("The client is filing as single for TY 2025.")
        )
        service = AgentService(anthropic_client=mock_client, model="test-model",
                               max_tokens=1024, max_tool_rounds=5, history_token_budget=4000,
                               tool_registry=build_tool_registry())
        result = await service.reply(user_message="What is the filing status?",
                                     session=agent_session, history=[])
        assert result == "The client is filing as single for TY 2025."


@pytest.mark.asyncio
async def test_agent_tool_call_then_text(app):
    session_factory = app.state.test_session_factory
    async with session_factory() as db:
        from api.auth.models import OrganizationModel, UserModel
        from api.db.models import ClientModel, ConversationModel
        org = OrganizationModel(name="Agent Org2", slug="agent2", plan="starter")
        db.add(org); await db.flush()
        user = UserModel(org_id=org.id, auth0_sub="auth0|agent2", email="agent2@test.com",
                         name="Agent Tester 2", role="admin", onboarding_status="complete")
        db.add(user); await db.flush()
        client = ClientModel(org_id=org.id, created_by=user.id, name="Tool Client",
                             filing_status="mfj", tax_year=2025)
        db.add(client); await db.flush()
        conv = ConversationModel(org_id=org.id, client_id=client.id, user_id=user.id, created_by=user.id)
        db.add(conv); await db.commit()

        enc = PIIEncryptor(_DEV_FALLBACK_KEY)
        agent_session = AgentSession(org_id=org.id, client_id=client.id, user_id=user.id,
                                     conversation_id=conv.id, db_session=db, pii_encryptor=enc)
        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(side_effect=[
            _make_tool_call_response("get_client_summary", {}),
            _make_text_response("The client Tool Client is filing MFJ for TY 2025."),
        ])
        service = AgentService(anthropic_client=mock_client, model="test-model",
                               max_tokens=1024, max_tool_rounds=5, history_token_budget=4000,
                               tool_registry=build_tool_registry())
        result = await service.reply(user_message="Tell me about this client",
                                     session=agent_session, history=[])
        assert "Tool Client" in result
        assert "MFJ" in result
        assert mock_client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_agent_end_to_end_via_http(client):
    """Full round-trip: create client -> conversation -> send message -> verify response."""
    c = await client.post("/api/clients", json={
        "name": "E2E Client", "filing_status": "single", "tax_year": 2025,
    })
    cid = c.json()["id"]
    conv = await client.post(f"/api/clients/{cid}/conversations", json={})
    conv_id = conv.json()["id"]
    resp = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "What is this client's filing status?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "assistant"
    assert len(body["content"]) > 0
    # Verify history persisted
    hist = await client.get(f"/api/conversations/{conv_id}/messages")
    assert hist.status_code == 200
    assert len(hist.json()["messages"]) >= 2
