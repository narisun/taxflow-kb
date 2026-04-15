"""Concrete validation rules V001–V008."""
from decimal import Decimal
from api.tax_engine.validation.base import ValidationResult, ValidationRule
from api.tax_engine.models.tax_return import TaxReturn

class SCorporateW2Rule(ValidationRule):
    rule_id = "V001"
    severity = "WARNING"
    description = "S-Corp K-1 should have matching W-2"
    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        results = []
        w2_eins = {w.employer_ein for w in tax_return.w2s}
        for k1 in tax_return.k1s:
            if k1.entity_type == "S" and k1.entity_ein not in w2_eins:
                results.append(ValidationResult(rule_id=self.rule_id, severity=self.severity,
                    message=f"S-Corp '{k1.entity_name}' (EIN {k1.entity_ein}) has no matching W-2",
                    affected_fields=["k1s", "w2s"],
                    suggestion="S-Corp shareholders who work for the corp must receive a W-2"))
        return results

class SSNFormatRule(ValidationRule):
    rule_id = "V002"
    severity = "ERROR"
    description = "SSN format validation"
    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        return []  # SSN validation handled by Pydantic validators

class MFJSpouseRequiredRule(ValidationRule):
    rule_id = "V003"
    severity = "ERROR"
    description = "MFJ requires spouse information"
    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        if tax_return.filing_status == "MFJ" and tax_return.spouse is None:
            return [ValidationResult(rule_id=self.rule_id, severity=self.severity,
                message="Filing status is MFJ but no spouse information provided",
                affected_fields=["filing_status", "spouse"],
                suggestion="Add spouse information or change filing status")]
        return []

class HSAContributionMatchRule(ValidationRule):
    rule_id = "V004"
    severity = "WARNING"
    description = "HSA employer contribution should match W-2 box 12 code W"
    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        results = []
        w2_hsa = sum((w.box12_codes.get("W", Decimal("0")) for w in tax_return.w2s), Decimal("0"))
        hsa_employer = sum((h.employer_contributions for h in tax_return.hsas), Decimal("0"))
        if hsa_employer > Decimal("0") and w2_hsa == Decimal("0"):
            results.append(ValidationResult(rule_id=self.rule_id, severity=self.severity,
                message="HSA employer contributions reported but no W-2 box 12 code W found",
                affected_fields=["hsas", "w2s.box12_codes"],
                suggestion="Verify employer HSA contributions match W-2 reporting"))
        return results

class WithholdingExceedsIncomeRule(ValidationRule):
    rule_id = "V006"
    severity = "WARNING"
    description = "Withholding exceeds total income"
    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        total_income = sum((w.box1_wages for w in tax_return.w2s), Decimal("0"))
        total_withheld = sum((w.box2_fed_withheld for w in tax_return.w2s), Decimal("0"))
        if total_income > Decimal("0") and total_withheld > total_income:
            return [ValidationResult(rule_id=self.rule_id, severity=self.severity,
                message="Federal withholding exceeds total W-2 wages",
                affected_fields=["w2s.box1_wages", "w2s.box2_fed_withheld"],
                suggestion="Verify W-2 amounts are correct")]
        return []

class DuplicateSSNRule(ValidationRule):
    rule_id = "V007"
    severity = "ERROR"
    description = "Duplicate SSN among dependents"
    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        ssns = [d.ssn for d in tax_return.dependents]
        seen, dupes = set(), set()
        for ssn in ssns:
            if ssn in seen:
                dupes.add(ssn)
            seen.add(ssn)
        if dupes:
            return [ValidationResult(rule_id=self.rule_id, severity=self.severity,
                message=f"Duplicate SSN(s) found among dependents: {', '.join(dupes)}",
                affected_fields=["dependents.ssn"])]
        return []

class HOHRequiresDependentRule(ValidationRule):
    rule_id = "V008"
    severity = "ERROR"
    description = "HOH requires qualifying dependent"
    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        if tax_return.filing_status == "HOH" and not tax_return.dependents:
            return [ValidationResult(rule_id=self.rule_id, severity=self.severity,
                message="Head of Household filing status requires at least one dependent",
                affected_fields=["filing_status", "dependents"],
                suggestion="Add qualifying dependent or change filing status")]
        return []

def default_rules() -> list[ValidationRule]:
    return [SCorporateW2Rule(), SSNFormatRule(), MFJSpouseRequiredRule(),
            HSAContributionMatchRule(), WithholdingExceedsIncomeRule(),
            DuplicateSSNRule(), HOHRequiresDependentRule()]
