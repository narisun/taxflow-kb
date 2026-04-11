"""
taxflow_kb/models.py
Pydantic models for all MeF business rule entities.
"""
from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────────────────────────────────────

class RuleType(str, Enum):
    MATH       = "MATH"       # Arithmetic consistency check (field = sum of parts)
    REJECT     = "REJECT"     # Hard reject — return cannot be accepted
    ALERT      = "ALERT"      # Soft alert / warning
    DATABASE   = "DATABASE"   # Lookup against IRS threshold/limits database


class Severity(str, Enum):
    ERROR   = "ERROR"    # Return rejected
    WARNING = "WARNING"  # Informational; return accepted with flag
    INFO    = "INFO"     # Audit trail only


class FilingStatus(int, Enum):
    SINGLE = 1
    MFJ    = 2   # Married Filing Jointly
    MFS    = 3   # Married Filing Separately
    HOH    = 4   # Head of Household
    QSS    = 5   # Qualifying Surviving Spouse


class ChangeType(str, Enum):
    ADDED    = "ADDED"
    MODIFIED = "MODIFIED"
    REMOVED  = "REMOVED"
    UNCHANGED = "UNCHANGED"


# ──────────────────────────────────────────────────────────────────────────────
# AST Node types
# ──────────────────────────────────────────────────────────────────────────────

class ASTNodeType(str, Enum):
    BINARY_OP       = "BINARY_OP"       # left op right  (=, !=, <, >, <=, >=, +, -, *, /)
    LOGICAL_OP      = "LOGICAL_OP"      # left AND/OR right
    UNARY_OP        = "UNARY_OP"        # NOT operand
    FIELD_REF       = "FIELD_REF"       # [FieldName]
    LITERAL_NUMBER  = "LITERAL_NUMBER"  # 10000, 0.038, etc.
    LITERAL_STRING  = "LITERAL_STRING"  # 'MFJ', 'S', etc.
    LITERAL_BOOL    = "LITERAL_BOOL"    # true / false
    CONDITIONAL     = "CONDITIONAL"     # IF condition THEN consequence
    ATTACHMENT_REQ  = "ATTACHMENT_REQ"  # [FormXXX] must be attached
    PRESENCE_CHECK  = "PRESENCE_CHECK"  # [Field] is present / not present
    DB_LOOKUP       = "DB_LOOKUP"       # Field NOT IN IRS_DATABASE / matches pattern
    FUNCTION_CALL   = "FUNCTION_CALL"   # SUM([...]), MAX(...), MIN(...), CEIL(...)
    RANGE_CONSTRAINT= "RANGE_CONSTRAINT"# must not exceed / must be at least
    PARSE_ERROR     = "PARSE_ERROR"     # Could not parse — raw expression preserved


class ASTNode(BaseModel):
    """Recursive AST node. Serialises cleanly to JSONB for PostgreSQL storage."""
    node_type : ASTNodeType
    op        : Optional[str]       = None   # operator string
    left      : Optional[Any]       = None   # child node (dict or ASTNode)
    right     : Optional[Any]       = None
    operand   : Optional[Any]       = None   # for unary ops
    condition : Optional[Any]       = None   # for CONDITIONAL
    consequence: Optional[Any]      = None
    alternate  : Optional[Any]      = None   # for CONDITIONAL Else branch
    field_path : Optional[str]      = None   # for FIELD_REF
    value     : Optional[Any]       = None   # for LITERAL_*
    func_name : Optional[str]       = None   # for FUNCTION_CALL
    args      : Optional[list[Any]] = None
    form_name : Optional[str]       = None   # for ATTACHMENT_REQ
    raw       : Optional[str]       = None   # for PARSE_ERROR

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)


# ──────────────────────────────────────────────────────────────────────────────
# Core domain models
# ──────────────────────────────────────────────────────────────────────────────

class MeFRule(BaseModel):
    """
    One row from the IRS MeF business rules CSV.
    After parsing, expression_ast is populated by the AST parser.
    """
    rule_id         : str
    rule_type       : RuleType
    form_family     : str
    field_path      : str
    rule_text       : str
    rule_expression : str
    error_code      : str
    severity        : Severity
    tax_year        : int
    schema_version  : str

    # Populated post-parse
    expression_ast  : Optional[dict] = None
    parse_success   : bool = False
    parse_error_msg : Optional[str] = None

    @field_validator("rule_id")
    @classmethod
    def rule_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("rule_id cannot be empty")
        return v.strip()

    @field_validator("field_path")
    @classmethod
    def field_path_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("field_path cannot be empty")
        return v.strip()

    @property
    def short_field(self) -> str:
        """Last segment of the XPath field_path, e.g. TotalIncomeAmt."""
        return self.field_path.split("/")[-1]

    @property
    def unique_key(self) -> str:
        return f"{self.rule_id}::{self.tax_year}::{self.schema_version}"


class RuleVersionDiff(BaseModel):
    """Represents a change between two schema versions for the same rule_id."""
    rule_id         : str
    tax_year        : int
    old_version     : str
    new_version     : str
    change_type     : ChangeType
    changed_fields  : list[str] = Field(default_factory=list)
    old_expression  : Optional[str] = None
    new_expression  : Optional[str] = None


class ParseResult(BaseModel):
    """Summary result from a CSV parse run."""
    schema_version  : str
    tax_year        : int
    total_rows      : int
    parse_success   : int
    parse_failed    : int
    null_field_rows : int
    duplicate_ids   : list[str] = Field(default_factory=list)
    failed_rules    : list[dict] = Field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.parse_success / self.total_rows if self.total_rows else 0.0


class ValidationReport(BaseModel):
    """Aggregate report produced by a validation step."""
    step            : str
    passed          : bool
    total_checked   : int
    total_passed    : int
    total_failed    : int
    failures        : list[dict] = Field(default_factory=list)
    warnings        : list[dict] = Field(default_factory=list)
    notes           : list[str]  = Field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.total_passed / self.total_checked if self.total_checked else 0.0

    def summary_line(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] {self.step}: "
            f"{self.total_passed}/{self.total_checked} "
            f"({self.pass_rate*100:.1f}%)"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Test-return models (for V1.3)
# ──────────────────────────────────────────────────────────────────────────────

class TestReturnOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class TestReturnCase(BaseModel):
    """
    One IRS-published test return scenario.
    In production, XML is loaded from the IRS MeF developer portal.
    For tests we use synthetic data dicts.
    """
    case_id          : str
    description      : str
    expected_outcome : TestReturnOutcome
    expected_errors  : list[str] = Field(default_factory=list)  # error_codes on REJECT
    return_data      : dict      = Field(default_factory=dict)   # field → value map


class TestReturnResult(BaseModel):
    """Result of running the rule engine against one test return."""
    case_id          : str
    actual_outcome   : TestReturnOutcome
    fired_rules      : list[str] = Field(default_factory=list)   # rule_ids that fired
    fired_errors     : list[str] = Field(default_factory=list)   # error_codes
    outcome_match    : bool = False
    error_code_match : bool = False
    notes            : str = ""
