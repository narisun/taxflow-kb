"""Validation regression for the new contact fields on ClientCreate/Update.

Locks in:
* email format is enforced (Pydantic EmailStr)
* phone format is enforced (digits + common formatting chars)
* state must be 2 letters
* zip_code must be 5 or 9 digits
* size limits match the DB column widths
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


async def test_create_client_with_contact(authenticated_client):
    resp = await authenticated_client.post(
        "/api/clients",
        json={
            "name": "Sarah Smith",
            "filing_status": "single",
            "tax_year": 2025,
            "email": "sarah@example.com",
            "phone": "(555) 123-4567",
            "city": "Boston",
            "state": "ma",  # lowercase normalized to MA
            "zip_code": "02115",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "sarah@example.com"
    assert body["phone"] == "(555) 123-4567"
    assert body["state"] == "MA"
    assert body["zip_code"] == "02115"


async def test_invalid_email_rejected(authenticated_client):
    resp = await authenticated_client.post(
        "/api/clients",
        json={"name": "X", "email": "not-an-email"},
    )
    assert resp.status_code == 422
    assert "email" in resp.text.lower()


async def test_invalid_phone_rejected(authenticated_client):
    resp = await authenticated_client.post(
        "/api/clients",
        json={"name": "X", "phone": "abc-DEF-1234"},
    )
    assert resp.status_code == 422
    assert "phone" in resp.text.lower()


async def test_invalid_state_rejected(authenticated_client):
    resp = await authenticated_client.post(
        "/api/clients",
        json={"name": "X", "state": "Massachusetts"},
    )
    assert resp.status_code == 422


async def test_invalid_zip_rejected(authenticated_client):
    resp = await authenticated_client.post(
        "/api/clients",
        json={"name": "X", "zip_code": "ABCDE"},
    )
    assert resp.status_code == 422


async def test_email_size_limit_enforced(authenticated_client):
    # 254 chars is the RFC limit; 255 must be rejected.
    too_long = "a" * 245 + "@x.com"  # 251 chars — still ok
    resp = await authenticated_client.post(
        "/api/clients",
        json={"name": "X", "email": too_long},
    )
    assert resp.status_code == 201

    way_too_long = "a" * 250 + "@x.com"  # 256 chars — over limit
    resp = await authenticated_client.post(
        "/api/clients",
        json={"name": "Y", "email": way_too_long},
    )
    assert resp.status_code == 422


async def test_blank_optional_fields_become_null(authenticated_client):
    """Empty strings for optional fields normalize to None (DB stores NULL)."""
    resp = await authenticated_client.post(
        "/api/clients",
        json={"name": "X", "email": None, "phone": "  "},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] is None
    assert body["phone"] is None


async def test_update_changes_contact_fields(authenticated_client):
    create = await authenticated_client.post(
        "/api/clients", json={"name": "X", "email": "x@example.com"}
    )
    cid = create.json()["id"]

    update = await authenticated_client.patch(
        f"/api/clients/{cid}",
        json={"email": "x2@example.com", "phone": "555-555-5555"},
    )
    assert update.status_code == 200
    body = update.json()
    assert body["email"] == "x2@example.com"
    assert body["phone"] == "555-555-5555"
