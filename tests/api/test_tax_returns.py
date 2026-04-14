"""Tests for tax return draft endpoints."""
import pytest


@pytest.mark.asyncio
async def test_generate_draft_return(client):
    c = await client.post(
        "/api/clients",
        json={"name": "Smith Family", "filing_status": "mfj", "tax_year": 2024, "dependents": 2},
    )
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["lines"]) >= 8
    assert body["filing_status"] == "mfj"
    assert body["refund_or_owed"] > 0  # should be a refund for this scenario


@pytest.mark.asyncio
async def test_get_draft_after_generate(client):
    c = await client.post(
        "/api/clients",
        json={"name": "Smith Family", "filing_status": "mfj", "tax_year": 2024, "dependents": 2},
    )
    cid = c.json()["id"]
    await client.post(f"/api/clients/{cid}/returns/draft")
    resp = await client.get(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 200
    assert resp.json()["client_id"] == cid


@pytest.mark.asyncio
async def test_get_draft_before_generate(client):
    c = await client.post(
        "/api/clients",
        json={"name": "Test", "filing_status": "single", "tax_year": 2024},
    )
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_draft_single_filer(client):
    c = await client.post(
        "/api/clients",
        json={"name": "Solo Person", "filing_status": "single", "tax_year": 2024, "dependents": 0},
    )
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert body["filing_status"] == "single"
    assert body["total_deductions"] == 14600.0


@pytest.mark.asyncio
async def test_draft_has_effective_rate(client):
    c = await client.post(
        "/api/clients",
        json={"name": "Test", "filing_status": "mfj", "tax_year": 2024, "dependents": 0},
    )
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/returns/draft")
    body = resp.json()
    assert body["effective_rate"] > 0


@pytest.mark.asyncio
async def test_draft_nonexistent_client(client):
    resp = await client.post("/api/clients/9999/returns/draft")
    assert resp.status_code == 404
