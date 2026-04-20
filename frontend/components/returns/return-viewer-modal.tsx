"use client";

import { useEffect, useState } from "react";
import { Modal, ModalHeader, ModalBody, ModalFooter } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { PdfViewer } from "@/components/documents/pdf-viewer";
import { api, FormManifestEntry, ReturnManifest } from "@/lib/api-client";
import { cn } from "@/lib/utils";

interface ReturnViewerModalProps {
  open: boolean;
  onClose: () => void;
  clientId: string;
}

export function ReturnViewerModal({ open, onClose, clientId }: ReturnViewerModalProps) {
  const [manifest, setManifest] = useState<ReturnManifest | null>(null);
  const [selectedForm, setSelectedForm] = useState<FormManifestEntry | null>(null);
  const [goToPage, setGoToPage] = useState<number | undefined>(undefined);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!open || !clientId) return;
    setLoading(true);
    api.returns.manifest(clientId).then((m) => {
      setManifest(m);
      const firstActive = m.forms.find((f) => f.active);
      setSelectedForm(firstActive || null);
      setGoToPage(firstActive?.start_page ?? 1);
      setLoading(false);
    }).catch(() => {
      setLoading(false);
    });
  }, [open, clientId]);

  const handleFormClick = (form: FormManifestEntry) => {
    if (!form.active || !form.start_page) return;
    setSelectedForm(form);
    setGoToPage(form.start_page);
  };

  const handleDownload = () => {
    window.open(api.returns.pdfUrl(clientId, "attachment"), "_blank");
  };

  const pdfSrc = api.returns.pdfUrl(clientId, "inline");
  const headerLabel = selectedForm ? `Tax Return — ${selectedForm.label}` : "Tax Return";

  return (
    <Modal open={open} onClose={onClose} className="w-[90vw] max-w-6xl h-[calc(100vh-64px)]">
      <ModalHeader onClose={onClose}>{headerLabel}</ModalHeader>
      <ModalBody className="flex flex-row gap-0 p-0 overflow-hidden flex-1 min-h-0">
        {/* Left nav */}
        <div className="w-[180px] shrink-0 border-r border-divider bg-surface-secondary/30 overflow-y-auto py-2">
          {loading ? (
            <div className="px-3 py-2 text-[11px] text-tertiary">Loading...</div>
          ) : (
            manifest?.forms.map((form) => (
              <button
                key={form.id}
                onClick={() => handleFormClick(form)}
                disabled={!form.active}
                className={cn(
                  "w-full text-left px-3 py-2 text-[12px] transition-colors",
                  form.active
                    ? "cursor-pointer hover:bg-surface-secondary"
                    : "opacity-40 cursor-not-allowed",
                  selectedForm?.id === form.id && form.active
                    ? "bg-brand/10 text-brand font-medium border-l-2 border-brand"
                    : "text-secondary",
                )}
              >
                {form.label}
              </button>
            ))
          )}
        </div>

        {/* PDF viewer */}
        <div className="flex-1 min-w-0 p-3">
          {open && <PdfViewer src={pdfSrc} goToPage={goToPage} className="h-full" />}
        </div>
      </ModalBody>
      <ModalFooter>
        <div className="flex items-center justify-end gap-2 w-full">
          <Button variant="ghost" onClick={handleDownload} className="text-[12px]">
            Download PDF
          </Button>
          <Button variant="secondary" onClick={onClose} className="text-[12px]">
            Close
          </Button>
        </div>
      </ModalFooter>
    </Modal>
  );
}
