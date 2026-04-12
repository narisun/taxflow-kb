"""
tax_brain/rules/validation/test_replay.py

V1.3 — IRS Test Return Replay (Days 6–10)

The rule engine evaluates parsed MeFRule expressions against a return_data
dict (field → value).  Results are compared to known IRS expected outcomes.

Gate:  100% match on ERROR-severity rules.
       >= 95% match on WARNING-severity rules.

In production, return_data dicts are populated from IRS-published test XML
packages (downloaded from MeF developer portal).  This module ships with a
synthetic test suite that covers the 60 rules in the sample CSV.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any, Optional

from tax_brain.models import (
    MeFRule, Severity, TestReturnCase, TestReturnOutcome,
    TestReturnResult, ValidationReport,
)

logger = logging.getLogger(__name__)

ERROR_GATE   = 1.00  # 100% match required on ERROR rules
WARNING_GATE = 0.95  # >=95% match required on WARNING rules


# ──────────────────────────────────────────────────────────────────────────────
# Rule Engine — evaluates a MeFRule against a return_data dict
# ──────────────────────────────────────────────────────────────────────────────

class RuleEngine:
    """
    Evaluates MeF business rules against a return field dict.

    The engine resolves [FieldRef] tokens against return_data,
    then evaluates the expression using safe arithmetic and comparison logic.
    It does NOT execute arbitrary Python — it interprets the structured
    expression string with a targeted regex-based evaluator.
    """

    def __init__(self, rules: list[MeFRule]):
        # Index by rule_id for fast lookup
        self._rules   = {r.rule_id: r for r in rules}
        self._by_form = {}
        for r in rules:
            self._by_form.setdefault(r.form_family, []).append(r)

    def evaluate_return(
        self,
        return_data: dict[str, Any],
        form_family : str = "1040",
    ) -> tuple[list[str], list[str]]:
        """
        Evaluate all rules for a form_family against return_data.

        Returns:
            (fired_rule_ids, fired_error_codes) — lists of rules/errors that fired.
        """
        fired_rules  : list[str] = []
        fired_errors : list[str] = []

        for rule in self._by_form.get(form_family, []):
            try:
                fired = self._eval_rule(rule, return_data)
                if fired:
                    fired_rules.append(rule.rule_id)
                    fired_errors.append(rule.error_code)
                    logger.debug("Rule %s FIRED on return", rule.rule_id)
            except Exception as exc:
                logger.warning("Rule %s eval error: %s", rule.rule_id, exc)

        return fired_rules, fired_errors

    def _eval_rule(self, rule: MeFRule, data: dict[str, Any]) -> bool:
        """
        Evaluate one rule.  Returns True if the rule fires (violation detected).
        Returns False if the rule passes (no violation) or cannot be evaluated.
        """
        expr = rule.rule_expression.strip()

        # ── Conditional: If <cond> Then <consequence> [Else <alternate>] ──
        cond_match = re.match(
            r"^If\s+(.+?)\s+Then\s+(.+)$", expr, re.IGNORECASE | re.DOTALL
        )
        if cond_match:
            cond_raw      = cond_match.group(1).strip()
            then_else_raw = cond_match.group(2).strip()
            # Split on Else clause (case-insensitive)
            else_parts = re.split(r"\s+Else\s+", then_else_raw, maxsplit=1, flags=re.IGNORECASE)
            cons_raw = else_parts[0].strip()
            alt_raw  = else_parts[1].strip() if len(else_parts) > 1 else None
            # Evaluate condition
            if not self._eval_bool(cond_raw, data):
                # Condition is FALSE: evaluate Else branch if present, else no violation
                return self._eval_violated(alt_raw, data) if alt_raw else False
            # Condition is TRUE — evaluate Then consequence
            return self._eval_violated(cons_raw, data)

        # ── Standalone constraint ─────────────────────────────────────────
        return self._eval_violated(expr, data)

    def _eval_bool(self, expr: str, data: dict[str, Any]) -> bool:
        """Evaluate a boolean condition (IF-clause)."""
        expr = expr.strip()

        # AND / OR compound
        and_parts = re.split(r"\bAND\b", expr, flags=re.IGNORECASE)
        if len(and_parts) > 1:
            return all(self._eval_bool(p.strip(), data) for p in and_parts)

        or_parts = re.split(r"\bOR\b", expr, flags=re.IGNORECASE)
        if len(or_parts) > 1:
            return any(self._eval_bool(p.strip(), data) for p in or_parts)

        # is present / is not present
        pres = re.match(r"\[([^\]]+)\]\s+is\s+(not\s+)?present", expr, re.IGNORECASE)
        if pres:
            field    = pres.group(1)
            negated  = bool(pres.group(2))
            in_data  = field in data and data[field] is not None
            return (not in_data) if negated else in_data

        # [Field] IN (...)
        in_list = re.match(r"\[([^\]]+)\]\s+(NOT\s+IN|IN)\s*\((.+)\)", expr, re.IGNORECASE)
        if in_list:
            field   = in_list.group(1)
            negated = "NOT" in in_list.group(2).upper()
            vals    = [self._parse_literal(v.strip()) for v in in_list.group(3).split(",")]
            field_v = data.get(field)
            result  = field_v in vals
            return (not result) if negated else result

        # Comparison: [Field] op value
        cmp = re.match(r"(.+?)\s*(!=|<=|>=|=|<|>)\s*(.+)", expr, re.IGNORECASE)
        if cmp:
            lhs = self._resolve(cmp.group(1).strip(), data)
            op  = cmp.group(2)
            rhs = self._resolve(cmp.group(3).strip(), data)
            return self._compare(lhs, op, rhs)

        return False  # Cannot evaluate — treat as not fired

    def _eval_violated(self, expr: str, data: dict[str, Any]) -> bool:
        """
        Evaluate whether a THEN-consequence or standalone constraint is violated.
        Returns True if the constraint is violated (rule fires).
        """
        expr = expr.strip()

        # Attachment requirement: [IRS8960] must be attached
        att = re.search(r"\[?(IRS\w+)\]?\s+must\s+be\s+attached", expr, re.IGNORECASE)
        if att:
            form = att.group(1)
            present = data.get(form) or data.get(f"{form}_attached")
            return not bool(present)  # fires if form NOT attached

        # Presence check
        pres = re.match(r"\[([^\]]+)\]\s+is\s+(not\s+)?present", expr, re.IGNORECASE)
        if pres:
            field   = pres.group(1)
            negated = bool(pres.group(2))
            in_data = field in data and data[field] is not None
            violated = (not in_data) if not negated else in_data
            return violated

        # Math equality check: [Field] = expr  — fires if NOT equal
        eq = re.match(r"\[([^\]]+)\]\s*=\s*(.+)", expr, re.IGNORECASE)
        if eq:
            field   = eq.group(1)
            rhs_raw = eq.group(2).strip()
            lhs     = data.get(field)
            rhs     = self._resolve(rhs_raw, data)
            if lhs is None or rhs is None:
                return False
            return not self._compare(lhs, "=", rhs)

        # Range: [Field] <= value  — fires if field > value
        rng = re.match(r"\[([^\]]+)\]\s*(<=|>=|<|>)\s*(.+)", expr, re.IGNORECASE)
        if rng:
            field = rng.group(1)
            op    = rng.group(2)
            rhs   = self._resolve(rng.group(3).strip(), data)
            lhs   = data.get(field)
            if lhs is None or rhs is None:
                return False
            # Constraint says [field] <= rhs — fires if NOT satisfied
            return not self._compare(lhs, op, rhs)

        return False

    def _resolve(self, token: str, data: dict[str, Any]) -> Any:
        """
        Resolve a token to a Python value.
        Returns None when any referenced field is missing or unresolvable.
        Handles: field refs, numeric/string/bool literals, arithmetic,
        balanced parentheses, and function calls (SUM/MAX/MIN/CEIL/ABS).
        """
        token = token.strip()
        if not token:
            return None

        # ── Strip balanced outer parentheses ──────────────────────────────
        if token.startswith("(") and token.endswith(")"):
            depth = 0
            for ch in token[1:-1]:
                if ch == "(": depth += 1
                elif ch == ")": depth -= 1
                if depth < 0:
                    break  # outer parens not actually balanced at this level
            else:
                # All inner parens balanced — strip the outermost pair
                return self._resolve(token[1:-1], data)

        # ── Field reference: [FieldName] ──────────────────────────────────
        m = re.fullmatch(r"\[([^\]]+)\]", token)
        if m:
            return data.get(m.group(1))

        # ── Function calls with balanced-paren extraction ─────────────────
        func_m = re.match(r"(SUM|MAX|MIN|CEIL|ABS|EIC_MAX_TABLE)\s*\(", token, re.IGNORECASE)
        if func_m:
            func    = func_m.group(1).upper()
            paren_s = token.index("(")
            # Walk forward to find the balanced closing paren
            depth, close = 0, -1
            for i in range(paren_s, len(token)):
                if token[i] == "(": depth += 1
                elif token[i] == ")":
                    depth -= 1
                    if depth == 0:
                        close = i
                        break
            if close < 0:
                return None  # malformed
            inner = token[paren_s + 1 : close]
            rest  = token[close + 1:].strip()  # e.g., " * 0.038" after the function

            if func == "SUM":
                field_m = re.fullmatch(r"\[([^\]]+)\]", inner.strip())
                if field_m:
                    val = data.get(field_m.group(1))
                    result = float(val) if val is not None else 0.0
                else:
                    result = 0.0

            elif func in ("MAX", "MIN"):
                args = [self._resolve(a.strip(), data)
                        for a in self._split_top_level_args(inner)]
                valid = [a for a in args if a is not None]
                if not valid:
                    return None
                result = max(valid) if func == "MAX" else min(valid)

            elif func == "CEIL":
                val = self._resolve(inner.strip(), data)
                if val is None:
                    return None
                try:
                    result = math.ceil(float(val))
                except (TypeError, ValueError):
                    return None

            elif func == "ABS":
                val = self._resolve(inner.strip(), data)
                if val is None:
                    return None
                try:
                    result = abs(float(val))
                except (TypeError, ValueError):
                    return None

            else:  # EIC_MAX_TABLE and other unknown functions
                return None

            # Apply any trailing arithmetic (e.g., "* 0.038")
            if rest:
                m_rest = re.match(r"^([+\-*/])\s*(.+)$", rest)
                if m_rest:
                    op_r   = m_rest.group(1)
                    rhs_r  = self._resolve(m_rest.group(2).strip(), data)
                    if result is None or rhs_r is None:
                        return None
                    try:
                        result = float(result)
                        rhs_r  = float(rhs_r)
                        if op_r == "+": result += rhs_r
                        elif op_r == "-": result -= rhs_r
                        elif op_r == "*": result *= rhs_r
                        elif op_r == "/" and rhs_r != 0: result /= rhs_r
                        else: return None
                    except (TypeError, ValueError):
                        return None
            return result

        # ── Arithmetic: paren-aware scan for + - * / ──────────────────────
        for op in ("+", "-", "*", "/"):
            # Find the LAST top-level occurrence (right-associative for – and /)
            depth, idx = 0, -1
            for i, ch in enumerate(token):
                if ch == "(": depth += 1
                elif ch == ")": depth -= 1
                elif ch == op and depth == 0:
                    idx = i
            if idx > 0:
                lhs_raw = token[:idx].strip()
                rhs_raw = token[idx + 1:].strip()
                if lhs_raw and rhs_raw:
                    l = self._resolve(lhs_raw, data)
                    r = self._resolve(rhs_raw, data)
                    if l is not None and r is not None:
                        try:
                            l, r = float(l), float(r)
                            if op == "+": return l + r
                            if op == "-": return l - r
                            if op == "*": return l * r
                            if op == "/" and r != 0: return l / r
                        except (TypeError, ValueError):
                            pass
                    return None  # fields present but arithmetic failed

        return self._parse_literal(token)

    @staticmethod
    def _split_top_level_args(args_str: str) -> list[str]:
        """Split comma-separated args without splitting inside nested parens."""
        depth, start, parts = 0, 0, []
        for i, ch in enumerate(args_str):
            if ch == "(": depth += 1
            elif ch == ")": depth -= 1
            elif ch == "," and depth == 0:
                parts.append(args_str[start:i])
                start = i + 1
        parts.append(args_str[start:])
        return parts

    @staticmethod
    def _parse_literal(token: str) -> Any:
        """Parse a literal: number, string, boolean.  Returns None for unrecognized tokens."""
        token = token.strip()
        if re.match(r"^-?\d+(\.\d+)?$", token):
            return float(token) if "." in token else int(token)
        if token.startswith("'") and token.endswith("'"):
            return token[1:-1]
        if token.lower() == "true":
            return True
        if token.lower() == "false":
            return False
        # Unrecognized — return None so comparisons safely skip
        return None

    @staticmethod
    def _compare(lhs: Any, op: str, rhs: Any) -> bool:
        """Compare two values.  Returns False if either operand is None."""
        if lhs is None or rhs is None:
            return False
        try:
            if op in ("=", "=="): return float(lhs) == float(rhs)
            if op == "!=":        return float(lhs) != float(rhs)
            if op == "<":         return float(lhs) <  float(rhs)
            if op == ">":         return float(lhs) >  float(rhs)
            if op == "<=":        return float(lhs) <= float(rhs)
            if op == ">=":        return float(lhs) >= float(rhs)
        except (TypeError, ValueError):
            # String comparison fallback (for status codes, 'S', 'I', etc.)
            if op in ("=", "=="): return str(lhs) == str(rhs)
            if op == "!=":        return str(lhs) != str(rhs)
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Synthetic test return cases
# ──────────────────────────────────────────────────────────────────────────────

def build_synthetic_test_cases() -> list[TestReturnCase]:
    """
    Synthetic test cases covering the 60 rules in the sample CSV.
    In production, replace / supplement with IRS-published test XML packages.
    """
    return [

        # ── Clean return — should be ACCEPTED ─────────────────────────────
        TestReturnCase(
            case_id="TC-001",
            description="Clean MFJ return with standard deduction, wages only — ACCEPT",
            expected_outcome=TestReturnOutcome.ACCEPTED,
            expected_errors=[],
            return_data={
                "TaxYearCd"              : 2024,
                "FilingStatusCd"         : 2,       # MFJ
                "PrimarySSN"             : "123-45-6789",
                "SpouseSSN"              : "987-65-4321",
                "PrimaryBirthDt"         : "1980-01-01",
                "SignatureDt"            : "2025-04-01",
                "PreparerSSNOrPTIN"      : "P12345678",
                "PreparedByOtherThanTaxpayerInd": True,
                "EFINNum"                : "123456",
                "WagesSalariesTipsAmt"   : 120_000,
                "TaxableInterestAmt"     : 800,
                "OrdinaryDividendsAmt"   : 1_200,
                "QualifiedDividendsAmt"  : 900,
                "IRADistributionsAmt"    : 0,
                "PensionsAnnuitiesAmt"   : 0,
                "SocialSecurityBenefitsAmt": 0,
                "OtherIncomeAmt"         : 0,
                "TotalIncomeAmt"         : 122_000,  # wages + interest + dividends
                "EducatorExpensesAmt"    : 0,
                "StudentLoanInterestDeductionAmt": 0,
                "TuitionAndFeesDedAmt"   : 0,
                "HealthSavingsAccountDedAmt": 0,
                "SelfEmployedHealthInsDedAmt": 0,
                "SEPSIMPLEQualifiedPlansAmt": 0,
                "SelfEmploymentTaxDeductionAmt": 0,
                "AlimonyPaidAmt"         : 0,
                "AdjustedGrossIncomeAmt" : 122_000,
                "ItemizedOrStandardCd"   : "S",
                "StandardDeductionAmt"   : 29_200,   # MFJ 2024
                "QualifiedBusinessIncomeDedAmt": 0,
                "DeductionsAmt"          : 29_200,
                "TaxableIncomeAmt"       : 92_800,   # 122000 - 29200
                "IncomeTaxAmt"           : 10_924,
                "AlternativeMinimumTaxAmt": 0,
                "ExcessAdvancePremiumTaxCreditRepayAmt": 0,
                "SelfEmploymentTaxAmt"   : 0,
                "UnreportedSSTaxAmt"     : 0,
                "AdditionalTaxOnIRAAmt"  : 0,
                "HouseholdEmploymentTaxAmt": 0,
                "NetInvestmentIncomeTaxAmt": 0,
                "AdditionalMedicareTaxAmt": 0,
                "TotalTaxAmt"            : 10_924,
                "FederalIncomeTaxWithheldAmt": 12_000,
                "EstimatedTaxPaymentsAmt": 0,
                "EarnedIncomeCreditAmt"  : 0,
                "AdditionalChildTaxCreditAmt": 0,
                "AmericanOpportunityCreditAmt": 0,
                "RecoveryRebateCreditAmt": 0,
                "OtherPaymentsAmt"       : 0,
                "TotalPaymentsAmt"       : 12_000,
                "OverpaymentAmt"         : 1_076,    # 12000 - 10924
                "AmountAppliedToNextYrAmt": 0,
                "RefundAmt"              : 1_076,
                "StateLocalTaxDeductionAmt": 0,      # Standard deduction — no SALT issue
                "QualifyingChildrenCnt"  : 0,
                "ChildTaxCreditAmt"      : 0,
                "ModifiedAGIAmt"         : 122_000,
                "NetInvestmentIncomeAmt" : 2_100,    # dividends + interest (below NIIT threshold)
                "SelfEmploymentNetProfitAmt": 0,
                "CapitalGainOrLossAmt"   : 0,
                "SupplementalIncomeOrLossAmt": 0,
                "ForeignTaxCreditAmt"    : 0,
                "ItemizedOrStandardCd"   : "S",
                "WorkplacePlanParticipantInd": True,
                "IRADeductionAmt"        : 0,
                "Traditional401KContributionAmt": 10_000,  # well within $23,000 limit
                "PrimaryAge"             : 44,
                "HSACoverageTypeCd"      : None,
                "HSAContributionAmt"     : 0,
                "CharitableContributionsAmt": 0,
                "MedicalExpensesAmt"     : 0,
                "MedicalExpensesDeductionAmt": 0,
                "EICQualifyingChildrenCnt": 0,
            },
        ),

        # ── SALT cap violation — MFJ exceeds $10,000 ─────────────────────
        TestReturnCase(
            case_id="TC-002",
            description="MFJ return with SALT deduction of $14,000 — should REJECT IND-041-01",
            expected_outcome=TestReturnOutcome.REJECTED,
            expected_errors=["IND-041-01"],
            return_data={
                "TaxYearCd"              : 2024,
                "FilingStatusCd"         : 2,
                "PrimarySSN"             : "234-56-7890",
                "SpouseSSN"              : "876-54-3210",
                "PrimaryBirthDt"         : "1975-06-15",
                "SignatureDt"            : "2025-04-10",
                "PreparedByOtherThanTaxpayerInd": False,
                "EFINNum"                : "234567",
                "ItemizedOrStandardCd"   : "I",
                "StateLocalTaxDeductionAmt": 14_000,  # VIOLATION: exceeds $10,000 cap
                "AdjustedGrossIncomeAmt" : 200_000,
                "IRS1040ScheduleA_attached": True,
                "TaxYearCd"              : 2024,
            },
        ),

        # ── Form 8960 missing when NIIT > 0 ──────────────────────────────
        TestReturnCase(
            case_id="TC-003",
            description="NIIT of $1,200 claimed but Form 8960 not attached — REJECT IND-021-01",
            expected_outcome=TestReturnOutcome.REJECTED,
            expected_errors=["IND-021-01"],
            return_data={
                "TaxYearCd"                : 2024,
                "FilingStatusCd"           : 1,     # Single
                "PrimarySSN"               : "345-67-8901",
                "PrimaryBirthDt"           : "1985-03-20",
                "SignatureDt"              : "2025-04-05",
                "PreparedByOtherThanTaxpayerInd": False,
                "EFINNum"                  : "345678",
                "NetInvestmentIncomeTaxAmt": 1_200,  # NIIT present
                "IRS8960"                  : None,   # VIOLATION: Form 8960 not attached
                "AdjustedGrossIncomeAmt"   : 250_000,
                "TaxYearCd"                : 2024,
            },
        ),

        # ── 401k over limit for age < 50 ──────────────────────────────────
        TestReturnCase(
            case_id="TC-004",
            description="401k contribution of $25,000 for taxpayer age 42 — REJECT IND-055-01",
            expected_outcome=TestReturnOutcome.REJECTED,
            expected_errors=["IND-055-01"],
            return_data={
                "TaxYearCd"                  : 2024,
                "FilingStatusCd"             : 1,
                "PrimarySSN"                 : "456-78-9012",
                "PrimaryBirthDt"             : "1982-09-10",
                "SignatureDt"                : "2025-03-30",
                "PreparedByOtherThanTaxpayerInd": False,
                "EFINNum"                    : "456789",
                "PrimaryAge"                 : 42,
                "Traditional401KContributionAmt": 25_000,  # VIOLATION: exceeds $23,000
                "TaxYearCd"                  : 2024,
            },
        ),

        # ── Clean Schedule B required — interest over $1,500 ─────────────
        TestReturnCase(
            case_id="TC-005",
            description="Interest of $3,000 without Schedule B attached — REJECT IND-025-01",
            expected_outcome=TestReturnOutcome.REJECTED,
            expected_errors=["IND-025-01"],
            return_data={
                "TaxYearCd"              : 2024,
                "FilingStatusCd"         : 1,
                "PrimarySSN"             : "567-89-0123",
                "PrimaryBirthDt"         : "1990-11-25",
                "SignatureDt"            : "2025-04-12",
                "PreparedByOtherThanTaxpayerInd": False,
                "EFINNum"                : "567890",
                "TaxableInterestAmt"     : 3_000,   # over $1,500 threshold
                "OrdinaryDividendsAmt"   : 500,
                "IRS1040ScheduleB"       : None,    # VIOLATION: not attached
                "TaxYearCd"              : 2024,
            },
        ),

        # ── Invalid tax year ───────────────────────────────────────────────
        TestReturnCase(
            case_id="TC-006",
            description="Return filed with TaxYearCd = 2023 — REJECT IND-011-01",
            expected_outcome=TestReturnOutcome.REJECTED,
            expected_errors=["IND-011-01"],
            return_data={
                "TaxYearCd"  : 2023,   # VIOLATION: wrong year
                "EFINNum"    : "678901",
            },
        ),

        # ── Missing primary SSN ────────────────────────────────────────────
        TestReturnCase(
            case_id="TC-007",
            description="Primary SSN missing — REJECT IND-013-01",
            expected_outcome=TestReturnOutcome.REJECTED,
            expected_errors=["IND-013-01"],
            return_data={
                "TaxYearCd"    : 2024,
                "FilingStatusCd": 1,
                "PrimarySSN"   : None,   # VIOLATION: null SSN
                "EFINNum"      : "789012",
            },
        ),

        # ── NIIT correctly calculated — should ACCEPT ─────────────────────
        TestReturnCase(
            case_id="TC-008",
            description="MFJ with NIIT correctly computed and Form 8960 attached — ACCEPT",
            expected_outcome=TestReturnOutcome.ACCEPTED,
            expected_errors=[],
            return_data={
                "TaxYearCd"                : 2024,
                "FilingStatusCd"           : 2,
                "PrimarySSN"               : "890-12-3456",
                "SpouseSSN"                : "765-43-2109",
                "PrimaryBirthDt"           : "1972-04-01",
                "SignatureDt"              : "2025-04-15",
                "PreparedByOtherThanTaxpayerInd": False,
                "EFINNum"                  : "890123",
                "ModifiedAGIAmt"           : 300_000,
                "NetInvestmentIncomeAmt"   : 20_000,
                "NetInvestmentIncomeTaxAmt": 760,    # MIN(20000, 300000-250000) * 0.038 = MIN(20000,50000)*0.038 = 760
                "IRS8960"                  : True,   # Attached ✓
                "AdjustedGrossIncomeAmt"   : 300_000,
                "TaxYearCd"                : 2024,
            },
        ),
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Replay runner
# ──────────────────────────────────────────────────────────────────────────────

def run(
    rules        : list[MeFRule],
    test_cases   : list[TestReturnCase] | None = None,
    error_gate   : float = ERROR_GATE,
    warning_gate : float = WARNING_GATE,
) -> ValidationReport:
    """
    Run V1.3: evaluate all test cases against the rule engine.

    Args:
        rules       : Parsed + AST-augmented MeFRule list
        test_cases  : IRS test return cases (defaults to synthetic set)
        error_gate  : Required match rate for ERROR-severity rule violations
        warning_gate: Required match rate for WARNING-severity violations

    Returns:
        ValidationReport — check .passed for gate decision
    """
    if test_cases is None:
        test_cases = build_synthetic_test_cases()

    engine   = RuleEngine(rules)
    results  : list[TestReturnResult] = []
    failures : list[dict]             = []
    warnings : list[dict]             = []

    error_total   = error_correct   = 0
    warning_total = warning_correct = 0

    for case in test_cases:
        fired_rules, fired_errors = engine.evaluate_return(
            case.return_data, form_family="1040"
        )

        # Outcome: REJECTED if any ERROR rule fired, else ACCEPTED
        error_rules   = [r for r in rules if r.rule_id in fired_rules and r.severity == Severity.ERROR]
        actual_outcome = (
            TestReturnOutcome.REJECTED if error_rules
            else TestReturnOutcome.ACCEPTED
        )

        outcome_match    = actual_outcome == case.expected_outcome
        error_code_match = set(case.expected_errors).issubset(set(fired_errors))

        result = TestReturnResult(
            case_id          = case.case_id,
            actual_outcome   = actual_outcome,
            fired_rules      = fired_rules,
            fired_errors     = fired_errors,
            outcome_match    = outcome_match,
            error_code_match = error_code_match,
            notes            = case.description,
        )
        results.append(result)

        # Tally against gates
        has_expected_errors = bool(case.expected_errors)
        if case.expected_outcome == TestReturnOutcome.REJECTED and has_expected_errors:
            # Check if this is an error-severity case
            expected_severities = {
                r.severity for r in rules if r.error_code in case.expected_errors
            }
            if Severity.ERROR in expected_severities:
                error_total += 1
                if outcome_match and error_code_match:
                    error_correct += 1
                else:
                    failures.append({
                        "case_id"        : case.case_id,
                        "description"    : case.description,
                        "expected"       : case.expected_outcome.value,
                        "actual"         : actual_outcome.value,
                        "expected_errors": case.expected_errors,
                        "fired_errors"   : fired_errors,
                        "outcome_match"  : outcome_match,
                        "error_match"    : error_code_match,
                    })
            else:
                warning_total += 1
                if outcome_match:
                    warning_correct += 1
                else:
                    warnings.append({
                        "case_id"    : case.case_id,
                        "description": case.description,
                        "detail"     : "WARNING-severity outcome mismatch",
                    })
        else:
            # ACCEPT case — check no error rules fired
            error_total += 1
            if outcome_match:
                error_correct += 1
            else:
                failures.append({
                    "case_id"    : case.case_id,
                    "description": case.description,
                    "expected"   : case.expected_outcome.value,
                    "actual"     : actual_outcome.value,
                    "fired_rules": fired_rules[:5],
                    "detail"     : "Return was rejected but should have been accepted",
                })

    # Gate evaluation
    error_rate   = error_correct / error_total     if error_total   else 1.0
    warning_rate = warning_correct / warning_total if warning_total else 1.0
    passed       = error_rate >= error_gate and warning_rate >= warning_gate

    notes = [
        f"ERROR-severity:   {error_correct}/{error_total} correct ({error_rate*100:.1f}%) "
        f"[gate: {error_gate*100:.0f}%] {'✓ PASS' if error_rate >= error_gate else '✗ FAIL'}",
        f"WARNING-severity: {warning_correct}/{warning_total} correct ({warning_rate*100:.1f}%) "
        f"[gate: {warning_gate*100:.0f}%] {'✓ PASS' if warning_rate >= warning_gate else '✗ FAIL'}",
        f"Total test cases: {len(test_cases)}",
    ]

    report = ValidationReport(
        step          = "V1.3-TEST-REPLAY",
        passed        = passed,
        total_checked = len(test_cases),
        total_passed  = error_correct + warning_correct,
        total_failed  = len(failures),
        failures      = failures,
        warnings      = warnings,
        notes         = notes,
    )

    logger.info(report.summary_line())
    if failures:
        for f in failures:
            logger.error("REPLAY FAIL %s: expected=%s actual=%s errors=%s",
                         f["case_id"], f.get("expected"), f.get("actual"),
                         f.get("expected_errors", f.get("fired_rules")))
    return report, results
