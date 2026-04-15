"""Integration test: year-over-year comparison endpoint."""
import pytest


@pytest.mark.asyncio
async def test_compare_returns_sections(client):
    c = await client.post("/api/clients", json={"name": "Test User", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/compare?prior_year=2025")
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_year"] == 2024
    assert body["prior_year"] == 2025
    assert len(body["sections"]) == 4
    assert body["sections"][0]["title"] == "Income"
    assert "summary" in body


@pytest.mark.asyncio
async def test_compare_same_year_error(client):
    c = await client.post("/api/clients", json={"name": "Test", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/compare?prior_year=2024")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_compare_nonexistent_client(client):
    resp = await client.get("/api/clients/9999/returns/compare?prior_year=2023")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_compare_unsupported_year(client):
    c = await client.post("/api/clients", json={"name": "Test", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/compare?prior_year=2020")
    assert resp.status_code == 400
