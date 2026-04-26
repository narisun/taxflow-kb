"use client";

import { useState } from "react";
import { Modal, ModalHeader, ModalBody } from "@/components/ui/modal";
import { cn, fmtDate } from "@/lib/utils";
import { useTimezone } from "@/components/auth/me-context";
import type { Client } from "@/lib/api-client";

interface ClientMasterModalProps {
  open: boolean;
  onClose: () => void;
  clients: Client[];
  initialFilter?: string;
  onSelectClient?: (id: string) => void;
}

const statusLabels: Record<string, string> = {
  intake: "Intake",
  documents: "Documents",
  review: "Review",
  preparation: "Preparation",
  filing: "Filing",
  filed: "Filed",
};

const statusColors: Record<string, string> = {
  intake: "bg-surface-tertiary text-secondary",
  documents: "bg-badge-progress-bg text-badge-progress-text",
  review: "bg-badge-review-bg text-badge-review-text",
  preparation: "bg-badge-progress-bg text-badge-progress-text",
  filing: "bg-badge-complete-bg text-badge-complete-text",
  filed: "bg-badge-filed-bg text-badge-filed-text",
};

const filters = [
  { id: "", label: "All" },
  { id: "intake", label: "Intake" },
  { id: "documents", label: "Documents" },
  { id: "review", label: "Review" },
  { id: "preparation", label: "Preparation" },
  { id: "filing", label: "Filing" },
  { id: "filed", label: "Filed" },
];

export function ClientMasterModal({ open, onClose, clients, initialFilter = "", onSelectClient }: ClientMasterModalProps) {
  const tz = useTimezone();
  const [filter, setFilter] = useState(initialFilter);
  const [search, setSearch] = useState("");

  const filtered = clients.filter((c) => {
    if (filter && c.workflow_step !== filter) return false;
    if (search) {
      const q = search.toLowerCase();
      return c.name.toLowerCase().includes(q) || c.filing_status.toLowerCase().includes(q);
    }
    return true;
  });

  // Reset filter when modal opens with a new initialFilter
  useState(() => { setFilter(initialFilter); });

  return (
    <Modal open={open} onClose={onClose} className="max-w-3xl">
      <ModalHeader onClose={onClose}>Client Master</ModalHeader>
      <ModalBody className="p-0 max-h-[70vh]">
        {/* Toolbar: search + filter chips */}
        <div className="px-4 py-3 border-b border-divider space-y-2">
          <input
            type="text"
            placeholder="Search clients..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full px-3 py-1.5 text-[12px] bg-surface border border-divider rounded-lg outline-none focus:border-apple-blue transition-colors text-primary placeholder:text-tertiary"
          />
          <div className="flex gap-1 flex-wrap">
            {filters.map((f) => {
              const count = f.id ? clients.filter((c) => c.workflow_step === f.id).length : clients.length;
              return (
                <button
                  key={f.id}
                  onClick={() => setFilter(f.id)}
                  className={cn(
                    "text-[10px] font-medium px-2 py-1 rounded-full transition-colors cursor-pointer",
                    filter === f.id
                      ? "bg-apple-blue text-white"
                      : "bg-surface-secondary text-secondary hover:bg-surface-tertiary"
                  )}
                >
                  {f.label} ({count})
                </button>
              );
            })}
          </div>
        </div>

        {/* Client table */}
        <div className="overflow-y-auto scroll-visible max-h-[50vh]">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-divider bg-surface-secondary/50 sticky top-0">
                <th className="text-left px-4 py-2 text-[10px] font-semibold text-tertiary uppercase">Name</th>
                <th className="text-left px-4 py-2 text-[10px] font-semibold text-tertiary uppercase">Filing</th>
                <th className="text-left px-4 py-2 text-[10px] font-semibold text-tertiary uppercase">Year</th>
                <th className="text-left px-4 py-2 text-[10px] font-semibold text-tertiary uppercase">Dep.</th>
                <th className="text-left px-4 py-2 text-[10px] font-semibold text-tertiary uppercase">Status</th>
                <th className="text-left px-4 py-2 text-[10px] font-semibold text-tertiary uppercase">Created</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((client) => (
                <tr
                  key={client.id}
                  onClick={() => { onSelectClient?.(client.id); onClose(); }}
                  className="border-b border-divider hover:bg-surface-secondary transition-colors cursor-pointer"
                >
                  <td className="px-4 py-2.5">
                    <span className="text-primary font-medium">{client.name}</span>
                  </td>
                  <td className="px-4 py-2.5 text-secondary uppercase">{client.filing_status}</td>
                  <td className="px-4 py-2.5 text-secondary">{client.tax_year}</td>
                  <td className="px-4 py-2.5 text-secondary">{client.dependents}</td>
                  <td className="px-4 py-2.5">
                    <span className={cn(
                      "text-[9px] font-medium px-1.5 py-0.5 rounded-full",
                      statusColors[client.workflow_step] || "bg-surface-tertiary text-secondary"
                    )}>
                      {statusLabels[client.workflow_step] || client.workflow_step}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-tertiary">
                    {fmtDate(client.created_at, tz)}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-tertiary">No clients found</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-divider text-[11px] text-tertiary">
          Showing {filtered.length} of {clients.length} clients
        </div>
      </ModalBody>
    </Modal>
  );
}
