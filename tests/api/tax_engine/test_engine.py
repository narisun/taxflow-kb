"""End-to-end test: TaxReturn → TaxCalculationEngine → TaxResult."""
from datetime import date
from decimal import Decimal
from api.tax_engine.models.people import Person, Dependent, Address
from api.tax_engine.models.income import W2, Income1099Int
from api.tax_engine.models.tax_return import TaxReturn

class TestTaxCalculationEngine:
    def test_simple_w2_single(self, constants_2024):
        from api.tax_engine.services.engine import TaxCalculationEngine
        tr = TaxReturn(
            tax_year=2024, filing_status="S",
            primary=Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 1, 1)),
            address=Address(street="123 Main", city="Springfield", state="IL", zip_code="62701"),
            w2s=[W2(employer_name="Acme", employer_ein="12-3456789", box1_wages=Decimal("85000"),
                     box2_fed_withheld=Decimal("15000"), box3_ss_wages=Decimal("85000"), box5_medicare_wages=Decimal("85000"))],
        )
        result = TaxCalculationEngine(constants_2024).compute(tr)
        assert result.tax_year == 2024
        assert result.filing_status == "S"
        assert result.total_income == Decimal("85000")
        assert result.taxable_income == Decimal("70400")
        assert result.total_tax > Decimal("0")
        assert result.total_payments == Decimal("15000")
        assert len(result.all_traces) > 0

    def test_mfj_with_children_and_interest(self, constants_2024):
        from api.tax_engine.services.engine import TaxCalculationEngine
        tr = TaxReturn(
            tax_year=2024, filing_status="MFJ",
            primary=Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 1, 1)),
            spouse=Person(first_name="Jane", last_name="Doe", ssn="987654321", date_of_birth=date(1987, 5, 10)),
            address=Address(street="123 Main", city="Springfield", state="IL", zip_code="62701"),
            dependents=[Dependent(first_name="Kid", last_name="Doe", ssn="111223333", relationship="son", date_of_birth=date(2015, 6, 1))],
            w2s=[
                W2(employer_name="Acme", employer_ein="12-3456789", box1_wages=Decimal("120000"), box2_fed_withheld=Decimal("20000"),
                   box3_ss_wages=Decimal("120000"), box5_medicare_wages=Decimal("120000"), person_role="primary"),
                W2(employer_name="Beta", employer_ein="98-7654321", box1_wages=Decimal("65000"), box2_fed_withheld=Decimal("10000"),
                   box3_ss_wages=Decimal("65000"), box5_medicare_wages=Decimal("65000"), person_role="spouse"),
            ],
            interest_1099s=[Income1099Int(payer="Chase", box1_interest=Decimal("3800"))],
        )
        result = TaxCalculationEngine(constants_2024).compute(tr)
        assert result.total_income == Decimal("188800")
        assert result.taxable_income == Decimal("159600")
        assert result.total_credits >= Decimal("0")
        assert result.total_payments == Decimal("30000")

    def test_zero_income(self, constants_2024):
        from api.tax_engine.services.engine import TaxCalculationEngine
        tr = TaxReturn(
            tax_year=2024, filing_status="S",
            primary=Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 1, 1)),
            address=Address(street="123 Main", city="Springfield", state="IL", zip_code="62701"),
        )
        result = TaxCalculationEngine(constants_2024).compute(tr)
        assert result.total_income == Decimal("0")
        assert result.total_tax == Decimal("0")
        assert result.refund_or_owed == Decimal("0")
