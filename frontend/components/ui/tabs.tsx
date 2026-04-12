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
    <div className={cn("flex border-b border-gray-200", className)}>
      {tabs.map((tab) => (
        <button
          key={tab}
          onClick={() => onTabChange(tab)}
          className={cn(
            "px-4 py-2 text-[13px] font-medium transition-colors cursor-pointer",
            tab === activeTab
              ? "text-[#0071e3] border-b-2 border-[#0071e3]"
              : "text-gray-500 hover:text-gray-900"
          )}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}

export { Tabs, type TabsProps };
