import pytest


@pytest.mark.asyncio
async def test_send_message_and_get_response(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/chat", json={"content": "What is the standard deduction?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "assistant"
    assert len(body["content"]) > 0


@pytest.mark.asyncio
async def test_chat_history_persists(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    await client.post(f"/api/clients/{cid}/chat", json={"content": "Hello"})
    resp = await client.get(f"/api/clients/{cid}/chat")
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) >= 2  # user + assistant


@pytest.mark.asyncio
async def test_chat_for_nonexistent_client(client):
    resp = await client.post("/api/clients/9999/chat", json={"content": "Hello"})
    assert resp.status_code == 404
