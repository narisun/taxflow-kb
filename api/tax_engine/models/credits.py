"""Credit-related input models."""
from decimal import Decimal

from pydantic import BaseModel

from api.tax_engine.models.income import PersonRole


class DependentCareExpense(BaseModel):
    provider_name: str
    provider_tin: str | None = None
    provider_address: str | None = None
    amount_paid: Decimal = Decimal("0")
    dependent_name: str
    dependent_ssn: str


class Tuition1098T(BaseModel):
    institution: str
    box1_payments_received: Decimal = Decimal("0")
    box5_scholarships: Decimal = Decimal("0")
    student_name: str
    student_ssn: str
    is_half_time: bool = True
    is_graduate: bool = False
    person_role: PersonRole = "primary"


class EnergyImprovement(BaseModel):
    description: str
    amount: Decimal = Decimal("0")
    is_heat_pump_or_biomass: bool = False


class ResidentialCleanEnergy(BaseModel):
    description: str
    amount: Decimal = Decimal("0")


class Form1095A(BaseModel):
    marketplace_name: str = ""
    annual_enrollment_premium: Decimal = Decimal("0")
    annual_slcsp: Decimal = Decimal("0")
    annual_aptc: Decimal = Decimal("0")
    coverage_months: int = 12
    person_role: PersonRole = "primary"


class EstimatedPayment(BaseModel):
    label: str
    amount: Decimal = Decimal("0")
