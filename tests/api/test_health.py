import pytest

@pytest.mark.asyncio
async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "tax-brain-api"

@pytest.mark.asyncio
async def test_health_returns_json(client):
    resp = await client.get("/health")
    assert resp.headers["content-type"] == "application/json"
