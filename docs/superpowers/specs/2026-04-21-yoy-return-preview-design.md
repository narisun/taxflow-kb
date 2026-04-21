# Year-over-Year Deltas in ReturnPreview — Design Spec

**Date:** 2026-04-21
**Status:** Approved
**Scope:** Enhance the Tax Return tab in the right panel to show inline YoY deltas

---

## 1. Overview

CPAs need to quickly see how a client's current year return compares to the prior year. This enhancement adds inline delta indicators (dollar amount + percentage) to the existing `ReturnPreview` component — both in the summary card and line items.

### Design Decisions

- **Inline deltas (not side-by-side columns)** — the right panel is ~384px wide; inline deltas keep the layout clean
- **Dollar + percentage** — CPAs care about both absolute impact and proportional change
- **Deltas on summary card AND line items** — full visibility into what changed
- **No special treatment for new/removed lines** — delta shows the full amount, no badges or strikethrough
- **Client-specific prior year mock data** — realistic 2024 variations per client for demo purposes

---

## 2. Data Layer

### 2.1 Prior Year Mock Data (`mock-data.ts`)

Add `mockPriorYearDrafts: Record<number, TaxReturnDraft>` with 2024 data for each client:

| Client | 2025 Income | 2024 Variation |
|--------|-------------|----------------|
| 1 — Smith (Single) | $114,740 | ~$105K, lower wages/interest, lower withholding |
| 4 — Garcia (MFJ, 4 dep) | $143,200 | ~$132K, lower wages, lower dividends |
| 5 — Patel (MFJ, 1 dep) | $310,000 | ~$285K, lower wages |
| 8 — O'Brien (Single) | $235,500 | ~$195K wages only (no K-1 in 2024) |
| 9 — Nguyen (MFJ, 2 dep) | $251,800 | ~$238K, lower dividends |

Each entry is a full `TaxReturnDraft` with `tax_year: 2024`, matching line structure where applicable.

### 2.2 Mock API Integration (`mock-api.ts`)

Add a method or lookup to serve prior year data by client ID, following existing patterns.

---

## 3. Component Changes

### 3.1 `ReturnPreview` — New Props

```typescript
priorYear?: {
  totalIncome?: number;
  totalDeductions?: number;
  taxableIncome?: number;
  totalTax?: number;
  totalPayments?: number;
  refundOrOwed?: number;
  effectiveRate?: number;
  lines?: TaxLine[];
}
```

### 3.2 Delta Computation (internal helper)

```typescript
function deltaLabel(current: number, prior: number): { text: string; positive: boolean }
// Returns e.g. { text: "+$3,200 (+2.8%)", positive: true }
// For effective rate: "+1.2pp" (percentage points)
```

### 3.3 Context-Aware Coloring

Deltas are colored by whether the change is **favorable for the taxpayer**:

| Metric | Increase = | Decrease = |
|--------|-----------|-----------|
| Total Income | green (good) | red |
| Deductions | green (good) | red |
| Taxable Income | red (bad) | green |
| Total Tax | red (bad) | green |
| Payments | green (good) | red |
| Effective Rate | red (bad) | green |
| Refund | green (good) | red |
| Amount Owed | red (bad) | green |

For line items, default to neutral: increases green, decreases red (standard financial convention).

### 3.4 Summary Card Layout

Each metric row adds a delta below the value:

```
Total Income          $114,740
                      +$9,540 (+9.1%)
```

Delta text: `text-[10px]`, colored per section 3.3.

Year label: Small `2025 vs 2024` badge in the summary card header area.

### 3.5 Line Items

Each line item row shows the delta to the right of the value, same `text-[10px]` styling. Lines with no prior-year counterpart show the full current value as delta.

### 3.6 Refund/Owed Line

Delta shown inline next to the refund/owed amount.

---

## 4. Wiring (`page.tsx`)

Pass `priorYear` to both `ReturnPreview` render sites (desktop inline panel and tablet overlay). Source from `mockPriorYearDrafts[activeClientId]` alongside existing `returnDraft`.

---

## 5. Files Changed

1. `frontend/lib/mock-data.ts` — add `mockPriorYearDrafts`
2. `frontend/components/returns/return-preview.tsx` — add `priorYear` prop, delta helpers, render deltas
3. `frontend/app/page.tsx` — pass `priorYear` prop to both `ReturnPreview` instances

---

## 6. Out of Scope

- Backend API for prior year data (exists in Phase 3C comparison engine)
- State tax comparisons
- Multi-year trends (3+ years)
- Export/print of comparison view
