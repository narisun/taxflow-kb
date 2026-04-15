"use client";

import { useState } from "react";
import { Modal, ModalHeader, ModalBody, ModalFooter } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { PdfViewer } from "@/components/documents/pdf-viewer";

interface DocumentData {
  id: number;
  form_type: string;
  title: string;
  status: string;
  confidence: number;
  extracted_data: string;
  flags: string;
}

interface DocumentViewerModalProps {
  open: boolean;
  onClose: () => void;
  document: DocumentData | null;
  onApprove?: (docId: number) => void;
}

function getDocUrl(docId: number | string): string {
  const apiBase = process.env.NEXT_PUBLIC_API_URL;
  if (apiBase) {
    return `${apiBase}/api/documents/${docId}/file`;
  }
  return "/sample-forms/fw2.pdf";
}

/* ── Full field definitions per form type ────────────────────────────────
   Each entry: [fieldKey, fieldNumber, fieldLabel]
   fieldNumber is the IRS box/line number (or "" for non-numbered fields).
   All fields are shown even if empty — CPAs need to see what's missing.
*/
type FieldDef = [string, string, string];

const FORM_FIELDS: Record<string, FieldDef[]> = {
  "W-2": [
    ["employer_name", "", "Employer Name"],
    ["employer_ein", "", "Employer EIN"],
    ["box1_wages", "1", "Wages, salaries, tips"],
    ["box2_fed_withheld", "2", "Federal income tax withheld"],
    ["box3_ss_wages", "3", "Social Security wages"],
    ["box4_ss_withheld", "4", "Social Security tax withheld"],
    ["box5_medicare_wages", "5", "Medicare wages and tips"],
    ["box6_medicare_withheld", "6", "Medicare tax withheld"],
    ["box15_state", "15", "State"],
    ["box16_state_wages", "16", "State wages, tips"],
    ["box17_state_withheld", "17", "State income tax"],
  ],
  "1099-INT": [
    ["payer", "", "Payer Name"],
    ["box1_interest", "1", "Interest income"],
    ["box4_fed_withheld", "4", "Federal income tax withheld"],
  ],
  "1099-DIV": [
    ["payer", "", "Payer Name"],
    ["box1a_ordinary_dividends", "1a", "Total ordinary dividends"],
    ["box1b_qualified_dividends", "1b", "Qualified dividends"],
    ["box2a_capital_gain_distributions", "2a", "Total capital gain distributions"],
  ],
  "1099-B": [
    ["payer", "", "Broker Name"],
    ["short_term_proceeds", "", "Short-term proceeds"],
    ["short_term_cost_basis", "", "Short-term cost basis"],
    ["long_term_proceeds", "", "Long-term proceeds"],
    ["long_term_cost_basis", "", "Long-term cost basis"],
  ],
  "1099-NEC": [
    ["payer", "", "Payer Name"],
    ["nec_compensation", "1", "Nonemployee compensation"],
    ["fed_tax_withheld", "4", "Federal income tax withheld"],
  ],
  "1098": [
    ["lender", "", "Lender Name"],
    ["box1_interest", "1", "Mortgage interest received"],
    ["box10_property_taxes", "10", "Property taxes"],
  ],
  "K-1": [
    ["entity_name", "", "Entity Name"],
    ["entity_ein", "", "Entity EIN"],
    ["entity_type", "", "Entity Type (P/S)"],
    ["box1_ordinary_income", "1", "Ordinary business income/loss"],
    ["box2_rental_income", "2", "Net rental real estate income/loss"],
    ["box4a_guaranteed_payments", "4a", "Guaranteed payments"],
    ["box14a_se_earnings", "14a", "Self-employment earnings"],
    ["box20z_section_199a_qbi", "20-Z", "Section 199A QBI"],
  ],
};

function formatFieldLabel(fieldNumber: string, fieldLabel: string): string {
  if (fieldNumber) {
    return `Box ${fieldNumber}. ${fieldLabel}`;
  }
  return fieldLabel;
}

function formatValue(val: unknown): string {
  if (val === null || val === undefined || val === "") return "\u2014"; // em dash for empty
  const s = String(val);
  // Format numeric values as currency
  const num = parseFloat(s);
  if (!isNaN(num) && s.match(/^\d+\.?\d*$/)) {
    return `$${num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return s;
}

export function DocumentViewerModal({
  open,
  onClose,
  document: doc,
  onApprove,
}: DocumentViewerModalProps) {
  const [editedFields, setEditedFields] = useState<Record<string, string>>({});

  if (!doc) return null;

  let parsedData: Record<string, unknown> = {};
  try {
    const raw = doc.extracted_data ? JSON.parse(doc.extracted_data) : {};
    parsedData = typeof raw === "object" && raw !== null && !Array.isArray(raw) ? raw : {};
  } catch {
    parsedData = {};
  }

  let parsedFlags: string[] = [];
  try {
    parsedFlags = doc.flags ? JSON.parse(doc.flags) : [];
  } catch {
    parsedFlags = doc.flags ? [doc.flags] : [];
  }

  const handleFieldEdit = (key: string, value: string) => {
    setEditedFields((prev) => ({ ...prev, [key]: value }));
  };

  const isFlagged = (key: string) =>
    parsedFlags.some((f) => f.toLowerCase().includes(key.toLowerCase().replace(/_/g, " ")));

  // Get field definitions for this form type, or build from extracted data
  const fieldDefs: FieldDef[] = FORM_FIELDS[doc.form_type] ||
    Object.keys(parsedData).map((key) => [key, "", key.replace(/_/g, " ")] as FieldDef);

  // Also include any extracted keys not in the field defs (unexpected fields from Claude)
  const definedKeys = new Set(fieldDefs.map(([key]) => key));
  const extraFields: FieldDef[] = Object.keys(parsedData)
    .filter((key) => !definedKeys.has(key))
    .map((key) => [key, "", key.replace(/_/g, " ")] as FieldDef);
  const allFields = [...fieldDefs, ...extraFields];

  return (
    <Modal open={open} onClose={onClose} className="max-w-7xl w-[95vw]">
      <ModalHeader onClose={onClose}>
        <div className="flex items-center gap-3">
          <span>{doc.title}</span>
          <Badge
            variant={doc.status === "verified" || doc.status === "approved" ? "completed" : doc.status === "flagged" || doc.status === "review" ? "review" : "pending"}
          >
            {doc.status}
          </Badge>
        </div>
      </ModalHeader>

      <ModalBody className="max-h-[80vh] p-0">
        <div className="grid grid-cols-[1fr_400px] max-md:grid-cols-1 h-full">
          {/* Left: PDF viewer — takes most space */}
          <div className="p-4 border-r border-divider max-md:border-r-0 max-md:border-b min-h-[60vh]">
            <PdfViewer src={getDocUrl(doc.id)} />
          </div>

          {/* Right: Extracted fields */}
          <div className="p-4 overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <div className="text-[13px] font-semibold text-primary">
                Extracted Fields
              </div>
              <div className="text-[11px] text-tertiary">
                {Object.keys(parsedData).length} of {allFields.length} fields
              </div>
            </div>

            <div className="space-y-1">
              {allFields.map(([key, fieldNumber, fieldLabel]) => {
                const value = parsedData[key];
                const hasValue = value !== null && value !== undefined && value !== "";
                const flagged = isFlagged(key);
                const fieldFlag = flagged
                  ? parsedFlags.find((f) => f.toLowerCase().includes(key.toLowerCase().replace(/_/g, " ")))
                  : null;

                return (
                  <div
                    key={key}
                    className={`rounded-md px-2.5 py-1.5 ${
                      flagged
                        ? "bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800"
                        : !hasValue
                          ? "bg-surface-secondary/50"
                          : "hover:bg-surface-secondary/50"
                    } transition-colors`}
                  >
                    {flagged ? (
                      <>
                        <div className="flex items-center gap-1.5 mb-1">
                          <span className="text-[10px] text-amber-600">&#9888;</span>
                          <span className="text-[11px] text-amber-700 dark:text-amber-400 font-medium">
                            {formatFieldLabel(fieldNumber, fieldLabel)}
                          </span>
                        </div>
                        <Input
                          value={editedFields[key] !== undefined ? editedFields[key] : formatValue(value)}
                          onChange={(e) => handleFieldEdit(key, e.target.value)}
                          validation="warning"
                          className="text-[13px]"
                        />
                        {fieldFlag && (
                          <div className="text-[10px] text-amber-600 mt-0.5 leading-tight">
                            {fieldFlag}
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="flex items-baseline justify-between gap-2">
                        <span className={`text-[11px] ${hasValue ? "text-secondary" : "text-tertiary"} shrink-0`}>
                          {formatFieldLabel(fieldNumber, fieldLabel)}
                        </span>
                        <span className={`text-[13px] font-medium text-right ${
                          hasValue ? "text-primary" : "text-tertiary/50"
                        }`}>
                          {hasValue ? formatValue(value) : "\u2014"}
                        </span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {parsedFlags.length > 0 && (
              <div className="mt-4 pt-3 border-t border-divider">
                <div className="text-[11px] font-semibold text-secondary mb-1.5">Flags</div>
                {parsedFlags.map((flag, i) => (
                  <div key={i} className="text-[11px] text-amber-600 dark:text-amber-400 flex items-start gap-1.5 mb-1">
                    <span>&#9888;</span>
                    <span>{flag}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </ModalBody>

      <ModalFooter>
        <div className="flex items-center gap-3 w-full">
          <div className="flex items-center gap-2 flex-1">
            <span className="text-[12px] text-secondary">AI Confidence:</span>
            <Progress
              value={doc.confidence}
              color={doc.confidence >= 90 ? "green" : doc.confidence >= 70 ? "orange" : "red"}
              className="w-24"
            />
            <span className="text-[12px] font-medium text-primary">{Math.round(doc.confidence * 100)}%</span>
          </div>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          {doc.status !== "approved" && (
            <Button
              variant="primary"
              onClick={() => {
                if (onApprove) onApprove(doc.id);
                onClose();
              }}
            >
              Approve
            </Button>
          )}
        </div>
      </ModalFooter>
    </Modal>
  );
}
