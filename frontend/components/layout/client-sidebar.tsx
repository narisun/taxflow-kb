"use client";

import { cn } from "@/lib/utils";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { useState, useEffect } from "react";

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
}

const statusLabels: Record<string, string> = {
  pending: "Pending",
  inProgress: "In Progress",
  review: "Review",
  completed: "Completed",
  filed: "Filed",
};

function ClientSidebar({ clients, activeClientId, onSelectClient }: ClientSidebarProps) {
  const [search, setSearch] = useState("");

  const filtered = clients.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.meta.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <aside className="w-72 shrink-0 bg-[#f5f5f7] border-r border-gray-200 flex flex-col overflow-hidden">
      {/* Search */}
      <div className="p-3">
        <div className="relative">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <circle cx="11" cy="11" r="8" strokeWidth="2" />
            <path d="m21 21-4.3-4.3" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            placeholder="Search clients..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-[12px] bg-white border border-gray-200 rounded-lg outline-none focus:border-[#0071e3] transition-colors"
          />
        </div>
      </div>

      {/* Section header */}
      <div className="flex items-center justify-between px-3 pb-2">
        <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
          Clients <span className="text-gray-400">({filtered.length})</span>
        </span>
        <button className="w-5 h-5 rounded-md bg-[#0071e3] text-white text-[12px] flex items-center justify-center cursor-pointer hover:brightness-110 transition-all">
          +
        </button>
      </div>

      {/* Client list — accordion style */}
      <div className="flex-1 overflow-y-auto">
        {filtered.map((client) => {
          const isActive = client.id === activeClientId;

          return (
            <div key={client.id}>
              {/* Client row */}
              <div
                role="button"
                tabIndex={0}
                onClick={() => onSelectClient(client.id)}
                onKeyDown={(e) => { if (e.key === "Enter") onSelectClient(client.id); }}
                className={cn(
                  "w-full flex items-center gap-2.5 px-3 py-2.5 text-left transition-all cursor-pointer border-l-3",
                  isActive
                    ? "bg-white border-l-[#0071e3] shadow-sm"
                    : "hover:bg-white/60 border-l-transparent"
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className={cn(
                    "text-[13px] truncate transition-all",
                    isActive
                      ? "font-semibold text-[#1d1d1f]"
                      : "font-medium text-gray-600"
                  )}>
                    {client.name}
                  </div>
                  <div className={cn(
                    "text-[11px] truncate",
                    isActive ? "text-gray-500" : "text-gray-400"
                  )}>
                    {client.meta}
                  </div>
                </div>
                <Badge variant={client.status as BadgeVariant}>
                  {statusLabels[client.status] ?? client.status}
                </Badge>
              </div>

              {/* Accordion panel — auto-expands when client is active */}
              {isActive && client.years && (
                <div className="bg-white border-l-3 border-l-[#0071e3] px-3 pb-2">
                  {client.years.map((y) => (
                    <div key={y.year} className="mt-1">
                      <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-0.5 pl-3">
                        {y.year}
                      </div>
                      {y.docs.map((doc) => (
                        <div
                          key={doc}
                          className="text-[11px] text-gray-500 pl-3 py-1 rounded hover:bg-gray-50 cursor-pointer transition-colors"
                        >
                          {doc}
                        </div>
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
