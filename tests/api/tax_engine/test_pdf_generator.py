"""Tests for PDF generator."""
from datetime import date
from decimal import Decimal
import io
import pytest

import api.tax_engine.constants  # noqa: F401
from api.tax_engine.constants.registry import get_constants
from api.tax_engine.models.people import Person, Address
from api.tax_engine.models.income import W2, Income1099B
from api.tax_engine.models.tax_return import TaxReturn
from api.tax_engine.services.engine import TaxCalculationEngine


def _person():
    return Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 1, 1))

def _address():
    return Address(street="123 Main St", city="Springfield", state="IL", zip_code="62701")


class TestPDFGenerator:
    def test_generates_valid_pdf(self):
        from api.tax_engine.pdf.generator import PDFGenerator
        tr = TaxReturn(tax_year=2024, filing_status="S", primary=_person(), address=_address(),
                       w2s=[W2(employer_name="Acme", employer_ein="12-3456789",
                               box1_wages=Decimal("85000"), box2_fed_withheld=Decimal("15000"),
                               box3_ss_wages=Decimal("85000"), box5_medicare_wages=Decimal("85000"))])
        result = TaxCalculationEngine(get_constants(2024)).compute(tr)
        pdf_bytes = PDFGenerator().generate(tr, result)
        assert pdf_bytes[:5] == b"%PDF-"
        assert len(pdf_bytes) > 1000

    def test_empty_return_produces_1040_only(self):
        from api.tax_engine.pdf.generator import PDFGenerator
        from pypdf import PdfReader
        tr = TaxReturn(tax_year=2024, filing_status="S", primary=_person(), address=_address())
        result = TaxCalculationEngine(get_constants(2024)).compute(tr)
        pdf_bytes = PDFGenerator().generate(tr, result)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) == 2  # Form 1040 is 2 pages

    def test_return_with_capital_gains_includes_schedule_d(self):
        from api.tax_engine.pdf.generator import PDFGenerator
        from pypdf import PdfReader
        tr = TaxReturn(tax_year=2024, filing_status="S", primary=_person(), address=_address(),
                       w2s=[W2(employer_name="Acme", employer_ein="12-3456789",
                               box1_wages=Decimal("85000"), box3_ss_wages=Decimal("85000"),
                               box5_medicare_wages=Decimal("85000"))],
                       broker_1099s=[Income1099B(payer="Fidelity",
                                                 long_term_proceeds=Decimal("50000"),
                                                 long_term_cost_basis=Decimal("30000"))])
        result = TaxCalculationEngine(get_constants(2024)).compute(tr)
        pdf_bytes = PDFGenerator().generate(tr, result)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) >= 4  # 1040 (2) + Schedule D (2)


from api.models.tax_return import ReturnManifest


class TestPDFManifest:
    def test_manifest_returns_all_ten_forms(self):
        from api.tax_engine.pdf.generator import PDFGenerator
        tr = TaxReturn(tax_year=2024, filing_status="S", primary=_person(), address=_address())
        result = TaxCalculationEngine(get_constants(2024)).compute(tr)
        manifest = PDFGenerator().generate_manifest(tr, result)
        assert isinstance(manifest, ReturnManifest)
        assert len(manifest.forms) == 10

    def test_manifest_empty_return_only_1040_active(self):
        from api.tax_engine.pdf.generator import PDFGenerator
        tr = TaxReturn(tax_year=2024, filing_status="S", primary=_person(), address=_address())
        result = TaxCalculationEngine(get_constants(2024)).compute(tr)
        manifest = PDFGenerator().generate_manifest(tr, result)
        active = [f for f in manifest.forms if f.active]
        assert len(active) == 1
        assert active[0].id == "f1040"
        assert active[0].start_page == 1
        assert active[0].page_count == 2
        assert manifest.total_pages == 2

    def test_manifest_inactive_forms_have_null_start_page(self):
        from api.tax_engine.pdf.generator import PDFGenerator
        tr = TaxReturn(tax_year=2024, filing_status="S", primary=_person(), address=_address())
        result = TaxCalculationEngine(get_constants(2024)).compute(tr)
        manifest = PDFGenerator().generate_manifest(tr, result)
        inactive = [f for f in manifest.forms if not f.active]
        assert len(inactive) == 9
        for f in inactive:
            assert f.start_page is None
            assert f.page_count == 0

    def test_manifest_with_capital_gains_includes_schedule_d(self):
        from api.tax_engine.pdf.generator import PDFGenerator
        tr = TaxReturn(tax_year=2024, filing_status="S", primary=_person(), address=_address(),
                       w2s=[W2(employer_name="Acme", employer_ein="12-3456789",
                               box1_wages=Decimal("85000"), box3_ss_wages=Decimal("85000"),
                               box5_medicare_wages=Decimal("85000"))],
                       broker_1099s=[Income1099B(payer="Fidelity",
                                                 long_term_proceeds=Decimal("50000"),
                                                 long_term_cost_basis=Decimal("30000"))])
        result = TaxCalculationEngine(get_constants(2024)).compute(tr)
        manifest = PDFGenerator().generate_manifest(tr, result)
        sd = next(f for f in manifest.forms if f.id == "sd")
        assert sd.active is True
        assert sd.start_page is not None
        assert sd.start_page > 2

    def test_manifest_page_numbers_are_sequential(self):
        from api.tax_engine.pdf.generator import PDFGenerator
        tr = TaxReturn(tax_year=2024, filing_status="S", primary=_person(), address=_address(),
                       w2s=[W2(employer_name="Acme", employer_ein="12-3456789",
                               box1_wages=Decimal("85000"), box3_ss_wages=Decimal("85000"),
                               box5_medicare_wages=Decimal("85000"))],
                       broker_1099s=[Income1099B(payer="Fidelity",
                                                 long_term_proceeds=Decimal("50000"),
                                                 long_term_cost_basis=Decimal("30000"))])
        result = TaxCalculationEngine(get_constants(2024)).compute(tr)
        manifest = PDFGenerator().generate_manifest(tr, result)
        active_forms = [f for f in manifest.forms if f.active]
        for i in range(1, len(active_forms)):
            prev = active_forms[i - 1]
            curr = active_forms[i]
            assert curr.start_page == prev.start_page + prev.page_count
