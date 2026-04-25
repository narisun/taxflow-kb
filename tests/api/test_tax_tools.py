"""Tests for tax agent tools — TaxReturnService calls mocked."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from api.agent.session import AgentSession


def _make_session() -> AgentSession:
    return AgentSession(
        org_id="org-1", client_id="client-1", user_id="user-1",
        conversation_id="conv-1", db_session=MagicMock(),
        pii_encryptor=MagicMock(),
    )


class TestSSNLast4:
    def test_full_ssn_with_dashes(self):
        from api.agent.tools.tax_tools import _ssn_last4
        assert _ssn_last4("123-45-6789") == "6789"

    def test_full_ssn_digits_only(self):
        from api.agent.tools.tax_tools import _ssn_last4
        assert _ssn_last4("123456789") == "6789"

    def test_masked_ssn(self):
        from api.agent.tools.tax_tools import _ssn_last4
        assert _ssn_last4("***-**-6789") == "6789"

    def test_too_short_returns_empty(self):
        from api.agent.tools.tax_tools import _ssn_last4
        assert _ssn_last4("12") == ""

    def test_empty_returns_empty(self):
        from api.agent.tools.tax_tools import _ssn_last4
        assert _ssn_last4("") == ""


class TestValidateIntakeVsDocuments:
    @pytest.mark.asyncio
    async def test_reports_ssn_mismatch(self):
        from api.agent.tools.tax_tools import validate_intake_vs_documents

        mock_session = _make_session()
        mock_client = MagicMock()
        mock_client.primary_ssn_enc = b"encrypted"
        mock_client.primary_first_name = "John"
        mock_client.primary_last_name = "Doe"
        mock_client.city = "Princeton"
        mock_client.state = "NJ"
        mock_client.tax_year = 2025
        mock_session.pii_encryptor.decrypt.return_value = "123-45-6789"

        mock_doc = MagicMock()
        mock_doc.id = "doc-1"
        mock_doc.form_type = "W-2"
        mock_doc.file_name = "w2.pdf"
        mock_doc.status = "approved"
        mock_doc.extracted_data = '{"employee_ssn": "987-65-4321", "employee_name": "John Doe"}'

        with patch("api.agent.tools.tax_tools._load_client", return_value=mock_client), \
             patch("api.agent.tools.tax_tools._load_approved_docs", return_value=[mock_doc]):
            result = await validate_intake_vs_documents(mock_session)

        assert len(result["mismatches"]) > 0
        ssn_mismatch = [m for m in result["mismatches"] if m["field"] == "ssn"]
        assert len(ssn_mismatch) == 1
        assert ssn_mismatch[0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_no_mismatches(self):
        from api.agent.tools.tax_tools import validate_intake_vs_documents

        mock_session = _make_session()
        mock_client = MagicMock()
        mock_client.primary_ssn_enc = b"encrypted"
        mock_client.primary_first_name = "John"
        mock_client.primary_last_name = "Doe"
        mock_client.city = "Princeton"
        mock_client.state = "NJ"
        mock_client.tax_year = 2025
        mock_session.pii_encryptor.decrypt.return_value = "123-45-6789"

        mock_doc = MagicMock()
        mock_doc.id = "doc-1"
        mock_doc.form_type = "W-2"
        mock_doc.file_name = "w2.pdf"
        mock_doc.status = "approved"
        mock_doc.extracted_data = '{"employee_ssn": "123-45-6789", "employee_name": "John Doe"}'

        with patch("api.agent.tools.tax_tools._load_client", return_value=mock_client), \
             patch("api.agent.tools.tax_tools._load_approved_docs", return_value=[mock_doc]):
            result = await validate_intake_vs_documents(mock_session)

        assert len(result["mismatches"]) == 0
        assert "No discrepancies" in result["summary"]

    @pytest.mark.asyncio
    async def test_masked_ssn_matches_plaintext(self):
        """Document SSN stored masked (***-**-6789) should match decrypted
        intake SSN (123-45-6789) when last 4 digits are the same."""
        from api.agent.tools.tax_tools import validate_intake_vs_documents

        mock_session = _make_session()
        mock_client = MagicMock()
        mock_client.primary_ssn_enc = b"encrypted"
        mock_client.primary_first_name = "John"
        mock_client.primary_last_name = "Doe"
        mock_client.city = "Princeton"
        mock_client.state = "NJ"
        mock_client.tax_year = 2025
        mock_session.pii_encryptor.decrypt.return_value = "123-45-6789"

        mock_doc = MagicMock()
        mock_doc.id = "doc-1"
        mock_doc.form_type = "W-2"
        mock_doc.file_name = "w2.pdf"
        mock_doc.status = "approved"
        # SSN is masked in extracted_data (as stored by the upload pipeline)
        mock_doc.extracted_data = '{"employee_ssn": "***-**-6789", "employee_name": "John Doe"}'

        with patch("api.agent.tools.tax_tools._load_client", return_value=mock_client), \
             patch("api.agent.tools.tax_tools._load_approved_docs", return_value=[mock_doc]):
            result = await validate_intake_vs_documents(mock_session)

        assert len(result["mismatches"]) == 0
        assert "No discrepancies" in result["summary"]

    @pytest.mark.asyncio
    async def test_masked_ssn_mismatch_detected(self):
        """Different last-4 digits between masked doc SSN and intake SSN
        should still be caught as a mismatch."""
        from api.agent.tools.tax_tools import validate_intake_vs_documents

        mock_session = _make_session()
        mock_client = MagicMock()
        mock_client.primary_ssn_enc = b"encrypted"
        mock_client.primary_first_name = "John"
        mock_client.primary_last_name = "Doe"
        mock_client.city = "Princeton"
        mock_client.state = "NJ"
        mock_client.tax_year = 2025
        mock_session.pii_encryptor.decrypt.return_value = "123-45-6789"

        mock_doc = MagicMock()
        mock_doc.id = "doc-1"
        mock_doc.form_type = "W-2"
        mock_doc.file_name = "w2.pdf"
        mock_doc.status = "approved"
        mock_doc.extracted_data = '{"employee_ssn": "***-**-4321", "employee_name": "John Doe"}'

        with patch("api.agent.tools.tax_tools._load_client", return_value=mock_client), \
             patch("api.agent.tools.tax_tools._load_approved_docs", return_value=[mock_doc]):
            result = await validate_intake_vs_documents(mock_session)

        ssn_mismatch = [m for m in result["mismatches"] if m["field"] == "ssn"]
        assert len(ssn_mismatch) == 1
        assert ssn_mismatch[0]["severity"] == "critical"


class TestComputeTaxReturn:
    @pytest.mark.asyncio
    async def test_returns_computed_draft(self):
        from api.agent.tools.tax_tools import compute_tax_return

        mock_draft = MagicMock()
        mock_draft.total_income = 85000
        mock_draft.taxable_income = 70000
        mock_draft.total_tax = 12000
        mock_draft.total_payments = 14000
        mock_draft.refund_or_owed = 2000
        mock_draft.effective_rate = 14.1
        mock_draft.tax_year = 2025
        mock_draft.filing_status = "single"
        mock_draft.total_deductions = 15000

        mock_service = MagicMock()
        mock_service.compute_and_save_draft = AsyncMock(return_value=mock_draft)

        with patch("api.agent.tools.tax_tools._get_tax_service", return_value=mock_service), \
             patch("api.agent.tools.tax_tools._get_user", return_value=MagicMock()):
            result = await compute_tax_return(_make_session())

        assert result["total_income"] == 85000
        assert result["refund_or_owed"] == 2000
        assert result["status"] == "computed"


class TestRunAdvisoryAnalysis:
    @pytest.mark.asyncio
    async def test_returns_recommendations(self):
        from api.agent.tools.tax_tools import run_advisory_analysis

        mock_item = MagicMock()
        mock_item.title = "Maximize HSA"
        mock_item.detail = "Contribute more to HSA"
        mock_item.estimated_savings = 1500

        mock_service = MagicMock()
        mock_service.get_advisory = AsyncMock(return_value=[mock_item])

        with patch("api.agent.tools.tax_tools._get_tax_service", return_value=mock_service), \
             patch("api.agent.tools.tax_tools._get_user", return_value=MagicMock()):
            result = await run_advisory_analysis(_make_session())

        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["title"] == "Maximize HSA"
        assert result["total_potential_savings"] == 1500


class TestComparePriorYear:
    @pytest.mark.asyncio
    async def test_returns_comparison(self):
        from api.agent.tools.tax_tools import compare_prior_year

        mock_row = MagicMock()
        mock_row.label = "Wages"
        mock_row.current = 85000
        mock_row.prior = 80000
        mock_row.change = 5000
        mock_row.pct_change = 6.25

        mock_section = MagicMock()
        mock_section.title = "Income"
        mock_section.rows = [mock_row]

        mock_summary = MagicMock()
        mock_summary.current = 2000
        mock_summary.prior = 1500
        mock_summary.change = 500

        mock_report = MagicMock()
        mock_report.sections = [mock_section]
        mock_report.summary = mock_summary

        mock_client = MagicMock()
        mock_client.tax_year = 2025

        mock_service = MagicMock()
        mock_service.compare_years = AsyncMock(return_value=mock_report)

        with patch("api.agent.tools.tax_tools._get_tax_service", return_value=mock_service), \
             patch("api.agent.tools.tax_tools._get_user", return_value=MagicMock()), \
             patch("api.agent.tools.tax_tools._load_client", return_value=mock_client):
            result = await compare_prior_year(_make_session())

        assert len(result["sections"]) == 1
        assert result["sections"][0]["name"] == "Income"
        assert result["prior_year"] == 2024


class TestRunValidationRules:
    @pytest.mark.asyncio
    async def test_returns_results(self):
        from api.agent.tools.tax_tools import run_validation_rules

        mock_service = MagicMock()
        mock_service.validate = AsyncMock(return_value={
            "results": [{"rule_id": "V001", "severity": "WARNING", "message": "test"}],
            "has_errors": False,
        })

        with patch("api.agent.tools.tax_tools._get_tax_service", return_value=mock_service), \
             patch("api.agent.tools.tax_tools._get_user", return_value=MagicMock()):
            result = await run_validation_rules(_make_session())

        assert len(result["results"]) == 1
        assert result["has_errors"] is False
