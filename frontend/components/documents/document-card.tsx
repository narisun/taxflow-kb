// components/documents/document-card.tsx
"use client";

import { cn } from "@/lib/utils";
import { parseJson, fmtCurrency, fmtTimestamp } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

interface DocumentCardProps {
  doc: {
    id: string;
    form_type: string;
    name: string;
    status: string;
    confidence: number;
    extracted_data: string;
    flags: string;
    created_at?: string;
  };
  onClick: () => void;
  onDelete?: (docId: string) => void;
  isDuplicate?: boolean;
}

// Maps form_type → list of [extractedKey, displayLabel, isMoney]
const FORM_KEY_FIELDS: Record<string, [string, string, boolean][]> = {
  "W-2": [
    ["employer_name", "Employer", false],
    ["box1_wages", "Wages", true],
    ["box2_fed_withheld", "Fed W/H", true],
    ["box3_ss_wages", "SS Wages", true],
    ["box5_medicare_wages", "Medicare", true],
    ["box15_state", "State", false],
    ["box17_state_withheld", "State Tax", true],
  ],
  "1099-INT": [
    ["payer", "Payer", false],
    ["box1_interest", "Interest", true],
    ["box4_fed_withheld", "Fed W/H", true],
  ],
  "1099-DIV": [
    ["payer", "Payer", false],
    ["box1a_ordinary_dividends", "Ordinary Div", true],
    ["box1b_qualified_dividends", "Qualified Div", true],
    ["box2a_capital_gain_distributions", "Cap Gains", true],
  ],
  "1099-NEC": [
    ["payer", "Payer", false],
    ["nec_compensation", "Compensation", true],
    ["fed_tax_withheld", "Fed W/H", true],
  ],
  "1099-B": [
    ["payer", "Broker", false],
    ["short_term_proceeds", "ST Proceeds", true],
    ["long_term_proceeds", "LT Proceeds", true],
  ],
  "1098": [
    ["lender", "Lender", false],
    ["box1_interest", "Mort. Interest", true],
    ["box10_property_taxes", "Prop. Tax", true],
  ],
  "K-1": [
    ["entity_name", "Entity", false],
    ["entity_type", "Type", false],
    ["box1_ordinary_income", "Ord. Income", true],
  ],
};

export function DocumentCard({ doc, onClick, onDelete, isDuplicate }: DocumentCardProps) {
  const data = parseJson<Record<string, any>>(doc.extracted_data, {});
  const flags = parseJson<string[]>(doc.flags || "[]", []);

  const confidencePercent = Math.round(doc.confidence * 100);

  // Get key fields for this form type
  const keyFields = FORM_KEY_FIELDS[doc.form_type] || [];
  const kvPairs: { label: string; value: string }[] = [];
  for (const [key, label, isMoney] of keyFields) {
    const val = data[key];
    if (val != null && val !== "" && val !== "0.00") {
      if (isMoney) {
        const num = parseFloat(String(val).replace(/,/g, ""));
        kvPairs.push({ label, value: isNaN(num) ? String(val) : fmtCurrency(num) });
      } else {
        kvPairs.push({ label, value: String(val) });
      }
    }
  }
  // For unknown form types, show first few non-empty fields
  if (kvPairs.length === 0 && Object.keys(data).length > 0) {
    Object.entries(data).slice(0, 4).forEach(([key, val]) => {
      if (val != null && val !== "") {
        const label = key.replace(/_/g, " ").replace(/^box\d+_?/, "");
        kvPairs.push({ label: label.slice(0, 15), value: String(val).slice(0, 20) });
      }
    });
  }

  // Build timeline
  const ts = doc.created_at ? new Date(doc.created_at) : new Date();
  const events: { icon: string; text: string; accent?: string }[] = [
    { icon: "\u2B06", text: `Uploaded ${fmtTimestamp(ts.toISOString())}` },
  ];
  if (doc.status === "review" || doc.status === "flagged") {
    events.push({ icon: "\u23F3", text: "Needs Review" });
  } else if (doc.status === "verified") {
    events.push({ icon: "\u2713", text: "Verified" });
  } else if (doc.status === "approved") {
    const approvedAt = doc.reviewed_at ? fmtTimestamp(doc.reviewed_at) : "";
    events.push({ icon: "\u2713", text: approvedAt ? `Approved ${approvedAt}` : "Approved" });
  }
  if (flags.length > 0) {
    flags.forEach((flag) => {
      events.push({ icon: "\u26A0", text: flag.slice(0, 60), accent: "text-amber-600 dark:text-amber-400" });
    });
  }

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDelete && confirm("Delete this document? This cannot be undone.")) {
      onDelete(doc.id);
    }
  };

  return (
    <div onClick={onClick} role="button" tabIndex={0} className="w-full text-left cursor-pointer group">
      <Card className="p-0 overflow-hidden hover:shadow-md transition-shadow">
        {/* Header */}
        <div className="flex items-center justify-between px-3 pt-2.5 pb-1.5">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-medium text-primary truncate">{doc.name}</span>
              {isDuplicate && (
                <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 shrink-0">
                  Possible Duplicate
                </span>
              )}
            </div>
            <div className="text-[11px] text-tertiary truncate">
              {data.employer_name || data.payer || data.lender || data.entity_name || doc.form_type}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0 ml-2">
            <div className="flex items-center gap-1">
              <Progress
                value={confidencePercent}
                color={confidencePercent >= 90 ? "green" : confidencePercent >= 70 ? "orange" : "red"}
                className="w-10"
              />
              <span className="text-[10px] font-medium text-secondary">{confidencePercent}%</span>
            </div>
            {onDelete && (
              <button
                onClick={handleDelete}
                className="w-6 h-6 rounded flex items-center justify-center text-tertiary hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 opacity-0 group-hover:opacity-100 transition-all"
                title="Delete document"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14"/>
                </svg>
              </button>
            )}
          </div>
        </div>

        {/* Divider */}
        <div className="border-t border-divider mx-3" />

        {/* Body: two columns */}
        <div className="grid grid-cols-[1fr_auto] gap-3 px-3 py-2">
          {/* Left: key data points */}
          <div className="space-y-0.5 text-[11px] min-w-0">
            {kvPairs.slice(0, 5).map((kv) => (
              <div key={kv.label} className="flex items-baseline justify-between gap-1">
                <span className="text-tertiary shrink-0">{kv.label}</span>
                <span className="text-primary font-medium truncate text-right">{kv.value}</span>
              </div>
            ))}
            {kvPairs.length === 0 && (
              <div className="text-tertiary italic">No data extracted</div>
            )}
          </div>

          {/* Right: timeline */}
          <div className="space-y-0.5 text-[10px] max-w-[160px]">
            {events.map((evt, i) => (
              <div key={i} className={cn("leading-tight", evt.accent || "text-tertiary")}>
                <span className="mr-0.5">{evt.icon}</span>{evt.text}
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}
