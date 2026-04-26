"""Tests for document management endpoints."""
import json
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
    body = resp.json()
    assert body["status"] == "approved"
    # Approval must populate the audit trail used by the "Review docs" chip.
    assert body["reviewed_by"], "reviewed_by must be set after approval"
    assert body["reviewed_at"], "reviewed_at must be set after approval"
    assert body["reviewed_by_name"], "reviewed_by_name must resolve from user join"


@pytest.mark.asyncio
async def test_document_response_exposes_uploader_and_filename(client):
    """List + GET must surface file_name and uploader name for the chips."""
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    upload = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2_acme_2024.pdf", b"fake", "application/pdf")},
    )
    body = upload.json()
    assert body["file_name"] == "w2_acme_2024.pdf"
    assert body["created_by"], "created_by must be present on upload response"
    assert body["created_by_name"], "created_by_name must resolve from user join"
    # Pre-approval the review fields are unset.
    assert body["reviewed_by"] is None
    assert body["reviewed_at"] is None

    listing = await client.get(f"/api/clients/{cid}/documents")
    items = listing.json()["items"]
    assert items[0]["file_name"] == "w2_acme_2024.pdf"
    assert items[0]["created_by_name"] == body["created_by_name"]


@pytest.mark.asyncio
async def test_get_fields_structured(client):
    """Verify fields endpoint returns structured keys with display labels."""
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
    assert len(fields) >= 3
    names = [f["name"] for f in fields]
    assert "box1_wages" in names
    assert "employer_name" in names
    wages_field = next(f for f in fields if f["name"] == "box1_wages")
    assert wages_field["label"] == "Box 1 \u2014 Wages, salaries, tips"


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
    assert len(fields) >= 2


@pytest.mark.asyncio
async def test_upload_to_nonexistent_client(client):
    resp = await client.post(
        "/api/clients/9999/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_extracted_data_is_structured_dict(client):
    """Verify extracted_data stored as structured JSON dict."""
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    did = doc.json()["id"]
    resp = await client.get(f"/api/documents/{did}")
    data = json.loads(resp.json()["extracted_data"])
    assert isinstance(data, dict)
    assert "box1_wages" in data
