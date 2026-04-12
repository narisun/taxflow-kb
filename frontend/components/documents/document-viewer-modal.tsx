"use client";

import { useState } from "react";
import { Modal, ModalHeader, ModalBody, ModalFooter } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { FormRenderer } from "@/components/forms/form-renderer";

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

  const hasFlaggedFields = parsedFlags.length > 0;

  const handleFieldEdit = (key: string, value: string) => {
    setEditedFields((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <Modal open={open} onClose={onClose} className="w-[90vw] max-w-4xl">
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

      <ModalBody className="max-h-[60vh]">
        <div className={`grid gap-6 ${hasFlaggedFields ? "grid-cols-2" : "grid-cols-1"}`}>
          {/* Left: Form render */}
          <div>
            <FormRenderer formType={doc.form_type} data={parsedData} />
            <div className="mt-2 text-center">
              {doc.status === "verified" ? (
                <span className="inline-block bg-green-100 text-green-700 text-[11px] font-bold uppercase tracking-wider px-3 py-1 rounded-full">
                  Verified
                </span>
              ) : (
                <span className="inline-block bg-orange-100 text-orange-700 text-[11px] font-bold uppercase tracking-wider px-3 py-1 rounded-full">
                  Needs Review
                </span>
              )}
            </div>
          </div>

          {/* Right: Editable extraction fields (for flagged docs) */}
          {hasFlaggedFields && (
            <div className="space-y-3">
              <div className="text-[13px] font-semibold text-[#1d1d1f] mb-2">
                Flagged Fields
              </div>
              {parsedFlags.map((flag, i) => (
                <div
                  key={i}
                  className="bg-orange-50 text-orange-700 text-[12px] px-3 py-2 rounded-lg"
                >
                  &#9888; {flag}
                </div>
              ))}

              <div className="text-[13px] font-semibold text-[#1d1d1f] mt-4 mb-2">
                Extracted Fields
              </div>
              {Object.entries(parsedData).map(([key, value]) => (
                <div key={key} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <label className="text-[11px] text-gray-500 uppercase">
                      {key.replace(/_/g, " ")}
                    </label>
                    <Badge
                      variant={doc.confidence >= 90 ? "completed" : doc.confidence >= 70 ? "review" : "pending"}
                    >
                      {doc.confidence}%
                    </Badge>
                  </div>
                  <Input
                    value={
                      editedFields[key] !== undefined
                        ? editedFields[key]
                        : String(value ?? "")
                    }
                    onChange={(e) => handleFieldEdit(key, e.target.value)}
                    validation={
                      parsedFlags.some((f) =>
                        f.toLowerCase().includes(key.toLowerCase().replace(/_/g, " "))
                      )
                        ? "warning"
                        : "default"
                    }
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </ModalBody>

      <ModalFooter>
        <div className="flex items-center gap-3 w-full">
          <div className="flex items-center gap-2 flex-1">
            <span className="text-[12px] text-gray-500">AI Confidence:</span>
            <Progress
              value={doc.confidence}
              color={doc.confidence >= 90 ? "green" : doc.confidence >= 70 ? "orange" : "red"}
              className="w-24"
            />
            <span className="text-[12px] font-medium">{doc.confidence}%</span>
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
