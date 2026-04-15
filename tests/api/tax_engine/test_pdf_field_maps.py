"""Tests for PDF field mapping functions."""
from datetime import date
from decimal import Decimal

import api.tax_engine.constants  # noqa: F401
from api.tax_engine.constants.registry import get_constants
from api.tax_engine.models.people import Person, Dependent, Address
from api.tax_engine.models.income import W2, Income1099Int, Income1099B
from api.tax_engine.models.deductions import ItemizedDeductions, RentalProperty
from api.tax_engine.models.tax_return import TaxReturn, TaxResult, FormResult, LineTrace


def _person():
    return Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 1, 1))


def _address():
    return Address(street="123 Main St", city="Springfield", state="IL", zip_code="62701")


def _make_return(**kwargs) -> TaxReturn:
    defaults = dict(tax_year=2024, filing_status="S", primary=_person(), address=_address())
    defaults.update(kwargs)
    return TaxReturn(**defaults)


def _make_result(**kwargs) -> TaxResult:
    defaults = dict(tax_year=2024, filing_status="S", total_income=Decimal("85000"),
                    agi=Decimal("85000"), taxable_income=Decimal("70400"),
                    total_tax=Decimal("10000"), total_payments=Decimal("15000"),
                    refund_or_owed=Decimal("5000"))
    defaults.update(kwargs)
    return TaxResult(**defaults)


class TestFmt:
    def test_formats_with_commas(self):
        from api.tax_engine.pdf.field_maps import fmt
        assert fmt(Decimal("85000")) == "85,000"

    def test_zero_returns_empty(self):
        from api.tax_engine.pdf.field_maps import fmt
        assert fmt(Decimal("0")) == ""

    def test_none_returns_empty(self):
        from api.tax_engine.pdf.field_maps import fmt
        assert fmt(None) == ""

    def test_string_passthrough(self):
        from api.tax_engine.pdf.field_maps import fmt
        assert fmt("IL") == "IL"


class TestForm1040Map:
    def test_basic_fields(self):
        from api.tax_engine.pdf.field_maps import map_f1040
        tr = _make_return(w2s=[W2(employer_name="Acme", employer_ein="12-3456789",
                                  box1_wages=Decimal("85000"), box2_fed_withheld=Decimal("15000"))])
        result = _make_result(
            form_results={
                "1040": FormResult(form_name="1040", total=Decimal("5000"), lines={
                    "1a": LineTrace(form="1040", line="1a", label="Wages", value=Decimal("85000"), formula="test"),
                    "9": LineTrace(form="1040", line="9", label="Total income", value=Decimal("85000"), formula="test"),
                    "11": LineTrace(form="1040", line="11", label="AGI", value=Decimal("85000"), formula="test"),
                    "12": LineTrace(form="1040", line="12", label="Deduction", value=Decimal("14600"), formula="test"),
                    "15": LineTrace(form="1040", line="15", label="Taxable income", value=Decimal("70400"), formula="test"),
                    "16": LineTrace(form="1040", line="16", label="Tax", value=Decimal("11000"), formula="test"),
                    "24": LineTrace(form="1040", line="24", label="Total tax", value=Decimal("11000"), formula="test"),
                    "25": LineTrace(form="1040", line="25", label="Withholding", value=Decimal("15000"), formula="test"),
                    "33": LineTrace(form="1040", line="33", label="Total payments", value=Decimal("15000"), formula="test"),
                    "35a": LineTrace(form="1040", line="35a", label="Refund", value=Decimal("4000"), formula="test"),
                }),
            })
        fields = map_f1040(tr, result)
        assert 0 in fields  # Page 1
        assert 1 in fields  # Page 2
        assert fields[0]["f1_04[0]"] == "John"
        assert fields[0]["f1_05[0]"] == "Doe"
        assert fields[0]["f1_06[0]"] == "123456789"
        assert fields[0]["f1_10[0]"] == "123 Main St"
        assert fields[0]["c1_1[0]"] == "/1"  # Single filing status
        assert fields[0]["f1_32[0]"] == "85,000"  # Line 1a wages

    def test_mfj_checkbox(self):
        from api.tax_engine.pdf.field_maps import map_f1040
        spouse = Person(first_name="Jane", last_name="Doe", ssn="987654321", date_of_birth=date(1987, 5, 10))
        tr = _make_return(filing_status="MFJ", spouse=spouse)
        result = _make_result(filing_status="MFJ", form_results={
            "1040": FormResult(form_name="1040", total=Decimal("0"), lines={})})
        fields = map_f1040(tr, result)
        assert fields[0]["c1_2[0]"] == "/1"  # MFJ
        assert fields[0]["f1_07[0]"] == "Jane"

    def test_dependents(self):
        from api.tax_engine.pdf.field_maps import map_f1040
        tr = _make_return(dependents=[
            Dependent(first_name="Kid", last_name="Doe", ssn="111223333",
                      relationship="son", date_of_birth=date(2015, 1, 1)),
        ])
        result = _make_result(form_results={
            "1040": FormResult(form_name="1040", total=Decimal("0"), lines={})})
        fields = map_f1040(tr, result)
        assert fields[0]["f1_20[0]"] == "Kid Doe"
        assert fields[0]["f1_21[0]"] == "111223333"


class TestActiveFormChecks:
    def test_schedule_d_active_with_broker(self):
        from api.tax_engine.pdf.field_maps import is_schedule_d_active
        tr = _make_return(broker_1099s=[Income1099B(payer="Fidelity", long_term_proceeds=Decimal("50000"))])
        assert is_schedule_d_active(tr, _make_result()) is True

    def test_schedule_d_inactive(self):
        from api.tax_engine.pdf.field_maps import is_schedule_d_active
        assert is_schedule_d_active(_make_return(), _make_result()) is False

    def test_schedule_a_active_when_itemizing(self):
        from api.tax_engine.pdf.field_maps import is_schedule_a_active
        result = _make_result(form_results={
            "Schedule A": FormResult(form_name="Schedule A", total=Decimal("20000")),
            "deduction": FormResult(form_name="deduction", total=Decimal("20000"),
                lines={"12": LineTrace(form="1040", line="12", label="Itemized", value=Decimal("20000"), formula="itemized")})})
        tr = _make_return(itemized=ItemizedDeductions(mortgage_interest_1098=Decimal("15000"), charity_cash=Decimal("5000")))
        assert is_schedule_a_active(tr, result) is True

    def test_schedule_a_inactive_standard(self):
        from api.tax_engine.pdf.field_maps import is_schedule_a_active
        result = _make_result(form_results={
            "deduction": FormResult(form_name="deduction", total=Decimal("14600"),
                lines={"12": LineTrace(form="1040", line="12", label="Standard", value=Decimal("14600"), formula="standard")})})
        assert is_schedule_a_active(_make_return(), result) is False
