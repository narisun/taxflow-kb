"""
tests/test_layer1.py

End-to-end tests for the Layer 1 pipeline:
  - CSV parsing
  - AST expression parsing
  - V1.1 structural integrity
  - V1.3 test return replay

Run with:  pytest tests/ -v
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pathlib import Path

from taxkb.models import (
    MeFRule, RuleType, Severity, ASTNodeType,
    TestReturnOutcome,
)
from taxkb.rules.csv_parser import CSVParser
from taxkb.rules.ast_parser import parse_expression
from taxkb.rules.validation import structural as v1_structural, test_replay as v1_test_replay
from taxkb.rules.validation.structural import StructuralCheckConfig
from taxkb.rules.validation.test_replay import (
    RuleEngine, build_synthetic_test_cases,
)

SAMPLE_CSV = Path(__file__).parent.parent.parent / "data/sample/mef_1040_2024_v5_2.csv"


# ──────────────────────────────────────────────────────────────────────────────
# CSV Parser tests
# ──────────────────────────────────────────────────────────────────────────────

class TestCSVParser:
    def test_parse_sample_csv_succeeds(self):
        parser = CSVParser(SAMPLE_CSV)
        rules, result = parser.parse()
        assert len(rules) > 0, "Should parse at least one rule"
        assert result.parse_failed == 0, "No rows should fail to parse"

    def test_all_rules_have_required_fields(self):
        rules, _ = CSVParser(SAMPLE_CSV).parse()
        for rule in rules:
            assert rule.rule_id,   f"rule_id empty for {rule}"
            assert rule.error_code,f"error_code empty for {rule.rule_id}"
            assert rule.field_path,f"field_path empty for {rule.rule_id}"
            assert rule.severity in Severity, f"Invalid severity: {rule.severity}"

    def test_no_duplicate_rule_ids(self):
        rules, result = CSVParser(SAMPLE_CSV).parse()
        assert result.duplicate_ids == [], \
            f"Duplicate rule IDs found: {result.duplicate_ids}"

    def test_rule_types_are_valid(self):
        rules, _ = CSVParser(SAMPLE_CSV).parse()
        valid_types = set(RuleType)
        for rule in rules:
            assert rule.rule_type in valid_types, \
                f"Invalid rule_type '{rule.rule_type}' in {rule.rule_id}"

    def test_tax_year_is_2024(self):
        rules, _ = CSVParser(SAMPLE_CSV).parse()
        for rule in rules:
            assert rule.tax_year == 2024, \
                f"Expected tax_year 2024 for {rule.rule_id}, got {rule.tax_year}"

    def test_short_field_extraction(self):
        rules, _ = CSVParser(SAMPLE_CSV).parse()
        for rule in rules:
            assert "/" not in rule.short_field, \
                f"short_field should not contain '/': {rule.short_field}"


# ──────────────────────────────────────────────────────────────────────────────
# AST Parser tests
# ──────────────────────────────────────────────────────────────────────────────

class TestASTParser:
    def test_simple_equality(self):
        expr = "[TotalIncomeAmt] = [WagesAmt] + [InterestAmt]"
        node = parse_expression(expr)
        assert node.node_type == ASTNodeType.BINARY_OP
        assert node.op == "="

    def test_conditional_expression(self):
        expr = "If [FilingStatusCd] = 2 Then [SpouseSSN] is present"
        node = parse_expression(expr)
        assert node.node_type == ASTNodeType.CONDITIONAL
        assert node.condition is not None
        assert node.consequence is not None

    def test_attachment_requirement(self):
        expr = "If [NetInvestmentIncomeTaxAmt] > 0 Then [IRS8960] must be attached"
        node = parse_expression(expr)
        assert node.node_type == ASTNodeType.CONDITIONAL
        consequence = node.consequence
        assert consequence["node_type"] == ASTNodeType.ATTACHMENT_REQ.value

    def test_in_list_condition(self):
        expr = "If [FilingStatusCd] IN (1, 2, 4, 5) Then [StateLocalTaxDeductionAmt] <= 10000"
        node = parse_expression(expr)
        assert node.node_type == ASTNodeType.CONDITIONAL

    def test_compound_and_condition(self):
        expr = (
            "If [WorkplacePlanParticipantInd] = true AND [FilingStatusCd] = 1 "
            "AND [AdjustedGrossIncomeAmt] > 77000 Then [IRADeductionAmt] <= 7000"
        )
        node = parse_expression(expr)
        assert node.node_type == ASTNodeType.CONDITIONAL

    def test_field_ref_extraction(self):
        expr = "[TotalIncomeAmt] = [WagesAmt]"
        node = parse_expression(expr)
        assert node.left["field_path"] == "TotalIncomeAmt"
        assert node.right["field_path"] == "WagesAmt"

    def test_all_sample_csv_rules_parse(self):
        """All 60 sample rules should parse without PARSE_ERROR."""
        rules, _ = CSVParser(SAMPLE_CSV).parse()
        parse_errors = []
        for rule in rules:
            ast = parse_expression(rule.rule_expression)
            if ast.node_type == ASTNodeType.PARSE_ERROR:
                parse_errors.append({"rule_id": rule.rule_id, "reason": ast.value})

        rate = 1 - len(parse_errors) / len(rules)
        assert rate >= 0.98, (
            f"AST parse success rate {rate*100:.1f}% below 98% threshold. "
            f"Errors: {parse_errors[:3]}"
        )

    def test_no_parse_error_is_returned_as_none(self):
        """A successfully parsed expression should set expression_ast, not leave it None."""
        expr = "[StateLocalTaxDeductionAmt] <= 10000"
        node = parse_expression(expr)
        assert node.node_type != ASTNodeType.PARSE_ERROR
        assert node.to_dict() is not None


# ──────────────────────────────────────────────────────────────────────────────
# V1.1 Structural Integrity tests
# ──────────────────────────────────────────────────────────────────────────────

class TestV11Structural:
    @pytest.fixture
    def parsed(self):
        rules, result = CSVParser(SAMPLE_CSV).parse()
        for rule in rules:
            ast = parse_expression(rule.rule_expression)
            rule.expression_ast = ast.to_dict() if ast.node_type != ASTNodeType.PARSE_ERROR else None
            rule.parse_success  = ast.node_type != ASTNodeType.PARSE_ERROR
        return rules, result

    def test_v11_passes_on_clean_csv(self, parsed):
        rules, result = parsed
        report = v1_structural.run(rules, result)
        assert report.passed, f"V1.1 failed: {report.failures}"

    def test_v11_fails_on_row_count_mismatch(self, parsed):
        rules, result = parsed
        cfg = StructuralCheckConfig(expected_row_count=999)
        report = v1_structural.run(rules, result, cfg)
        checks = {f["check"] for f in report.failures}
        assert "ROW_COUNT" in checks

    def test_v11_pass_rate_is_calculated(self, parsed):
        rules, result = parsed
        report = v1_structural.run(rules, result)
        assert 0.0 <= report.pass_rate <= 1.0

    def test_v11_notes_populated(self, parsed):
        rules, result = parsed
        report = v1_structural.run(rules, result)
        assert len(report.notes) > 0


# ──────────────────────────────────────────────────────────────────────────────
# V1.3 Test Return Replay tests
# ──────────────────────────────────────────────────────────────────────────────

class TestV13Replay:
    @pytest.fixture
    def rules(self):
        r, _ = CSVParser(SAMPLE_CSV).parse()
        for rule in r:
            ast = parse_expression(rule.rule_expression)
            rule.expression_ast = ast.to_dict()
            rule.parse_success  = ast.node_type != ASTNodeType.PARSE_ERROR
        return r

    def test_clean_return_accepted(self, rules):
        """TC-001: clean MFJ return should be ACCEPTED."""
        engine = RuleEngine(rules)
        cases  = [c for c in build_synthetic_test_cases() if c.case_id == "TC-001"]
        assert cases, "TC-001 not found in test cases"
        fired, errors = engine.evaluate_return(cases[0].return_data)
        # No ERROR rules should fire on a clean return
        error_rules = [r for r in rules if r.rule_id in fired and r.severity == Severity.ERROR]
        assert not error_rules, f"ERROR rules fired on clean return: {[r.rule_id for r in error_rules]}"

    def test_salt_cap_violation_detected(self, rules):
        """TC-002: SALT of $14,000 on MFJ should fire IND-041-01."""
        engine = RuleEngine(rules)
        return_data = {
            "FilingStatusCd"           : 2,
            "StateLocalTaxDeductionAmt": 14_000,
        }
        fired, errors = engine.evaluate_return(return_data)
        assert "IND-041-01" in errors, \
            f"Expected IND-041-01 to fire, got: {errors}"

    def test_401k_limit_violation_detected(self, rules):
        """TC-004: 401k of $25,000 for age 42 should fire IND-055-01."""
        engine = RuleEngine(rules)
        return_data = {
            "PrimaryAge"                    : 42,
            "Traditional401KContributionAmt": 25_000,
        }
        fired, errors = engine.evaluate_return(return_data)
        assert "IND-055-01" in errors, \
            f"Expected IND-055-01 to fire, got: {errors}"

    def test_wrong_tax_year_rejected(self, rules):
        """TC-006: TaxYearCd = 2023 should fire IND-011-01."""
        engine = RuleEngine(rules)
        return_data = {"TaxYearCd": 2023}
        fired, errors = engine.evaluate_return(return_data)
        assert "IND-011-01" in errors, \
            f"Expected IND-011-01 to fire, got: {errors}"

    def test_full_replay_suite_passes_gate(self, rules):
        """Full V1.3 replay should pass both ERROR and WARNING gates."""
        report, _ = v1_test_replay.run(rules)
        assert report.passed, (
            f"V1.3 FAILED.\n"
            f"Notes: {report.notes}\n"
            f"Failures: {report.failures}"
        )

    def test_8960_attachment_detected(self, rules):
        """TC-003: NIIT > 0 without Form 8960 attached should fire IND-021-01."""
        engine = RuleEngine(rules)
        return_data = {
            "NetInvestmentIncomeTaxAmt": 1_200,
            "IRS8960"                  : None,
        }
        fired, errors = engine.evaluate_return(return_data)
        assert "IND-021-01" in errors, \
            f"Expected IND-021-01 for missing 8960, got: {errors}"
