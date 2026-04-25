"""Tests for multi-year draft storage, prior-year retrieval, and 1040 import."""
import pytest

from api.tax_engine.prior_year_import import build_draft_from_lines, _parse_dollar


class TestParseDollar:
    def test_integer(self):
        assert _parse_dollar(85000) == 85000.0

    def test_float(self):
        assert _parse_dollar(85000.50) == 85000.50

    def test_string_with_commas(self):
        assert _parse_dollar("85,000") == 85000.0

    def test_string_with_dollar_sign(self):
        assert _parse_dollar("$85,000") == 85000.0

    def test_string_with_dollar_and_commas(self):
        assert _parse_dollar("$1,234,567") == 1234567.0

    def test_none_returns_zero(self):
        assert _parse_dollar(None) == 0.0

    def test_empty_returns_zero(self):
        assert _parse_dollar("") == 0.0

    def test_dash_returns_zero(self):
        assert _parse_dollar("-") == 0.0


class TestBuildDraftFromLines:
    def test_builds_draft_with_lines(self):
        extracted = {
            "line_1a": "85000",
            "line_2b": "1200",
            "line_9": "90000",
            "line_12": "14600",
            "line_15": "75400",
            "line_16": "12000",
            "line_24": "12000",
            "line_25a": "14000",
            "line_33": "14000",
            "line_35a": "2000",
        }
        draft = build_draft_from_lines("client-1", 2024, extracted, "S")

        assert draft.client_id == "client-1"
        assert draft.tax_year == 2024
        assert draft.filing_status == "S"
        assert draft.total_income == 90000.0
        assert draft.total_deductions == 14600.0
        assert draft.taxable_income == 75400.0
        assert draft.total_tax == 12000.0
        assert draft.total_payments == 14000.0
        assert draft.refund_or_owed == 2000.0
        assert draft.effective_rate == 13.3
        assert len(draft.lines) > 0
        # Verify specific lines exist
        line_nums = {l.number for l in draft.lines}
        assert "1a" in line_nums
        assert "9" in line_nums
        assert "35a" in line_nums

    def test_empty_extraction_returns_zero_draft(self):
        draft = build_draft_from_lines("client-1", 2024, {})
        assert draft.total_income == 0.0
        assert draft.total_deductions == 0.0
        assert draft.refund_or_owed == 0.0
        assert draft.effective_rate == 0.0
        # Should still have the "always included" lines (9, 15, 24, 33)
        line_nums = {l.number for l in draft.lines}
        assert "9" in line_nums

    def test_amount_owed_is_negative(self):
        extracted = {
            "line_9": "50000",
            "line_15": "35000",
            "line_24": "5000",
            "line_33": "3000",
            "line_37": "2000",
        }
        draft = build_draft_from_lines("client-1", 2024, extracted)
        assert draft.refund_or_owed == -2000.0

    def test_dollar_formatting_handled(self):
        extracted = {
            "line_1a": "$85,000",
            "line_9": "$90,000",
            "line_12": "$14,600",
            "line_15": "$75,400",
            "line_24": "$12,000",
            "line_33": "$14,000",
            "line_35a": "$2,000",
        }
        draft = build_draft_from_lines("client-1", 2024, extracted)
        assert draft.total_income == 90000.0
        assert draft.refund_or_owed == 2000.0


# ── Integration tests (require DB fixtures) ──────────────────────────────


@pytest.mark.asyncio
async def test_compute_drafts_for_two_years(authenticated_client):
    """Computing drafts for 2024 and 2025 creates two separate rows."""
    resp = await authenticated_client.post("/api/clients", json={
        "name": "Multi Year Test",
        "primary_first_name": "Test",
        "primary_last_name": "User",
        "filing_status": "single",
        "tax_year": 2025,
    })
    assert resp.status_code == 201
    client_id = resp.json()["id"]

    # Compute 2025 draft
    resp = await authenticated_client.post(f"/api/clients/{client_id}/returns/draft")
    assert resp.status_code == 200
    assert resp.json()["tax_year"] == 2025

    # Switch to 2024 and compute
    await authenticated_client.patch(f"/api/clients/{client_id}", json={"tax_year": 2024})
    resp = await authenticated_client.post(f"/api/clients/{client_id}/returns/draft")
    assert resp.status_code == 200

    # Switch back to 2025
    await authenticated_client.patch(f"/api/clients/{client_id}", json={"tax_year": 2025})

    # Both drafts should exist
    resp = await authenticated_client.get(f"/api/clients/{client_id}/returns/draft?tax_year=2025")
    assert resp.status_code == 200
    assert resp.json()["tax_year"] == 2025

    resp = await authenticated_client.get(f"/api/clients/{client_id}/returns/draft?tax_year=2024")
    assert resp.status_code == 200
    assert resp.json()["tax_year"] == 2024


@pytest.mark.asyncio
async def test_prior_year_returns_null_when_none(authenticated_client):
    """GET /prior-year returns null draft when no prior year exists."""
    resp = await authenticated_client.post("/api/clients", json={
        "name": "No Prior",
        "primary_first_name": "No",
        "primary_last_name": "Prior",
        "filing_status": "single",
        "tax_year": 2025,
    })
    client_id = resp.json()["id"]

    resp = await authenticated_client.get(f"/api/clients/{client_id}/returns/prior-year")
    assert resp.status_code == 200
    body = resp.json()
    assert body["draft"] is None


@pytest.mark.asyncio
async def test_prior_year_returns_stored_draft(authenticated_client):
    """GET /prior-year returns the stored prior-year draft."""
    resp = await authenticated_client.post("/api/clients", json={
        "name": "Prior Test",
        "primary_first_name": "Prior",
        "primary_last_name": "Test",
        "filing_status": "single",
        "tax_year": 2024,
    })
    client_id = resp.json()["id"]

    # Compute 2024 draft
    await authenticated_client.post(f"/api/clients/{client_id}/returns/draft")

    # Switch to 2025
    await authenticated_client.patch(f"/api/clients/{client_id}", json={"tax_year": 2025})

    # Prior-year should return the 2024 draft
    resp = await authenticated_client.get(f"/api/clients/{client_id}/returns/prior-year")
    assert resp.status_code == 200
    body = resp.json()
    assert body["draft"] is not None
    assert body["draft"]["tax_year"] == 2024
    assert body["source_type"] == "computed"
