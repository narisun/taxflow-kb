"use client";

import { useState } from "react";
import { cn, fmtCurrency } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { api, type AdvisoryItem } from "@/lib/api-client";

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
  clientId?: string | null;
  clientName?: string;
  filingStatus?: string;
  dependents?: number;
}

interface UIItem extends AdvisoryItem {
  selected: boolean;
}

function parseSavings(v: string | number | null | undefined): number {
  if (v == null) return 0;
  const n = typeof v === "number" ? v : parseFloat(v);
  return isNaN(n) ? 0 : n;
}

export function AdvisoryPanel({ clientId, clientName = "Client" }: AdvisoryPanelProps) {
  const [items, setItems] = useState<UIItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generated, setGenerated] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleGenerate = async () => {
    if (!clientId) {
      setError("Select a client first.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await api.returns.advisory(clientId);
      setItems(data.map((it) => ({ ...it, selected: it.selected ?? true })));
      setGenerated(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate advisory");
    } finally {
      setLoading(false);
    }
  };

  const toggleItem = (id: string) => {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, selected: !item.selected } : item)));
  };

  const selectedItems = items.filter((i) => i.selected);
  const selectedCount = selectedItems.length;

  const totalSavings = selectedItems.reduce((sum, it) => sum + parseSavings(it.estimated_savings), 0);

  const buildAdvisoryText = (): string => {
    const lines: string[] = [`Tax Advisory for ${clientName}`, ""];
    selectedItems.forEach((it, idx) => {
      lines.push(`${idx + 1}. ${it.title} [${categoryLabels[it.category] || it.category}]`);
      if (it.savings) lines.push(`   Estimated savings: ${it.savings}`);
      lines.push(`   ${it.detail}`);
      lines.push("");
    });
    if (totalSavings > 0) {
      lines.push(`Total estimated savings: ${fmtCurrency(Math.round(totalSavings))}`);
    }
    return lines.join("\n");
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(buildAdvisoryText());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Could not copy to clipboard");
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 gap-2">
        <div className="min-w-0">
          <div className="text-[12px] font-semibold text-secondary tracking-wide">Tax Advisory</div>
          <div className="text-[11px] text-tertiary mt-0.5 truncate">
            {generated
              ? `${items.length} recommendation${items.length !== 1 ? "s" : ""} sorted by priority`
              : "Generate AI-prioritized recommendations"}
          </div>
        </div>
        <Button
          variant="pill"
          onClick={handleGenerate}
          disabled={loading || !clientId}
          title={!clientId ? "Select a client to generate advisory" : undefined}
          className="text-[11px] px-3 py-1 shrink-0"
        >
          {loading ? "Generating\u2026" : generated ? "Refresh" : "Create Advisory"}
        </Button>
      </div>

      {/* Selected summary chip */}
      {generated && items.length > 0 && (
        <div className="flex items-center justify-between gap-2 px-2.5 py-1.5 mb-2 rounded-md bg-apple-blue/5 border border-apple-blue/20">
          <span className="text-[11px] text-secondary">
            <span className="font-medium text-primary">{selectedCount}</span> of {items.length} selected
          </span>
          {totalSavings > 0 && (
            <span className="text-[11px] text-brand-green font-medium">
              ~{fmtCurrency(Math.round(totalSavings))} savings
            </span>
          )}
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {error && (
          <div className="text-[11px] text-red-600 dark:text-red-400 px-2.5 py-2 rounded bg-red-50 dark:bg-red-950/30 mb-2">
            {error}
          </div>
        )}

        {!generated && !loading && !error && (
          <div className="flex flex-col items-center justify-center text-center py-10 px-4 text-tertiary">
            <span className="text-[28px] mb-2">{"\u{1F4A1}"}</span>
            <div className="text-[12px] text-secondary font-medium mb-1">No advisory yet</div>
            <div className="text-[11px] mb-4">
              Click <span className="text-primary font-medium">Create Advisory</span> to analyze this return
              and surface the highest-impact tax-saving opportunities.
            </div>
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center text-center py-10 text-tertiary">
            <div className="w-6 h-6 border-2 border-apple-blue border-t-transparent rounded-full animate-spin mb-2" />
            <div className="text-[11px]">Analyzing return&hellip;</div>
          </div>
        )}

        {generated && items.length === 0 && !loading && (
          <div className="text-center py-10 text-tertiary text-[11px]">
            No advisory recommendations were generated. Try after the draft return is fully computed.
          </div>
        )}

        <div className="space-y-2">
          {items.map((item, idx) => (
            <div
              key={item.id}
              onClick={() => toggleItem(item.id)}
              className={cn(
                "rounded-lg border p-2.5 cursor-pointer transition-all",
                item.selected
                  ? "border-apple-blue/30 bg-apple-blue/5"
                  : "border-divider bg-surface-secondary/50 opacity-70 hover:opacity-90 hover:border-tertiary"
              )}
            >
              <div className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={item.selected}
                  onChange={() => toggleItem(item.id)}
                  onClick={(e) => e.stopPropagation()}
                  className="w-3.5 h-3.5 mt-0.5 accent-apple-blue cursor-pointer shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-mono text-tertiary w-4 shrink-0">#{idx + 1}</span>
                    <span className="text-[12px]">{categoryIcons[item.category]}</span>
                    <span
                      className={cn(
                        "text-[12px] font-medium",
                        item.selected ? "text-primary" : "text-secondary"
                      )}
                    >
                      {item.title}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5 ml-6">
                    <span className="text-[9px] font-medium px-1.5 py-px rounded-full bg-surface-tertiary text-secondary">
                      {categoryLabels[item.category] || item.category}
                    </span>
                    {item.savings && (
                      <span className="text-[10px] text-brand-green font-medium">
                        {item.savings}
                      </span>
                    )}
                  </div>
                  <div
                    className={cn(
                      "text-[10px] mt-1 ml-6 leading-relaxed",
                      item.selected ? "text-tertiary" : "text-tertiary/70"
                    )}
                  >
                    {item.detail}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Sticky footer — share actions */}
      {generated && items.length > 0 && (
        <div className="shrink-0 pt-3 mt-2 border-t border-divider flex gap-2">
          <Button
            variant="pill"
            onClick={handleCopy}
            disabled={selectedCount === 0}
            title={selectedCount === 0 ? "Select at least one advisory item to copy" : undefined}
            className="flex-1 text-[11px] py-1.5"
          >
            {copied ? "\u2713 Copied" : `Copy summary (${selectedCount})`}
          </Button>
          <Button
            variant="ghost"
            onClick={handleGenerate}
            disabled={loading}
            className="text-[11px]"
            title="Re-run analysis"
          >
            {"\u21BB"}
          </Button>
        </div>
      )}
    </div>
  );
}
