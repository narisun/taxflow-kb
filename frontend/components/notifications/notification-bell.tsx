// frontend/components/notifications/notification-bell.tsx
"use client";

import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";

interface Notification {
  id: number;
  type: "document" | "return" | "message" | "deadline" | "system";
  title: string;
  time: string;
  read: boolean;
}

const mockNotifications: Notification[] = [
  { id: 1, type: "document", title: "W-2 uploaded for Sarah Johnson", time: "2h ago", read: false },
  { id: 2, type: "return", title: "Draft return generated for Mike Chen", time: "5h ago", read: false },
  { id: 3, type: "message", title: "New response for Lisa Park's query", time: "8h ago", read: true },
  { id: 4, type: "deadline", title: "April 15 deadline \u2014 8 returns pending", time: "1d ago", read: true },
  { id: 5, type: "system", title: "TaxFlow AI updated to v0.1.0", time: "2d ago", read: true },
];

const typeIcons: Record<string, string> = {
  document: "\u2B06",
  return: "\uD83D\uDCC4",
  message: "\uD83D\uDCAC",
  deadline: "\u23F0",
  system: "\u2139\uFE0F",
};

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState(mockNotifications);
  const ref = useRef<HTMLDivElement>(null);

  const unreadCount = notifications.filter((n) => !n.read).length;

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const markAllRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  };

  return (
    <div ref={ref} className="relative hidden md:block">
      <button
        onClick={() => setOpen(!open)}
        className="w-8 h-8 rounded-lg flex items-center justify-center text-current opacity-70 hover:opacity-100 hover:bg-white/10 transition-all cursor-pointer relative"
        aria-label="Notifications"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
          <path d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
            {unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-10 w-80 bg-surface rounded-xl shadow-xl border border-divider overflow-hidden z-50 animate-scale-in">
          <div className="flex items-center justify-between px-4 py-3 border-b border-divider">
            <span className="text-[13px] font-semibold text-primary">Notifications</span>
            {unreadCount > 0 && (
              <button onClick={markAllRead} className="text-[11px] text-apple-blue hover:underline cursor-pointer">
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {notifications.map((n) => (
              <div
                key={n.id}
                className={cn(
                  "flex items-start gap-3 px-4 py-3 border-b border-divider last:border-0 transition-colors",
                  !n.read && "bg-surface-secondary"
                )}
              >
                <span className="text-[14px] mt-0.5">{typeIcons[n.type]}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-[12px] text-primary">{n.title}</div>
                  <div className="text-[11px] text-tertiary mt-0.5">{n.time}</div>
                </div>
                {!n.read && <div className="w-2 h-2 bg-apple-blue rounded-full shrink-0 mt-1.5" />}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
