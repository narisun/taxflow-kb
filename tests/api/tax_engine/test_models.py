"""Tests for tax engine domain models."""
import pytest
from datetime import date
from decimal import Decimal


class TestPerson:
    def test_valid_person(self):
        from api.tax_engine.models.people import Person
        p = Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 3, 15))
        assert p.first_name == "John"
        assert p.ssn == "123456789"
        assert p.is_blind is False

    def test_ssn_must_be_9_digits(self):
        from api.tax_engine.models.people import Person
        with pytest.raises(ValueError):
            Person(first_name="John", last_name="Doe", ssn="12345", date_of_birth=date(1985, 3, 15))

    def test_ssn_normalizes_dashed_input(self):
        """SSNs flow in from UIs, OCR, and intake forms with dashes — model
        should normalize to the 9-digit canonical form."""
        from api.tax_engine.models.people import Person
        p = Person(
            first_name="Jane", last_name="Doe",
            ssn="100-10-1001", date_of_birth=date(1990, 1, 1),
        )
        assert p.ssn == "100101001"

    def test_ssn_normalizes_spaced_input(self):
        from api.tax_engine.models.people import Person
        p = Person(
            first_name="Jane", last_name="Doe",
            ssn="100 10 1001", date_of_birth=date(1990, 1, 1),
        )
        assert p.ssn == "100101001"

    def test_ssn_rejects_all_zeros_in_area(self):
        from api.tax_engine.models.people import Person
        with pytest.raises(ValueError):
            Person(first_name="John", last_name="Doe", ssn="000456789", date_of_birth=date(1985, 3, 15))

    def test_ssn_rejects_all_zeros_in_group(self):
        from api.tax_engine.models.people import Person
        with pytest.raises(ValueError):
            Person(first_name="John", last_name="Doe", ssn="123006789", date_of_birth=date(1985, 3, 15))

    def test_ssn_rejects_all_zeros_in_serial(self):
        from api.tax_engine.models.people import Person
        with pytest.raises(ValueError):
            Person(first_name="John", last_name="Doe", ssn="123450000", date_of_birth=date(1985, 3, 15))


class TestDependent:
    def test_valid_dependent(self):
        from api.tax_engine.models.people import Dependent
        d = Dependent(first_name="Jane", last_name="Doe", ssn="987654321", relationship="daughter", date_of_birth=date(2015, 7, 20))
        assert d.months_lived_with == 12
        assert d.is_qualifying_child is True

    def test_months_lived_with_range(self):
        from api.tax_engine.models.people import Dependent
        with pytest.raises(ValueError):
            Dependent(first_name="Jane", last_name="Doe", ssn="987654321", relationship="daughter", date_of_birth=date(2015, 7, 20), months_lived_with=13)


class TestAddress:
    def test_valid_address(self):
        from api.tax_engine.models.people import Address
        a = Address(street="123 Main St", city="Springfield", state="IL", zip_code="62701")
        assert a.apt is None

    def test_zip_must_be_5_or_9_digits(self):
        from api.tax_engine.models.people import Address
        with pytest.raises(ValueError):
            Address(street="123 Main St", city="Springfield", state="IL", zip_code="123")


class TestW2:
    def test_valid_w2(self):
        from api.tax_engine.models.income import W2
        w = W2(employer_name="Acme Corp", employer_ein="12-3456789", box1_wages=Decimal("85000"), box2_fed_withheld=Decimal("15000"))
        assert w.box1_wages == Decimal("85000")
        assert w.person_role == "primary"

    def test_ein_format_validation(self):
        from api.tax_engine.models.income import W2
        with pytest.raises(ValueError):
            W2(employer_name="Acme", employer_ein="invalid", box1_wages=Decimal("1000"))

    def test_defaults_to_zero(self):
        from api.tax_engine.models.income import W2
        w = W2(employer_name="Acme", employer_ein="12-3456789")
        assert w.box3_ss_wages == Decimal("0")
        assert w.box12_codes == {}


class TestIncome1099Int:
    def test_valid(self):
        from api.tax_engine.models.income import Income1099Int
        f = Income1099Int(payer="Chase Bank", box1_interest=Decimal("1500"))
        assert f.box4_fed_withheld == Decimal("0")


class TestIncome1099Div:
    def test_valid(self):
        from api.tax_engine.models.income import Income1099Div
        f = Income1099Div(payer="Vanguard", box1a_ordinary_dividends=Decimal("5000"), box1b_qualified_dividends=Decimal("4000"))
        assert f.box2a_capital_gain_distributions == Decimal("0")


class TestIncome1099B:
    def test_valid(self):
        from api.tax_engine.models.income import Income1099B
        f = Income1099B(payer="Fidelity", short_term_proceeds=Decimal("10000"), short_term_cost_basis=Decimal("8000"), long_term_proceeds=Decimal("50000"), long_term_cost_basis=Decimal("30000"))
        assert f.collectibles_gain == Decimal("0")


class TestScheduleC:
    def test_net_profit_computed(self):
        from api.tax_engine.models.income import ScheduleC
        sc = ScheduleC(business_name="My Consulting", gross_receipts=Decimal("120000"), cost_of_goods_sold=Decimal("10000"), advertising=Decimal("2000"), supplies=Decimal("3000"))
        assert sc.net_profit == Decimal("105000")

    def test_total_expenses(self):
        from api.tax_engine.models.income import ScheduleC
        sc = ScheduleC(business_name="Test", gross_receipts=Decimal("100000"), advertising=Decimal("1000"), insurance=Decimal("2000"), rent_lease=Decimal("3000"))
        assert sc.total_expenses == Decimal("6000")


class TestScheduleK1:
    def test_valid_partnership(self):
        from api.tax_engine.models.income import ScheduleK1
        k1 = ScheduleK1(entity_name="ABC Partners", entity_ein="98-7654321", entity_type="P", box1_ordinary_income=Decimal("50000"))
        assert k1.is_passive is False
        assert k1.is_sstb is False


class TestItemizedDeductions:
    def test_defaults_to_zero(self):
        from api.tax_engine.models.deductions import ItemizedDeductions
        d = ItemizedDeductions()
        assert d.medical_dental == Decimal("0")
        assert d.charity_cash == Decimal("0")


class TestRentalProperty:
    def test_net_income_computed(self):
        from api.tax_engine.models.deductions import RentalProperty
        rp = RentalProperty(address="456 Oak Ave", rent_received=Decimal("24000"), mortgage_interest=Decimal("8000"), taxes=Decimal("4000"), insurance=Decimal("2000"))
        assert rp.net_income == Decimal("10000")


class TestLineTrace:
    def test_frozen(self):
        from api.tax_engine.models.tax_return import LineTrace
        lt = LineTrace(form="1040", line="1a", label="Wages", value=Decimal("85000"), formula="sum(w2.box1_wages)")
        with pytest.raises(Exception):
            lt.value = Decimal("0")

    def test_fields(self):
        from api.tax_engine.models.tax_return import LineTrace
        lt = LineTrace(form="Schedule A", line="7", label="SALT", value=Decimal("10000"), formula="min(salt_total, salt_cap)", constants_used={"salt_cap": "10000"}, irs_citation="TCJA §11042")
        assert lt.irs_citation == "TCJA §11042"


class TestTaxReturn:
    def test_minimal_return(self):
        from api.tax_engine.models.people import Person, Address
        from api.tax_engine.models.tax_return import TaxReturn
        tr = TaxReturn(
            tax_year=2024, filing_status="S",
            primary=Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 1, 1)),
            address=Address(street="123 Main St", city="Springfield", state="IL", zip_code="62701"),
        )
        assert tr.w2s == []
        assert tr.filing_status == "S"

    def test_full_return_with_income(self):
        from api.tax_engine.models.people import Person, Address
        from api.tax_engine.models.income import W2
        from api.tax_engine.models.tax_return import TaxReturn
        tr = TaxReturn(
            tax_year=2024, filing_status="MFJ",
            primary=Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 1, 1)),
            spouse=Person(first_name="Jane", last_name="Doe", ssn="987654321", date_of_birth=date(1987, 5, 10)),
            address=Address(street="123 Main St", city="Springfield", state="IL", zip_code="62701"),
            w2s=[W2(employer_name="Acme", employer_ein="12-3456789", box1_wages=Decimal("85000"))],
        )
        assert len(tr.w2s) == 1


class TestFormResult:
    def test_basic(self):
        from api.tax_engine.models.tax_return import FormResult, LineTrace
        fr = FormResult(
            form_name="Schedule B",
            lines={"4": LineTrace(form="Schedule B", line="4", label="Total interest", value=Decimal("5000"), formula="sum(1099_int)")},
            total=Decimal("5000"),
        )
        assert fr.lines["4"].value == Decimal("5000")
