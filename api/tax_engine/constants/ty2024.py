"""TY2024 IRS tax constants."""
from decimal import Decimal

from api.tax_engine.constants.registry import TaxYearConstants, register

_INF = Decimal("Infinity")

_ordinary_brackets_s = [
    (Decimal("11600"), Decimal("0.10")),
    (Decimal("47150"), Decimal("0.12")),
    (Decimal("100525"), Decimal("0.22")),
    (Decimal("191950"), Decimal("0.24")),
    (Decimal("243725"), Decimal("0.32")),
    (Decimal("609350"), Decimal("0.35")),
    (_INF, Decimal("0.37")),
]

_ordinary_brackets_mfj = [
    (Decimal("23200"), Decimal("0.10")),
    (Decimal("94300"), Decimal("0.12")),
    (Decimal("201050"), Decimal("0.22")),
    (Decimal("383900"), Decimal("0.24")),
    (Decimal("487450"), Decimal("0.32")),
    (Decimal("731200"), Decimal("0.35")),
    (_INF, Decimal("0.37")),
]

_ordinary_brackets_mfs = [
    (Decimal("11600"), Decimal("0.10")),
    (Decimal("47150"), Decimal("0.12")),
    (Decimal("100525"), Decimal("0.22")),
    (Decimal("191950"), Decimal("0.24")),
    (Decimal("243725"), Decimal("0.32")),
    (Decimal("365600"), Decimal("0.35")),
    (_INF, Decimal("0.37")),
]

_ordinary_brackets_hoh = [
    (Decimal("16550"), Decimal("0.10")),
    (Decimal("63100"), Decimal("0.12")),
    (Decimal("100500"), Decimal("0.22")),
    (Decimal("191950"), Decimal("0.24")),
    (Decimal("243700"), Decimal("0.32")),
    (Decimal("609350"), Decimal("0.35")),
    (_INF, Decimal("0.37")),
]

_ltcg_brackets_s = [
    (Decimal("47025"), Decimal("0.00")),
    (Decimal("518900"), Decimal("0.15")),
    (_INF, Decimal("0.20")),
]

_ltcg_brackets_mfj = [
    (Decimal("94050"), Decimal("0.00")),
    (Decimal("583750"), Decimal("0.15")),
    (_INF, Decimal("0.20")),
]

_ltcg_brackets_mfs = [
    (Decimal("47025"), Decimal("0.00")),
    (Decimal("291850"), Decimal("0.15")),
    (_INF, Decimal("0.20")),
]

_ltcg_brackets_hoh = [
    (Decimal("63000"), Decimal("0.00")),
    (Decimal("551350"), Decimal("0.15")),
    (_INF, Decimal("0.20")),
]

TY2024 = TaxYearConstants(
    tax_year=2024,
    standard_deduction={
        "S": Decimal("14600"),
        "MFJ": Decimal("29200"),
        "MFS": Decimal("14600"),
        "HOH": Decimal("21900"),
        "QSS": Decimal("29200"),
    },
    ordinary_brackets={
        "S": _ordinary_brackets_s,
        "MFJ": _ordinary_brackets_mfj,
        "MFS": _ordinary_brackets_mfs,
        "HOH": _ordinary_brackets_hoh,
        "QSS": _ordinary_brackets_mfj,  # QSS uses MFJ brackets
    },
    ltcg_brackets={
        "S": _ltcg_brackets_s,
        "MFJ": _ltcg_brackets_mfj,
        "MFS": _ltcg_brackets_mfs,
        "HOH": _ltcg_brackets_hoh,
        "QSS": _ltcg_brackets_mfj,
    },
    ctc_amount_per_child=Decimal("2000"),
    ctc_other_dependent=Decimal("500"),
    ctc_phase_out={
        "S": Decimal("200000"),
        "MFJ": Decimal("400000"),
        "MFS": Decimal("200000"),
        "HOH": Decimal("200000"),
        "QSS": Decimal("400000"),
    },
    ctc_phase_out_rate=Decimal("0.05"),
    ctc_refundable_max_per_child=Decimal("1600"),
    ctc_earned_income_threshold=Decimal("2500"),
    ss_wage_base=Decimal("168600"),
    ss_tax_rate=Decimal("0.062"),
    ss_combined_rate=Decimal("0.124"),
    medicare_tax_rate=Decimal("0.0145"),
    medicare_combined_rate=Decimal("0.029"),
    additional_medicare_rate=Decimal("0.009"),
    additional_medicare_threshold={
        "S": Decimal("200000"),
        "MFJ": Decimal("250000"),
        "MFS": Decimal("125000"),
        "HOH": Decimal("200000"),
        "QSS": Decimal("250000"),
    },
    niit_rate=Decimal("0.038"),
    niit_threshold={
        "S": Decimal("200000"),
        "MFJ": Decimal("250000"),
        "MFS": Decimal("125000"),
        "HOH": Decimal("200000"),
        "QSS": Decimal("250000"),
    },
    salt_cap={
        "S": Decimal("10000"),
        "MFJ": Decimal("10000"),
        "MFS": Decimal("5000"),
        "HOH": Decimal("10000"),
        "QSS": Decimal("10000"),
    },
    medical_agi_floor_pct=Decimal("0.075"),
    qbi_deduction_rate=Decimal("0.20"),
    qbi_threshold={
        "S": Decimal("191950"),
        "MFJ": Decimal("383900"),
        "MFS": Decimal("191950"),
        "HOH": Decimal("191950"),
        "QSS": Decimal("383900"),
    },
    qbi_phase_in_range={
        "S": Decimal("50000"),
        "MFJ": Decimal("100000"),
        "MFS": Decimal("50000"),
        "HOH": Decimal("50000"),
        "QSS": Decimal("100000"),
    },
    hsa_limit={
        "self-only": Decimal("4150"),
        "family": Decimal("8300"),
    },
    hsa_catchup=Decimal("1000"),
    ira_contribution_limit=Decimal("7000"),
    ira_catchup=Decimal("1000"),
    amt_exemption={
        "S": Decimal("85700"),
        "MFJ": Decimal("133300"),
        "MFS": Decimal("66650"),
        "HOH": Decimal("85700"),
        "QSS": Decimal("133300"),
    },
    amt_phase_out={
        "S": Decimal("609350"),
        "MFJ": Decimal("1218700"),
        "MFS": Decimal("609350"),
        "HOH": Decimal("609350"),
        "QSS": Decimal("1218700"),
    },
    amt_rate_low=Decimal("0.26"),
    amt_rate_high=Decimal("0.28"),
    amt_bracket={
        "S": Decimal("232600"),
        "MFJ": Decimal("232600"),
        "MFS": Decimal("116300"),
        "HOH": Decimal("232600"),
        "QSS": Decimal("232600"),
    },
    student_loan_max_deduction=Decimal("2500"),
    student_loan_phase_out={
        "S": (Decimal("75000"), Decimal("90000")),
        "MFJ": (Decimal("155000"), Decimal("185000")),
        "MFS": (Decimal("0"), Decimal("0")),
        "HOH": (Decimal("75000"), Decimal("90000")),
        "QSS": (Decimal("155000"), Decimal("185000")),
    },
    capital_loss_limit={
        "S": Decimal("3000"),
        "MFJ": Decimal("3000"),
        "MFS": Decimal("1500"),
        "HOH": Decimal("3000"),
        "QSS": Decimal("3000"),
    },
)

register(TY2024)
