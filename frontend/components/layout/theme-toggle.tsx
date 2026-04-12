"use client";

import { useTheme } from "@/components/providers/theme-provider";
import { useCallback } from "react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  const cycle = useCallback(() => {
    const next = theme === "system" ? "light" : theme === "light" ? "dark" : "system";
    document.documentElement.classList.add("theme-transitioning");
    setTheme(next);
    setTimeout(() => document.documentElement.classList.remove("theme-transitioning"), 400);
  }, [theme, setTheme]);

  const label =
    theme === "system" ? "System theme" : theme === "light" ? "Light mode" : "Dark mode";

  return (
    <button
      onClick={cycle}
      className="w-8 h-8 rounded-lg flex items-center justify-center text-secondary hover:text-primary hover:bg-surface-secondary transition-colors cursor-pointer"
      aria-label={label}
      title={label}
    >
      {theme === "light" && (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <circle cx="12" cy="12" r="5" />
          <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" strokeLinecap="round" />
        </svg>
      )}
      {theme === "dark" && (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      {theme === "system" && (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <rect x="2" y="3" width="20" height="14" rx="2" />
          <path d="M8 21h8M12 17v4" strokeLinecap="round" />
        </svg>
      )}
    </button>
  );
}
