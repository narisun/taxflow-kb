"""Tests for tax return draft endpoints — engine-backed."""
import pytest


@pytest.mark.asyncio
async def test_generate_draft_return(client):
    c = await client.post("/api/clients", json={"name": "Smith Family", "filing_status": "mfj", "tax_year": 2024, "dependents": 2})
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert "lines" in body
    assert body["filing_status"] == "mfj"


@pytest.mark.asyncio
async def test_get_draft_after_generate(client):
    c = await client.post("/api/clients", json={"name": "Smith Family", "filing_status": "mfj", "tax_year": 2024, "dependents": 2})
    cid = c.json()["id"]
    await client.post(f"/api/clients/{cid}/returns/draft")
    resp = await client.get(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 200
    assert resp.json()["client_id"] == cid


@pytest.mark.asyncio
async def test_get_draft_before_generate(client):
    c = await client.post("/api/clients", json={"name": "Test", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_draft_single_filer(client):
    c = await client.post("/api/clients", json={"name": "Solo Person", "filing_status": "single", "tax_year": 2024, "dependents": 0})
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert body["filing_status"] == "single"


@pytest.mark.asyncio
async def test_draft_nonexistent_client(client):
    resp = await client.post("/api/clients/9999/returns/draft")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_manual_entry_crud(client):
    c = await client.post("/api/clients", json={"name": "Test Client", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    # Create
    resp = await client.post(f"/api/clients/{cid}/returns/entries", json={
        "form_type": "W-2", "form_index": 0, "field_name": "box1_wages", "value": "90000"})
    assert resp.status_code == 200
    # List
    resp = await client.get(f"/api/clients/{cid}/returns/entries")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["value"] == "90000"
    # Delete
    entry_id = entries[0]["id"]
    resp = await client.delete(f"/api/clients/{cid}/returns/entries/{entry_id}")
    assert resp.status_code == 200
    # Verify deleted
    resp = await client.get(f"/api/clients/{cid}/returns/entries")
    assert len(resp.json()) == 0
