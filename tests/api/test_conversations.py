"""Tests for conversation CRUD and tenant isolation."""
import pytest


@pytest.mark.asyncio
async def test_create_conversation(client):
    c = await client.post("/api/clients", json={"name": "Conv Test"})
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/conversations", json={})
    assert resp.status_code == 201
    body = resp.json()
    assert isinstance(body["id"], str) and len(body["id"]) == 36
    assert body["client_id"] == cid
    assert body["is_active"] is True
    assert body["title"] == "New conversation"


@pytest.mark.asyncio
async def test_list_conversations(client):
    c = await client.post("/api/clients", json={"name": "List Test"})
    cid = c.json()["id"]
    await client.post(f"/api/clients/{cid}/conversations", json={})
    await client.post(f"/api/clients/{cid}/conversations", json={})
    resp = await client.get(f"/api/clients/{cid}/conversations")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2
    assert len(resp.json()["items"]) == 2


@pytest.mark.asyncio
async def test_send_message_and_get_history(client):
    c = await client.post("/api/clients", json={"name": "Msg Test"})
    cid = c.json()["id"]
    conv = await client.post(f"/api/clients/{cid}/conversations", json={})
    conv_id = conv.json()["id"]
    resp = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "What is the client's filing status?"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "assistant"
    assert len(resp.json()["content"]) > 0
    hist = await client.get(f"/api/conversations/{conv_id}/messages")
    assert hist.status_code == 200
    msgs = hist.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_conversation_title_auto_set(client):
    c = await client.post("/api/clients", json={"name": "Title Test"})
    cid = c.json()["id"]
    conv = await client.post(f"/api/clients/{cid}/conversations", json={})
    conv_id = conv.json()["id"]
    await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Check status of the return"},
    )
    listing = await client.get(f"/api/clients/{cid}/conversations")
    titles = [item["title"] for item in listing.json()["items"]]
    assert "Check status of the return" in titles


@pytest.mark.asyncio
async def test_delete_conversation_soft(client):
    c = await client.post("/api/clients", json={"name": "Del Test"})
    cid = c.json()["id"]
    conv = await client.post(f"/api/clients/{cid}/conversations", json={})
    conv_id = conv.json()["id"]
    resp = await client.delete(f"/api/conversations/{conv_id}")
    assert resp.status_code == 204
    listing = await client.get(f"/api/clients/{cid}/conversations")
    assert listing.json()["total"] == 0
    resp = await client.get(f"/api/conversations/{conv_id}/messages")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_conversation_not_found(client):
    resp = await client.get("/api/conversations/nonexistent-id/messages")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_conversation_for_nonexistent_client(client):
    resp = await client.post("/api/clients/nonexistent/conversations", json={})
    assert resp.status_code == 404
