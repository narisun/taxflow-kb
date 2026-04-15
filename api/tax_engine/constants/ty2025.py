"""TY2025 IRS tax constants."""
from decimal import Decimal

from api.tax_engine.constants.registry import TaxYearConstants, register

_INF = Decimal("Infinity")

_ordinary_brackets_s = [
    (Decimal("11925"), Decimal("0.10")),
    (Decimal("48475"), Decimal("0.12")),
    (Decimal("103350"), Decimal("0.22")),
    (Decimal("197300"), Decimal("0.24")),
    (Decimal("250525"), Decimal("0.32")),
    (Decimal("626350"), Decimal("0.35")),
    (_INF, Decimal("0.37")),
]

_ordinary_brackets_mfj = [
    (Decimal("23850"), Decimal("0.10")),
    (Decimal("96950"), Decimal("0.12")),
    (Decimal("206700"), Decimal("0.22")),
    (Decimal("394600"), Decimal("0.24")),
    (Decimal("501050"), Decimal("0.32")),
    (Decimal("751600"), Decimal("0.35")),
    (_INF, Decimal("0.37")),
]

_ordinary_brackets_mfs = [
    (Decimal("11925"), Decimal("0.10")),
    (Decimal("48475"), Decimal("0.12")),
    (Decimal("103350"), Decimal("0.22")),
    (Decimal("197300"), Decimal("0.24")),
    (Decimal("250525"), Decimal("0.32")),
    (Decimal("375800"), Decimal("0.35")),
    (_INF, Decimal("0.37")),
]

_ordinary_brackets_hoh = [
    (Decimal("17000"), Decimal("0.10")),
    (Decimal("64850"), Decimal("0.12")),
    (Decimal("103350"), Decimal("0.22")),
    (Decimal("197300"), Decimal("0.24")),
    (Decimal("250500"), Decimal("0.32")),
    (Decimal("626350"), Decimal("0.35")),
    (_INF, Decimal("0.37")),
]

_ltcg_brackets_s = [
    (Decimal("48350"), Decimal("0.00")),
    (Decimal("533400"), Decimal("0.15")),
    (_INF, Decimal("0.20")),
]

_ltcg_brackets_mfj = [
    (Decimal("96700"), Decimal("0.00")),
    (Decimal("600050"), Decimal("0.15")),
    (_INF, Decimal("0.20")),
]

_ltcg_brackets_mfs = [
    (Decimal("48350"), Decimal("0.00")),
    (Decimal("300000"), Decimal("0.15")),
    (_INF, Decimal("0.20")),
]

_ltcg_brackets_hoh = [
    (Decimal("64750"), Decimal("0.00")),
    (Decimal("566700"), Decimal("0.15")),
    (_INF, Decimal("0.20")),
]

TY2025 = TaxYearConstants(
    tax_year=2025,
    standard_deduction={
        "S": Decimal("15000"),
        "MFJ": Decimal("30000"),
        "MFS": Decimal("15000"),
        "HOH": Decimal("22500"),
        "QSS": Decimal("30000"),
    },
    ordinary_brackets={
        "S": _ordinary_brackets_s,
        "MFJ": _ordinary_brackets_mfj,
        "MFS": _ordinary_brackets_mfs,
        "HOH": _ordinary_brackets_hoh,
        "QSS": _ordinary_brackets_mfj,
    },
    ltcg_brackets={
        "S": _ltcg_brackets_s,
        "MFJ": _ltcg_brackets_mfj,
        "MFS": _ltcg_brackets_mfs,
        "HOH": _ltcg_brackets_hoh,
        "QSS": _ltcg_brackets_mfj,
    },
    ctc_amount_per_child=Decimal("2200"),
    ctc_other_dependent=Decimal("500"),
    ctc_phase_out={
        "S": Decimal("200000"),
        "MFJ": Decimal("400000"),
        "MFS": Decimal("200000"),
        "HOH": Decimal("200000"),
        "QSS": Decimal("400000"),
    },
    ctc_phase_out_rate=Decimal("0.05"),
    ctc_refundable_max_per_child=Decimal("1700"),
    ctc_earned_income_threshold=Decimal("2500"),
    ss_wage_base=Decimal("176100"),
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
        "S": Decimal("40000"),
        "MFJ": Decimal("40000"),
        "MFS": Decimal("20000"),
        "HOH": Decimal("40000"),
        "QSS": Decimal("40000"),
    },
    medical_agi_floor_pct=Decimal("0.075"),
    qbi_deduction_rate=Decimal("0.20"),
    qbi_threshold={
        "S": Decimal("197300"),
        "MFJ": Decimal("394600"),
        "MFS": Decimal("197300"),
        "HOH": Decimal("197300"),
        "QSS": Decimal("394600"),
    },
    qbi_phase_in_range={
        "S": Decimal("50000"),
        "MFJ": Decimal("100000"),
        "MFS": Decimal("50000"),
        "HOH": Decimal("50000"),
        "QSS": Decimal("100000"),
    },
    hsa_limit={
        "self-only": Decimal("4300"),
        "family": Decimal("8550"),
    },
    hsa_catchup=Decimal("1000"),
    ira_contribution_limit=Decimal("7000"),
    ira_catchup=Decimal("1000"),
    amt_exemption={
        "S": Decimal("88100"),
        "MFJ": Decimal("137000"),
        "MFS": Decimal("68500"),
        "HOH": Decimal("88100"),
        "QSS": Decimal("137000"),
    },
    amt_phase_out={
        "S": Decimal("626350"),
        "MFJ": Decimal("1252700"),
        "MFS": Decimal("626350"),
        "HOH": Decimal("626350"),
        "QSS": Decimal("1252700"),
    },
    amt_rate_low=Decimal("0.26"),
    amt_rate_high=Decimal("0.28"),
    amt_bracket={
        "S": Decimal("239100"),
        "MFJ": Decimal("239100"),
        "MFS": Decimal("119550"),
        "HOH": Decimal("239100"),
        "QSS": Decimal("239100"),
    },
    student_loan_max_deduction=Decimal("2500"),
    student_loan_phase_out={
        "S": (Decimal("80000"), Decimal("95000")),
        "MFJ": (Decimal("160000"), Decimal("195000")),
        "MFS": (Decimal("0"), Decimal("0")),
        "HOH": (Decimal("80000"), Decimal("95000")),
        "QSS": (Decimal("160000"), Decimal("195000")),
    },
    capital_loss_limit={
        "S": Decimal("3000"),
        "MFJ": Decimal("3000"),
        "MFS": Decimal("1500"),
        "HOH": Decimal("3000"),
        "QSS": Decimal("3000"),
    },
)

register(TY2025)
