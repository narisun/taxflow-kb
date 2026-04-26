// frontend/components/notifications/notification-bell.tsx
"use client";

import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";

export interface Alert {
  id: string;
  type: "document" | "return" | "deadline" | "workflow";
  title: string;
  detail?: string;
  clientName?: string;
  time?: string;
  read: boolean;
}

interface NotificationBellProps {
  alerts?: Alert[];
  onMarkAllRead?: () => void;
}

const typeIcons: Record<string, string> = {
  document: "\u26A0",
  return: "\uD83D\uDCC4",
  deadline: "\u23F0",
  workflow: "\u25B6",
};

const typeLabels: Record<string, string> = {
  document: "Document Issue",
  return: "Return",
  deadline: "Deadline",
  workflow: "Workflow",
};

export function NotificationBell({ alerts = [], onMarkAllRead }: NotificationBellProps) {
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const ref = useRef<HTMLDivElement>(null);

  const visibleAlerts = alerts.filter((a) => !dismissed.has(a.id));
  const unreadCount = visibleAlerts.filter((n) => !n.read).length;

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleMarkAllRead = () => {
    onMarkAllRead?.();
    setDismissed(new Set(alerts.map((a) => a.id)));
  };

  return (
    <div ref={ref} className="relative hidden md:block">
      <button
        onClick={() => setOpen(!open)}
        className="w-8 h-8 rounded-lg flex items-center justify-center text-secondary hover:text-primary hover:bg-surface-secondary transition-colors cursor-pointer relative"
        aria-label="Alerts"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
          <path d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-10 w-80 bg-surface rounded-xl shadow-xl border border-divider overflow-hidden z-50 animate-scale-in">
          <div className="flex items-center justify-between px-4 py-3 border-b border-divider">
            <span className="text-[13px] font-semibold text-primary">Alerts</span>
            {unreadCount > 0 && (
              <button onClick={handleMarkAllRead} className="text-[11px] text-apple-blue hover:underline cursor-pointer">
                Dismiss all
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {visibleAlerts.length === 0 ? (
              <div className="px-4 py-8 text-center text-tertiary text-[12px]">
                No alerts — everything looks good
              </div>
            ) : (
              visibleAlerts.map((n) => (
                <div
                  key={n.id}
                  className={cn(
                    "flex items-start gap-3 px-4 py-3 border-b border-divider last:border-0 transition-colors",
                    !n.read && "bg-surface-secondary"
                  )}
                >
                  <span className="text-[14px] mt-0.5">{typeIcons[n.type] || "\u26A0"}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[9px] font-medium px-1.5 py-px rounded-full bg-surface-tertiary text-secondary">{typeLabels[n.type] || n.type}</span>
                      {n.clientName && <span className="text-[10px] text-tertiary">{n.clientName}</span>}
                    </div>
                    <div className="text-[12px] text-primary mt-0.5">{n.title}</div>
                    {n.detail && <div className="text-[10px] text-tertiary mt-0.5">{n.detail}</div>}
                  </div>
                  <button
                    onClick={() => setDismissed((prev) => new Set([...prev, n.id]))}
                    className="text-[10px] text-tertiary hover:text-primary shrink-0 mt-0.5 cursor-pointer"
                    title="Dismiss"
                  >&times;</button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
