"""Tests for validation endpoint."""
import pytest


@pytest.mark.asyncio
async def test_validate_returns_results(client):
    c = await client.post("/api/clients", json={
        "name": "Test", "filing_status": "mfj", "tax_year": 2024,
    })
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/returns/validate")
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert "has_errors" in body
    assert body["has_errors"] is True
    assert any(r["rule_id"] == "V003" for r in body["results"])


@pytest.mark.asyncio
async def test_validate_valid_return(client):
    c = await client.post("/api/clients", json={
        "name": "Test", "filing_status": "single", "tax_year": 2024,
    })
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/returns/validate")
    assert resp.status_code == 200
    assert resp.json()["has_errors"] is False


@pytest.mark.asyncio
async def test_validate_nonexistent_client(client):
    resp = await client.post("/api/clients/9999/returns/validate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_draft_includes_validation(client):
    c = await client.post("/api/clients", json={
        "name": "Test", "filing_status": "mfj", "tax_year": 2024,
    })
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert "validation_results" in body
