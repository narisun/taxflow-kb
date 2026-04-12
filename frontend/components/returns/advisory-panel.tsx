"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface AdvisoryItem {
  id: string;
  category: "deduction" | "credit" | "retirement" | "planning" | "compliance";
  title: string;
  detail: string;
  savings?: string;
  selected: boolean;
}

const categoryLabels: Record<string, string> = {
  deduction: "Deduction",
  credit: "Tax Credit",
  retirement: "Retirement",
  planning: "Planning",
  compliance: "Compliance",
};

const categoryIcons: Record<string, string> = {
  deduction: "\u2193",
  credit: "\u2605",
  retirement: "\u23F3",
  planning: "\u{1F4C5}",
  compliance: "\u2713",
};

interface AdvisoryPanelProps {
  clientName?: string;
  filingStatus?: string;
  dependents?: number;
}

function getAdvisoryItems(filingStatus: string, dependents: number): AdvisoryItem[] {
  const items: AdvisoryItem[] = [
    {
      id: "hsa",
      category: "deduction",
      title: "Maximize HSA contributions",
      detail: "You can contribute up to $4,300 (individual) or $8,550 (family) pre-tax to a Health Savings Account for 2026. HSA contributions reduce taxable income and grow tax-free.",
      savings: "Up to $1,500/yr",
      selected: true,
    },
    {
      id: "401k",
      category: "retirement",
      title: "Increase 401(k) contributions",
      detail: "The 2026 401(k) limit is $23,500 ($31,000 if age 50+). Increasing contributions reduces your current taxable income while building retirement savings.",
      savings: "Up to $5,000/yr",
      selected: true,
    },
    {
      id: "ira",
      category: "retirement",
      title: "Consider backdoor Roth IRA",
      detail: "Your income may exceed Roth IRA limits. A backdoor Roth conversion lets you contribute post-tax to a traditional IRA and convert to Roth, enabling tax-free growth.",
      savings: "Long-term benefit",
      selected: false,
    },
    {
      id: "estimated",
      category: "compliance",
      title: "Set up quarterly estimated payments",
      detail: "Based on your withholding, you may owe at year-end. Setting up quarterly estimated payments (Form 1040-ES) avoids underpayment penalties.",
      selected: true,
    },
    {
      id: "charitable",
      category: "deduction",
      title: "Bunch charitable donations",
      detail: "Consider bunching two years of charitable donations into one year to exceed the standard deduction threshold, then take the standard deduction the following year.",
      savings: "Up to $2,000/yr",
      selected: false,
    },
    {
      id: "529",
      category: "planning",
      title: "Open or fund 529 education plan",
      detail: dependents > 0
        ? `With ${dependents} dependent${dependents > 1 ? "s" : ""}, a 529 plan offers tax-free growth for education expenses. Some states offer a state tax deduction for contributions.`
        : "A 529 plan offers tax-free growth for education expenses. Even without dependents, you can name yourself or a future beneficiary.",
      savings: dependents > 0 ? "State deduction varies" : undefined,
      selected: dependents > 0,
    },
  ];

  if (filingStatus === "mfj") {
    items.push({
      id: "spouse-ira",
      category: "retirement",
      title: "Spousal IRA contribution",
      detail: "A non-working or lower-income spouse can contribute to an IRA based on the working spouse's income. This doubles your household retirement savings capacity.",
      savings: "Up to $7,000/yr",
      selected: false,
    });
  }

  if (filingStatus === "single" || filingStatus === "hoh") {
    items.push({
      id: "home-office",
      category: "deduction",
      title: "Home office deduction review",
      detail: "If you use part of your home exclusively for business, you may qualify for the home office deduction — $5/sq ft up to 300 sq ft ($1,500 max) using the simplified method.",
      savings: "Up to $1,500/yr",
      selected: false,
    });
  }

  items.push({
    id: "withholding",
    category: "compliance",
    title: "Review W-4 withholding",
    detail: "Based on this year's return, your withholding may be too high or too low. Adjusting your W-4 can optimize your paycheck and avoid a large refund or balance due.",
    selected: true,
  });

  items.push({
    id: "records",
    category: "compliance",
    title: "Organize records for next year",
    detail: "Start tracking deductible expenses now — medical expenses over 7.5% of AGI, charitable donations, business expenses, and investment losses for tax-loss harvesting.",
    selected: false,
  });

  return items;
}

export function AdvisoryPanel({ clientName = "Client", filingStatus = "single", dependents = 0 }: AdvisoryPanelProps) {
  const [items, setItems] = useState<AdvisoryItem[]>(() => getAdvisoryItems(filingStatus, dependents));
  const [sent, setSent] = useState(false);

  const toggleItem = (id: string) => {
    setItems((prev) => prev.map((item) => item.id === id ? { ...item, selected: !item.selected } : item));
  };

  const selectedCount = items.filter((i) => i.selected).length;

  const handleSend = () => {
    setSent(true);
  };

  if (sent) {
    return (
      <div className="space-y-4">
        <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">Tax Advisory</div>
        <div className="flex flex-col items-center py-8 text-center">
          <span className="w-10 h-10 rounded-full bg-green-500 text-white flex items-center justify-center text-[18px] mb-3">{"\u2713"}</span>
          <div className="text-[13px] font-medium text-primary mb-1">Advisory Sent</div>
          <div className="text-[11px] text-tertiary mb-4">
            {selectedCount} recommendation{selectedCount !== 1 ? "s" : ""} sent to {clientName}
          </div>
          <Button variant="ghost" onClick={() => setSent(false)} className="text-[12px]">
            Edit &amp; Resend
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">Tax Advisory</div>
          <div className="text-[11px] text-tertiary mt-0.5">Select items to include in client letter</div>
        </div>
        <span className="text-[10px] text-tertiary">{selectedCount} selected</span>
      </div>

      {/* Advisory items */}
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.id}
            onClick={() => toggleItem(item.id)}
            className={cn(
              "rounded-lg border p-2.5 cursor-pointer transition-all",
              item.selected
                ? "border-apple-blue/30 bg-apple-blue/5"
                : "border-divider hover:border-tertiary"
            )}
          >
            <div className="flex items-start gap-2">
              {/* Checkbox */}
              <input
                type="checkbox"
                checked={item.selected}
                onChange={() => toggleItem(item.id)}
                className="w-3.5 h-3.5 mt-0.5 accent-apple-blue cursor-pointer shrink-0"
              />
              <div className="flex-1 min-w-0">
                {/* Title row */}
                <div className="flex items-center gap-1.5">
                  <span className="text-[12px]">{categoryIcons[item.category]}</span>
                  <span className="text-[12px] font-medium text-primary">{item.title}</span>
                </div>
                {/* Category + savings */}
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[9px] font-medium px-1.5 py-px rounded-full bg-surface-tertiary text-secondary">
                    {categoryLabels[item.category]}
                  </span>
                  {item.savings && (
                    <span className="text-[10px] text-green-600 dark:text-green-400 font-medium">
                      {item.savings}
                    </span>
                  )}
                </div>
                {/* Detail */}
                <div className="text-[10px] text-tertiary mt-1 leading-relaxed">
                  {item.detail}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Send button */}
      <div className="flex justify-end pt-1">
        <Button
          variant="primary"
          onClick={handleSend}
          disabled={selectedCount === 0}
          className="text-[12px] px-4 py-1.5"
        >
          Send to {clientName} ({selectedCount})
        </Button>
      </div>
    </div>
  );
}
