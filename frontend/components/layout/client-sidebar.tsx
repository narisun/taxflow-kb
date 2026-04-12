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
  adults?: string;
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
      c.meta.toLowerCase().includes(search.toLowerCase()) ||
      (c.adults || "").toLowerCase().includes(search.toLowerCase())
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

      {/* Section header + New Intake button */}
      <div className="flex items-center justify-between px-3 pb-2">
        <span className="text-[10px] font-semibold text-tertiary uppercase tracking-wider">
          Clients ({filtered.length})
        </span>
        <button
          onClick={onNewIntake}
          className="flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium text-secondary border border-divider bg-surface hover:bg-surface-secondary hover:border-tertiary active:scale-[0.97] transition-all cursor-pointer"
        >
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
            <path d="M12 4.5v15m7.5-7.5h-15" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          New Intake
        </button>
      </div>

      {/* Client list with visible scrollbar */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {filtered.map((client, index) => {
          const isActive = client.id === activeClientId;
          const metaParts = client.meta.split(" \u00b7 ");
          const filingInfo = metaParts.slice(0, -1).join(" \u00b7 ");
          const taxYear = metaParts[metaParts.length - 1] || "2025";
          const statusLabel = statusLabels[client.status] ?? client.status;

          return (
            <div key={client.id}>
              {index > 0 && <div className="border-t border-divider mx-3" />}
              <div
                role="button"
                tabIndex={0}
                onClick={() => onSelectClient(client.id)}
                onKeyDown={(e) => { if (e.key === "Enter") onSelectClient(client.id); }}
                className={cn(
                  "w-full px-3 py-2.5 text-left transition-all cursor-pointer",
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
                {client.adults && (
                  <div className={cn(
                    "text-[11px] truncate",
                    isActive ? "text-apple-blue/60" : "text-tertiary"
                  )}>
                    {client.adults}
                  </div>
                )}
                <div className={cn(
                  "text-[11px] mt-0.5 truncate",
                  isActive ? "text-apple-blue/70" : "text-tertiary"
                )}>
                  {filingInfo} &middot; {statusLabel} &middot; {taxYear}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}

export { ClientSidebar, type ClientSidebarProps, type Client };
