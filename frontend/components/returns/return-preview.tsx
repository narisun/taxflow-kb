"use client";

import { Button } from "@/components/ui/button";

interface TaxLine { number: string; label: string; value: number; section: string; }

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
  onViewFull?: () => void;
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
  onViewFull,
  onApproveFile,
}: ReturnPreviewProps) {
  const hasData = lines && lines.length > 0;
  const fmt = (v: number | undefined) => v !== undefined ? `$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 0 })}` : "\u2014";
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
          <div className="text-[12px] font-semibold text-primary">Federal Return Summary</div>
          {onViewFull && (
            <Button variant="pill" onClick={onViewFull} className="text-[10px] px-2.5 py-1">
              Recompute
            </Button>
          )}
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
          <div className="flex justify-between">
            <span className="text-secondary">Total Income</span>
            <span className="font-medium text-primary">{fmt(totalIncome)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-secondary">Deductions</span>
            <span className="font-medium text-primary">{fmt(totalDeductions)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-secondary">Taxable Income</span>
            <span className="font-medium text-primary">{fmt(taxableIncome)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-secondary">Total Tax</span>
            <span className="font-medium text-primary">{fmt(totalTax)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-secondary">Payments</span>
            <span className="font-medium text-primary">{fmt(totalPayments)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-secondary">Effective Rate</span>
            <span className="font-medium text-primary">{effectiveRate ?? 0}%</span>
          </div>
        </div>
        {/* Refund/Owed highlight */}
        {refundOrOwed !== undefined && (
          <div className={`mt-2 pt-2 border-t border-divider flex items-center justify-between text-[13px] font-semibold ${refundOrOwed >= 0 ? "text-green-600" : "text-red-500"}`}>
            <span>{refundOrOwed >= 0 ? "Refund" : "Amount Owed"}</span>
            <span>{fmt(refundOrOwed)}</span>
          </div>
        )}
        {computedAt && (
          <div className="text-[10px] text-tertiary mt-1.5">
            Last computed: {new Date(computedAt).toLocaleString()}
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
                  <div className="flex items-center gap-2">
                    <span className="text-tertiary w-5 text-right font-mono text-[10px]">{line.number}</span>
                    <span className="text-secondary">{line.label}</span>
                  </div>
                  <span className="font-medium">{fmt(line.value)}</span>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
