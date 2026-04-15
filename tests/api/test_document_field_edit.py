"""Tests for document field editing."""
import json
import pytest


@pytest.mark.asyncio
async def test_edit_extracted_field(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"}, files={"file": ("w2.pdf", b"fake", "application/pdf")})
    did = doc.json()["id"]
    resp = await client.patch(f"/api/documents/{did}/fields", json={
        "field_name": "box1_wages", "value": "115000.00",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "review"
    fields_resp = await client.get(f"/api/documents/{did}/fields")
    fields = fields_resp.json()
    wages = next((f for f in fields if f["name"] == "box1_wages"), None)
    assert wages is not None
    assert wages["value"] == "115000.00"


@pytest.mark.asyncio
async def test_edit_nonexistent_document(client):
    resp = await client.patch("/api/documents/9999/fields", json={
        "field_name": "box1_wages", "value": "100000",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_edit_resets_status_to_review(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"}, files={"file": ("w2.pdf", b"fake", "application/pdf")})
    did = doc.json()["id"]
    await client.patch(f"/api/documents/{did}/approve")
    detail = await client.get(f"/api/documents/{did}")
    assert detail.json()["status"] == "approved"
    await client.patch(f"/api/documents/{did}/fields", json={
        "field_name": "employer_name", "value": "NEW CORP",
    })
    detail = await client.get(f"/api/documents/{did}")
    assert detail.json()["status"] == "review"
