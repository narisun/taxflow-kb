import pytest


@pytest.mark.asyncio
async def test_list_clients_empty(client):
    resp = await client.get("/api/clients")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_create_client(client):
    resp = await client.post("/api/clients", json={
        "name": "Smith Family", "filing_status": "mfj", "tax_year": 2024, "dependents": 2,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Smith Family"
    assert body["filing_status"] == "mfj"
    assert body["id"] > 0


@pytest.mark.asyncio
async def test_get_client(client):
    create = await client.post("/api/clients", json={"name": "Test"})
    cid = create.json()["id"]
    resp = await client.get(f"/api/clients/{cid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test"


@pytest.mark.asyncio
async def test_get_nonexistent_client(client):
    resp = await client.get("/api/clients/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_client(client):
    create = await client.post("/api/clients", json={"name": "Old Name"})
    cid = create.json()["id"]
    resp = await client.patch(f"/api/clients/{cid}", json={"name": "New Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_delete_client(client):
    create = await client.post("/api/clients", json={"name": "To Delete"})
    cid = create.json()["id"]
    resp = await client.delete(f"/api/clients/{cid}")
    assert resp.status_code == 204
    get = await client.get(f"/api/clients/{cid}")
    assert get.status_code == 404
