"use client";

import { useState, useRef, useEffect } from "react";
import { Avatar } from "@/components/ui/avatar";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { NotificationBell } from "@/components/notifications/notification-bell";
import { cn } from "@/lib/utils";

interface TopBarProps {
  stats: { clients: number; filed: number; review: number };
  deadline: string;
  user: { initials: string; name?: string };
  onMenuToggle?: () => void;
  showMenu?: boolean;
  clientName?: string;
  onDashboard?: () => void;
  onAvatarClick?: () => void;
  onInbox?: () => void;
  inboxUnread?: number;
}

const irsNewsItems = [
  { id: 1, title: "EITC refunds released — check Where\u2019s My Refund tool", date: "Apr 11", category: "Refunds" },
  { id: 2, title: "Form 1099-K reporting threshold remains $5,000 for 2025", date: "Apr 10", category: "Compliance" },
  { id: 3, title: "Direct File expanded to 25 states for TY 2025", date: "Apr 8", category: "E-File" },
  { id: 4, title: "IRS processed over 90 million returns this filing season", date: "Apr 7", category: "Stats" },
  { id: 5, title: "Free File available for taxpayers with AGI $84,000 or less", date: "Apr 3", category: "Resources" },
  { id: 6, title: "Estimated tax payment Q1 deadline April 15", date: "Mar 28", category: "Deadlines" },
  { id: 7, title: "IRS warns of new phishing scams targeting tax professionals", date: "Mar 25", category: "Security" },
  { id: 8, title: "Standard mileage rate set at 70 cents per mile for 2025", date: "Mar 20", category: "Deductions" },
];

function IrsNewsFeed({ deadline }: { deadline: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const latest = irsNewsItems[0];
  void deadline; // used by parent for positioning

  return (
    <div ref={ref} className="hidden lg:flex items-center relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 max-w-[240px] xl:max-w-[320px] hover:bg-surface-secondary px-2 py-1 rounded-md transition-colors cursor-pointer"
      >
        <span className="text-[10px] font-semibold text-tertiary uppercase shrink-0">IRS</span>
        <span className="text-[11px] text-secondary truncate">{latest.title}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-10 w-96 bg-surface rounded-xl shadow-xl border border-divider overflow-hidden z-50 animate-scale-in">
          <div className="flex items-center justify-between px-4 py-3 border-b border-divider">
            <span className="text-[13px] font-semibold text-primary">IRS News &amp; Updates</span>
            <span className="text-[10px] text-tertiary">irs.gov/newsroom</span>
          </div>
          <div className="max-h-80 overflow-y-auto scroll-visible">
            {irsNewsItems.map((item) => (
              <div key={item.id} className="px-4 py-3 border-b border-divider last:border-0 hover:bg-surface-secondary transition-colors">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-[9px] font-medium px-1.5 py-px rounded-full bg-surface-tertiary text-secondary">{item.category}</span>
                  <span className="text-[10px] text-tertiary">{item.date}</span>
                </div>
                <div className="text-[12px] text-primary leading-relaxed">{item.title}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TopBar({ stats, deadline, user, onMenuToggle, showMenu, clientName, onDashboard, onAvatarClick, onInbox, inboxUnread }: TopBarProps) {
  return (
    <nav
      className="h-12 max-md:h-10 flex items-center px-4 gap-4 shrink-0 z-50 border-b"
      style={{
        background: "var(--t-nav-bg)",
        backdropFilter: "saturate(180%) blur(20px)",
        WebkitBackdropFilter: "saturate(180%) blur(20px)",
        borderColor: "var(--t-nav-border)",
      }}
    >
      {/* Hamburger — tablet and below */}
      {showMenu && (
        <button
          onClick={onMenuToggle}
          className="lg:hidden w-8 h-8 rounded-lg flex items-center justify-center text-secondary hover:text-primary hover:bg-surface-secondary transition-colors cursor-pointer"
          aria-label="Toggle client sidebar"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
            <path d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}

      {/* Logo */}
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 bg-apple-blue rounded-md flex items-center justify-center text-white text-[13px] font-bold">
          T
        </div>
        <span className="text-primary text-[14px] font-semibold tracking-tight max-md:hidden">
          TaxFlow AI
        </span>
      </div>

      {/* Mobile: client name */}
      {clientName && (
        <span className="md:hidden text-[13px] font-medium text-primary truncate flex-1 text-center">
          {clientName}
        </span>
      )}

      {/* Spacer — desktop */}
      <div className="flex-1 max-md:hidden" />

      {/* IRS News — left of stats */}
      <IrsNewsFeed deadline={deadline} />

      {/* Stats — desktop only */}
      <div className="hidden lg:flex items-center gap-4 text-[12px] text-secondary">
        <span>
          <span className="text-primary font-medium">{stats.clients}</span> clients
        </span>
        <span className="text-[10px] text-tertiary">&middot;</span>
        <span>
          <span className="text-green-500 font-medium">{stats.filed}</span> filed
        </span>
        <span className="text-[10px] text-tertiary">&middot;</span>
        <span>
          <span className="text-orange-500 font-medium">{stats.review}</span> review
        </span>
      </div>

      {/* Right cluster */}
      <div className="flex items-center gap-2">
        {/* Dashboard icon */}
        {onDashboard && (
          <button
            onClick={onDashboard}
            className="hidden md:flex w-8 h-8 rounded-lg items-center justify-center text-secondary hover:text-primary hover:bg-surface-secondary transition-colors cursor-pointer"
            aria-label="Dashboard"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
              <path d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}

        {/* Inbox */}
        {onInbox && (
          <button
            onClick={onInbox}
            className="hidden md:flex w-8 h-8 rounded-lg items-center justify-center text-secondary hover:text-primary hover:bg-surface-secondary transition-colors cursor-pointer relative"
            aria-label="Inbox"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
              <path d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {inboxUnread != null && inboxUnread > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
                {inboxUnread > 9 ? "9+" : inboxUnread}
              </span>
            )}
          </button>
        )}

        <NotificationBell />

        {/* Deadline */}
        <span className="hidden md:inline text-[12px] text-red-500 font-medium bg-surface-secondary px-2.5 py-1 rounded-full shrink-0">
          {deadline}
        </span>

        <ThemeToggle />

        {/* User avatar */}
        <button onClick={onAvatarClick} className="hidden md:block cursor-pointer">
          <Avatar initials={user.initials} size="sm" color="#6B7280" />
        </button>
      </div>
    </nav>
  );
}

export { TopBar, type TopBarProps };
