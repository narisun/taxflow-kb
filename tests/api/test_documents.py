"""Tests for document management endpoints."""
import pytest


@pytest.mark.asyncio
async def test_upload_document(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake-pdf", "application/pdf")},
    )
    assert resp.status_code == 201
    assert resp.json()["form_type"] == "W-2"


@pytest.mark.asyncio
async def test_upload_document_1099int(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "1099-INT"},
        files={"file": ("1099int.pdf", b"fake-pdf", "application/pdf")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["form_type"] == "1099-INT"
    assert body["confidence"] < 1.0


@pytest.mark.asyncio
async def test_list_documents(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    resp = await client.get(f"/api/clients/{cid}/documents")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_list_documents_empty(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/documents")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_get_document(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    did = doc.json()["id"]
    resp = await client.get(f"/api/documents/{did}")
    assert resp.status_code == 200
    assert resp.json()["id"] == did


@pytest.mark.asyncio
async def test_get_document_not_found(client):
    resp = await client.get("/api/documents/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_document(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    did = doc.json()["id"]
    resp = await client.patch(f"/api/documents/{did}/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_get_fields(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    did = doc.json()["id"]
    resp = await client.get(f"/api/documents/{did}/fields")
    assert resp.status_code == 200
    fields = resp.json()
    assert len(fields) == 3
    assert fields[0]["name"] == "Box 1 — Wages"


@pytest.mark.asyncio
async def test_get_fields_1099int_has_flags(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "1099-INT"},
        files={"file": ("1099int.pdf", b"fake", "application/pdf")},
    )
    did = doc.json()["id"]
    resp = await client.get(f"/api/documents/{did}/fields")
    assert resp.status_code == 200
    fields = resp.json()
    flagged = [f for f in fields if f["flagged"]]
    assert len(flagged) >= 1


@pytest.mark.asyncio
async def test_upload_to_nonexistent_client(client):
    resp = await client.post(
        "/api/clients/9999/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    assert resp.status_code == 404
