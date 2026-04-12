"use client";

import { Button } from "@/components/ui/button";

interface TaxLine { number: string; label: string; value: number; section: string; }

interface ReturnPreviewProps {
  lines?: TaxLine[]; totalIncome?: number; taxableIncome?: number; totalTax?: number;
  refundOrOwed?: number; effectiveRate?: number; onViewFull?: () => void; onApproveFile?: () => void;
}

const defaultLines: TaxLine[] = [
  { number: "1", label: "Wages, salaries, tips", value: 142500, section: "Income" },
  { number: "2b", label: "Taxable interest", value: 1230, section: "Income" },
  { number: "9", label: "Total income", value: 143730, section: "Income" },
  { number: "10", label: "Standard deduction", value: 27700, section: "Deductions" },
  { number: "11", label: "Adjusted gross income", value: 131230, section: "Deductions" },
  { number: "15", label: "Taxable income", value: 103730, section: "Deductions" },
  { number: "22", label: "Child tax credit", value: 4000, section: "Tax & Credits" },
  { number: "24", label: "Total tax", value: 17412, section: "Tax & Credits" },
  { number: "33", label: "Total payments", value: 20700, section: "Payments" },
  { number: "34", label: "Overpayment / Refund", value: 3288, section: "Payments" },
];

export function ReturnPreview({ lines = defaultLines, effectiveRate = 13.3, onViewFull, onApproveFile }: ReturnPreviewProps) {
  const sections = ["Income", "Deductions", "Tax & Credits", "Payments"];
  const fmt = (v: number) => `$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 0 })}`;

  return (
    <div className="space-y-3">
      {/* Header row: title + View 1040 button */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">Form 1040 Preview</div>
          <div className="text-[11px] text-tertiary mt-0.5">Effective tax rate: {effectiveRate}%</div>
        </div>
        {onViewFull && (
          <Button variant="pill" onClick={onViewFull} className="text-[11px] px-3 py-1">
            View 1040
          </Button>
        )}
      </div>

      {/* Line items by section */}
      {sections.map((section) => {
        const sectionLines = lines.filter((l) => l.section === section);
        if (sectionLines.length === 0) return null;
        return (
          <div key={section}>
            <div className="text-[11px] font-semibold text-form-header uppercase tracking-wider mb-1">{section}</div>
            <div className="space-y-0.5">
              {sectionLines.map((line) => (
                <div key={line.number} className="flex items-center justify-between py-1.5 px-2 rounded text-[12px] text-primary">
                  <div className="flex items-center gap-2">
                    <span className="text-tertiary w-6 text-right font-mono text-[11px]">{line.number}</span>
                    <span>{line.label}</span>
                  </div>
                  <span className="font-medium">{fmt(line.value)}</span>
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {/* Approve & File button */}
      {onApproveFile && (
        <div className="flex justify-end pt-2">
          <Button variant="primary" onClick={onApproveFile} className="text-[13px]">
            Approve &amp; File
          </Button>
        </div>
      )}
    </div>
  );
}
