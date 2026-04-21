# YoY Return Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add inline year-over-year delta indicators (dollar + percentage) to the Tax Return right panel, with client-specific 2024 mock data.

**Architecture:** Enhance `ReturnPreview` with a `priorYear` prop. Add `mockPriorYearDrafts` to mock-data.ts. Wire the prop through `page.tsx` at both render sites (desktop + mobile).

**Tech Stack:** React, TypeScript, Tailwind CSS, Next.js

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `frontend/lib/mock-data.ts` | Modify | Add `mockPriorYearDrafts` with 2024 data for all 5 clients |
| `frontend/components/returns/return-preview.tsx` | Modify | Add `priorYear` prop, delta helpers, render inline deltas |
| `frontend/app/page.tsx` | Modify | Pass `priorYear` to both `ReturnPreview` render sites |

---

## Task 1: Add Prior Year Mock Data

**Files:**
- Modify: `frontend/lib/mock-data.ts:894` (after `mockReturnDrafts` closing brace)

- [ ] **Step 1: Add `mockPriorYearDrafts` export**

Add this block after the `mockReturnDrafts` export (after line 894) and before the `mockAdults` section:

```typescript
// ── Prior Year (2024) Tax Return Drafts ──────────────────────
// Realistic 2024 variants for YoY comparison in the right panel.

export const mockPriorYearDrafts: Record<number, TaxReturnDraft> = {
  // Client 1 — Smith (single, 1 dep) — 2024: lower wages, similar structure
  1: {
    client_id: "mock-1",
    tax_year: 2024,
    filing_status: "single",
    lines: [
      { number: "1a", label: "Wages, salaries, tips", value: 104200, section: "Income" },
      { number: "2b", label: "Taxable interest", value: 1890, section: "Income" },
      { number: "9", label: "Total income", value: 106090, section: "Income" },
      { number: "12", label: "Standard deduction", value: 14600, section: "Deductions" },
      { number: "15", label: "Taxable income", value: 91490, section: "Deductions" },
      { number: "16", label: "Tax", value: 15580, section: "Tax & Credits" },
      { number: "19", label: "Child tax credit", value: 2000, section: "Tax & Credits" },
      { number: "24", label: "Total tax", value: 13580, section: "Tax & Credits" },
      { number: "25a", label: "W-2 withholding", value: 17200, section: "Payments" },
      { number: "33", label: "Total payments", value: 17200, section: "Payments" },
      { number: "34", label: "Overpayment / Refund", value: 3620, section: "Payments" },
    ],
    total_income: 106090,
    taxable_income: 91490,
    total_tax: 13580,
    refund_or_owed: 3620,
    effective_rate: 12.8,
    total_deductions: 14600,
    total_payments: 17200,
  },

  // Client 4 — Garcia (MFJ, 4 dep) — 2024: lower wages and dividends
  4: {
    client_id: "mock-4",
    tax_year: 2024,
    filing_status: "mfj",
    lines: [
      { number: "1a", label: "Wages, salaries, tips", value: 129500, section: "Income" },
      { number: "3b", label: "Ordinary dividends", value: 2100, section: "Income" },
      { number: "9", label: "Total income", value: 131600, section: "Income" },
      { number: "12", label: "Standard deduction", value: 29200, section: "Deductions" },
      { number: "15", label: "Taxable income", value: 102400, section: "Deductions" },
      { number: "16", label: "Tax", value: 15120, section: "Tax & Credits" },
      { number: "19", label: "Child tax credit", value: 8000, section: "Tax & Credits" },
      { number: "24", label: "Total tax", value: 7120, section: "Tax & Credits" },
      { number: "25a", label: "W-2 withholding", value: 17500, section: "Payments" },
      { number: "33", label: "Total payments", value: 17500, section: "Payments" },
      { number: "34", label: "Overpayment / Refund", value: 10380, section: "Payments" },
    ],
    total_income: 131600,
    taxable_income: 102400,
    total_tax: 7120,
    refund_or_owed: 10380,
    effective_rate: 5.4,
    total_deductions: 29200,
    total_payments: 17500,
  },

  // Client 5 — Patel (MFJ, 1 dep) — 2024: lower wages
  5: {
    client_id: "mock-5",
    tax_year: 2024,
    filing_status: "mfj",
    lines: [
      { number: "1a", label: "Wages, salaries, tips", value: 285000, section: "Income" },
      { number: "9", label: "Total income", value: 285000, section: "Income" },
      { number: "12", label: "Standard deduction", value: 29200, section: "Deductions" },
      { number: "15", label: "Taxable income", value: 255800, section: "Deductions" },
      { number: "16", label: "Tax", value: 50260, section: "Tax & Credits" },
      { number: "19", label: "Child tax credit", value: 2000, section: "Tax & Credits" },
      { number: "24", label: "Total tax", value: 48260, section: "Tax & Credits" },
      { number: "25a", label: "W-2 withholding", value: 52000, section: "Payments" },
      { number: "33", label: "Total payments", value: 52000, section: "Payments" },
      { number: "34", label: "Overpayment / Refund", value: 3740, section: "Payments" },
    ],
    total_income: 285000,
    taxable_income: 255800,
    total_tax: 48260,
    refund_or_owed: 3740,
    effective_rate: 16.9,
    total_deductions: 29200,
    total_payments: 52000,
  },

  // Client 8 — O'Brien (single, 0 dep) — 2024: wages only, NO K-1 income
  8: {
    client_id: "mock-8",
    tax_year: 2024,
    filing_status: "single",
    lines: [
      { number: "1a", label: "Wages, salaries, tips", value: 185000, section: "Income" },
      { number: "9", label: "Total income", value: 185000, section: "Income" },
      { number: "12", label: "Standard deduction", value: 14600, section: "Deductions" },
      { number: "15", label: "Taxable income", value: 170400, section: "Deductions" },
      { number: "16", label: "Tax", value: 35680, section: "Tax & Credits" },
      { number: "24", label: "Total tax", value: 35680, section: "Tax & Credits" },
      { number: "25a", label: "W-2 withholding", value: 38000, section: "Payments" },
      { number: "33", label: "Total payments", value: 38000, section: "Payments" },
      { number: "34", label: "Overpayment / Refund", value: 2320, section: "Payments" },
    ],
    total_income: 185000,
    taxable_income: 170400,
    total_tax: 35680,
    refund_or_owed: 2320,
    effective_rate: 19.3,
    total_deductions: 14600,
    total_payments: 38000,
  },

  // Client 9 — Nguyen (MFJ, 2 dep) — 2024: lower wages and dividends
  9: {
    client_id: "mock-9",
    tax_year: 2024,
    filing_status: "mfj",
    lines: [
      { number: "1a", label: "Wages, salaries, tips", value: 232000, section: "Income" },
      { number: "3b", label: "Ordinary dividends", value: 3600, section: "Income" },
      { number: "9", label: "Total income", value: 235600, section: "Income" },
      { number: "12", label: "Standard deduction", value: 29200, section: "Deductions" },
      { number: "15", label: "Taxable income", value: 206400, section: "Deductions" },
      { number: "16", label: "Tax", value: 40920, section: "Tax & Credits" },
      { number: "19", label: "Child tax credit", value: 4000, section: "Tax & Credits" },
      { number: "24", label: "Total tax", value: 36920, section: "Tax & Credits" },
      { number: "25a", label: "W-2 withholding", value: 40200, section: "Payments" },
      { number: "33", label: "Total payments", value: 40200, section: "Payments" },
      { number: "34", label: "Overpayment / Refund", value: 3280, section: "Payments" },
    ],
    total_income: 235600,
    taxable_income: 206400,
    total_tax: 36920,
    refund_or_owed: 3280,
    effective_rate: 15.7,
    total_deductions: 29200,
    total_payments: 40200,
  },
};
```

- [ ] **Step 2: Verify no TypeScript errors**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors related to `mockPriorYearDrafts`

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/mock-data.ts
git commit -m "feat: add 2024 prior year mock data for YoY comparison"
```

---

## Task 2: Enhance ReturnPreview with Delta Rendering

**Files:**
- Modify: `frontend/components/returns/return-preview.tsx`

- [ ] **Step 1: Add `priorYear` prop and delta helper types**

Replace the existing `ReturnPreviewProps` interface (lines 9-22) with:

```typescript
interface PriorYearData {
  totalIncome?: number;
  totalDeductions?: number;
  taxableIncome?: number;
  totalTax?: number;
  totalPayments?: number;
  refundOrOwed?: number;
  effectiveRate?: number;
  lines?: TaxLine[];
}

interface ReturnPreviewProps {
  lines?: TaxLine[];
  totalIncome?: number;
  totalDeductions?: number;
  taxableIncome?: number;
  totalTax?: number;
  totalPayments?: number;
  refundOrOwed?: number;
  effectiveRate?: number;
  computedAt?: string;
  priorYear?: PriorYearData;
  onViewFull?: () => void;
  onViewReturn?: () => void;
  onApproveFile?: () => void;
}
```

- [ ] **Step 2: Add `priorYear` to destructured props**

Update the function signature (line 24-37) to include `priorYear`:

```typescript
export function ReturnPreview({
  lines,
  totalIncome,
  totalDeductions,
  taxableIncome,
  totalTax,
  totalPayments,
  refundOrOwed,
  effectiveRate,
  computedAt,
  priorYear,
  onViewFull,
  onViewReturn,
  onApproveFile,
}: ReturnPreviewProps) {
```

- [ ] **Step 3: Add delta computation helpers**

Add these helpers right after the existing `fmt` function (after line 40), before `const sections`:

```typescript
  // ── YoY delta helpers ──────────────────────────────────────
  const fmtDelta = (current: number | undefined, prior: number | undefined): string | null => {
    if (current === undefined || prior === undefined) return null;
    const diff = current - prior;
    if (diff === 0) return null;
    const sign = diff > 0 ? "+" : "";
    const dollarPart = `${sign}$${Math.abs(diff).toLocaleString("en-US", { minimumFractionDigits: 0 })}`;
    const pctPart = prior !== 0
      ? ` (${sign}${((diff / Math.abs(prior)) * 100).toFixed(1)}%)`
      : "";
    return `${dollarPart}${pctPart}`;
  };

  const fmtRateDelta = (current: number | undefined, prior: number | undefined): string | null => {
    if (current === undefined || prior === undefined) return null;
    const diff = current - prior;
    if (diff === 0) return null;
    const sign = diff > 0 ? "+" : "";
    return `${sign}${diff.toFixed(1)}pp`;
  };

  // "favorable" means good for the taxpayer: more income/deductions/payments = green,
  // less tax/taxable income = green, more refund = green, more owed = red.
  type Favorability = "up-good" | "up-bad";
  const deltaColor = (current: number | undefined, prior: number | undefined, favor: Favorability): string => {
    if (current === undefined || prior === undefined) return "text-secondary";
    const diff = current - prior;
    if (diff === 0) return "text-secondary";
    const isUp = diff > 0;
    const isGood = favor === "up-good" ? isUp : !isUp;
    return isGood ? "text-brand-green" : "text-red-500";
  };

  const priorLineValue = (lineNum: string): number | undefined =>
    priorYear?.lines?.find((l) => l.number === lineNum)?.value;
```

- [ ] **Step 4: Add a `DeltaBadge` inline component**

Add this right after the delta helpers (before `const sections`):

```typescript
  const DeltaBadge = ({ text, colorClass }: { text: string | null; colorClass: string }) => {
    if (!text) return null;
    return <span className={`text-[10px] ${colorClass} ml-1`}>{text}</span>;
  };
```

- [ ] **Step 5: Update the summary card header to show year label**

Replace the header line (line 68):
```typescript
          <div className="text-[12px] font-semibold text-primary">Federal Return Summary</div>
```

With:
```typescript
          <div className="flex items-center gap-2">
            <span className="text-[12px] font-semibold text-primary">Federal Return Summary</span>
            {priorYear && (
              <span className="text-[9px] font-medium text-tertiary bg-surface-tertiary/50 rounded-full px-2 py-0.5">
                2025 vs 2024
              </span>
            )}
          </div>
```

- [ ] **Step 6: Update the 6 summary metric rows with inline deltas**

Replace the entire `grid grid-cols-2` block (lines 82-107) with:

```typescript
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
          <div>
            <div className="flex justify-between">
              <span className="text-secondary">Total Income</span>
              <span className="font-medium text-primary">{fmt(totalIncome)}</span>
            </div>
            {priorYear && <div className="text-right"><DeltaBadge text={fmtDelta(totalIncome, priorYear.totalIncome)} colorClass={deltaColor(totalIncome, priorYear.totalIncome, "up-good")} /></div>}
          </div>
          <div>
            <div className="flex justify-between">
              <span className="text-secondary">Deductions</span>
              <span className="font-medium text-primary">{fmt(totalDeductions)}</span>
            </div>
            {priorYear && <div className="text-right"><DeltaBadge text={fmtDelta(totalDeductions, priorYear.totalDeductions)} colorClass={deltaColor(totalDeductions, priorYear.totalDeductions, "up-good")} /></div>}
          </div>
          <div>
            <div className="flex justify-between">
              <span className="text-secondary">Taxable Income</span>
              <span className="font-medium text-primary">{fmt(taxableIncome)}</span>
            </div>
            {priorYear && <div className="text-right"><DeltaBadge text={fmtDelta(taxableIncome, priorYear.taxableIncome)} colorClass={deltaColor(taxableIncome, priorYear.taxableIncome, "up-bad")} /></div>}
          </div>
          <div>
            <div className="flex justify-between">
              <span className="text-secondary">Total Tax</span>
              <span className="font-medium text-primary">{fmt(totalTax)}</span>
            </div>
            {priorYear && <div className="text-right"><DeltaBadge text={fmtDelta(totalTax, priorYear.totalTax)} colorClass={deltaColor(totalTax, priorYear.totalTax, "up-bad")} /></div>}
          </div>
          <div>
            <div className="flex justify-between">
              <span className="text-secondary">Payments</span>
              <span className="font-medium text-primary">{fmt(totalPayments)}</span>
            </div>
            {priorYear && <div className="text-right"><DeltaBadge text={fmtDelta(totalPayments, priorYear.totalPayments)} colorClass={deltaColor(totalPayments, priorYear.totalPayments, "up-good")} /></div>}
          </div>
          <div>
            <div className="flex justify-between">
              <span className="text-secondary">Effective Rate</span>
              <span className="font-medium text-primary">{effectiveRate ?? 0}%</span>
            </div>
            {priorYear && <div className="text-right"><DeltaBadge text={fmtRateDelta(effectiveRate, priorYear.effectiveRate)} colorClass={deltaColor(effectiveRate, priorYear.effectiveRate, "up-bad")} /></div>}
          </div>
        </div>
```

- [ ] **Step 7: Update the Refund/Owed highlight with delta**

Replace the refund/owed block (lines 109-114) with:

```typescript
        {refundOrOwed !== undefined && (
          <div className={`mt-2 pt-2 border-t border-divider flex items-center justify-between text-[13px] font-semibold ${refundOrOwed >= 0 ? "text-brand-green" : "text-red-500"}`}>
            <span>{refundOrOwed >= 0 ? "Refund" : "Amount Owed"}</span>
            <div className="flex items-center">
              <span>{fmt(refundOrOwed)}</span>
              {priorYear && (
                <DeltaBadge
                  text={fmtDelta(refundOrOwed, priorYear.refundOrOwed)}
                  colorClass={deltaColor(refundOrOwed, priorYear.refundOrOwed, refundOrOwed >= 0 ? "up-good" : "up-bad")}
                />
              )}
            </div>
          </div>
        )}
```

- [ ] **Step 8: Update line items with deltas**

Replace the line item row (lines 130-137) — the inner `{sectionLines.map(...)}` block — with:

```typescript
              {sectionLines.map((line) => (
                <div key={line.number} className="flex items-center justify-between py-1 px-2 rounded hover:bg-surface-secondary/50 text-[12px] text-primary">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-tertiary w-5 text-right font-mono text-[10px] shrink-0">{line.number}</span>
                    <span className="text-secondary truncate">{line.label}</span>
                  </div>
                  <div className="flex items-center shrink-0">
                    <span className="font-medium">{fmt(line.value)}</span>
                    {priorYear && (
                      <DeltaBadge
                        text={fmtDelta(line.value, priorLineValue(line.number))}
                        colorClass={deltaColor(line.value, priorLineValue(line.number), "up-good")}
                      />
                    )}
                  </div>
                </div>
              ))}
```

- [ ] **Step 9: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 10: Commit**

```bash
git add frontend/components/returns/return-preview.tsx
git commit -m "feat: add inline YoY delta indicators to ReturnPreview"
```

---

## Task 3: Wire Prior Year Data in page.tsx

**Files:**
- Modify: `frontend/app/page.tsx:92,645-657,876-888`

- [ ] **Step 1: Import `mockPriorYearDrafts`**

Find the import of `mockReturnDrafts` in `page.tsx` and add `mockPriorYearDrafts` to the same import:

Search for:
```typescript
mockReturnDrafts,
```

Add after it:
```typescript
mockPriorYearDrafts,
```

- [ ] **Step 2: Add `priorYearDraft` state**

After the existing `returnDraft` state (line 92):
```typescript
const [returnDraft, setReturnDraft] = useState<TaxReturnDraft | null>(null);
```

Add:
```typescript
const [priorYearDraft, setPriorYearDraft] = useState<TaxReturnDraft | null>(null);
```

- [ ] **Step 3: Load prior year data when client changes**

Find where `returnDraft` is loaded on client change. There's a `useEffect` around line 266 that calls `api.returns.get(cid)`. Add prior year loading alongside it.

Find this block:
```typescript
    api.returns.get(cid).then((draft) => {
      if (draft) setReturnDraft(draft);
    });
```

Replace with:
```typescript
    api.returns.get(cid).then((draft) => {
      if (draft) setReturnDraft(draft);
    });
    // Load prior year for YoY comparison (mock data for now)
    const numId = typeof cid === "string" ? parseInt(cid.replace("mock-", ""), 10) : cid;
    setPriorYearDraft(mockPriorYearDrafts[numId as number] ?? null);
```

- [ ] **Step 4: Also set prior year when client first loads**

Find the block around line 152 where `setReturnDraft` is called during initial client load:
```typescript
      if (draft) setReturnDraft(draft);
```

Add right after:
```typescript
      {
        const numId = typeof activeClientId === "string" ? parseInt(activeClientId.replace("mock-", ""), 10) : activeClientId;
        setPriorYearDraft(mockPriorYearDrafts[numId as number] ?? null);
      }
```

- [ ] **Step 5: Pass `priorYear` to the desktop `ReturnPreview` (line ~645)**

Add the `priorYear` prop to the first `ReturnPreview` instance. After the `computedAt` prop and before `onViewFull`:

```typescript
            priorYear={priorYearDraft ? {
              totalIncome: priorYearDraft.total_income,
              totalDeductions: priorYearDraft.total_deductions,
              taxableIncome: priorYearDraft.taxable_income,
              totalTax: priorYearDraft.total_tax,
              totalPayments: priorYearDraft.total_payments,
              refundOrOwed: priorYearDraft.refund_or_owed,
              effectiveRate: priorYearDraft.effective_rate,
              lines: priorYearDraft.lines,
            } : undefined}
```

- [ ] **Step 6: Pass `priorYear` to the mobile `ReturnPreview` (line ~876)**

Add the same `priorYear` prop to the second `ReturnPreview` instance (in the mobile tab view), after `computedAt` and before `onViewFull`:

```typescript
                      priorYear={priorYearDraft ? {
                        totalIncome: priorYearDraft.total_income,
                        totalDeductions: priorYearDraft.total_deductions,
                        taxableIncome: priorYearDraft.taxable_income,
                        totalTax: priorYearDraft.total_tax,
                        totalPayments: priorYearDraft.total_payments,
                        refundOrOwed: priorYearDraft.refund_or_owed,
                        effectiveRate: priorYearDraft.effective_rate,
                        lines: priorYearDraft.lines,
                      } : undefined}
```

- [ ] **Step 7: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 8: Verify dev server runs**

Run: `cd frontend && npm run dev` and confirm no runtime errors in the console.

- [ ] **Step 9: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat: wire prior year data to ReturnPreview for YoY comparison"
```
