"use client";

import { Avatar } from "@/components/ui/avatar";
import { ThemeToggle } from "@/components/layout/theme-toggle";

interface TopBarProps {
  stats: { clients: number; filed: number; review: number };
  deadline: string;
  user: { initials: string; name?: string };
  onMenuToggle?: () => void;
  showMenu?: boolean;
  clientName?: string;
  onDashboard?: () => void;
  onAvatarClick?: () => void;
}

function TopBar({ stats, deadline, user, onMenuToggle, showMenu, clientName, onDashboard, onAvatarClick }: TopBarProps) {
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
          className="lg:hidden w-8 h-8 rounded-lg flex items-center justify-center text-primary hover:bg-surface-secondary transition-colors cursor-pointer"
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
            className="hidden md:flex w-8 h-8 rounded-lg items-center justify-center text-secondary hover:bg-surface-secondary transition-colors cursor-pointer"
            aria-label="Dashboard"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
              <path d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}

        {/* Deadline */}
        <span className="hidden md:inline text-[12px] text-red-500 font-medium bg-surface-secondary px-2.5 py-1 rounded-full">
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
