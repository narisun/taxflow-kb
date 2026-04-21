"use client";

import { Button } from "@/components/ui/button";
import { fmtTimestamp } from "@/lib/utils";
import { useTimezone } from "@/components/auth/me-context";

interface TaxLine { number: string; label: string; value: number; section: string; }

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
  const tz = useTimezone();
  const hasData = lines && lines.length > 0;
  const fmt = (v: number | undefined) => v !== undefined ? `$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 0 })}` : "\u2014";

  // ── YoY delta helpers ──────────────────────────────────────
  const fmtDelta = (current: number | undefined, prior: number | undefined): string | null => {
    if (current === undefined || prior === undefined) return null;
    const diff = current - prior;
    if (diff === 0) return null;
    const sign = diff > 0 ? "+" : "-";
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

  const DeltaBadge = ({ text, colorClass }: { text: string | null; colorClass: string }) => {
    if (!text) return null;
    return <span className={`text-[10px] ${colorClass} ml-1`}>{text}</span>;
  };

  const sections = ["income", "deductions", "tax_credits", "payments"];
  const sectionLabels: Record<string, string> = {
    income: "Income", deductions: "Deductions", tax_credits: "Tax & Credits", payments: "Payments",
  };

  if (!hasData) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="text-[32px] mb-3">📋</div>
        <div className="text-[14px] font-medium text-primary mb-1">No Tax Return Computed</div>
        <div className="text-[12px] text-tertiary mb-4 max-w-[280px]">
          Upload and approve documents, then compute the return to see Form 1040 details.
        </div>
        {onViewFull && (
          <Button variant="primary" onClick={onViewFull} className="text-[12px]">
            Compute Return
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Summary card */}
      <div className="bg-surface-secondary/50 rounded-xl p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-[12px] font-semibold text-primary">Federal Return Summary</span>
            {priorYear && (
              <span className="text-[9px] font-medium text-tertiary bg-surface-tertiary/50 rounded-full px-2 py-0.5">
                2025 vs 2024
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {onViewReturn && (
              <Button variant="pill" onClick={onViewReturn} className="text-[10px] px-2.5 py-1">
                View Return
              </Button>
            )}
            {onViewFull && (
              <Button variant="pill" onClick={onViewFull} className="text-[10px] px-2.5 py-1">
                Recompute
              </Button>
            )}
          </div>
        </div>
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
        {/* Refund/Owed highlight */}
        {refundOrOwed !== undefined && (
          <div className={`mt-2 pt-2 border-t border-divider flex items-center justify-between text-[13px] font-semibold ${refundOrOwed >= 0 ? "text-brand-green" : "text-red-500"}`}>
            <span>{refundOrOwed >= 0 ? "Refund" : "Amount Owed"}</span>
            <div className="flex items-center">
              <span>{fmt(refundOrOwed)}</span>
              {priorYear && (
                <DeltaBadge
                  text={fmtDelta(refundOrOwed, priorYear.refundOrOwed)}
                  colorClass={deltaColor(refundOrOwed, priorYear.refundOrOwed, "up-good")}
                />
              )}
            </div>
          </div>
        )}
        {computedAt && (
          <div className="text-[10px] text-tertiary mt-1.5">
            Last computed: {fmtTimestamp(computedAt, tz)}
          </div>
        )}
      </div>

      {/* Line items by section */}
      {sections.map((section) => {
        const sectionLines = (lines || []).filter((l) => l.section === section);
        if (sectionLines.length === 0) return null;
        return (
          <div key={section}>
            <div className="text-[10px] font-semibold text-secondary uppercase tracking-wider mb-1">{sectionLabels[section] || section}</div>
            <div className="space-y-0">
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
                        colorClass={deltaColor(line.value, priorLineValue(line.number), section === "tax_credits" ? "up-bad" : "up-good")}
                      />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
