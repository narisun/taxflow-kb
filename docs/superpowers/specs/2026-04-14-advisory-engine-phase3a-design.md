# Phase 3A: Tax Advisory Engine — Design Spec

**Date:** 2026-04-14
**Status:** Approved
**Scope:** Pluggable advisory rule system, 12 strategy rules, marginal rate estimation, API endpoint

---

## 1. Overview

Add a tax advisory engine that analyzes a computed tax return and generates personalized strategy recommendations for CPAs. Each recommendation includes a title, explanation with specific dollar amounts, and estimated savings based on the taxpayer's marginal rate. The advisory panel in the frontend already exists — this backend provides the data dynamically instead of hardcoded items.

### Design Principles

- **Pluggable rules** — each strategy is an independent `AdvisoryRule` class. Adding a new strategy is just adding a class and registering it.
- **No re-computation** — savings estimated via marginal rate, not full what-if engine runs.
- **Frontend-compatible** — output matches the existing `AdvisoryItem` TypeScript interface exactly.
- **Testability** — rules are pure functions of `(TaxReturn, TaxResult, TaxYearConstants)` with no DB or network deps.

---

## 2. Directory Structure

```
api/tax_engine/advisory/
├── __init__.py
├── models.py          # AdvisoryItem Pydantic model
├── base.py            # AdvisoryRule ABC + marginal_rate helper
├── rules.py           # 12 concrete rule implementations
└── engine.py          # AdvisoryEngine orchestrator
```

---

## 3. Components

### 3.1 `models.py` — Advisory Data Model

```python
class AdvisoryItem(BaseModel):
    id: str
    category: Literal["deduction", "credit", "retirement", "planning", "compliance"]
    title: str
    detail: str
    savings: str | None = None
    estimated_savings: Decimal | None = None
    selected: bool = True
```

Fields match the frontend `AdvisoryItem` interface. `estimated_savings` is the raw decimal for backend sorting (frontend can ignore it). `selected` defaults to `True` — the CPA deselects items they don't want in the client letter.

### 3.2 `base.py` — Rule ABC + Marginal Rate Helper

```python
class AdvisoryRule(ABC):
    rule_id: str
    category: Literal["deduction", "credit", "retirement", "planning", "compliance"]

    @abstractmethod
    def evaluate(
        self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants
    ) -> AdvisoryItem | None:
        """Return an advisory item if applicable, else None."""


def marginal_rate(
    taxable_income: Decimal, filing_status: str, constants: TaxYearConstants
) -> Decimal:
    """Return the marginal ordinary tax rate for the given taxable income."""
    brackets = constants.ordinary_brackets[filing_status]
    rate = Decimal("0.10")
    prev_upper = Decimal("0")
    for upper, bracket_rate in brackets:
        if taxable_income <= prev_upper:
            break
        rate = bracket_rate
        prev_upper = upper
    return rate
```

### 3.3 `rules.py` — 12 Concrete Rules

Each rule follows the pattern: check applicability → calculate gap/opportunity → estimate savings via marginal rate → return `AdvisoryItem` with specific numbers.

#### Deduction Rules

**HSAOptimizationRule** (`id="hsa"`, category=`"deduction"`):
- Check: taxpayer has HSA contributions below the limit (from constants)
- Gap: `hsa_limit[coverage_type] - (employee_contributions + employer_contributions)`
- If gap > 0: savings = `gap × marginal_rate`
- Detail: "You contributed $X to your HSA but the {coverage_type} limit is $Y. Contributing $Z more would save ~$S in federal tax."

**CharitableBunchingRule** (`id="charitable_bunch"`, category=`"deduction"`):
- Check: taxpayer uses standard deduction AND has some charitable giving
- Check: itemized total (from Schedule A result) is within $5,000 of standard deduction
- If applicable: suggest bunching 2 years of charitable into 1 year to exceed standard deduction
- Savings estimate: the amount by which bunched itemized would exceed standard × marginal rate
- Detail: "Your itemized deductions total $X, which is $Y below the standard deduction of $Z. Bunching two years of charitable donations into one year could push you over the threshold."

**SALTCapAwarenessRule** (`id="salt_cap"`, category=`"deduction"`):
- Check: total SALT (from itemized input) exceeds the cap
- If applicable: flag the lost deduction amount
- Detail: "Your state and local taxes total $X but are capped at $Y. You're losing $Z in deductions due to the SALT cap."
- No savings estimate (informational — can't be optimized)

#### Retirement Rules

**RetirementContributionRule** (`id="401k"`, category=`"retirement"`):
- Check: W-2 box 12 code D (401k deferrals) below the limit ($23,000 for 2024, $23,500 for 2025)
- Gap: `limit - current_deferrals`
- Savings: `gap × marginal_rate`
- Detail: "You contributed $X to your 401(k) but the limit is $Y. Contributing $Z more would save ~$S in federal tax."

**RothConversionRule** (`id="roth_conversion"`, category=`"retirement"`):
- Check: taxable income is below the top of the current bracket
- Room: `bracket_top - taxable_income`
- If room > $5,000: suggest filling the bracket with Roth conversion
- Detail: "You have $X of room before reaching the next tax bracket (Y%). Converting up to $X from traditional IRA to Roth would be taxed at Z% — a potentially favorable rate."
- Savings: "Long-term benefit" (no dollar estimate — depends on future rates)

**SpousalIRARule** (`id="spousal_ira"`, category=`"retirement"`):
- Check: filing_status == "MFJ" AND spouse exists AND no IRA contributions for spouse role
- Savings: `ira_limit × marginal_rate` (if deductible)
- Detail: "Your spouse can contribute up to $X to a spousal IRA. If deductible, this would save ~$S in federal tax."

#### Credit Rules

**CTCReviewRule** (`id="ctc_review"`, category=`"credit"`):
- Check: qualifying children exist AND CTC was reduced by phase-out (check Schedule 8812 result)
- If phase-out applied: explain the threshold and phase-out amount
- Detail: "Your AGI of $X exceeds the $Y CTC threshold. Your credit was reduced by $Z. Consider strategies to reduce AGI below $Y."
- Savings: the phase-out amount (potential recovery if AGI reduced)

**EducationCreditRule** (`id="education_credit"`, category=`"credit"`):
- Check: tuition_1098ts list is non-empty
- If present AND no education credit was claimed: flag the opportunity
- Detail: "You have $X in qualified education expenses. The American Opportunity Credit provides up to $2,500 per student (40% refundable)."
- Savings: estimated AOTC amount

#### Compliance Rules

**EstimatedPaymentRule** (`id="estimated_payments"`, category=`"compliance"`):
- Check: result.refund_or_owed < -$1,000 (owes > $1,000) AND no estimated payments made
- Detail: "You owe $X this year with no estimated payments. To avoid underpayment penalties next year, consider quarterly estimated payments of ~$Y (Form 1040-ES)."
- No savings — compliance warning

**WithholdingReviewRule** (`id="withholding"`, category=`"compliance"`):
- Check: refund > $2,000 OR owed > $500
- If large refund: "Your refund of $X means too much is being withheld. Adjusting your W-4 could increase your paycheck by ~$Y/month."
- If owed: "You owe $X. Adjusting your W-4 to increase withholding would avoid a year-end tax bill."
- Selected by default

#### Planning Rules

**Plan529Rule** (`id="529"`, category=`"planning"`):
- Check: dependents list is non-empty
- Detail: "With {N} dependent(s), a 529 plan offers tax-free growth for education expenses. Some states offer a state tax deduction for contributions."
- Selected only if dependents > 0

**CapitalLossHarvestRule** (`id="capital_loss_harvest"`, category=`"planning"`):
- Check: Schedule D result shows net capital gains > 0
- Detail: "You have $X in net capital gains this year. Consider selling underperforming positions before year-end to offset gains. A $X loss would save ~$S in tax."
- Savings: `net_gains × ltcg_rate` (use 15% as default estimate)

### 3.4 `engine.py` — AdvisoryEngine

```python
def default_rules() -> list[AdvisoryRule]:
    """All 12 built-in advisory rules."""

class AdvisoryEngine:
    def __init__(self, rules: list[AdvisoryRule] | None = None):
        self.rules = rules or default_rules()

    def analyze(
        self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants
    ) -> list[AdvisoryItem]:
        """Run all rules, return items sorted by estimated savings (highest first)."""
        items = []
        for rule in self.rules:
            item = rule.evaluate(tax_return, result, constants)
            if item is not None:
                items.append(item)
        items.sort(key=lambda i: i.estimated_savings or Decimal("0"), reverse=True)
        return items
```

---

## 4. API Endpoint

### `GET /api/clients/{client_id}/returns/advisory`

Added to `api/routers/tax_returns.py`.

**Flow:**
1. Load client, verify access
2. Assemble TaxReturn via DocumentAssembler
3. Compute TaxResult via TaxCalculationEngine
4. Run AdvisoryEngine.analyze()
5. Return `list[AdvisoryItem]`

**Response:** JSON array of `AdvisoryItem` objects matching the frontend interface.

**Auth:** Requires `get_current_user` (any authenticated role can view advisory).

**Error cases:**
- Client not found → 404
- No documents uploaded → returns empty advisory list (engine still runs, rules check applicability)

---

## 5. Testing Strategy

### Unit Tests

- `test_marginal_rate.py` — verify correct rate at bracket boundaries for each filing status
- `test_rules.py` — each of the 12 rules tested with:
  - Applicable scenario → returns `AdvisoryItem` with correct fields
  - Not applicable scenario → returns `None`
  - Edge cases (e.g., HSA at exact limit, AGI at exact CTC threshold)
- `test_engine.py` — verify engine runs all rules, sorts by savings, handles empty results

### Integration Tests

- `test_advisory_endpoint.py` — create client with W-2 document, compute draft, call advisory endpoint, verify items returned with correct structure

---

## 6. Scope Summary

| Component | Count | Description |
|-----------|-------|-------------|
| Pydantic model | 1 | AdvisoryItem |
| Rule ABC | 1 | AdvisoryRule base class |
| Concrete rules | 12 | One per strategy |
| Helper function | 1 | marginal_rate() |
| Engine | 1 | AdvisoryEngine orchestrator |
| API endpoint | 1 | GET /advisory |
| Test files | 3 | Rules, engine, integration |

### Out of Scope

- What-if re-computation (full engine re-runs with modified inputs)
- State-specific advisory (state tax strategies)
- Multi-year planning (only current year recommendations)
- Client letter PDF generation (frontend handles the letter UI)
- Frontend changes (advisory panel already exists with compatible interface)
