"use client";

import { cn } from "@/lib/utils";
import { Avatar } from "@/components/ui/avatar";
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
  const [expandedClients, setExpandedClients] = useState<Set<string>>(new Set());

  const filtered = clients.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.meta.toLowerCase().includes(search.toLowerCase())
  );

  function toggleExpand(id: string) {
    setExpandedClients((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

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

      {/* Client list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.map((client) => {
          const isActive = client.id === activeClientId;
          const isExpanded = expandedClients.has(client.id);

          return (
            <div key={client.id}>
              <button
                onClick={() => onSelectClient(client.id)}
                className={cn(
                  "w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors cursor-pointer",
                  isActive
                    ? "bg-blue-50 border-l-2 border-[#0071e3]"
                    : "hover:bg-gray-100 border-l-2 border-transparent"
                )}
              >
                <Avatar initials={client.initials} color={client.color} size="sm" />
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-medium text-[#1d1d1f] truncate">
                    {client.name}
                  </div>
                  <div className="text-[11px] text-gray-500 truncate">{client.meta}</div>
                </div>
                <Badge variant={client.status as BadgeVariant}>
                  {statusLabels[client.status] ?? client.status}
                </Badge>
                {client.years && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleExpand(client.id);
                    }}
                    className={cn(
                      "text-gray-400 text-[10px] transition-transform cursor-pointer",
                      isExpanded && "rotate-90"
                    )}
                  >
                    &#9654;
                  </button>
                )}
              </button>

              {/* Expandable tree */}
              {isExpanded && client.years && (
                <div className="pl-12 pr-3 pb-1">
                  {client.years.map((y) => (
                    <div key={y.year} className="mb-1">
                      <div className="text-[11px] font-semibold text-gray-500">{y.year}</div>
                      {y.docs.map((doc) => (
                        <div key={doc} className="text-[11px] text-gray-400 pl-2 py-0.5">
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
