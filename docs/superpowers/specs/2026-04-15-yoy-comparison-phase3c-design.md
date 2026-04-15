# Phase 3C: Year-over-Year Comparison — Design Spec

**Date:** 2026-04-15
**Status:** Approved
**Scope:** Compare two tax years for the same client, produce structured JSON diff report

---

## 1. Overview

Compare a client's current and prior year tax results, producing a structured report showing per-line changes in income, deductions, tax, and payments. CPAs use this to review year-over-year trends with clients ("your income went up $15K, your tax went up $3K, but your refund dropped $2K because withholding didn't keep pace").

### Design Principles

- **Same-client comparison** — compare drafts within one client across tax years
- **Recompute on demand** — assembles and computes both years fresh (not stale draft JSON)
- **Structured JSON** — frontend renders the comparison; no HTML generation
- **Pure function** — ComparisonEngine takes two TaxResults, no DB dependencies

---

## 2. Directory Structure

```
api/tax_engine/comparison/
├── __init__.py
├── models.py          # ComparisonRow, ComparisonSection, ComparisonReport
└── engine.py          # ComparisonEngine
```

---

## 3. Components

### 3.1 `models.py`

```python
class ComparisonRow(BaseModel):
    label: str              # "Wages, salaries, tips"
    line: str               # "1a"
    current: Decimal        # Current year value
    prior: Decimal          # Prior year value
    change: Decimal         # current - prior
    pct_change: float       # Percentage change (0.0 if prior is zero)

class ComparisonSection(BaseModel):
    title: str              # "Income", "Deductions", "Tax", "Payments"
    rows: list[ComparisonRow]

class ComparisonReport(BaseModel):
    current_year: int
    prior_year: int
    client_id: int
    sections: list[ComparisonSection]
    summary: ComparisonRow  # Bottom-line refund/owed change
```

### 3.2 `engine.py`

```python
class ComparisonEngine:
    def compare(self, current: TaxResult, prior: TaxResult, client_id: int) -> ComparisonReport:
        """Compare two TaxResults and return a structured report."""
```

**Lines compared (from Form 1040 results):**

| Section | Line | Label |
|---------|------|-------|
| Income | 1a | Wages, salaries, tips |
| Income | 2b | Taxable interest |
| Income | 3b | Ordinary dividends |
| Income | 7 | Capital gain/loss |
| Income | 8 | Other income |
| Income | 9 | Total income |
| Income | 10 | Adjustments to income |
| Income | 11 | Adjusted gross income |
| Deductions | 12 | Deduction (standard/itemized) |
| Deductions | 13a | QBI deduction |
| Deductions | 15 | Taxable income |
| Tax | 16 | Tax |
| Tax | 23 | Other taxes |
| Tax | 24 | Total tax |
| Payments | 25 | Federal tax withheld |
| Payments | 26 | Estimated tax payments |
| Payments | 33 | Total payments |
| Payments | 35a | Refund (or 37 Amount owed) |

The summary row shows the refund/owed change.

**Percentage change:** `(current - prior) / abs(prior) * 100` if prior != 0, else 100.0 if current != 0, else 0.0.

---

## 4. API Endpoint

### `GET /api/clients/{client_id}/returns/compare?prior_year=2023`

Added to `api/routers/tax_returns.py`.

**Flow:**
1. Load client, verify access
2. Determine current year from client.tax_year, prior year from query param
3. Assemble TaxReturn for current year → compute TaxResult
4. Change client tax_year temporarily to prior_year, assemble → compute prior TaxResult
5. Run ComparisonEngine.compare()
6. Return ComparisonReport

**Query params:**
- `prior_year` (required) — the year to compare against

**Error cases:**
- Client not found → 404
- prior_year same as current → 400 "Cannot compare a year to itself"
- No data for either year → still works (zeros for missing data)

---

## 5. Testing Strategy

### Unit Tests
- `test_comparison_engine.py`:
  - Two results with different values → correct deltas
  - Prior year all zeros → pct_change handles division by zero
  - Same values → all changes are zero
  - Negative changes (income decreased)
  - Summary row reflects refund/owed change

### Integration Test
- `test_comparison_endpoint.py`:
  - Create client, call compare endpoint → 200 with sections
  - Nonexistent client → 404
  - Same year comparison → 400

---

## 6. Scope Summary

| Component | Type | Description |
|-----------|------|-------------|
| `models.py` | New | ComparisonRow, ComparisonSection, ComparisonReport |
| `engine.py` | New | ComparisonEngine.compare() |
| `tax_returns.py` | Modified | Add GET /compare endpoint |
| Test files | 2 new | Engine unit tests, endpoint integration |

### Out of Scope
- HTML report generation
- Cross-client comparison
- Schedule-level comparison (only 1040 lines)
- Multi-year trends (only 2-year comparison)
