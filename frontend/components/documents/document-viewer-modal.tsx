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
   Each entry: [fieldKey, fieldNumber, fieldLabel, valueType]
   - fieldNumber: IRS box/line number ("" for non-numbered fields)
   - valueType: "money" | "text" | "ein" | "ssn" | "id" | "state"
   All fields shown even if empty — CPAs need to see what's missing.
*/
type ValueType = "money" | "text" | "ein" | "ssn" | "id" | "state";
type FieldDef = [string, string, string, ValueType];

const FORM_FIELDS: Record<string, FieldDef[]> = {
  "W-2": [
    ["employee_ssn", "a", "Employee SSN", "ssn"],
    ["employer_ein", "b", "Employer EIN", "ein"],
    ["employer_name", "c", "Employer Name", "text"],
    ["employer_address", "c", "Employer Address", "text"],
    ["control_number", "d", "Control Number", "id"],
    ["employee_name", "e", "Employee Name", "text"],
    ["employee_address", "f", "Employee Address", "text"],
    ["box1_wages", "1", "Wages, salaries, tips", "money"],
    ["box2_fed_withheld", "2", "Federal income tax withheld", "money"],
    ["box3_ss_wages", "3", "Social Security wages", "money"],
    ["box4_ss_withheld", "4", "Social Security tax withheld", "money"],
    ["box5_medicare_wages", "5", "Medicare wages and tips", "money"],
    ["box6_medicare_withheld", "6", "Medicare tax withheld", "money"],
    ["box7_ss_tips", "7", "Social Security tips", "money"],
    ["box8_allocated_tips", "8", "Allocated tips", "money"],
    ["box10_dependent_care", "10", "Dependent care benefits", "money"],
    ["box11_nonqualified_plans", "11", "Nonqualified plans", "money"],
    ["box12a", "12a", "Code 12a", "text"],
    ["box12b", "12b", "Code 12b", "text"],
    ["box12c", "12c", "Code 12c", "text"],
    ["box12d", "12d", "Code 12d", "text"],
    ["box13_statutory", "13", "Statutory employee / Retirement / Third-party sick pay", "text"],
    ["box14a_other", "14a", "Other", "text"],
    ["box15_state", "15", "State", "state"],
    ["box15_state_ein", "15", "State Employer ID", "id"],
    ["box16_state_wages", "16", "State wages, tips", "money"],
    ["box17_state_withheld", "17", "State income tax", "money"],
    ["box18_local_wages", "18", "Local wages, tips", "money"],
    ["box19_local_tax", "19", "Local income tax", "money"],
    ["box20_locality_name", "20", "Locality name", "text"],
  ],
  "1099-INT": [
    ["payer", "", "Payer Name", "text"],
    ["box1_interest", "1", "Interest income", "money"],
    ["box2_early_withdrawal_penalty", "2", "Early withdrawal penalty", "money"],
    ["box3_savings_bond_interest", "3", "Interest on U.S. Savings Bonds", "money"],
    ["box4_fed_withheld", "4", "Federal income tax withheld", "money"],
    ["box5_investment_expenses", "5", "Investment expenses", "money"],
    ["box6_foreign_tax", "6", "Foreign tax paid", "money"],
    ["box8_tax_exempt_interest", "8", "Tax-exempt interest", "money"],
  ],
  "1099-DIV": [
    ["payer", "", "Payer Name", "text"],
    ["box1a_ordinary_dividends", "1a", "Total ordinary dividends", "money"],
    ["box1b_qualified_dividends", "1b", "Qualified dividends", "money"],
    ["box2a_capital_gain_distributions", "2a", "Total capital gain distributions", "money"],
    ["box4_fed_withheld", "4", "Federal income tax withheld", "money"],
    ["box5_section_199a", "5", "Section 199A dividends", "money"],
    ["box7_foreign_tax_paid", "7", "Foreign tax paid", "money"],
  ],
  "1099-B": [
    ["payer", "", "Broker Name", "text"],
    ["short_term_proceeds", "", "Short-term proceeds", "money"],
    ["short_term_cost_basis", "", "Short-term cost basis", "money"],
    ["long_term_proceeds", "", "Long-term proceeds", "money"],
    ["long_term_cost_basis", "", "Long-term cost basis", "money"],
    ["box4_fed_withheld", "4", "Federal income tax withheld", "money"],
  ],
  "1099-NEC": [
    ["payer", "", "Payer Name", "text"],
    ["nec_compensation", "1", "Nonemployee compensation", "money"],
    ["fed_tax_withheld", "4", "Federal income tax withheld", "money"],
  ],
  "1098": [
    ["lender", "", "Lender Name", "text"],
    ["box1_interest", "1", "Mortgage interest received", "money"],
    ["box2_outstanding_principal", "2", "Outstanding mortgage principal", "money"],
    ["box5_mortgage_insurance", "5", "Mortgage insurance premiums", "money"],
    ["box6_points_paid", "6", "Points paid on purchase", "money"],
    ["box7_property_address", "7", "Property address", "text"],
    ["box10_property_taxes", "10", "Property taxes", "money"],
  ],
  "K-1": [
    ["entity_name", "", "Entity Name", "text"],
    ["entity_ein", "", "Entity EIN", "ein"],
    ["entity_type", "", "Entity Type (P/S)", "text"],
    ["box1_ordinary_income", "1", "Ordinary business income/loss", "money"],
    ["box2_rental_income", "2", "Net rental real estate income/loss", "money"],
    ["box4a_guaranteed_payments", "4a", "Guaranteed payments", "money"],
    ["box14a_se_earnings", "14a", "Self-employment earnings", "money"],
    ["box20z_section_199a_qbi", "20-Z", "Section 199A QBI", "money"],
  ],
};

function formatFieldLabel(fieldNumber: string, fieldLabel: string): string {
  if (fieldNumber) {
    return `Box ${fieldNumber}. ${fieldLabel}`;
  }
  return fieldLabel;
}

function formatValue(val: unknown, valueType: ValueType = "text"): string {
  if (val === null || val === undefined || val === "") return "\u2014";
  const s = String(val);

  switch (valueType) {
    case "money": {
      const num = parseFloat(s.replace(/,/g, ""));
      if (!isNaN(num)) {
        return `$${num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
      }
      return s;
    }
    case "ssn":
      // Show masked: ***-**-1234
      if (s.length >= 4) {
        const last4 = s.replace(/-/g, "").slice(-4);
        return `***-**-${last4}`;
      }
      return s;
    case "ein":
      // Show as-is (XX-XXXXXXX format)
      return s;
    case "id":
    case "state":
    case "text":
    default:
      return s;
  }
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
    Object.keys(parsedData).map((key) => [key, "", key.replace(/_/g, " "), "text"] as FieldDef);

  // Also include any extracted keys not in the field defs (unexpected fields)
  const definedKeys = new Set(fieldDefs.map(([key]) => key));
  const extraFields: FieldDef[] = Object.keys(parsedData)
    .filter((key) => !definedKeys.has(key))
    .map((key) => [key, "", key.replace(/_/g, " "), "text"] as FieldDef);
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

      <ModalBody className="h-[80vh] p-0 overflow-hidden">
        <div className="grid grid-cols-[1fr_380px] max-md:grid-cols-1 h-full">
          {/* Left: PDF viewer — independently scrollable, full height */}
          <div className="p-4 border-r border-divider max-md:border-r-0 max-md:border-b overflow-y-auto">
            <PdfViewer src={getDocUrl(doc.id)} />
          </div>

          {/* Right: Extracted fields — independently scrollable */}
          <div className="p-3 overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <div className="text-[13px] font-semibold text-primary">
                Extracted Fields
              </div>
              <div className="text-[11px] text-tertiary">
                {Object.keys(parsedData).length} of {allFields.length} fields
              </div>
            </div>

            <div className="space-y-1">
              {allFields.map(([key, fieldNumber, fieldLabel, valueType]) => {
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
                          value={editedFields[key] !== undefined ? editedFields[key] : formatValue(value, valueType)}
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
                          {hasValue ? formatValue(value, valueType) : "\u2014"}
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
        <div className="flex items-center gap-2 w-full">
          <div className="flex items-center gap-2 flex-1">
            <span className="text-[11px] text-secondary">Confidence:</span>
            <Progress
              value={doc.confidence}
              color={doc.confidence >= 90 ? "green" : doc.confidence >= 70 ? "orange" : "red"}
              className="w-20"
            />
            <span className="text-[11px] font-medium text-primary">{Math.round(doc.confidence * 100)}%</span>
          </div>
          <Button variant="secondary" onClick={onClose} className="text-[12px] px-3 py-1.5 h-auto">
            Close
          </Button>
          {doc.status !== "approved" && (
            <Button
              variant="primary"
              className="text-[12px] px-3 py-1.5 h-auto"
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
