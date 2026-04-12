"use client";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

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

export function ReturnPreview({ lines = defaultLines, refundOrOwed = 3288, effectiveRate = 13.3, onViewFull, onApproveFile }: ReturnPreviewProps) {
  const sections = ["Income", "Deductions", "Tax & Credits", "Payments"];
  const fmt = (v: number) => `$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 0 })}`;

  return (
    <div className="space-y-3">
      <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">Form 1040 Preview</div>
      {sections.map((section) => {
        const sectionLines = lines.filter((l) => l.section === section);
        if (sectionLines.length === 0) return null;
        return (
          <div key={section}>
            <div className="text-[11px] font-semibold text-form-header uppercase tracking-wider mb-1">{section}</div>
            <div className="space-y-0.5">
              {sectionLines.map((line) => {
                const isRefund = line.number === "34";
                return (
                  <div key={line.number} className={cn("flex items-center justify-between py-1.5 px-2 rounded text-[12px]", isRefund ? "bg-green-50 dark:bg-green-950/30 font-semibold text-green-700 dark:text-green-400" : "text-primary")}>
                    <div className="flex items-center gap-2">
                      <span className="text-tertiary w-6 text-right font-mono text-[11px]">{line.number}</span>
                      <span>{line.label}</span>
                    </div>
                    <span className="font-medium">{fmt(line.value)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
      <Card className="text-center p-4">
        <div className="text-[11px] text-secondary uppercase tracking-wider mb-1">{refundOrOwed >= 0 ? "Estimated Refund" : "Amount Owed"}</div>
        <div className={cn("text-[28px] font-semibold", refundOrOwed >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400")}>{fmt(refundOrOwed)}</div>
        <div className="text-[12px] text-secondary mt-1">Effective rate: {effectiveRate}%</div>
        <div className="flex gap-2 mt-3 justify-center">
          <Button variant="pill" onClick={onViewFull}>View Full 1040</Button>
          <Button variant="primary" onClick={onApproveFile}>Approve &amp; File</Button>
        </div>
      </Card>
    </div>
  );
}
