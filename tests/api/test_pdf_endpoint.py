"""Integration test: PDF download endpoint."""
import pytest

@pytest.mark.asyncio
async def test_pdf_download(client):
    c = await client.post("/api/clients", json={"name": "Test User", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
    assert len(resp.content) > 1000

@pytest.mark.asyncio
async def test_pdf_with_documents(client):
    c = await client.post("/api/clients", json={"name": "Smith Family", "filing_status": "mfj", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(f"/api/clients/{cid}/documents", data={"form_type": "W-2"},
                            files={"file": ("w2.pdf", b"fake", "application/pdf")})
    did = doc.json()["id"]
    await client.patch(f"/api/documents/{did}/approve")
    resp = await client.get(f"/api/clients/{cid}/returns/pdf")
    assert resp.status_code == 200
    assert resp.content[:5] == b"%PDF-"

@pytest.mark.asyncio
async def test_pdf_content_disposition(client):
    c = await client.post("/api/clients", json={"name": "John Doe", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/pdf")
    assert "1040_John_Doe_2024.pdf" in resp.headers.get("content-disposition", "")

@pytest.mark.asyncio
async def test_pdf_nonexistent_client(client):
    resp = await client.get("/api/clients/9999/returns/pdf")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_manifest_returns_all_forms(client):
    c = await client.post("/api/clients", json={"name": "Test User", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/manifest")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_pages" in data
    assert "forms" in data
    assert len(data["forms"]) == 10
    f1040 = data["forms"][0]
    assert f1040["id"] == "f1040"
    assert f1040["active"] is True
    assert f1040["start_page"] == 1


@pytest.mark.asyncio
async def test_manifest_nonexistent_client(client):
    resp = await client.get("/api/clients/9999/returns/manifest")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pdf_inline_disposition(client):
    c = await client.post("/api/clients", json={"name": "John Doe", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/pdf?disposition=inline")
    assert resp.status_code == 200
    assert "inline" in resp.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_pdf_default_disposition_is_attachment(client):
    c = await client.post("/api/clients", json={"name": "John Doe", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/pdf")
    assert "attachment" in resp.headers.get("content-disposition", "")
