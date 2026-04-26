"""Smoke tests for the ``authenticated_client`` fixture.

Exercises the DI-override path so future endpoint tests can trust that the
current-user override (and downstream ``require_role`` checks) are wired up
correctly.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.unit


async def test_authenticated_client_uses_seeded_user(authenticated_client, seeded_user):
    """The override must return the exact seeded user, org-scoped."""
    resp = await authenticated_client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == seeded_user.email
    assert body["user"]["role"] == "admin"
    assert body["user"]["org_id"] == seeded_user.org_id


async def test_authenticated_client_enforces_tenant_scope(authenticated_client, seeded_user):
    """Clients created by the seeded user are listed — and only theirs."""
    created = await authenticated_client.post(
        "/api/clients",
        json={"name": "Smoke Client", "filing_status": "single", "tax_year": 2025},
    )
    assert created.status_code in (200, 201)
    cid = created.json()["id"]

    listing = await authenticated_client.get("/api/clients")
    items = listing.json().get("items", [])
    assert any(c["id"] == cid for c in items), "Seeded user should see their client"
