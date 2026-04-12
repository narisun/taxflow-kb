"""
tax_brain/ingestion/ast_parser.py

Parses IRS MeF rule expression strings into an AST (ASTNode tree).

IRS rule expressions use a semi-structured pseudo-code syntax.  Six
surface patterns are recognised:

  1. CONDITIONAL  – If <cond> Then <consequence>
  2. MATH         – [Field] = expr  /  [Field] op expr
  3. ATTACHMENT   – [IRS{Form}] must be attached
  4. PRESENCE     – [Field] is present  /  is not present
  5. DB_LOOKUP    – [Field] NOT IN DATABASE  /  matches pattern 'regex'
  6. FUNCTION     – SUM([...])  MAX(...)  MIN(...)  CEIL(...)  ABS(...)

Field references use bracket notation: [FieldName]
Numeric literals are bare numbers or decimals.
String literals are single-quoted: 'MFJ'
Boolean literals: true / false (case-insensitive)
"""
from __future__ import annotations

import re
import logging
from typing import Optional

from tax_brain.models import ASTNode, ASTNodeType

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Token regexes
# ──────────────────────────────────────────────────────────────────────────────
RE_FIELD        = re.compile(r"\[([^\]]+)\]")
RE_NUMBER       = re.compile(r"(?<!\w)-?\d+(?:\.\d+)?(?!\w)")
RE_STRING_LIT   = re.compile(r"'([^']*)'")
RE_BOOL         = re.compile(r"\b(true|false)\b", re.IGNORECASE)
RE_COMPARISON   = re.compile(
    r"(!=|<=|>=|=|<|>)",
    re.IGNORECASE,
)
RE_ARITHMETIC   = re.compile(r"(\+|-|\*|/)")
RE_LOGICAL      = re.compile(r"\b(AND|OR)\b", re.IGNORECASE)
RE_CONDITIONAL  = re.compile(
    r"^If\s+(.+?)\s+Then\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
RE_MUST_ATTACH  = re.compile(
    r"\[?(IRS\w+)\]?\s+must\s+be\s+attached",
    re.IGNORECASE,
)
RE_PRESENCE     = re.compile(
    r"\[([^\]]+)\]\s+is\s+(not\s+)?present",
    re.IGNORECASE,
)
RE_DB_LOOKUP    = re.compile(
    r"\[([^\]]+)\]\s+(NOT\s+IN|IN|matches pattern|matches)\s+(.+)",
    re.IGNORECASE,
)
RE_FUNC_CALL    = re.compile(
    r"\b(SUM|MAX|MIN|CEIL|ABS|EIC_MAX_TABLE)\s*\((.+)\)",
    re.IGNORECASE,
)
RE_RANGE        = re.compile(
    r"\[([^\]]+)\]\s*(must not exceed|must be at least|<=|>=)\s*(.+)",
    re.IGNORECASE,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _field(name: str) -> ASTNode:
    return ASTNode(node_type=ASTNodeType.FIELD_REF, field_path=name)

def _num(val: float | int) -> ASTNode:
    return ASTNode(node_type=ASTNodeType.LITERAL_NUMBER, value=val)

def _str_lit(val: str) -> ASTNode:
    return ASTNode(node_type=ASTNodeType.LITERAL_STRING, value=val)

def _bool_lit(val: bool) -> ASTNode:
    return ASTNode(node_type=ASTNodeType.LITERAL_BOOL, value=val)

def _binop(op: str, left: ASTNode, right: ASTNode) -> ASTNode:
    return ASTNode(node_type=ASTNodeType.BINARY_OP, op=op,
                   left=left.to_dict(), right=right.to_dict())

def _logical(op: str, left: ASTNode, right: ASTNode) -> ASTNode:
    return ASTNode(node_type=ASTNodeType.LOGICAL_OP, op=op,
                   left=left.to_dict(), right=right.to_dict())

def _cond(condition: ASTNode, consequence: ASTNode,
          alternate: Optional[ASTNode] = None) -> ASTNode:
    node = ASTNode(node_type=ASTNodeType.CONDITIONAL,
                   condition=condition.to_dict(),
                   consequence=consequence.to_dict())
    if alternate is not None:
        node.alternate = alternate.to_dict()
    return node

def _attachment(form: str) -> ASTNode:
    return ASTNode(node_type=ASTNodeType.ATTACHMENT_REQ, form_name=form)

def _presence(field: str, required: bool = True) -> ASTNode:
    return ASTNode(node_type=ASTNodeType.PRESENCE_CHECK,
                   field_path=field, value=required)

def _parse_error(raw: str, reason: str) -> ASTNode:
    logger.debug("AST parse error [%s]: %s", reason, raw[:120])
    return ASTNode(node_type=ASTNodeType.PARSE_ERROR,
                   raw=raw, value=reason)


# ──────────────────────────────────────────────────────────────────────────────
# Atom parser — parses the smallest meaningful unit
# ──────────────────────────────────────────────────────────────────────────────

def _parse_atom(text: str) -> ASTNode:
    """Parse a single token: field ref, number, string, bool, or function call."""
    text = text.strip()

    # Function call: SUM([...]), MAX(..., ...), etc.
    m = RE_FUNC_CALL.fullmatch(text)
    if m:
        func = m.group(1).upper()
        args_raw = m.group(2)
        # Split top-level args by comma (don't split inside nested parens)
        args = _split_args(args_raw)
        parsed_args = [_parse_atom(a.strip()) for a in args]
        return ASTNode(
            node_type=ASTNodeType.FUNCTION_CALL,
            func_name=func,
            args=[a.to_dict() for a in parsed_args],
        )

    # Field reference: [FieldName]
    m = RE_FIELD.fullmatch(text)
    if m:
        return _field(m.group(1))

    # Boolean literal
    m = RE_BOOL.fullmatch(text)
    if m:
        return _bool_lit(text.lower() == "true")

    # Numeric literal
    m = RE_NUMBER.fullmatch(text)
    if m:
        val_str = m.group()
        val = float(val_str) if "." in val_str else int(val_str)
        return _num(val)

    # String literal: 'value'
    m = RE_STRING_LIT.fullmatch(text)
    if m:
        return _str_lit(m.group(1))

    # IN list: (1, 2, 3, 4, 5)
    if text.startswith("(") and text.endswith(")"):
        items_raw = text[1:-1].split(",")
        items = [_parse_atom(i.strip()) for i in items_raw]
        return ASTNode(
            node_type=ASTNodeType.FUNCTION_CALL,
            func_name="LIST",
            args=[i.to_dict() for i in items],
        )

    # Arithmetic expression: a + b, a - b * c …
    arith = _try_parse_arithmetic(text)
    if arith:
        return arith

    # Fall-through: unknown token, treat as raw string field reference
    return _field(text)


def _split_args(args_str: str) -> list[str]:
    """Split comma-separated args without splitting inside nested parentheses."""
    depth, start, parts = 0, 0, []
    for i, ch in enumerate(args_str):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(args_str[start:i])
            start = i + 1
    parts.append(args_str[start:])
    return parts


def _try_parse_arithmetic(text: str) -> Optional[ASTNode]:
    """Try to parse a simple binary arithmetic expression (no nested parens)."""
    # Try each arithmetic operator in reverse precedence order (+ and - last)
    for op in ("+", "-", "*", "/"):
        # Find rightmost top-level occurrence to build left-associative tree
        depth, idx = 0, -1
        for i, ch in enumerate(text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == op and depth == 0:
                idx = i
        if idx > 0:
            left_raw  = text[:idx].strip()
            right_raw = text[idx + 1:].strip()
            if left_raw and right_raw:
                return _binop(op, _parse_atom(left_raw), _parse_atom(right_raw))
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Condition parser — parses boolean expressions (possibly compound)
# ──────────────────────────────────────────────────────────────────────────────

def _parse_condition(text: str) -> ASTNode:
    """
    Parse a boolean condition expression.
    Handles AND / OR compound conditions, comparisons, IN-list checks,
    presence checks, pattern matches, and attachment requirements.
    """
    text = text.strip()

    # ── Compound: split on top-level AND / OR ───────────────────────────
    parts = _split_logical(text)
    if len(parts) > 1:
        # Re-assemble as a left-associative tree
        node = _parse_simple_condition(parts[0]["expr"])
        for part in parts[1:]:
            right = _parse_simple_condition(part["expr"])
            node = _logical(part["op"], node, right)
        return node

    return _parse_simple_condition(text)


def _split_logical(text: str) -> list[dict]:
    """Split on top-level AND/OR.  Returns list of {op, expr} dicts."""
    tokens = re.split(r"\b(AND|OR)\b", text, flags=re.IGNORECASE)
    if len(tokens) == 1:
        return [{"op": "", "expr": text}]
    parts = [{"op": "", "expr": tokens[0].strip()}]
    i = 1
    while i < len(tokens) - 1:
        op   = tokens[i].upper()
        expr = tokens[i + 1].strip()
        parts.append({"op": op, "expr": expr})
        i += 2
    return parts


def _parse_simple_condition(text: str) -> ASTNode:
    """Parse a single (non-compound) boolean condition."""
    text = text.strip()

    # Attachment requirement
    m = RE_MUST_ATTACH.search(text)
    if m:
        return _attachment(m.group(1))

    # Presence check: [Field] is (not) present
    m = RE_PRESENCE.search(text)
    if m:
        field    = m.group(1)
        negated  = bool(m.group(2))
        return _presence(field, required=not negated)

    # Database / pattern lookup
    m = RE_DB_LOOKUP.search(text)
    if m:
        field    = m.group(1)
        operator = m.group(2).upper().strip()
        operand  = m.group(3).strip()
        return ASTNode(
            node_type=ASTNodeType.DB_LOOKUP,
            field_path=field,
            op=operator,
            value=operand,
        )

    # Range constraint: [Field] must not exceed / must be at least
    m = RE_RANGE.fullmatch(text)
    if m:
        field  = m.group(1)
        op_str = m.group(2).lower()
        rhs    = _parse_atom(m.group(3).strip())
        op     = "<=" if "not exceed" in op_str or op_str == "<=" else ">="
        return _binop(op, _field(field), rhs)

    # IN list: [Field] IN (a, b, c)
    in_match = re.match(
        r"\[([^\]]+)\]\s+(NOT\s+IN|IN)\s*\((.+)\)",
        text, re.IGNORECASE,
    )
    if in_match:
        field   = in_match.group(1)
        negated = "NOT" in in_match.group(2).upper()
        items   = [_parse_atom(i.strip()) for i in in_match.group(3).split(",")]
        list_node = ASTNode(
            node_type=ASTNodeType.FUNCTION_CALL,
            func_name="LIST",
            args=[i.to_dict() for i in items],
        )
        op = "NOT IN" if negated else "IN"
        return _binop(op, _field(field), list_node)

    # Comparison: [Field] op value
    m = RE_COMPARISON.search(text)
    if m:
        op_str   = m.group(1)
        lhs_raw  = text[:m.start()].strip()
        rhs_raw  = text[m.end():].strip()
        lhs      = _parse_atom(lhs_raw)
        rhs      = _parse_atom(rhs_raw)
        return _binop(op_str, lhs, rhs)

    # Boolean literal (rare — e.g. "true" alone)
    m = RE_BOOL.fullmatch(text)
    if m:
        return _bool_lit(text.lower() == "true")

    # Could not parse — return a PARSE_ERROR leaf
    return _parse_error(text, "unrecognised condition pattern")


# ──────────────────────────────────────────────────────────────────────────────
# Top-level expression parser
# ──────────────────────────────────────────────────────────────────────────────

def parse_expression(expression: str) -> ASTNode:
    """
    Entry point.  Parse an IRS MeF rule expression string into an ASTNode tree.

    Examples:
        "[TotalIncomeAmt] = [WagesAmt] + [InterestAmt]"
        "If [AGIAmt] > 200000 Then [IRS8960] must be attached"
        "If [FilingStatusCd] = 2 AND [MAGI] > 250000 Then [NIITAmt] = ..."
    """
    expr = expression.strip()

    # ── Conditional: If ... Then ... [Else ...] ─────────────────────────
    m = RE_CONDITIONAL.match(expr)
    if m:
        cond_raw      = m.group(1).strip()
        then_else_raw = m.group(2).strip()
        # Split on Else clause (case-insensitive)
        else_parts = re.split(r"\s+Else\s+", then_else_raw, maxsplit=1, flags=re.IGNORECASE)
        cons_raw  = else_parts[0].strip()
        alt_raw   = else_parts[1].strip() if len(else_parts) > 1 else None
        condition   = _parse_condition(cond_raw)
        consequence = _parse_consequence(cons_raw)
        alternate   = _parse_consequence(alt_raw) if alt_raw else None
        return _cond(condition, consequence, alternate)

    # ── Standalone attachment requirement ───────────────────────────────
    m = RE_MUST_ATTACH.search(expr)
    if m:
        return _attachment(m.group(1))

    # ── Presence check ──────────────────────────────────────────────────
    m = RE_PRESENCE.search(expr)
    if m:
        return _presence(m.group(1), required=not bool(m.group(2)))

    # ── Math / comparison expression ────────────────────────────────────
    m = RE_COMPARISON.search(expr)
    if m:
        op_str  = m.group(1)
        lhs_raw = expr[:m.start()].strip()
        rhs_raw = expr[m.end():].strip()
        lhs     = _parse_atom(lhs_raw)
        rhs     = _parse_atom(rhs_raw)
        return _binop(op_str, lhs, rhs)

    # ── Range constraint ────────────────────────────────────────────────
    m = RE_RANGE.fullmatch(expr)
    if m:
        field  = m.group(1)
        op_str = m.group(2).lower()
        rhs    = _parse_atom(m.group(3).strip())
        op     = "<=" if "not exceed" in op_str or op_str == "<=" else ">="
        return _binop(op, _field(field), rhs)

    # ── DB lookup / IN list / presence / pattern at top level ───────────
    # Delegate to _parse_simple_condition which handles these cases
    node = _parse_simple_condition(expr)
    if node.node_type != ASTNodeType.PARSE_ERROR:
        return node

    # ── Fallback ────────────────────────────────────────────────────────
    return _parse_error(expr, "no recognised top-level pattern")


def _parse_consequence(text: str) -> ASTNode:
    """
    Parse the THEN-branch of a conditional.
    May be an attachment requirement, a math constraint, a DB lookup,
    a flag action, or a simple comparison.
    """
    text = text.strip()

    # Attachment
    m = RE_MUST_ATTACH.search(text)
    if m:
        return _attachment(m.group(1))

    # Presence
    m = RE_PRESENCE.search(text)
    if m:
        return _presence(m.group(1), required=not bool(m.group(2)))

    # FLAG action
    if text.lower().startswith("flag"):
        return ASTNode(
            node_type=ASTNodeType.DB_LOOKUP,
            op="FLAG",
            value=text,
        )

    # Range / comparison / math
    return _parse_condition(text)
