"use client";

import { cn } from "@/lib/utils";

interface TabsProps {
  tabs: string[];
  activeTab: string;
  onTabChange: (tab: string) => void;
  className?: string;
}

function Tabs({ tabs, activeTab, onTabChange, className }: TabsProps) {
  return (
    <div className={cn("flex border-b border-divider", className)} role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab}
          onClick={() => onTabChange(tab)}
          role="tab"
          aria-selected={tab === activeTab}
          className={cn(
            "px-4 py-2 text-[13px] font-medium transition-colors cursor-pointer",
            tab === activeTab
              ? "text-apple-blue border-b-2 border-apple-blue"
              : "text-secondary hover:text-primary"
          )}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}

export { Tabs, type TabsProps };
