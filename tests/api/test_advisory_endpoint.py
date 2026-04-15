"""Integration test: advisory endpoint returns recommendations based on client data."""
import pytest


@pytest.mark.asyncio
async def test_advisory_returns_items(client):
    c = await client.post("/api/clients", json={"name": "Test User", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]

    doc = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    did = doc.json()["id"]
    await client.patch(f"/api/documents/{did}/approve")
    await client.post(f"/api/clients/{cid}/returns/draft")

    resp = await client.get(f"/api/clients/{cid}/returns/advisory")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) > 0
    for item in items:
        assert "id" in item
        assert "category" in item
        assert "title" in item
        assert "detail" in item
        assert item["category"] in ("deduction", "credit", "retirement", "planning", "compliance")


@pytest.mark.asyncio
async def test_advisory_empty_client(client):
    c = await client.post("/api/clients", json={"name": "Empty Client", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/advisory")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_advisory_nonexistent_client(client):
    resp = await client.get("/api/clients/9999/returns/advisory")
    assert resp.status_code == 404
