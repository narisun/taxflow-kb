"use client";

import { cn } from "@/lib/utils";
import { useState } from "react";

interface Client {
  id: string;
  name: string;
  meta: string;
  status: string;
  initials: string;
  color: string;
  years?: { year: string; docs: string[] }[];
}

interface ClientSidebarProps {
  clients: Client[];
  activeClientId: string | null;
  onSelectClient: (id: string) => void;
  onNewIntake?: () => void;
}

const statusLabels: Record<string, string> = {
  pending: "Pending",
  inProgress: "In Progress",
  review: "Review",
  completed: "Completed",
  filed: "Filed",
};

function ClientSidebar({ clients, activeClientId, onSelectClient, onNewIntake }: ClientSidebarProps) {
  const [search, setSearch] = useState("");

  const filtered = clients.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.meta.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <aside className="w-72 shrink-0 bg-bg border-r border-divider flex flex-col overflow-hidden">
      {/* Search */}
      <div className="p-3 pb-2">
        <div className="relative">
          <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-tertiary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <circle cx="11" cy="11" r="8" strokeWidth="2" />
            <path d="m21 21-4.3-4.3" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            placeholder="Search clients..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-[12px] bg-surface border border-divider rounded-lg outline-none focus:border-apple-blue transition-colors text-primary placeholder:text-tertiary"
          />
        </div>
      </div>

      {/* Section header + New Intake button inline */}
      <div className="flex items-center justify-between px-3 pb-2">
        <span className="text-[10px] font-semibold text-tertiary uppercase tracking-wider">
          Clients ({filtered.length})
        </span>
        <button
          onClick={onNewIntake}
          className="text-[11px] text-secondary hover:text-primary transition-colors cursor-pointer flex items-center gap-0.5"
        >
          <span className="text-[13px] leading-none">+</span>
          New Intake
        </button>
      </div>

      {/* Client list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.map((client) => {
          const isActive = client.id === activeClientId;
          // Extract tax year from meta (format: "filing_status · N dep. · YEAR")
          const metaParts = client.meta.split(" \u00b7 ");
          const filingInfo = metaParts.slice(0, -1).join(" \u00b7 "); // e.g. "mfj · 3 dep."
          const taxYear = metaParts[metaParts.length - 1] || "2025";
          const statusLabel = statusLabels[client.status] ?? client.status;

          return (
            <div
              key={client.id}
              role="button"
              tabIndex={0}
              onClick={() => onSelectClient(client.id)}
              onKeyDown={(e) => { if (e.key === "Enter") onSelectClient(client.id); }}
              className={cn(
                "mx-2 my-0.5 px-2.5 py-2.5 rounded-lg text-left transition-all cursor-pointer border",
                isActive
                  ? "bg-surface border-apple-blue/30 shadow-sm"
                  : "border-transparent hover:border-teal-500/30 hover:bg-surface-secondary/60"
              )}
            >
              {/* Line 1: Name + filing info */}
              <div className="flex items-center justify-between gap-1.5">
                <div className="flex items-baseline gap-1.5 min-w-0">
                  <span className={cn(
                    "text-[13px] truncate",
                    isActive ? "font-semibold text-primary" : "font-medium text-secondary"
                  )}>
                    {client.name}
                  </span>
                  <span className="text-[10px] text-tertiary truncate shrink-0">
                    {filingInfo}
                  </span>
                </div>
                {isActive && (
                  <span className="shrink-0 text-[9px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-apple-blue text-white">
                    {statusLabel}
                  </span>
                )}
              </div>
              {/* Line 2: Status + year */}
              <div className="text-[11px] text-tertiary mt-0.5">
                {isActive ? taxYear : `${statusLabel} \u00b7 ${taxYear}`}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}

export { ClientSidebar, type ClientSidebarProps, type Client };
