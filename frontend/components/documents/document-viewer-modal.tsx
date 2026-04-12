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

function getPdfUrl(formType: string): string {
  switch (formType) {
    case "W-2": return "/sample-forms/fw2.pdf";
    case "1099-INT":
    case "1099-DIV": return "/sample-forms/f1099div.pdf";
    case "1099-NEC":
    case "1099-MISC": return "/sample-forms/f1099msc.pdf";
    default: return "/sample-forms/f1065sk1.pdf";
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
    parsedData = doc.extracted_data ? JSON.parse(doc.extracted_data) : {};
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

  const fmt = (val: unknown) => {
    if (typeof val === "number") return `$${val.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
    return String(val ?? "");
  };

  return (
    <Modal open={open} onClose={onClose} className="max-w-5xl">
      <ModalHeader onClose={onClose}>
        <div className="flex items-center gap-3">
          <span>{doc.title}</span>
          <Badge
            variant={doc.status === "verified" ? "completed" : doc.status === "flagged" ? "review" : "pending"}
          >
            {doc.status}
          </Badge>
        </div>
      </ModalHeader>

      <ModalBody className="max-h-[65vh] p-0">
        <div className="grid grid-cols-2 max-md:grid-cols-1 h-full">
          {/* Left: PDF viewer */}
          <div className="p-4 border-r border-divider max-md:border-r-0 max-md:border-b">
            <PdfViewer src={getPdfUrl(doc.form_type)} />
          </div>

          {/* Right: Extracted fields */}
          <div className="p-4 overflow-y-auto">
            <div className="text-[13px] font-semibold text-primary mb-3">
              Extracted Fields
            </div>

            <div className="space-y-2.5">
              {Object.entries(parsedData).map(([key, value]) => {
                const flagged = isFlagged(key);
                const fieldFlag = flagged ? parsedFlags.find((f) => f.toLowerCase().includes(key.toLowerCase().replace(/_/g, " "))) : null;

                return (
                  <div key={key}>
                    <div className="flex items-center justify-between mb-0.5">
                      <label className="text-[11px] text-tertiary uppercase">
                        {key.replace(/_/g, " ")}
                      </label>
                      {flagged && (
                        <span className="text-[10px] text-badge-review-text">&#9888;</span>
                      )}
                    </div>
                    {flagged ? (
                      <>
                        <Input
                          value={editedFields[key] !== undefined ? editedFields[key] : fmt(value)}
                          onChange={(e) => handleFieldEdit(key, e.target.value)}
                          validation="warning"
                        />
                        {fieldFlag && (
                          <div className="text-[10px] text-badge-review-text mt-0.5 leading-tight">
                            &#9888; {fieldFlag}
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-[13px] text-primary font-medium px-1">
                        {fmt(value)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
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
            <span className="text-[12px] font-medium text-primary">{doc.confidence}%</span>
          </div>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              if (onApprove) onApprove(doc.id);
              onClose();
            }}
          >
            Approve
          </Button>
        </div>
      </ModalFooter>
    </Modal>
  );
}
