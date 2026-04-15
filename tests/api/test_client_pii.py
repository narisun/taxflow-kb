"""Tests for client PII encryption, masking, and reveal."""
import pytest

@pytest.mark.asyncio
async def test_create_client_with_pii(client):
    resp = await client.post("/api/clients", json={
        "name": "Smith Family", "filing_status": "mfj", "tax_year": 2024,
        "primary_ssn": "123456789", "primary_dob": "1985-03-15",
        "spouse_first_name": "Jane", "spouse_last_name": "Smith",
        "spouse_ssn": "987654321", "spouse_dob": "1987-05-10",
        "street": "123 Main St", "city": "Springfield", "state": "IL", "zip_code": "62701",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["primary_ssn_masked"] == "***-**-6789"
    assert body["primary_dob_masked"] == "**/**/1985"
    assert body["spouse_ssn_masked"] == "***-**-4321"
    assert body["street_masked"] == "123 M***"
    assert body["city"] == "Springfield"

@pytest.mark.asyncio
async def test_get_client_returns_masked(client):
    c = await client.post("/api/clients", json={
        "name": "Test", "primary_ssn": "111223333", "street": "456 Oak Ave",
        "city": "Portland", "state": "OR", "zip_code": "97201",
    })
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["primary_ssn_masked"] == "***-**-3333"
    assert body["street_masked"] == "456 O***"
    assert "111223333" not in str(body)

@pytest.mark.asyncio
async def test_reveal_pii(client):
    c = await client.post("/api/clients", json={
        "name": "Test", "primary_ssn": "123456789", "street": "123 Main St",
        "primary_dob": "1985-03-15",
    })
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/reveal-pii", json={
        "fields": ["primary_ssn", "primary_dob", "street"],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["primary_ssn"] == "123456789"
    assert body["primary_dob"] == "1985-03-15"
    assert body["street"] == "123 Main St"

@pytest.mark.asyncio
async def test_update_client_pii(client):
    c = await client.post("/api/clients", json={"name": "Test", "primary_ssn": "111111111"})
    cid = c.json()["id"]
    resp = await client.patch(f"/api/clients/{cid}", json={"primary_ssn": "999888777"})
    assert resp.status_code == 200
    assert resp.json()["primary_ssn_masked"] == "***-**-8777"

@pytest.mark.asyncio
async def test_create_client_without_pii(client):
    resp = await client.post("/api/clients", json={"name": "Simple", "filing_status": "single", "tax_year": 2024})
    assert resp.status_code == 201
    body = resp.json()
    assert body["primary_ssn_masked"] == ""
    assert body["city"] is None

@pytest.mark.asyncio
async def test_list_clients_masked(client):
    await client.post("/api/clients", json={"name": "A", "primary_ssn": "111111111"})
    await client.post("/api/clients", json={"name": "B", "primary_ssn": "222222222"})
    resp = await client.get("/api/clients")
    assert resp.status_code == 200
    items = resp.json()["items"]
    for item in items:
        if item.get("primary_ssn_masked"):
            assert "***-**-" in item["primary_ssn_masked"]
