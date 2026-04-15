"""Shared test fixtures for tax engine tests."""
import pytest
from datetime import date
from decimal import Decimal
from api.tax_engine.models.people import Person, Address
from api.tax_engine.models.tax_return import TaxReturn
from api.tax_engine.constants.registry import get_constants, TaxYearConstants
import api.tax_engine.constants  # noqa: F401

@pytest.fixture
def constants_2024() -> TaxYearConstants:
    return get_constants(2024)

@pytest.fixture
def constants_2025() -> TaxYearConstants:
    return get_constants(2025)

@pytest.fixture
def primary_person() -> Person:
    return Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 3, 15))

@pytest.fixture
def spouse_person() -> Person:
    return Person(first_name="Jane", last_name="Doe", ssn="987654321", date_of_birth=date(1987, 5, 10))

@pytest.fixture
def address() -> Address:
    return Address(street="123 Main St", city="Springfield", state="IL", zip_code="62701")

@pytest.fixture
def minimal_return(primary_person, address) -> TaxReturn:
    return TaxReturn(tax_year=2024, filing_status="S", primary=primary_person, address=address)

@pytest.fixture
def mfj_return(primary_person, spouse_person, address) -> TaxReturn:
    return TaxReturn(tax_year=2024, filing_status="MFJ", primary=primary_person, spouse=spouse_person, address=address)
