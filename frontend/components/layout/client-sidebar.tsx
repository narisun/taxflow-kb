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

      {/* New Intake — Apple style button */}
      <div className="px-3 pb-2">
        <button
          onClick={onNewIntake}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-[7px] rounded-lg bg-apple-blue text-white text-[13px] font-medium cursor-pointer hover:brightness-110 active:scale-[0.98] transition-all"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path d="M12 4.5v15m7.5-7.5h-15" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          New Intake
        </button>
      </div>

      {/* Section header */}
      <div className="px-3 pb-1">
        <span className="text-[10px] font-semibold text-tertiary uppercase tracking-wider">
          Clients ({filtered.length})
        </span>
      </div>

      {/* Client list — Apple sidebar style */}
      <div className="flex-1 overflow-y-auto px-2">
        {filtered.map((client) => {
          const isActive = client.id === activeClientId;
          const metaParts = client.meta.split(" \u00b7 ");
          const filingInfo = metaParts.slice(0, -1).join(" \u00b7 ");
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
                "w-full px-2.5 py-2 rounded-lg text-left transition-all cursor-pointer mb-px",
                isActive
                  ? "bg-apple-blue/10 text-apple-blue"
                  : "hover:bg-surface-secondary text-secondary"
              )}
            >
              <div className={cn(
                "text-[13px] truncate",
                isActive ? "font-semibold text-apple-blue" : "font-medium"
              )}>
                {client.name}
              </div>
              <div className={cn(
                "text-[11px] mt-0.5 truncate",
                isActive ? "text-apple-blue/70" : "text-tertiary"
              )}>
                {filingInfo} &middot; {statusLabel} &middot; {taxYear}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}

export { ClientSidebar, type ClientSidebarProps, type Client };
