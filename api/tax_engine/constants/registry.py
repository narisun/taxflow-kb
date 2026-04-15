"""Tax year constants registry — year-agnostic architecture."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TaxYearConstants:
    tax_year: int
    standard_deduction: dict[str, Decimal]
    # Ordinary income brackets: list of (upper_bound, rate) per filing status
    ordinary_brackets: dict[str, list[tuple[Decimal, Decimal]]]
    ltcg_brackets: dict[str, list[tuple[Decimal, Decimal]]]
    # CTC
    ctc_amount_per_child: Decimal
    ctc_other_dependent: Decimal
    ctc_phase_out: dict[str, Decimal]
    ctc_phase_out_rate: Decimal
    ctc_refundable_max_per_child: Decimal
    ctc_earned_income_threshold: Decimal
    # FICA
    ss_wage_base: Decimal
    ss_tax_rate: Decimal
    ss_combined_rate: Decimal
    medicare_tax_rate: Decimal
    medicare_combined_rate: Decimal
    additional_medicare_rate: Decimal
    additional_medicare_threshold: dict[str, Decimal]
    # NIIT
    niit_rate: Decimal
    niit_threshold: dict[str, Decimal]
    # Deductions
    salt_cap: dict[str, Decimal]
    medical_agi_floor_pct: Decimal
    # QBI
    qbi_deduction_rate: Decimal
    qbi_threshold: dict[str, Decimal]
    qbi_phase_in_range: dict[str, Decimal]
    # HSA
    hsa_limit: dict[str, Decimal]
    hsa_catchup: Decimal
    # IRA
    ira_contribution_limit: Decimal
    ira_catchup: Decimal
    # AMT
    amt_exemption: dict[str, Decimal]
    amt_phase_out: dict[str, Decimal]
    amt_rate_low: Decimal
    amt_rate_high: Decimal
    amt_bracket: dict[str, Decimal]
    # Student loan
    student_loan_max_deduction: Decimal
    student_loan_phase_out: dict[str, tuple[Decimal, Decimal]]
    # Capital loss
    capital_loss_limit: dict[str, Decimal]


_REGISTRY: dict[int, TaxYearConstants] = {}


def register(constants: TaxYearConstants) -> None:
    _REGISTRY[constants.tax_year] = constants


def get_constants(year: int) -> TaxYearConstants:
    if year not in _REGISTRY:
        raise ValueError(f"No tax constants registered for year {year}")
    return _REGISTRY[year]


def available_years() -> list[int]:
    return sorted(_REGISTRY.keys())
