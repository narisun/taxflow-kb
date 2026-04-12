"use client";

import { cn } from "@/lib/utils";
import { Tabs } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useState } from "react";

interface Document {
  name: string;
  type: string;
  confidence: number;
  status: "verified" | "pending" | "missing";
}

interface TaxLine {
  line: string;
  label: string;
  value: string;
}

interface WorkPanelProps {
  documents?: Document[];
  missingDocs?: string[];
  taxLines?: TaxLine[];
  refundAmount?: string;
  filingStatus?: string;
  flagMessage?: string;
}

const defaultDocuments: Document[] = [
  { name: "W-2 (John)", type: "Income", confidence: 97, status: "verified" },
  { name: "W-2 (Jane)", type: "Income", confidence: 94, status: "verified" },
  { name: "1099-INT", type: "Interest", confidence: 88, status: "pending" },
  { name: "1098 Mortgage", type: "Deduction", confidence: 92, status: "verified" },
];

const defaultMissing = ["1099-DIV (Schwab)", "Childcare receipts"];

const defaultTaxLines: TaxLine[] = [
  { line: "1", label: "Wages, salaries, tips", value: "$142,500" },
  { line: "2b", label: "Taxable interest", value: "$1,230" },
  { line: "8", label: "Other income", value: "$0" },
  { line: "9", label: "Total income", value: "$143,730" },
  { line: "11", label: "Adjusted gross income", value: "$131,230" },
  { line: "15", label: "Taxable income", value: "$103,730" },
  { line: "24", label: "Total tax", value: "$17,412" },
  { line: "34", label: "Overpayment / Refund", value: "$3,288" },
];

function WorkPanel({
  documents = defaultDocuments,
  missingDocs = defaultMissing,
  taxLines = defaultTaxLines,
  refundAmount = "$3,288",
  filingStatus = "Submitted 04/10/2026",
  flagMessage = "2 documents need review before filing",
}: WorkPanelProps) {
  const [activeTab, setActiveTab] = useState("Documents");

  return (
    <aside className="w-96 shrink-0 bg-white border-l border-gray-200 flex flex-col overflow-hidden">
      <Tabs
        tabs={["Documents", "Tax Return", "Filed"]}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        className="px-2 pt-1"
      />

      <div className="flex-1 overflow-y-auto p-3">
        {activeTab === "Documents" && (
          <DocumentsTab
            documents={documents}
            missingDocs={missingDocs}
            flagMessage={flagMessage}
          />
        )}
        {activeTab === "Tax Return" && (
          <TaxReturnTab taxLines={taxLines} refundAmount={refundAmount} />
        )}
        {activeTab === "Filed" && <FiledTab status={filingStatus} />}
      </div>
    </aside>
  );
}

function DocumentsTab({
  documents,
  missingDocs,
  flagMessage,
}: {
  documents: Document[];
  missingDocs: string[];
  flagMessage: string;
}) {
  return (
    <div className="space-y-3">
      {/* Flag banner */}
      {flagMessage && (
        <div className="bg-orange-50 text-orange-700 text-[12px] px-3 py-2 rounded-lg">
          &#9888; {flagMessage}
        </div>
      )}

      {/* Document cards */}
      {documents.map((doc) => (
        <Card key={doc.name} className="p-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[13px] font-medium text-[#1d1d1f]">{doc.name}</span>
            <Badge
              variant={
                doc.status === "verified"
                  ? "completed"
                  : doc.status === "pending"
                    ? "pending"
                    : "review"
              }
            >
              {doc.status}
            </Badge>
          </div>
          <div className="text-[11px] text-gray-500 mb-1.5">{doc.type}</div>
          <div className="flex items-center gap-2">
            <Progress value={doc.confidence} className="flex-1" />
            <span className="text-[10px] text-gray-400 w-8 text-right">{doc.confidence}%</span>
          </div>
        </Card>
      ))}

      {/* Missing docs */}
      {missingDocs.length > 0 && (
        <div>
          <div className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Possibly Missing
          </div>
          {missingDocs.map((doc) => (
            <div
              key={doc}
              className="flex items-center gap-2 py-1.5 px-2 text-[12px] text-gray-600 bg-gray-50 rounded-lg mb-1 border border-dashed border-gray-200"
            >
              <span className="text-gray-400">&#9679;</span>
              <span>{doc}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TaxReturnTab({
  taxLines,
  refundAmount,
}: {
  taxLines: TaxLine[];
  refundAmount: string;
}) {
  return (
    <div className="space-y-3">
      <div className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
        Form 1040 Preview
      </div>

      <div className="space-y-0.5">
        {taxLines.map((line) => (
          <div
            key={line.line}
            className={cn(
              "flex items-center justify-between py-1.5 px-2 rounded text-[12px]",
              line.line === "34" ? "bg-green-50 font-semibold text-green-700" : "text-[#1d1d1f]"
            )}
          >
            <div className="flex items-center gap-2">
              <span className="text-gray-400 w-6 text-right">{line.line}</span>
              <span>{line.label}</span>
            </div>
            <span className="font-medium">{line.value}</span>
          </div>
        ))}
      </div>

      {/* Refund summary */}
      <Card className="text-center">
        <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">
          Estimated Refund
        </div>
        <div className="text-[28px] font-semibold text-green-600">{refundAmount}</div>
      </Card>
    </div>
  );
}

function FiledTab({ status }: { status: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-64 text-center">
      <div className="w-12 h-12 rounded-full bg-green-100 text-green-600 flex items-center justify-center text-[24px] mb-3">
        &#10003;
      </div>
      <div className="text-[15px] font-semibold text-[#1d1d1f] mb-1">Return Filed</div>
      <div className="text-[12px] text-gray-500">{status}</div>
      <Badge variant="filed" className="mt-3">
        E-Filed
      </Badge>
    </div>
  );
}

export { WorkPanel, type WorkPanelProps };
