"""Tests for validation rules and engine."""
from datetime import date
from decimal import Decimal
import pytest
from api.tax_engine.models.people import Person, Dependent, Address
from api.tax_engine.models.income import W2, ScheduleK1
from api.tax_engine.models.deductions import HSA
from api.tax_engine.models.tax_return import TaxReturn

def _make_return(**kwargs) -> TaxReturn:
    defaults = dict(
        tax_year=2024, filing_status="S",
        primary=Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 1, 1)),
        address=Address(street="123 Main", city="Springfield", state="IL", zip_code="62701"),
    )
    defaults.update(kwargs)
    return TaxReturn(**defaults)

class TestSSNFormatRule:
    def test_valid_passes(self):
        from api.tax_engine.validation.rules import SSNFormatRule
        rule = SSNFormatRule()
        assert rule.validate(_make_return()) == []

    def test_duplicate_ssn(self):
        from api.tax_engine.validation.rules import DuplicateSSNRule
        rule = DuplicateSSNRule()
        tr = _make_return(dependents=[
            Dependent(first_name="A", last_name="D", ssn="111223333", relationship="son", date_of_birth=date(2015, 1, 1)),
            Dependent(first_name="B", last_name="D", ssn="111223333", relationship="daughter", date_of_birth=date(2017, 1, 1)),
        ])
        results = rule.validate(tr)
        assert len(results) == 1
        assert results[0].severity == "ERROR"
        assert results[0].rule_id == "V007"

class TestMFJSpouseRequired:
    def test_mfj_without_spouse(self):
        from api.tax_engine.validation.rules import MFJSpouseRequiredRule
        rule = MFJSpouseRequiredRule()
        results = rule.validate(_make_return(filing_status="MFJ"))
        assert len(results) == 1
        assert results[0].rule_id == "V003"

    def test_mfj_with_spouse(self):
        from api.tax_engine.validation.rules import MFJSpouseRequiredRule
        rule = MFJSpouseRequiredRule()
        tr = _make_return(filing_status="MFJ",
            spouse=Person(first_name="Jane", last_name="Doe", ssn="987654321", date_of_birth=date(1987, 1, 1)))
        assert rule.validate(tr) == []

class TestSCorpW2Rule:
    def test_scorp_without_w2(self):
        from api.tax_engine.validation.rules import SCorporateW2Rule
        rule = SCorporateW2Rule()
        tr = _make_return(k1s=[ScheduleK1(entity_name="My Corp", entity_ein="12-3456789", entity_type="S", box1_ordinary_income=Decimal("50000"))])
        results = rule.validate(tr)
        assert len(results) == 1
        assert results[0].rule_id == "V001"

    def test_scorp_with_matching_w2(self):
        from api.tax_engine.validation.rules import SCorporateW2Rule
        rule = SCorporateW2Rule()
        tr = _make_return(
            k1s=[ScheduleK1(entity_name="My Corp", entity_ein="12-3456789", entity_type="S", box1_ordinary_income=Decimal("50000"))],
            w2s=[W2(employer_name="My Corp", employer_ein="12-3456789", box1_wages=Decimal("60000"))],
        )
        assert rule.validate(tr) == []

class TestValidationEngine:
    def test_runs_all_rules(self):
        from api.tax_engine.validation.engine import ValidationEngine
        engine = ValidationEngine()
        results = engine.validate(_make_return(filing_status="MFJ"))
        assert any(r.rule_id == "V003" for r in results)

    def test_has_errors(self):
        from api.tax_engine.validation.engine import ValidationEngine
        engine = ValidationEngine()
        assert engine.has_errors(_make_return(filing_status="MFJ")) is True

    def test_no_errors_on_valid(self):
        from api.tax_engine.validation.engine import ValidationEngine
        engine = ValidationEngine()
        assert engine.has_errors(_make_return()) is False
