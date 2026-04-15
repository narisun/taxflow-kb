"use client";

import { useState, useCallback, useRef } from "react";
import { Modal, ModalHeader, ModalBody } from "@/components/ui/modal";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { PdfViewer } from "@/components/documents/pdf-viewer";
import { parseJson, fmtCurrency } from "@/lib/utils";

interface DocItem {
  id: number;
  form_type: string;
  title: string;
  name?: string;
  status: string;
  confidence: number;
  extracted_data: string;
  flags: string;
  created_at?: string;
}

interface ClientInfo {
  name: string;
  filing_status: string;
  tax_year: number;
  dependents: number;
  primary_ssn_masked?: string;
  spouse_first_name?: string;
  spouse_last_name?: string;
  city?: string;
  state?: string;
}

interface Dependent {
  id: number;
  first_name: string;
  last_name: string;
  relationship: string;
  ssn_masked?: string;
}

interface UploadingFile {
  id: string;
  name: string;
  formType: string;
  status: "uploading" | "extracting" | "done" | "error";
  error?: string;
}

interface DocumentManagerModalProps {
  open: boolean;
  onClose: () => void;
  client: ClientInfo | null;
  dependents: Dependent[];
  documents: DocItem[];
  onUpload: (files: File[]) => Promise<void>;
  onDelete: (docId: number) => Promise<void>;
  onApprove: (docId: number) => Promise<void>;
  onViewDoc: (doc: DocItem) => void;
}

// Form type field definitions for inline review (same as document-viewer-modal)
type ValueType = "money" | "text" | "ein" | "ssn" | "id" | "state";
type FieldDef = [string, string, string, ValueType];

const FORM_FIELDS: Record<string, FieldDef[]> = {
  "W-2": [
    ["employee_ssn", "a", "Employee SSN", "ssn"],
    ["employer_ein", "b", "Employer EIN", "ein"],
    ["employer_name", "c", "Employer Name", "text"],
    ["employee_name", "e", "Employee Name", "text"],
    ["box1_wages", "1", "Wages, salaries, tips", "money"],
    ["box2_fed_withheld", "2", "Fed income tax withheld", "money"],
    ["box3_ss_wages", "3", "Social Security wages", "money"],
    ["box5_medicare_wages", "5", "Medicare wages", "money"],
    ["box15_state", "15", "State", "state"],
    ["box16_state_wages", "16", "State wages", "money"],
    ["box17_state_withheld", "17", "State income tax", "money"],
  ],
  "1099-INT": [
    ["payer", "", "Payer", "text"],
    ["box1_interest", "1", "Interest income", "money"],
    ["box4_fed_withheld", "4", "Fed tax withheld", "money"],
  ],
  "1099-DIV": [
    ["payer", "", "Payer", "text"],
    ["box1a_ordinary_dividends", "1a", "Ordinary dividends", "money"],
    ["box1b_qualified_dividends", "1b", "Qualified dividends", "money"],
  ],
  "1099-NEC": [
    ["payer", "", "Payer", "text"],
    ["nec_compensation", "1", "Compensation", "money"],
  ],
  "1098": [
    ["lender", "", "Lender", "text"],
    ["box1_interest", "1", "Mortgage interest", "money"],
    ["box10_property_taxes", "10", "Property taxes", "money"],
  ],
};

function formatValue(val: unknown, type: ValueType): string {
  if (val === null || val === undefined || val === "") return "\u2014";
  const s = String(val);
  if (type === "money") {
    const n = parseFloat(s.replace(/,/g, ""));
    return isNaN(n) ? s : `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (type === "ssn" && s.length >= 4) return `***-**-${s.replace(/-/g, "").slice(-4)}`;
  return s;
}

function detectFormType(filename: string): string {
  const f = filename.toLowerCase();
  if (f.includes("w2") || f.includes("w-2")) return "W-2";
  if (f.includes("1099-int") || f.includes("1099int")) return "1099-INT";
  if (f.includes("1099-nec") || f.includes("1099nec")) return "1099-NEC";
  if (f.includes("1099-div") || f.includes("1099div")) return "1099-DIV";
  if (f.includes("1099-b") || f.includes("1099b")) return "1099-B";
  if (f.includes("1099")) return "1099";
  if (f.includes("1098")) return "1098";
  if (f.includes("k-1") || f.includes("k1")) return "K-1";
  return "Other";
}

function getDocUrl(docId: number): string {
  const apiBase = process.env.NEXT_PUBLIC_API_URL;
  return apiBase ? `${apiBase}/api/documents/${docId}/file` : "/sample-forms/fw2.pdf";
}

function getStatusVariant(status: string): "completed" | "review" | "pending" {
  if (status === "approved" || status === "verified") return "completed";
  if (status === "review" || status === "flagged") return "review";
  return "pending";
}

const filingLabels: Record<string, string> = {
  single: "Single", mfj: "MFJ", mfs: "MFS", hoh: "HOH", qw: "QSS",
  S: "Single", MFJ: "MFJ", MFS: "MFS", HOH: "HOH", QSS: "QSS",
};

export function DocumentManagerModal({
  open, onClose, client, dependents, documents,
  onUpload, onDelete, onApprove, onViewDoc,
}: DocumentManagerModalProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([]);
  const [expandedDocId, setExpandedDocId] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(async (files: File[]) => {
    const validFiles = files.filter(f => f.type === "application/pdf" || f.type.startsWith("image/"));
    if (!validFiles.length) return;

    // Show uploading state
    const newUploads: UploadingFile[] = validFiles.map((f, i) => ({
      id: `${Date.now()}-${i}`,
      name: f.name,
      formType: detectFormType(f.name),
      status: "uploading" as const,
    }));
    setUploadingFiles(newUploads);

    // Upload (the parent handles actual API calls)
    await onUpload(validFiles);

    // Mark all as done after parent refreshes
    setUploadingFiles(prev => prev.map(u => ({ ...u, status: "done" as const })));
    // Clear after a delay
    setTimeout(() => setUploadingFiles([]), 2000);
  }, [onUpload]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(Array.from(e.dataTransfer.files));
  }, [handleFiles]);

  const handleDeleteDoc = async (e: React.MouseEvent, docId: number) => {
    e.stopPropagation();
    if (confirm("Delete this document?")) {
      if (expandedDocId === docId) setExpandedDocId(null);
      await onDelete(docId);
    }
  };

  if (!client) return null;

  const approved = documents.filter(d => d.status === "approved" || d.status === "verified").length;
  const needsReview = documents.filter(d => d.status === "review" || d.status === "flagged").length;

  // Duplicate detection
  const dupeIds = new Set<number>();
  for (let i = 0; i < documents.length; i++) {
    for (let j = i + 1; j < documents.length; j++) {
      if (documents[i].form_type === documents[j].form_type &&
          documents[i].extracted_data === documents[j].extracted_data &&
          documents[i].extracted_data !== "{}") {
        dupeIds.add(documents[i].id);
        dupeIds.add(documents[j].id);
      }
    }
  }

  return (
    <Modal open={open} onClose={onClose} className="max-w-6xl w-[92vw]">
      <ModalHeader onClose={onClose}>Document Manager</ModalHeader>

      <ModalBody className="h-[78vh] p-0 overflow-hidden flex flex-col">
        {/* Client info bar — compact */}
        <div className="px-4 py-2.5 bg-surface-secondary/40 border-b border-divider shrink-0 flex items-center justify-between">
          <div className="flex items-center gap-3 text-[12px]">
            <span className="font-semibold text-primary">{client.name}</span>
            <span className="text-secondary">{filingLabels[client.filing_status] || client.filing_status}</span>
            <span className="text-tertiary">TY {client.tax_year}</span>
            {client.spouse_first_name && (
              <span className="text-secondary">Spouse: {client.spouse_first_name}</span>
            )}
            {dependents.length > 0 && (
              <span className="text-secondary">
                {dependents.map(d => d.first_name).join(", ")} ({dependents.length} dep.)
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 text-[11px]">
            <span className="text-secondary">{documents.length} docs</span>
            {approved > 0 && <span className="text-green-600">{approved} approved</span>}
            {needsReview > 0 && <span className="text-amber-600">{needsReview} review</span>}
          </div>
        </div>

        {/* Upload zone + progress */}
        <div className="shrink-0 border-b border-divider">
          {uploadingFiles.length > 0 ? (
            /* Upload progress bar */
            <div className="px-4 py-3">
              <div className="text-[11px] text-secondary mb-2">Uploading {uploadingFiles.length} file{uploadingFiles.length > 1 ? "s" : ""}...</div>
              <div className="flex gap-2 overflow-x-auto pb-1">
                {uploadingFiles.map(uf => (
                  <div key={uf.id} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-secondary border border-divider shrink-0">
                    <span className="text-[11px] font-medium text-primary truncate max-w-[120px]">{uf.name}</span>
                    <span className="text-[10px] text-tertiary">{uf.formType}</span>
                    {uf.status === "uploading" && <span className="text-[10px] text-apple-blue animate-pulse">Uploading...</span>}
                    {uf.status === "extracting" && <span className="text-[10px] text-amber-600 animate-pulse">Extracting...</span>}
                    {uf.status === "done" && <span className="text-[10px] text-green-600">Done</span>}
                    {uf.status === "error" && <span className="text-[10px] text-red-500">Error</span>}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            /* Drop zone */
            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`mx-4 my-3 border-2 border-dashed rounded-xl px-6 py-4 text-center cursor-pointer transition-all ${
                isDragging ? "border-apple-blue bg-apple-blue/5" : "border-divider hover:border-apple-blue/40"
              }`}
            >
              <input ref={fileInputRef} type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.tiff"
                onChange={(e) => { handleFiles(Array.from(e.target.files || [])); e.target.value = ""; }}
                className="hidden" />
              <div className="text-[13px] text-secondary">
                Drop files here or <span className="text-apple-blue font-medium">browse</span>
                <span className="text-tertiary ml-2 text-[11px]">PDF, PNG, JPEG {"\u00b7"} Max 20 MB</span>
              </div>
            </div>
          )}
        </div>

        {/* Document list — scrollable */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {documents.length === 0 ? (
            <div className="flex items-center justify-center h-full text-[13px] text-tertiary">
              No documents uploaded yet. Drop files above to get started.
            </div>
          ) : (
            <div className="divide-y divide-divider">
              {documents.map(doc => {
                const confPct = Math.round(doc.confidence * 100);
                const flags = parseJson<string[]>(doc.flags || "[]", []);
                const data = parseJson<Record<string, string>>(doc.extracted_data, {});
                const isExpanded = expandedDocId === doc.id;
                const isDupe = dupeIds.has(doc.id);
                const fieldDefs = FORM_FIELDS[doc.form_type] || [];

                // Key data point for summary
                let keyAmount = "";
                if (data.box1_wages) keyAmount = formatValue(data.box1_wages, "money");
                else if (data.box1_interest) keyAmount = formatValue(data.box1_interest, "money");
                else if (data.nec_compensation) keyAmount = formatValue(data.nec_compensation, "money");

                return (
                  <div key={doc.id}>
                    {/* Document row */}
                    <div className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-secondary/30 transition-colors group">
                      {/* Form type */}
                      <span className="text-[12px] font-semibold text-primary w-16 shrink-0">{doc.form_type}</span>

                      {/* Title + key data */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[12px] text-secondary truncate">{doc.title || doc.name}</span>
                          {isDupe && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 shrink-0">Duplicate?</span>
                          )}
                        </div>
                        {keyAmount && <span className="text-[11px] text-primary font-medium">{keyAmount}</span>}
                      </div>

                      {/* Status + confidence */}
                      <Badge variant={getStatusVariant(doc.status)} className="text-[9px] shrink-0">{doc.status}</Badge>
                      <div className="flex items-center gap-1 shrink-0">
                        <Progress value={confPct} color={confPct >= 90 ? "green" : confPct >= 70 ? "orange" : "red"} className="w-8" />
                        <span className="text-[10px] text-secondary w-6">{confPct}%</span>
                      </div>
                      {flags.length > 0 && (
                        <span className="text-[10px] text-amber-600 shrink-0">{flags.length} flag{flags.length > 1 ? "s" : ""}</span>
                      )}

                      {/* Actions */}
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={(e) => { e.stopPropagation(); setExpandedDocId(isExpanded ? null : doc.id); }}
                          className="text-[10px] px-2 py-1 rounded bg-surface-secondary text-secondary hover:text-apple-blue hover:bg-apple-blue/10 transition-colors cursor-pointer"
                        >
                          {isExpanded ? "Close" : "Review"}
                        </button>
                        {(doc.status === "review" || doc.status === "verified") && (
                          <button
                            onClick={(e) => { e.stopPropagation(); onApprove(doc.id); }}
                            className="text-[10px] px-2 py-1 rounded bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400 hover:bg-green-100 transition-colors cursor-pointer"
                          >
                            Approve
                          </button>
                        )}
                        <button
                          onClick={(e) => handleDeleteDoc(e, doc.id)}
                          className="w-6 h-6 rounded flex items-center justify-center text-tertiary hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors opacity-0 group-hover:opacity-100 cursor-pointer"
                          title="Delete"
                        >
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14" />
                          </svg>
                        </button>
                      </div>
                    </div>

                    {/* Inline review — expanded */}
                    {isExpanded && (
                      <div className="border-t border-divider bg-surface-secondary/20">
                        <div className="grid grid-cols-[1fr_350px] max-md:grid-cols-1" style={{ height: "400px" }}>
                          {/* Left: PDF preview */}
                          <div className="p-3 border-r border-divider overflow-hidden">
                            <PdfViewer src={getDocUrl(doc.id)} />
                          </div>

                          {/* Right: Extracted fields */}
                          <div className="p-3 overflow-y-auto">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-[12px] font-semibold text-primary">Extracted Fields</span>
                              <span className="text-[10px] text-tertiary">
                                {Object.keys(data).length} extracted
                              </span>
                            </div>
                            <div className="space-y-0.5">
                              {(fieldDefs.length > 0 ? fieldDefs : Object.keys(data).map(k => [k, "", k.replace(/_/g, " "), "text"] as FieldDef)).map(([key, num, label, vtype]) => {
                                const val = data[key];
                                const hasVal = val != null && val !== "";
                                return (
                                  <div key={key} className="flex items-baseline justify-between gap-2 px-2 py-1 rounded hover:bg-surface-secondary/50">
                                    <span className={`text-[10px] ${hasVal ? "text-secondary" : "text-tertiary"} shrink-0`}>
                                      {num ? `Box ${num}. ${label}` : label}
                                    </span>
                                    <span className={`text-[12px] font-medium text-right ${hasVal ? "text-primary" : "text-tertiary/40"}`}>
                                      {hasVal ? formatValue(val, vtype) : "\u2014"}
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                            {flags.length > 0 && (
                              <div className="mt-3 pt-2 border-t border-divider">
                                {flags.map((flag, i) => (
                                  <div key={i} className="text-[10px] text-amber-600 flex items-start gap-1 mb-1">
                                    <span>{"\u26A0"}</span><span>{flag}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                            {/* Inline approve button */}
                            {(doc.status === "review" || doc.status === "verified") && (
                              <div className="mt-3 pt-2 border-t border-divider">
                                <Button
                                  variant="primary"
                                  className="w-full text-[12px] py-1.5 h-auto"
                                  onClick={() => { onApprove(doc.id); setExpandedDocId(null); }}
                                >
                                  Approve Document
                                </Button>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </ModalBody>
    </Modal>
  );
}
