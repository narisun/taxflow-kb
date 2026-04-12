"use client";

import { cn } from "@/lib/utils";

type TabId = "clients" | "chat" | "docs" | "returns";

interface BottomTabBarProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  docBadge?: number;
}

const tabs: { id: TabId; label: string; icon: string }[] = [
  { id: "clients", label: "Clients", icon: "M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" },
  { id: "chat", label: "Chat", icon: "M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" },
  { id: "docs", label: "Docs", icon: "M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" },
  { id: "returns", label: "Returns", icon: "M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" },
];

export function BottomTabBar({ activeTab, onTabChange, docBadge }: BottomTabBarProps) {
  return (
    <nav className="h-14 bg-surface border-t border-divider flex items-stretch shrink-0 z-40 md:hidden">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={cn(
            "flex-1 flex flex-col items-center justify-center gap-0.5 transition-all cursor-pointer relative",
            activeTab === tab.id ? "text-apple-blue" : "text-tertiary"
          )}
          aria-label={tab.label}
        >
          <svg
            className={cn("w-6 h-6 transition-transform", activeTab === tab.id && "scale-110")}
            fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}
          >
            <path d={tab.icon} strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className={cn("text-[10px]", activeTab === tab.id ? "font-medium" : "sr-only")}>
            {tab.label}
          </span>
          {tab.id === "docs" && docBadge && docBadge > 0 && (
            <span className="absolute top-1 right-1/4 w-4 h-4 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
              {docBadge > 9 ? "9+" : docBadge}
            </span>
          )}
        </button>
      ))}
    </nav>
  );
}

export type { TabId };
