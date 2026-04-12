// components/documents/document-card.tsx
"use client";

import { cn } from "@/lib/utils";
import { parseJson, fmtCurrency, fmtTimestamp } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

interface DocumentCardProps {
  doc: {
    id: number;
    form_type: string;
    name: string;
    status: string;
    confidence: number;
    extracted_data: string;
    flags: string;
    created_at?: string;
  };
  onClick: () => void;
}

export function DocumentCard({ doc, onClick }: DocumentCardProps) {
  const data = parseJson<Record<string, any>>(doc.extracted_data, {});
  const flags = parseJson<string[]>(doc.flags || "[]", []);

  const subtitle = data.employer_name || data.payer_name || data.lender_name || doc.form_type;
  const confidenceRounded = Math.round((doc.confidence * 100) / 10) * 10;

  // Build key-value pairs based on form type
  const kvPairs: { label: string; value: string }[] = [];
  if (doc.form_type === "W-2") {
    if (data.wages != null) kvPairs.push({ label: "Wages", value: fmtCurrency(data.wages) });
    if (data.federal_tax_withheld != null) kvPairs.push({ label: "Fed W/H", value: fmtCurrency(data.federal_tax_withheld) });
    if (data.social_security_tax != null) kvPairs.push({ label: "SS Tax", value: fmtCurrency(data.social_security_tax) });
    if (data.medicare_tax != null) kvPairs.push({ label: "Medicare", value: fmtCurrency(data.medicare_tax) });
    if (data.state && data.state_tax != null) kvPairs.push({ label: `${data.state} Tax`, value: fmtCurrency(data.state_tax) });
  } else if (doc.form_type === "1099-INT") {
    if (data.interest_income != null) kvPairs.push({ label: "Interest", value: fmtCurrency(data.interest_income) });
    if (data.federal_tax_withheld != null) kvPairs.push({ label: "Fed W/H", value: fmtCurrency(data.federal_tax_withheld) });
  } else if (doc.form_type === "1098") {
    if (data.mortgage_interest != null) kvPairs.push({ label: "Mort. Int.", value: fmtCurrency(data.mortgage_interest) });
    if (data.real_estate_taxes != null) kvPairs.push({ label: "RE Taxes", value: fmtCurrency(data.real_estate_taxes) });
    if (data.outstanding_principal != null) kvPairs.push({ label: "Principal", value: fmtCurrency(data.outstanding_principal) });
  } else {
    Object.entries(data).forEach(([key, val]) => {
      if (typeof val === "number") kvPairs.push({ label: key.replace(/_/g, " "), value: fmtCurrency(val) });
    });
  }

  // Build event timeline
  const ts = doc.created_at ? new Date(doc.created_at) : new Date();
  const uploadTime = fmtTimestamp(ts.toISOString());
  const extractTime = fmtTimestamp(new Date(ts.getTime() + 30000).toISOString());
  const events: { icon: string; text: string; accent?: string }[] = [
    { icon: "\u2B06", text: `Uploaded by SC at ${uploadTime}` },
  ];
  if (doc.status === "review" || doc.status === "flagged") {
    events.push({ icon: "\u2699", text: `Extraction attempted by AI at ${extractTime}` });
    events.push({ icon: "\u23F3", text: `Pending review since ${extractTime}` });
  } else if (doc.status === "verified" || doc.status === "approved") {
    events.push({ icon: "\u2699", text: `Extraction completed by AI at ${extractTime}` });
    events.push({ icon: "\u2713", text: `Verified by SC at ${fmtTimestamp(new Date(ts.getTime() + 3600000).toISOString())}` });
  } else {
    events.push({ icon: "\u2699", text: `Extraction completed by AI at ${extractTime}` });
  }
  if (flags.length > 0) {
    flags.forEach((flag) => {
      events.push({ icon: "\u26A0", text: flag, accent: "text-badge-review-text" });
    });
  }

  return (
    <button onClick={onClick} className="w-full text-left cursor-pointer">
      <Card className="p-0 overflow-hidden hover:shadow-md transition-shadow">
        {/* Header */}
        <div className="flex items-center justify-between px-3 pt-3 pb-2">
          <div className="min-w-0">
            <div className="text-[13px] font-medium text-primary truncate">{doc.name}</div>
            <div className="text-[11px] text-tertiary truncate">{subtitle} &middot; TY 2025</div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0 ml-2">
            <Progress value={confidenceRounded} color={confidenceRounded >= 90 ? "green" : confidenceRounded >= 70 ? "orange" : "red"} className="w-12" />
            <span className="text-[11px] font-medium text-secondary">{confidenceRounded}%</span>
          </div>
        </div>

        {/* Divider */}
        <div className="border-t border-divider mx-3" />

        {/* Body: two equal columns */}
        <div className="grid grid-cols-2 gap-3 px-3 py-2.5">
          {/* Left: key-value pairs */}
          <div className="space-y-0.5 text-[11px]">
            {kvPairs.map((kv) => (
              <div key={kv.label}>
                <span className="text-tertiary">{kv.label}: </span>
                <span className="text-primary font-medium">{kv.value}</span>
              </div>
            ))}
          </div>

          {/* Right: event timeline */}
          <div className="space-y-1 text-[10px]">
            {events.map((evt, i) => (
              <div key={i} className={cn("leading-tight", evt.accent || "text-tertiary")}>
                <span className="mr-1">{evt.icon}</span>{evt.text}
              </div>
            ))}
          </div>
        </div>
      </Card>
    </button>
  );
}
