"""Postgres integration smoke test.

One focused end-to-end test that exercises:
- schema creation on real Postgres
- multi-tenant FK constraints
- a full create-client → upload-document → approve → draft flow

Run with:

    pytest -m integration

Skipped automatically if ``TEST_DATABASE_URL`` is unreachable.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_full_workflow_against_postgres(pg_client):
    # Health
    health = await pg_client.get("/health")
    assert health.status_code == 200

    # Create a client
    resp = await pg_client.post(
        "/api/clients",
        json={"name": "Integration User", "filing_status": "single", "tax_year": 2025},
    )
    assert resp.status_code in (200, 201), resp.text
    cid = resp.json()["id"]

    # Upload a W-2 — mock extractor fills in plausible values
    up = await pg_client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake-pdf-bytes", "application/pdf")},
    )
    assert up.status_code == 201, up.text
    did = up.json()["id"]

    # Approve it
    approved = await pg_client.patch(f"/api/documents/{did}/approve")
    assert approved.status_code == 200

    # Compute draft — verifies Postgres transactions + upsert path
    draft = await pg_client.post(f"/api/clients/{cid}/returns/draft")
    assert draft.status_code == 200
    body = draft.json()
    assert body["total_income"] > 0
    assert body["tax_year"] == 2025
