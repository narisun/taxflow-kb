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
    assert isinstance(body["id"], str) and len(body["id"]) == 36


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


@pytest.mark.asyncio
async def test_address_and_street_round_trip(client):
    """Street is encrypted but the masked snippet must always reflect the latest value."""
    create = await client.post("/api/clients", json={
        "name": "Addr Test",
        "street": "123 Main St", "city": "LA", "state": "CA", "zip_code": "90001",
    })
    assert create.status_code == 201
    cid = create.json()["id"]
    assert create.json()["state"] == "CA"
    assert create.json()["street_masked"].startswith("123 M")

    update = await client.patch(f"/api/clients/{cid}", json={
        "street": "456 New Ave", "state": "NY",
    })
    assert update.status_code == 200, update.text

    got = await client.get(f"/api/clients/{cid}")
    body = got.json()
    assert body["state"] == "NY"
    assert body["street_masked"].startswith("456 N")


@pytest.mark.asyncio
async def test_filing_federal_and_filing_states_round_trip(client):
    """The Filing Needs section (federal toggle + multi-state list) must persist."""
    # Default: federal=True, states=[]
    create = await client.post("/api/clients", json={
        "name": "Filing Test",
        "filing_states": ["ca", "NY"],   # validator should normalize to upper + sort
        "filing_federal": False,
    })
    assert create.status_code == 201, create.text
    body = create.json()
    cid = body["id"]
    assert body["filing_federal"] is False
    assert body["filing_states"] == ["CA", "NY"]

    # Patch a single state and toggle federal back on
    upd = await client.patch(f"/api/clients/{cid}", json={
        "filing_states": ["TX"],
        "filing_federal": True,
    })
    assert upd.status_code == 200, upd.text
    assert upd.json()["filing_federal"] is True
    assert upd.json()["filing_states"] == ["TX"]

    # Re-fetch to confirm DB persistence
    got = await client.get(f"/api/clients/{cid}")
    assert got.json()["filing_states"] == ["TX"]
    assert got.json()["filing_federal"] is True

    # Empty patch leaves the existing values alone (exclude_unset semantics)
    noop = await client.patch(f"/api/clients/{cid}", json={"name": "Filing Test 2"})
    assert noop.status_code == 200
    assert noop.json()["filing_states"] == ["TX"]
    assert noop.json()["filing_federal"] is True


@pytest.mark.asyncio
async def test_filing_states_rejects_garbage(client):
    create = await client.post("/api/clients", json={
        "name": "Bad", "filing_states": ["XX", "California"],
    })
    assert create.status_code == 422
