"use client";

import { cn } from "@/lib/utils";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
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
      <div className="p-3">
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

      <div className="px-3 pb-2">
        <button
          onClick={onNewIntake}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-apple-blue text-white text-[12px] font-medium cursor-pointer hover:brightness-110 transition-all"
        >
          <span className="text-[14px] leading-none">+</span>
          New Intake
        </button>
      </div>

      <div className="flex items-center justify-between px-3 pb-1.5">
        <span className="text-[10px] font-semibold text-tertiary uppercase tracking-wider">
          Clients ({filtered.length})
        </span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {filtered.map((client) => {
          const isActive = client.id === activeClientId;
          return (
            <div key={client.id}>
              <div
                role="button"
                tabIndex={0}
                onClick={() => onSelectClient(client.id)}
                onKeyDown={(e) => { if (e.key === "Enter") onSelectClient(client.id); }}
                className={cn(
                  "w-full flex items-center gap-2.5 px-3 py-2.5 text-left transition-all cursor-pointer border-l-3",
                  isActive
                    ? "bg-surface border-l-apple-blue shadow-sm"
                    : "hover:bg-surface/60 border-l-transparent"
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className={cn("text-[13px] truncate transition-all", isActive ? "font-semibold text-primary" : "font-medium text-secondary")}>
                    {client.name}
                  </div>
                  <div className={cn("text-[11px] truncate", isActive ? "text-secondary" : "text-tertiary")}>
                    {client.meta}
                  </div>
                </div>
                <Badge variant={client.status as BadgeVariant}>
                  {statusLabels[client.status] ?? client.status}
                </Badge>
              </div>
              {isActive && client.years && (
                <div className="bg-surface border-l-3 border-l-apple-blue px-3 pb-2">
                  {client.years.map((y) => (
                    <div key={y.year} className="mt-1">
                      <div className="text-[10px] font-semibold text-tertiary uppercase tracking-wider mb-0.5 pl-3">{y.year}</div>
                      {y.docs.map((doc) => (
                        <div key={doc} className="text-[11px] text-secondary pl-3 py-1 rounded hover:bg-surface-secondary cursor-pointer transition-colors">{doc}</div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}

export { ClientSidebar, type ClientSidebarProps, type Client };
