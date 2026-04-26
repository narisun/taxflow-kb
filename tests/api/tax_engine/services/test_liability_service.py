"""Unit tests for :class:`api.tax_engine.services.liability.LiabilityService`.

Covers the progressive-bracket computation at and around bracket boundaries,
plus QBI-subtraction interaction and the surtax integrations.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from api.tax_engine.models.tax_return import FormResult, LineTrace
from api.tax_engine.services.liability import LiabilityService

pytestmark = pytest.mark.unit


def _ti_result(amount: Decimal) -> FormResult:
    return FormResult(
        form_name="pre-QBI",
        total=amount,
        lines={
            "15": LineTrace(
                form="1040",
                line="15",
                label="Taxable income (before QBI)",
                value=amount,
                formula="test fixture",
            )
        },
    )


class TestOrdinaryTaxBrackets:
    def test_zero_income_zero_tax(self, constants_2024, minimal_return):
        svc = LiabilityService(constants_2024)
        out = svc.compute(minimal_return, {"taxable_income_before_qbi": _ti_result(Decimal("0"))})
        assert out["ordinary_tax"].total == Decimal("0.00")

    def test_first_bracket_single(self, constants_2024, minimal_return):
        """Single 2024: 10% on first $11,600 → $1,160 on the nose."""
        svc = LiabilityService(constants_2024)
        out = svc.compute(
            minimal_return, {"taxable_income_before_qbi": _ti_result(Decimal("11600"))}
        )
        assert out["ordinary_tax"].total == Decimal("1160.00")

    def test_spans_first_and_second_bracket_single(
        self, constants_2024, minimal_return
    ):
        """Single 2024: $20,000 → 10% of 11,600 + 12% of 8,400 = 1,160 + 1,008 = 2,168."""
        svc = LiabilityService(constants_2024)
        out = svc.compute(
            minimal_return, {"taxable_income_before_qbi": _ti_result(Decimal("20000"))}
        )
        assert out["ordinary_tax"].total == Decimal("2168.00")

    def test_qbi_reduces_taxable_income(self, constants_2024, minimal_return):
        """Taxable income of 20,000 with 5,000 QBI deduction should tax 15,000."""
        svc = LiabilityService(constants_2024)
        qbi = FormResult(
            form_name="Form 8995",
            total=Decimal("5000"),
            lines={"15": LineTrace(form="8995", line="15", label="QBI", value=Decimal("5000"), formula="test")},
        )
        out = svc.compute(
            minimal_return,
            {
                "taxable_income_before_qbi": _ti_result(Decimal("20000")),
                "Form 8995": qbi,
            },
        )
        # 10% of 11,600 + 12% of 3,400 = 1,160 + 408 = 1,568
        assert out["ordinary_tax"].total == Decimal("1568.00")

    def test_qbi_cannot_produce_negative_taxable_income(
        self, constants_2024, minimal_return
    ):
        svc = LiabilityService(constants_2024)
        qbi = FormResult(
            form_name="Form 8995",
            total=Decimal("99999"),
            lines={"15": LineTrace(form="8995", line="15", label="QBI", value=Decimal("99999"), formula="test")},
        )
        out = svc.compute(
            minimal_return,
            {
                "taxable_income_before_qbi": _ti_result(Decimal("10000")),
                "Form 8995": qbi,
            },
        )
        assert out["ordinary_tax"].total == Decimal("0.00")


class TestSurtaxes:
    def test_schedule_se_present_in_output(self, constants_2024, minimal_return):
        svc = LiabilityService(constants_2024)
        out = svc.compute(
            minimal_return, {"taxable_income_before_qbi": _ti_result(Decimal("50000"))}
        )
        assert "Schedule SE" in out
        assert "Form 8959" in out
        assert "Form 8960" in out
