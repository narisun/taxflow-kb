"use client";

import { useState, useCallback, useRef } from "react";
import { Modal, ModalHeader, ModalBody } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
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
  // PII masked fields (from API response)
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

// Form type detection from filename
function detectFormType(filename: string): string {
  const f = filename.toLowerCase();
  if (f.includes("w2") || f.includes("w-2")) return "W-2";
  if (f.includes("1099-int") || f.includes("1099int")) return "1099-INT";
  if (f.includes("1099-nec") || f.includes("1099nec")) return "1099-NEC";
  if (f.includes("1099-b") || f.includes("1099b")) return "1099-B";
  if (f.includes("1099-div") || f.includes("1099div")) return "1099-DIV";
  if (f.includes("1099")) return "1099";
  if (f.includes("1098")) return "1098";
  if (f.includes("k-1") || f.includes("k1")) return "K-1";
  return "Other";
}

// Key data from extracted fields
function getKeyData(doc: DocItem): string {
  const data = parseJson<Record<string, string>>(doc.extracted_data, {});
  if (doc.form_type === "W-2") {
    const wages = data.box1_wages;
    if (wages) {
      const n = parseFloat(wages);
      return isNaN(n) ? "" : fmtCurrency(n);
    }
  }
  if (doc.form_type === "1099-INT") return data.box1_interest ? fmtCurrency(parseFloat(data.box1_interest)) : "";
  if (doc.form_type === "1099-NEC") return data.nec_compensation ? fmtCurrency(parseFloat(data.nec_compensation)) : "";
  if (doc.form_type === "1098") return data.box1_interest ? fmtCurrency(parseFloat(data.box1_interest)) : "";
  return "";
}

function getStatusColor(status: string): "completed" | "review" | "pending" {
  if (status === "approved" || status === "verified") return "completed";
  if (status === "review" || status === "flagged") return "review";
  return "pending";
}

export function DocumentManagerModal({
  open,
  onClose,
  client,
  dependents,
  documents,
  onUpload,
  onDelete,
  onApprove,
  onViewDoc,
}: DocumentManagerModalProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files).filter(
      (f) => f.type === "application/pdf" || f.type.startsWith("image/")
    );
    if (files.length > 0) {
      setUploading(true);
      await onUpload(files);
      setUploading(false);
    }
  }, [onUpload]);

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      setUploading(true);
      await onUpload(files);
      setUploading(false);
    }
    e.target.value = "";
  }, [onUpload]);

  const handleDelete = async (e: React.MouseEvent, docId: number) => {
    e.stopPropagation();
    if (confirm("Delete this document? This cannot be undone.")) {
      await onDelete(docId);
    }
  };

  if (!client) return null;

  // Stats
  const approved = documents.filter((d) => d.status === "approved" || d.status === "verified").length;
  const needsReview = documents.filter((d) => d.status === "review" || d.status === "flagged").length;
  const filingStatusLabel: Record<string, string> = {
    single: "Single", mfj: "Married Filing Jointly", mfs: "Married Filing Separately",
    hoh: "Head of Household", qw: "Qualifying Widow(er)",
    S: "Single", MFJ: "Married Filing Jointly", MFS: "Married Filing Separately",
    HOH: "Head of Household", QSS: "Qualifying Widow(er)",
  };

  // Duplicate detection
  const duplicateIds = new Set<number>();
  for (let i = 0; i < documents.length; i++) {
    for (let j = i + 1; j < documents.length; j++) {
      if (
        documents[i].form_type === documents[j].form_type &&
        documents[i].extracted_data === documents[j].extracted_data &&
        documents[i].extracted_data !== "{}"
      ) {
        duplicateIds.add(documents[i].id);
        duplicateIds.add(documents[j].id);
      }
    }
  }

  return (
    <Modal open={open} onClose={onClose} className="max-w-5xl w-[90vw]">
      <ModalHeader onClose={onClose}>
        <span>Document Manager</span>
      </ModalHeader>

      <ModalBody className="h-[75vh] p-0 overflow-hidden flex flex-col">
        {/* Client info bar */}
        <div className="px-4 py-3 bg-surface-secondary/50 border-b border-divider shrink-0">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[14px] font-semibold text-primary">{client.name}</div>
              <div className="text-[12px] text-secondary mt-0.5">
                {filingStatusLabel[client.filing_status] || client.filing_status}
                {" \u00b7 "}TY {client.tax_year}
                {client.city && ` \u00b7 ${client.city}, ${client.state}`}
              </div>
            </div>
            <div className="text-right text-[11px] text-secondary">
              {client.spouse_first_name && (
                <div>Spouse: {client.spouse_first_name} {client.spouse_last_name}</div>
              )}
              {dependents.length > 0 && (
                <div>
                  {dependents.length} dependent{dependents.length > 1 ? "s" : ""}:{" "}
                  {dependents.map((d) => `${d.first_name} (${d.relationship})`).join(", ")}
                </div>
              )}
              {!client.spouse_first_name && dependents.length === 0 && (
                <div>No spouse or dependents</div>
              )}
            </div>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-4 mt-2 text-[11px]">
            <span className="text-secondary">{documents.length} document{documents.length !== 1 ? "s" : ""}</span>
            {approved > 0 && <span className="text-green-600">{approved} approved</span>}
            {needsReview > 0 && <span className="text-amber-600">{needsReview} needs review</span>}
            {duplicateIds.size > 0 && <span className="text-red-500">{duplicateIds.size / 2} possible duplicate{duplicateIds.size > 2 ? "s" : ""}</span>}
          </div>
        </div>

        {/* Main content area */}
        <div className="flex-1 overflow-y-auto p-4">
          {/* Document list */}
          {documents.length > 0 && (
            <div className="space-y-2 mb-4">
              {documents.map((doc) => {
                const keyData = getKeyData(doc);
                const isDupe = duplicateIds.has(doc.id);
                const confPct = Math.round(doc.confidence * 100);

                return (
                  <div
                    key={doc.id}
                    onClick={() => onViewDoc(doc)}
                    className="flex items-center gap-3 px-3 py-2 rounded-lg border border-divider hover:border-apple-blue/30 hover:bg-surface-secondary/50 cursor-pointer transition-all group"
                  >
                    {/* Form type badge */}
                    <div className="w-16 shrink-0">
                      <div className="text-[12px] font-semibold text-primary">{doc.form_type}</div>
                    </div>

                    {/* Key info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[12px] text-secondary truncate">
                          {doc.title || doc.name}
                        </span>
                        {isDupe && (
                          <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 shrink-0">
                            Duplicate?
                          </span>
                        )}
                      </div>
                      {keyData && (
                        <span className="text-[11px] text-primary font-medium">{keyData}</span>
                      )}
                    </div>

                    {/* Status + confidence */}
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant={getStatusColor(doc.status)} className="text-[9px]">
                        {doc.status}
                      </Badge>
                      <div className="flex items-center gap-1">
                        <Progress value={confPct} color={confPct >= 90 ? "green" : confPct >= 70 ? "orange" : "red"} className="w-8" />
                        <span className="text-[10px] text-secondary w-7">{confPct}%</span>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                      {(doc.status === "review" || doc.status === "verified") && (
                        <button
                          onClick={(e) => { e.stopPropagation(); onApprove(doc.id); }}
                          className="text-[10px] px-2 py-1 rounded bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400 hover:bg-green-100 transition-colors"
                          title="Approve"
                        >
                          Approve
                        </button>
                      )}
                      <button
                        onClick={(e) => handleDelete(e, doc.id)}
                        className="w-6 h-6 rounded flex items-center justify-center text-tertiary hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                        title="Delete"
                      >
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14" />
                        </svg>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Drop zone */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
              isDragging
                ? "border-apple-blue bg-apple-blue/5 scale-[1.01]"
                : "border-divider hover:border-apple-blue/40 hover:bg-surface-secondary/30"
            } ${uploading ? "opacity-50 pointer-events-none" : ""}`}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.png,.jpg,.jpeg,.tiff"
              onChange={handleFileSelect}
              className="hidden"
            />
            <div className="text-[24px] mb-2">{uploading ? "\u23F3" : "\u{1F4C4}"}</div>
            <div className="text-[13px] font-medium text-primary">
              {uploading ? "Uploading..." : "Drop files here or click to browse"}
            </div>
            <div className="text-[11px] text-tertiary mt-1">
              PDF, PNG, JPEG, TIFF \u00b7 Max 20 MB per file \u00b7 Multiple files supported
            </div>
            <div className="flex flex-wrap justify-center gap-1.5 mt-3">
              {["W-2", "1099-INT", "1099-DIV", "1099-NEC", "1099-B", "1098", "K-1"].map((ft) => (
                <span key={ft} className="text-[10px] px-2 py-0.5 rounded-full bg-surface-secondary text-secondary border border-divider">
                  {ft}
                </span>
              ))}
            </div>
          </div>
        </div>
      </ModalBody>
    </Modal>
  );
}
