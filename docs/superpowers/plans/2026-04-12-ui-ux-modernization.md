# UI/UX Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modernize the TaxFlow AI frontend with theme support (dark/light/system), responsive layout (desktop → mobile), Apple-style translucent top bar, micro-interactions, and new pages (settings, notifications, onboarding, analytics dashboard).

**Architecture:** Theme via React context + `data-theme` attribute on `<html>` driving CSS custom properties. Responsive via Tailwind breakpoints with progressive panel disclosure. New components are self-contained with placeholder data.

**Tech Stack:** Next.js 16, React 19, TypeScript 5, Tailwind CSS 4 (v4 `@theme` directive), CSS custom properties

**Spec:** `docs/superpowers/specs/2026-04-12-ui-ux-modernization-design.md`

---

## Task 1: Theme Provider & CSS Token System

**Files:**
- Create: `frontend/components/providers/theme-provider.tsx`
- Modify: `frontend/app/globals.css`
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/app/providers.tsx`

This is the foundation — every subsequent task depends on it.

- [ ] **Step 1: Create the ThemeProvider component**

```tsx
// frontend/components/providers/theme-provider.tsx
"use client";

import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";

type Theme = "light" | "dark" | "system";
type ResolvedTheme = "light" | "dark";

interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function getStoredTheme(): Theme {
  if (typeof window === "undefined") return "system";
  return (localStorage.getItem("taxflow-theme") as Theme) || "system";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("system");
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("light");

  const applyTheme = useCallback((t: Theme) => {
    const resolved = t === "system" ? getSystemTheme() : t;
    setResolvedTheme(resolved);
    document.documentElement.setAttribute("data-theme", resolved);
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    localStorage.setItem("taxflow-theme", t);
    applyTheme(t);
  }, [applyTheme]);

  // Initialize on mount
  useEffect(() => {
    const stored = getStoredTheme();
    setThemeState(stored);
    applyTheme(stored);
  }, [applyTheme]);

  // Listen for OS theme changes when in system mode
  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyTheme("system");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme, applyTheme]);

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
```

- [ ] **Step 2: Rewrite globals.css with theme-aware tokens**

Replace the entire `frontend/app/globals.css` with:

```css
@import "tailwindcss";

/* =====================================================
   Apple Design Token Theme (Tailwind v4 @theme)
   ===================================================== */
@theme {
  /* Brand colors — constant across themes */
  --color-apple-blue: #0071e3;
  --color-link-blue: #0066cc;
  --color-bright-blue: #2997ff;

  /* Semantic surface aliases — resolved by data-theme */
  --color-bg: var(--t-bg);
  --color-surface: var(--t-surface);
  --color-surface-secondary: var(--t-surface-secondary);
  --color-surface-tertiary: var(--t-surface-tertiary);

  /* Semantic text aliases */
  --color-primary: var(--t-text);
  --color-secondary: var(--t-text-secondary);
  --color-tertiary: var(--t-text-tertiary);

  /* Semantic border */
  --color-divider: var(--t-divider);

  /* Chat */
  --color-chat-user: var(--t-chat-user);
  --color-chat-assistant: var(--t-chat-assistant);

  /* Nav */
  --color-nav-bg: var(--t-nav-bg);
  --color-nav-border: var(--t-nav-border);

  /* Form */
  --color-form-header: var(--t-form-header);

  /* Badge tokens */
  --color-badge-pending-bg: var(--t-badge-pending-bg);
  --color-badge-pending-text: var(--t-badge-pending-text);
  --color-badge-progress-bg: var(--t-badge-progress-bg);
  --color-badge-progress-text: var(--t-badge-progress-text);
  --color-badge-review-bg: var(--t-badge-review-bg);
  --color-badge-review-text: var(--t-badge-review-text);
  --color-badge-complete-bg: var(--t-badge-complete-bg);
  --color-badge-complete-text: var(--t-badge-complete-text);
  --color-badge-filed-bg: var(--t-badge-filed-bg);
  --color-badge-filed-text: var(--t-badge-filed-text);

  /* Font families */
  --font-display: "SF Pro Display", "SF Pro Icons", "Helvetica Neue", Helvetica, Arial, sans-serif;
  --font-body: "SF Pro Text", "SF Pro Icons", "Helvetica Neue", Helvetica, Arial, sans-serif;

  /* Letter spacing */
  --tracking-apple-display: -0.28px;
  --tracking-apple-body: -0.374px;
  --tracking-apple-caption: -0.224px;
  --tracking-apple-micro: -0.12px;

  /* Border radius */
  --radius-pill: 980px;

  /* Backdrop blur */
  --blur-apple: 20px;
}

/* =====================================================
   Light Theme Tokens
   ===================================================== */
[data-theme="light"] {
  --t-bg: #f5f5f7;
  --t-surface: #ffffff;
  --t-surface-secondary: #f5f5f7;
  --t-surface-tertiary: #e8e8ed;
  --t-text: #1d1d1f;
  --t-text-secondary: #6e6e73;
  --t-text-tertiary: #86868b;
  --t-divider: rgba(0, 0, 0, 0.1);
  --t-nav-bg: rgba(255, 255, 255, 0.72);
  --t-nav-border: rgba(0, 0, 0, 0.1);
  --t-chat-user: #e8edf2;
  --t-chat-assistant: #f5f5f7;
  --t-form-header: #1E3A5F;
  --t-shadow: rgba(0, 0, 0, 0.12);

  --t-badge-pending-bg: #f3f4f6;
  --t-badge-pending-text: #4b5563;
  --t-badge-progress-bg: #dbeafe;
  --t-badge-progress-text: #1d4ed8;
  --t-badge-review-bg: #ffedd5;
  --t-badge-review-text: #c2410c;
  --t-badge-complete-bg: #dcfce7;
  --t-badge-complete-text: #15803d;
  --t-badge-filed-bg: #f3e8ff;
  --t-badge-filed-text: #7e22ce;

  color-scheme: light;
}

/* =====================================================
   Dark Theme Tokens
   ===================================================== */
[data-theme="dark"] {
  --t-bg: #000000;
  --t-surface: #1c1c1e;
  --t-surface-secondary: #2c2c2e;
  --t-surface-tertiary: #3a3a3c;
  --t-text: #f5f5f7;
  --t-text-secondary: #a1a1a6;
  --t-text-tertiary: #6e6e73;
  --t-divider: rgba(255, 255, 255, 0.08);
  --t-nav-bg: rgba(29, 29, 31, 0.72);
  --t-nav-border: rgba(255, 255, 255, 0.08);
  --t-chat-user: #2c2c2e;
  --t-chat-assistant: #1c1c1e;
  --t-form-header: #2a4a6f;
  --t-shadow: rgba(0, 0, 0, 0.4);

  --t-badge-pending-bg: rgba(142, 142, 147, 0.2);
  --t-badge-pending-text: #a1a1a6;
  --t-badge-progress-bg: rgba(10, 132, 255, 0.2);
  --t-badge-progress-text: #64d2ff;
  --t-badge-review-bg: rgba(255, 159, 10, 0.2);
  --t-badge-review-text: #ffd60a;
  --t-badge-complete-bg: rgba(48, 209, 88, 0.2);
  --t-badge-complete-text: #30d158;
  --t-badge-filed-bg: rgba(191, 90, 242, 0.2);
  --t-badge-filed-text: #bf5af2;

  color-scheme: dark;
}

/* =====================================================
   Theme Transition (applied temporarily during toggle)
   ===================================================== */
html.theme-transitioning,
html.theme-transitioning * {
  transition: background-color 300ms ease, color 200ms ease, border-color 200ms ease !important;
}

/* =====================================================
   Base Layer Styles
   ===================================================== */
@layer base {
  html {
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  body {
    font-family: "SF Pro Text", "SF Pro Icons", "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 17px;
    line-height: 1.47;
    letter-spacing: -0.374px;
    color: var(--t-text);
    background-color: var(--t-surface);
  }

  h1, h2, h3 {
    font-family: "SF Pro Display", "SF Pro Icons", "Helvetica Neue", Helvetica, Arial, sans-serif;
  }
}

/* =====================================================
   Animation Keyframes
   ===================================================== */
@keyframes message-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slide-up {
  from { transform: translateY(100%); }
  to { transform: translateY(0); }
}

@keyframes slide-in-left {
  from { transform: translateX(-100%); }
  to { transform: translateX(0); }
}

@keyframes slide-in-right {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

@keyframes scale-in {
  from {
    opacity: 0;
    transform: scale(0.97);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes pulse-skeleton {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

@layer utilities {
  .animate-message-in {
    animation: message-in 200ms ease-out both;
  }
  .animate-fade-in {
    animation: fade-in 200ms ease both;
  }
  .animate-slide-up {
    animation: slide-up 300ms ease-out both;
  }
  .animate-slide-in-left {
    animation: slide-in-left 300ms cubic-bezier(0.4, 0, 0.2, 1) both;
  }
  .animate-slide-in-right {
    animation: slide-in-right 300ms cubic-bezier(0.4, 0, 0.2, 1) both;
  }
  .animate-scale-in {
    animation: scale-in 200ms ease both;
  }
  .animate-skeleton {
    animation: pulse-skeleton 1.5s ease-in-out infinite;
  }
}
```

- [ ] **Step 3: Wire ThemeProvider into the app**

Modify `frontend/app/providers.tsx` — add ThemeProvider as an outer wrapper:

```tsx
"use client";

import { createContext, useContext, useState, ReactNode } from "react";
import { ThemeProvider } from "@/components/providers/theme-provider";
import type { Client, ChatMessage, Document } from "@/lib/api-client";

interface AppState {
  activeClientId: number | null;
  setActiveClientId: (id: number | null) => void;
  clients: Client[];
  setClients: (c: Client[]) => void;
  messages: ChatMessage[];
  setMessages: (m: ChatMessage[]) => void;
  documents: Document[];
  setDocuments: (d: Document[]) => void;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeClientId, setActiveClientId] = useState<number | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);

  return (
    <ThemeProvider>
      <AppContext.Provider
        value={{
          activeClientId, setActiveClientId,
          clients, setClients,
          messages, setMessages,
          documents, setDocuments,
        }}
      >
        {children}
      </AppContext.Provider>
    </ThemeProvider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
```

- [ ] **Step 4: Add `data-theme` default to layout.tsx to prevent flash**

```tsx
// frontend/app/layout.tsx
import type { Metadata } from "next";
import "./globals.css";
import { AppProvider } from "./providers";

export const metadata: Metadata = {
  title: "TaxFlow AI — CPA Platform",
  description: "AI-powered tax preparation platform for CPAs",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full" data-theme="light" suppressHydrationWarning>
      <body className="h-screen overflow-hidden flex flex-col" suppressHydrationWarning>
        <AppProvider>{children}</AppProvider>
      </body>
    </html>
  );
}
```

- [ ] **Step 5: Verify the app builds and renders**

Run: `cd frontend && npm run build`

Expected: Build succeeds with no errors. The app renders in light mode by default.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/providers/theme-provider.tsx frontend/app/globals.css frontend/app/layout.tsx frontend/app/providers.tsx
git commit -m "feat(frontend): add theme provider and CSS token system (dark/light/system)"
```

---

## Task 2: Theme Toggle Component

**Files:**
- Create: `frontend/components/layout/theme-toggle.tsx`

- [ ] **Step 1: Create the theme toggle button**

```tsx
// frontend/components/layout/theme-toggle.tsx
"use client";

import { useTheme } from "@/components/providers/theme-provider";
import { useCallback } from "react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  const cycle = useCallback(() => {
    const next = theme === "system" ? "light" : theme === "light" ? "dark" : "system";
    // Add temporary transition class
    document.documentElement.classList.add("theme-transitioning");
    setTheme(next);
    setTimeout(() => document.documentElement.classList.remove("theme-transitioning"), 400);
  }, [theme, setTheme]);

  const label =
    theme === "system" ? "System theme" : theme === "light" ? "Light mode" : "Dark mode";

  return (
    <button
      onClick={cycle}
      className="w-8 h-8 rounded-lg flex items-center justify-center text-secondary hover:bg-surface-secondary transition-colors cursor-pointer"
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
```

- [ ] **Step 2: Verify it renders**

Run: `cd frontend && npm run build`

Expected: Build succeeds. (Component isn't mounted yet — that happens in Task 3.)

- [ ] **Step 3: Commit**

```bash
git add frontend/components/layout/theme-toggle.tsx
git commit -m "feat(frontend): add theme toggle component (sun/moon/monitor cycle)"
```

---

## Task 3: Migrate All UI Components to Theme Tokens

**Files:**
- Modify: `frontend/components/ui/button.tsx`
- Modify: `frontend/components/ui/card.tsx`
- Modify: `frontend/components/ui/modal.tsx`
- Modify: `frontend/components/ui/input.tsx`
- Modify: `frontend/components/ui/badge.tsx`
- Modify: `frontend/components/ui/avatar.tsx`
- Modify: `frontend/components/ui/progress.tsx`
- Modify: `frontend/components/ui/tabs.tsx`

- [ ] **Step 1: Migrate button.tsx**

Replace the `variantClasses` and focus class in `frontend/components/ui/button.tsx`:

```tsx
import { cn } from "@/lib/utils";
import { type ButtonHTMLAttributes, forwardRef } from "react";

type ButtonVariant = "primary" | "secondary" | "pill" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-apple-blue text-white rounded-lg px-4 py-2 text-[17px] hover:brightness-110 active:scale-[0.98]",
  secondary:
    "bg-primary text-surface rounded-lg px-4 py-2 text-[17px] active:scale-[0.98]",
  pill:
    "bg-transparent text-apple-blue border border-apple-blue rounded-[980px] px-4 py-2 text-[14px] hover:underline active:scale-[0.98]",
  ghost:
    "bg-transparent text-apple-blue text-[14px] hover:underline",
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", className, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "focus-visible:outline-2 focus-visible:outline-apple-blue focus-visible:outline-offset-2 transition-all cursor-pointer",
          variantClasses[variant],
          className
        )}
        {...props}
      >
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";

export { Button, type ButtonProps, type ButtonVariant };
```

- [ ] **Step 2: Migrate card.tsx**

```tsx
import { cn } from "@/lib/utils";

interface CardProps {
  elevated?: boolean;
  children: React.ReactNode;
  className?: string;
}

function Card({ elevated = false, children, className }: CardProps) {
  return (
    <div
      className={cn(
        "bg-surface-secondary rounded-xl p-4",
        elevated && "shadow-lg",
        className
      )}
    >
      {children}
    </div>
  );
}

export { Card, type CardProps };
```

- [ ] **Step 3: Migrate modal.tsx**

```tsx
"use client";

import { cn } from "@/lib/utils";
import { useEffect, type ReactNode } from "react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}

function Modal({ open, onClose, children, className }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center animate-fade-in"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={cn(
          "bg-surface rounded-2xl shadow-2xl max-h-[calc(100vh-48px)] overflow-hidden animate-scale-in w-full mx-4",
          className
        )}
      >
        {children}
      </div>
    </div>
  );
}

function ModalHeader({ children, onClose }: { children: ReactNode; onClose?: () => void }) {
  return (
    <div className="flex items-center justify-between px-6 py-4 border-b border-divider">
      <div className="text-[17px] font-semibold text-primary">{children}</div>
      {onClose && (
        <button
          onClick={onClose}
          className="rounded-lg border border-divider px-2 py-1 text-[13px] text-secondary hover:bg-surface-tertiary hover:text-primary transition-colors cursor-pointer"
        >
          Close
        </button>
      )}
    </div>
  );
}

function ModalBody({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("px-6 py-4 overflow-y-auto", className)}>{children}</div>
  );
}

function ModalFooter({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("px-6 py-4 border-t border-divider flex justify-end gap-2", className)}>
      {children}
    </div>
  );
}

export { Modal, ModalHeader, ModalBody, ModalFooter, type ModalProps };
```

- [ ] **Step 4: Migrate input.tsx**

```tsx
import { cn } from "@/lib/utils";
import { type InputHTMLAttributes, forwardRef } from "react";

type InputValidation = "default" | "ok" | "warning" | "error";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  validation?: InputValidation;
}

const validationClasses: Record<InputValidation, string> = {
  default: "border-divider focus:border-apple-blue",
  ok: "border-green-500 bg-green-50 dark:bg-green-950/30",
  warning: "border-orange-500 bg-orange-50 dark:bg-orange-950/30",
  error: "border-red-500 bg-red-50 dark:bg-red-950/30",
};

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ validation = "default", className, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(
          "border-[1.5px] rounded-lg px-3 py-2 text-[13px] outline-none transition-colors w-full bg-surface text-primary placeholder:text-tertiary",
          validationClasses[validation],
          className
        )}
        {...props}
      />
    );
  }
);

Input.displayName = "Input";

export { Input, type InputProps, type InputValidation };
```

- [ ] **Step 5: Migrate badge.tsx**

```tsx
import { cn } from "@/lib/utils";

type BadgeVariant = "pending" | "inProgress" | "review" | "completed" | "filed";

interface BadgeProps {
  variant: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  pending: "bg-badge-pending-bg text-badge-pending-text",
  inProgress: "bg-badge-progress-bg text-badge-progress-text",
  review: "bg-badge-review-bg text-badge-review-text",
  completed: "bg-badge-complete-bg text-badge-complete-text",
  filed: "bg-badge-filed-bg text-badge-filed-text",
};

function Badge({ variant, children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full inline-block",
        variantClasses[variant],
        className
      )}
    >
      {children}
    </span>
  );
}

export { Badge, type BadgeProps, type BadgeVariant };
```

- [ ] **Step 6: Migrate avatar.tsx**

```tsx
import { cn } from "@/lib/utils";

type AvatarSize = "sm" | "md" | "lg";

interface AvatarProps {
  initials: string;
  color?: string;
  size?: AvatarSize;
  className?: string;
}

const sizeClasses: Record<AvatarSize, string> = {
  sm: "w-6 h-6 text-[10px]",
  md: "w-8 h-8 text-[13px]",
  lg: "w-10 h-10 text-[15px]",
};

function Avatar({ initials, color = "#0071e3", size = "md", className }: AvatarProps) {
  return (
    <div
      className={cn(
        "rounded-lg flex items-center justify-center font-bold text-white shrink-0",
        sizeClasses[size],
        className
      )}
      style={{ backgroundColor: color }}
    >
      {initials}
    </div>
  );
}

export { Avatar, type AvatarProps, type AvatarSize };
```

Note: Avatar keeps inline `style={{ backgroundColor: color }}` since avatar colors are per-client, not theme-dependent.

- [ ] **Step 7: Migrate progress.tsx**

```tsx
import { cn } from "@/lib/utils";

type ProgressColor = "default" | "blue" | "green" | "orange" | "red";

interface ProgressProps {
  value: number;
  color?: ProgressColor;
  className?: string;
}

const colorClasses: Record<ProgressColor, string> = {
  default: "bg-tertiary",
  blue: "bg-apple-blue",
  green: "bg-green-500",
  orange: "bg-orange-500",
  red: "bg-red-500",
};

function Progress({ value, color = "default", className }: ProgressProps) {
  const clampedValue = Math.min(100, Math.max(0, value));

  return (
    <div className={cn("h-1 bg-surface-tertiary rounded-full overflow-hidden", className)}>
      <div
        className={cn("h-full rounded-full transition-all", colorClasses[color])}
        style={{ width: `${clampedValue}%` }}
      />
    </div>
  );
}

export { Progress, type ProgressProps, type ProgressColor };
```

- [ ] **Step 8: Migrate tabs.tsx**

```tsx
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
```

- [ ] **Step 9: Verify build**

Run: `cd frontend && npm run build`

Expected: Build succeeds with no errors.

- [ ] **Step 10: Commit**

```bash
git add frontend/components/ui/
git commit -m "feat(frontend): migrate all UI components to semantic theme tokens"
```

---

## Task 4: Top Bar Redesign with Theme-Aware Glass

**Files:**
- Modify: `frontend/components/layout/top-bar.tsx`

- [ ] **Step 1: Rewrite top-bar.tsx**

```tsx
// frontend/components/layout/top-bar.tsx
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
}

function TopBar({ stats, deadline, user, onMenuToggle, showMenu, clientName, onDashboard }: TopBarProps) {
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
          className="md:hidden w-8 h-8 rounded-lg flex items-center justify-center text-primary hover:bg-surface-secondary transition-colors cursor-pointer"
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
        {/* Dashboard icon — desktop/tablet */}
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

        {/* Deadline — hidden on mobile */}
        <span className="hidden md:inline text-[12px] text-red-500 font-medium bg-surface-secondary px-2.5 py-1 rounded-full">
          {deadline}
        </span>

        <ThemeToggle />

        {/* User avatar — hidden on mobile */}
        <div className="hidden md:block">
          <Avatar initials={user.initials} size="sm" color="#6B7280" />
        </div>
      </div>
    </nav>
  );
}

export { TopBar, type TopBarProps };
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/layout/top-bar.tsx
git commit -m "feat(frontend): redesign top bar with theme-aware glass and responsive layout"
```

---

## Task 5: Migrate Chat Components to Theme Tokens

**Files:**
- Modify: `frontend/components/chat/message-bubble.tsx`
- Modify: `frontend/components/chat/message-list.tsx`
- Modify: `frontend/components/chat/chat-input.tsx`
- Modify: `frontend/components/chat/typing-indicator.tsx`

- [ ] **Step 1: Migrate message-bubble.tsx**

```tsx
"use client";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  userInitials?: string;
}

export function MessageBubble({ role, content, timestamp, userInitials = "SC" }: MessageBubbleProps) {
  const isUser = role === "user";

  return (
    <div className={`flex gap-2.5 animate-message-in ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="w-7 h-7 bg-apple-blue rounded-md flex items-center justify-center text-white text-[12px] font-bold shrink-0 mt-0.5">
          T
        </div>
      )}
      <div className="flex flex-col max-w-[min(70%,560px)] max-md:max-w-[85%]">
        <div
          className={
            isUser
              ? "bg-chat-user rounded-2xl px-4 py-3 text-[13px] leading-relaxed text-primary"
              : "bg-chat-assistant rounded-2xl px-4 py-3 text-[13px] leading-relaxed text-primary"
          }
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{content}</p>
          ) : (
            <div
              className="whitespace-pre-wrap [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-4 [&_ol]:list-decimal [&_ol]:pl-4"
              dangerouslySetInnerHTML={{ __html: content }}
            />
          )}
        </div>
        {timestamp && (
          <span
            className={`text-[10px] mt-1 text-tertiary ${isUser ? "text-right" : ""}`}
          >
            {timestamp}
          </span>
        )}
      </div>
      {isUser && (
        <div className="w-7 h-7 bg-[#6B7280] rounded-md flex items-center justify-center text-white text-[10px] font-bold shrink-0 mt-0.5">
          {userInitials}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Migrate message-list.tsx**

```tsx
"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { MessageBubble } from "./message-bubble";
import { TypingIndicator } from "./typing-indicator";

interface Message {
  id: number | string;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  timestamp?: string;
}

interface MessageListProps {
  messages: Message[];
  isTyping?: boolean;
}

export function MessageList({ messages, isTyping = false }: MessageListProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  // Auto-scroll when new messages arrive (if user hasn't scrolled up)
  useEffect(() => {
    if (autoScroll) scrollToBottom();
  }, [messages, isTyping, autoScroll, scrollToBottom]);

  // Detect user scroll position
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setAutoScroll(distanceFromBottom < 100);
  }, []);

  return (
    <div className="relative flex-1 overflow-hidden">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="h-full overflow-y-auto px-5 py-4 pb-2 space-y-4"
      >
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-tertiary">
            <svg className="w-10 h-10 mb-3 text-tertiary" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1}>
              <path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <p className="text-[13px]">
              Start a conversation about this client&apos;s tax return.
            </p>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              role={msg.role}
              content={msg.content}
              timestamp={msg.timestamp || msg.created_at}
            />
          ))
        )}
        {isTyping && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* "New messages" pill — shown when user scrolled up */}
      {!autoScroll && (
        <button
          onClick={() => { setAutoScroll(true); scrollToBottom(); }}
          className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-surface text-primary text-[12px] px-3 py-1.5 rounded-full shadow-md border border-divider animate-fade-in cursor-pointer hover:bg-surface-secondary transition-colors"
        >
          &darr; New messages
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Migrate chat-input.tsx**

```tsx
"use client";

import { useState, useRef, useCallback, KeyboardEvent } from "react";

interface ChatInputProps {
  onSend: (message: string) => void;
  onAttach?: () => void;
  disabled?: boolean;
  hints?: string[];
}

export function ChatInput({
  onSend,
  onAttach,
  disabled = false,
  hints = ["Refund estimate", "Missing docs", "Year-over-year", "Credits check"],
}: ChatInputProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [input, onSend]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  };

  return (
    <div className="shrink-0 px-5 max-md:px-3 pb-4 pt-2">
      <div className="flex items-end gap-2.5 bg-surface/95 backdrop-blur-sm border border-divider rounded-2xl px-4 py-3 shadow-md transition-all focus-within:border-apple-blue focus-within:shadow-lg hover:shadow-md">
        <button
          onClick={onAttach}
          className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-tertiary hover:text-apple-blue hover:bg-surface-secondary transition-colors cursor-pointer text-[15px]"
          title="Attach file"
        >
          &#128206;
        </button>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about this return, or instruct the AI..."
          rows={2}
          disabled={disabled}
          className="flex-1 resize-none bg-transparent text-[14px] text-primary outline-none min-h-[48px] max-h-[120px] leading-relaxed placeholder:text-tertiary disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || disabled}
          className="shrink-0 w-9 h-9 rounded-xl bg-apple-blue text-white flex items-center justify-center hover:brightness-110 transition-all cursor-pointer text-[15px] disabled:opacity-30 shadow-sm"
          title="Send"
        >
          &#10148;
        </button>
      </div>

      {/* Quick hint chips — hidden on mobile */}
      <div className="hidden md:flex gap-2 mt-2 flex-wrap">
        {hints.map((hint) => (
          <button
            key={hint}
            onClick={() => {
              setInput(hint);
              textareaRef.current?.focus();
            }}
            className="text-[11px] px-3 py-1 rounded-full border border-divider bg-surface text-secondary hover:border-apple-blue hover:text-apple-blue hover:bg-surface-secondary transition-all cursor-pointer"
          >
            {hint}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Migrate typing-indicator.tsx**

```tsx
"use client";

export function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-chat-assistant rounded-xl px-4 py-3 flex items-center gap-1">
        <span className="w-2 h-2 bg-tertiary rounded-full animate-bounce [animation-delay:0ms] [animation-duration:1s]" />
        <span className="w-2 h-2 bg-tertiary rounded-full animate-bounce [animation-delay:150ms] [animation-duration:1s]" />
        <span className="w-2 h-2 bg-tertiary rounded-full animate-bounce [animation-delay:300ms] [animation-duration:1s]" />
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Verify build**

Run: `cd frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/chat/
git commit -m "feat(frontend): migrate chat components to theme tokens, add smart scroll"
```

---

## Task 6: Migrate Layout Components (Sidebar, Forms, Returns, Document Viewer)

**Files:**
- Modify: `frontend/components/layout/client-sidebar.tsx`
- Modify: `frontend/components/forms/w2-form.tsx`
- Modify: `frontend/components/forms/form-1099-int.tsx`
- Modify: `frontend/components/forms/generic-form.tsx`
- Modify: `frontend/components/returns/return-preview.tsx`
- Modify: `frontend/components/clients/intake-modal.tsx`
- Modify: `frontend/components/documents/document-viewer-modal.tsx`

- [ ] **Step 1: Migrate client-sidebar.tsx**

```tsx
"use client";

import { cn } from "@/lib/utils";
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
  onNewIntake?: () => void;
}

const statusLabels: Record<string, string> = {
  pending: "Pending",
  inProgress: "In Progress",
  review: "Review",
  completed: "Completed",
  filed: "Filed",
};

function ClientSidebar({ clients, activeClientId, onSelectClient, onNewIntake }: ClientSidebarProps) {
  const [search, setSearch] = useState("");

  const filtered = clients.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.meta.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <aside className="w-72 shrink-0 bg-bg border-r border-divider flex flex-col overflow-hidden">
      {/* Search */}
      <div className="p-3">
        <div className="relative">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-tertiary"
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
            className="w-full pl-8 pr-3 py-1.5 text-[12px] bg-surface border border-divider rounded-lg outline-none focus:border-apple-blue transition-colors text-primary placeholder:text-tertiary"
          />
        </div>
      </div>

      {/* New Intake button */}
      <div className="px-3 pb-2">
        <button
          onClick={onNewIntake}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-apple-blue text-white text-[12px] font-medium cursor-pointer hover:brightness-110 transition-all"
        >
          <span className="text-[14px] leading-none">+</span>
          New Intake
        </button>
      </div>

      {/* Section header */}
      <div className="flex items-center justify-between px-3 pb-1.5">
        <span className="text-[10px] font-semibold text-tertiary uppercase tracking-wider">
          Clients ({filtered.length})
        </span>
      </div>

      {/* Client list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.map((client) => {
          const isActive = client.id === activeClientId;

          return (
            <div key={client.id}>
              <div
                role="button"
                tabIndex={0}
                onClick={() => onSelectClient(client.id)}
                onKeyDown={(e) => { if (e.key === "Enter") onSelectClient(client.id); }}
                className={cn(
                  "w-full flex items-center gap-2.5 px-3 py-2.5 text-left transition-all cursor-pointer border-l-3",
                  isActive
                    ? "bg-surface border-l-apple-blue shadow-sm"
                    : "hover:bg-surface/60 border-l-transparent"
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className={cn(
                    "text-[13px] truncate transition-all",
                    isActive ? "font-semibold text-primary" : "font-medium text-secondary"
                  )}>
                    {client.name}
                  </div>
                  <div className={cn(
                    "text-[11px] truncate",
                    isActive ? "text-secondary" : "text-tertiary"
                  )}>
                    {client.meta}
                  </div>
                </div>
                <Badge variant={client.status as BadgeVariant}>
                  {statusLabels[client.status] ?? client.status}
                </Badge>
              </div>

              {isActive && client.years && (
                <div className="bg-surface border-l-3 border-l-apple-blue px-3 pb-2">
                  {client.years.map((y) => (
                    <div key={y.year} className="mt-1">
                      <div className="text-[10px] font-semibold text-tertiary uppercase tracking-wider mb-0.5 pl-3">
                        {y.year}
                      </div>
                      {y.docs.map((doc) => (
                        <div
                          key={doc}
                          className="text-[11px] text-secondary pl-3 py-1 rounded hover:bg-surface-secondary cursor-pointer transition-colors"
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
```

- [ ] **Step 2: Migrate w2-form.tsx**

Replace hardcoded colors. Change `bg-[#1E3A5F]` to `bg-form-header`, `border-gray-200` to `border-divider`, `text-gray-400` to `text-tertiary`, `text-gray-500` to `text-secondary`:

```tsx
"use client";

interface W2Data {
  employer_name?: string;
  employer_ein?: string;
  employee_name?: string;
  employee_ssn?: string;
  wages?: number;
  federal_tax_withheld?: number;
  social_security_wages?: number;
  social_security_tax?: number;
  medicare_wages?: number;
  medicare_tax?: number;
  box_12?: string;
  state?: string;
  state_wages?: number;
  state_tax?: number;
  [key: string]: unknown;
}

export function W2Form({ data }: { data: W2Data }) {
  const fmt = (v: number | undefined) =>
    v !== undefined ? `$${v.toLocaleString("en-US", { minimumFractionDigits: 2 })}` : "--";

  return (
    <div className="border border-divider rounded-lg overflow-hidden text-[12px]">
      <div className="bg-form-header text-white px-4 py-2 flex items-center justify-between">
        <span className="font-bold text-[14px]">Form W-2</span>
        <span className="text-white/70 text-[11px]">Wage and Tax Statement 2025</span>
      </div>

      <div className="p-3 space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <div className="border border-divider rounded p-2">
            <div className="text-[10px] text-tertiary uppercase mb-0.5">Employer</div>
            <div className="font-medium text-primary">{data.employer_name || "--"}</div>
            <div className="text-secondary">EIN: {data.employer_ein || "--"}</div>
          </div>
          <div className="border border-divider rounded p-2">
            <div className="text-[10px] text-tertiary uppercase mb-0.5">Employee</div>
            <div className="font-medium text-primary">{data.employee_name || "--"}</div>
            <div className="text-secondary">SSN: {data.employee_ssn || "***-**-****"}</div>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2">
          {[
            { box: "1", label: "Wages, tips, other comp.", value: fmt(data.wages) },
            { box: "2", label: "Federal income tax withheld", value: fmt(data.federal_tax_withheld) },
            { box: "3", label: "Social security wages", value: fmt(data.social_security_wages) },
            { box: "4", label: "Social security tax withheld", value: fmt(data.social_security_tax) },
            { box: "5", label: "Medicare wages and tips", value: fmt(data.medicare_wages) },
            { box: "6", label: "Medicare tax withheld", value: fmt(data.medicare_tax) },
          ].map((item) => (
            <div key={item.box} className="border border-divider rounded p-2">
              <div className="text-[10px] text-tertiary mb-0.5">
                Box {item.box} - {item.label}
              </div>
              <div className="font-semibold text-[13px] text-primary">{item.value}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="border border-divider rounded p-2">
            <div className="text-[10px] text-tertiary mb-0.5">Box 12 - Codes</div>
            <div className="font-medium text-primary">{data.box_12 || "--"}</div>
          </div>
          <div className="border border-divider rounded p-2">
            <div className="text-[10px] text-tertiary mb-0.5">State: {data.state || "--"}</div>
            <div className="flex justify-between text-primary">
              <span>Wages: {fmt(data.state_wages)}</span>
              <span>Tax: {fmt(data.state_tax)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Migrate form-1099-int.tsx**

Apply the same pattern — replace `bg-[#1E3A5F]` with `bg-form-header`, `border-gray-200` with `border-divider`, `text-gray-400` with `text-tertiary`, `text-gray-500` with `text-secondary`, and add `text-primary` to value text:

```tsx
"use client";

interface Form1099IntData {
  payer_name?: string;
  payer_tin?: string;
  recipient_name?: string;
  recipient_tin?: string;
  interest_income?: number;
  early_withdrawal_penalty?: number;
  interest_on_savings_bonds?: number;
  federal_tax_withheld?: number;
  investment_expenses?: number;
  foreign_tax_paid?: number;
  tax_exempt_interest?: number;
  [key: string]: unknown;
}

export function Form1099Int({ data }: { data: Form1099IntData }) {
  const fmt = (v: number | undefined) =>
    v !== undefined ? `$${v.toLocaleString("en-US", { minimumFractionDigits: 2 })}` : "--";

  return (
    <div className="border border-divider rounded-lg overflow-hidden text-[12px]">
      <div className="bg-form-header text-white px-4 py-2 flex items-center justify-between">
        <span className="font-bold text-[14px]">Form 1099-INT</span>
        <span className="text-white/70 text-[11px]">Interest Income 2025</span>
      </div>

      <div className="p-3 space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <div className="border border-divider rounded p-2">
            <div className="text-[10px] text-tertiary uppercase mb-0.5">Payer</div>
            <div className="font-medium text-primary">{data.payer_name || "--"}</div>
            <div className="text-secondary">TIN: {data.payer_tin || "--"}</div>
          </div>
          <div className="border border-divider rounded p-2">
            <div className="text-[10px] text-tertiary uppercase mb-0.5">Recipient</div>
            <div className="font-medium text-primary">{data.recipient_name || "--"}</div>
            <div className="text-secondary">TIN: {data.recipient_tin || "***-**-****"}</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          {[
            { box: "1", label: "Interest income", value: fmt(data.interest_income) },
            { box: "2", label: "Early withdrawal penalty", value: fmt(data.early_withdrawal_penalty) },
            { box: "3", label: "Interest on U.S. Savings Bonds", value: fmt(data.interest_on_savings_bonds) },
            { box: "4", label: "Federal income tax withheld", value: fmt(data.federal_tax_withheld) },
            { box: "5", label: "Investment expenses", value: fmt(data.investment_expenses) },
            { box: "6", label: "Foreign tax paid", value: fmt(data.foreign_tax_paid) },
            { box: "8", label: "Tax-exempt interest", value: fmt(data.tax_exempt_interest) },
          ].map((item) => (
            <div key={item.box} className="border border-divider rounded p-2">
              <div className="text-[10px] text-tertiary mb-0.5">
                Box {item.box} - {item.label}
              </div>
              <div className="font-semibold text-[13px] text-primary">{item.value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Migrate generic-form.tsx**

```tsx
"use client";

export function GenericForm({
  formType,
  data,
}: {
  formType: string;
  data: Record<string, unknown>;
}) {
  const entries = Object.entries(data || {}).filter(
    ([, v]) => v !== null && v !== undefined && v !== ""
  );

  return (
    <div className="border border-divider rounded-lg overflow-hidden text-[12px]">
      <div className="bg-form-header text-white px-4 py-2 flex items-center justify-between">
        <span className="font-bold text-[14px]">Form {formType}</span>
        <span className="text-white/70 text-[11px]">Tax Year 2025</span>
      </div>

      <div className="p-3">
        {entries.length === 0 ? (
          <p className="text-tertiary text-center py-4">No extracted data available</p>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {entries.map(([key, value]) => (
              <div key={key} className="border border-divider rounded p-2">
                <div className="text-[10px] text-tertiary uppercase mb-0.5">
                  {key.replace(/_/g, " ")}
                </div>
                <div className="font-medium text-[13px] text-primary">
                  {typeof value === "number"
                    ? `$${value.toLocaleString("en-US", { minimumFractionDigits: 2 })}`
                    : String(value)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Migrate return-preview.tsx**

Replace `text-[#1d1d1f]` with `text-primary`, `text-[#1E3A5F]` with `text-form-header`, `text-gray-*` with `text-secondary`/`text-tertiary`:

```tsx
"use client";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

interface TaxLine {
  number: string;
  label: string;
  value: number;
  section: string;
}

interface ReturnPreviewProps {
  lines?: TaxLine[];
  totalIncome?: number;
  taxableIncome?: number;
  totalTax?: number;
  refundOrOwed?: number;
  effectiveRate?: number;
  onViewFull?: () => void;
  onApproveFile?: () => void;
}

const defaultLines: TaxLine[] = [
  { number: "1", label: "Wages, salaries, tips", value: 142500, section: "Income" },
  { number: "2b", label: "Taxable interest", value: 1230, section: "Income" },
  { number: "9", label: "Total income", value: 143730, section: "Income" },
  { number: "10", label: "Standard deduction", value: 27700, section: "Deductions" },
  { number: "11", label: "Adjusted gross income", value: 131230, section: "Deductions" },
  { number: "15", label: "Taxable income", value: 103730, section: "Deductions" },
  { number: "22", label: "Child tax credit", value: 4000, section: "Tax & Credits" },
  { number: "24", label: "Total tax", value: 17412, section: "Tax & Credits" },
  { number: "33", label: "Total payments", value: 20700, section: "Payments" },
  { number: "34", label: "Overpayment / Refund", value: 3288, section: "Payments" },
];

export function ReturnPreview({
  lines = defaultLines,
  refundOrOwed = 3288,
  effectiveRate = 13.3,
  onViewFull,
  onApproveFile,
}: ReturnPreviewProps) {
  const sections = ["Income", "Deductions", "Tax & Credits", "Payments"];

  const fmt = (v: number) =>
    `$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 0 })}`;

  return (
    <div className="space-y-3">
      <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
        Form 1040 Preview
      </div>

      {sections.map((section) => {
        const sectionLines = lines.filter((l) => l.section === section);
        if (sectionLines.length === 0) return null;

        return (
          <div key={section}>
            <div className="text-[11px] font-semibold text-form-header uppercase tracking-wider mb-1">
              {section}
            </div>
            <div className="space-y-0.5">
              {sectionLines.map((line) => {
                const isRefund = line.number === "34";
                return (
                  <div
                    key={line.number}
                    className={cn(
                      "flex items-center justify-between py-1.5 px-2 rounded text-[12px]",
                      isRefund
                        ? "bg-green-50 dark:bg-green-950/30 font-semibold text-green-700 dark:text-green-400"
                        : "text-primary"
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-tertiary w-6 text-right font-mono text-[11px]">
                        {line.number}
                      </span>
                      <span>{line.label}</span>
                    </div>
                    <span className="font-medium">{fmt(line.value)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      <Card className="text-center p-4">
        <div className="text-[11px] text-secondary uppercase tracking-wider mb-1">
          {refundOrOwed >= 0 ? "Estimated Refund" : "Amount Owed"}
        </div>
        <div
          className={cn(
            "text-[28px] font-semibold",
            refundOrOwed >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
          )}
        >
          {fmt(refundOrOwed)}
        </div>
        <div className="text-[12px] text-secondary mt-1">
          Effective rate: {effectiveRate}%
        </div>
        <div className="flex gap-2 mt-3 justify-center">
          <Button variant="pill" onClick={onViewFull}>
            View Full 1040
          </Button>
          <Button variant="primary" onClick={onApproveFile}>
            Approve &amp; File
          </Button>
        </div>
      </Card>
    </div>
  );
}
```

- [ ] **Step 6: Migrate intake-modal.tsx**

Replace all hardcoded color classes. Key changes: `inputCls` uses `bg-surface border-divider text-primary`, `labelCls` uses `text-tertiary`, `sectionCls` uses `text-primary border-divider`, footer uses `bg-surface-secondary`:

In `frontend/components/clients/intake-modal.tsx`, replace these three `const` lines (lines 85-87):

```tsx
  const inputCls = "w-full border border-divider rounded-lg px-3 py-2 text-[13px] outline-none focus:border-apple-blue transition-colors bg-surface text-primary placeholder:text-tertiary";
  const labelCls = "text-[11px] font-medium text-tertiary uppercase tracking-wider mb-1 block";
  const sectionCls = "text-[12px] font-semibold text-primary pb-1.5 mb-3 border-b border-divider";
```

And replace the header (line 93-100):
```tsx
        <div className="px-6 py-4 border-b border-divider flex items-center justify-between shrink-0">
          <div>
            <div className="text-[16px] font-semibold text-primary">New Client Intake</div>
            <div className="text-[12px] text-tertiary mt-0.5">Enter taxpayer details to start a new return</div>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg border border-divider flex items-center justify-center text-tertiary hover:text-primary hover:bg-surface-secondary transition-colors cursor-pointer text-[16px]">
            &times;
          </button>
        </div>
```

Replace the state toggle button class (inside the filingStates `.map`):
```tsx
                  className={`text-[10px] px-2 py-1 rounded-md border cursor-pointer transition-all ${
                    form.filingStates.includes(s)
                      ? "bg-apple-blue text-white border-apple-blue"
                      : "bg-surface text-secondary border-divider hover:border-tertiary"
                  }`}
```

Replace the footer (line 244):
```tsx
        <div className="px-6 py-3 border-t border-divider flex items-center justify-end gap-2 shrink-0 bg-surface-secondary">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border border-divider text-[13px] text-secondary hover:bg-surface-tertiary transition-colors cursor-pointer">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!form.firstName || !form.lastName}
            className="px-4 py-2 rounded-lg bg-apple-blue text-white text-[13px] font-medium hover:brightness-110 transition-all cursor-pointer disabled:opacity-40"
          >
            Create Client
          </button>
        </div>
```

Also add `max-w-[640px]` instead of `w-[640px]` on the container div (line 91):
```tsx
      <div className="w-full max-w-[640px] max-h-[85vh] flex flex-col">
```

- [ ] **Step 7: Migrate document-viewer-modal.tsx**

In `frontend/components/documents/document-viewer-modal.tsx`, replace hardcoded colors:

Line 59 — change `className` prop:
```tsx
    <Modal open={open} onClose={onClose} className="max-w-4xl">
```

Line 77-84 — replace the verified/needs review badges:
```tsx
              {doc.status === "verified" ? (
                <span className="inline-block bg-badge-complete-bg text-badge-complete-text text-[11px] font-bold uppercase tracking-wider px-3 py-1 rounded-full">
                  Verified
                </span>
              ) : (
                <span className="inline-block bg-badge-review-bg text-badge-review-text text-[11px] font-bold uppercase tracking-wider px-3 py-1 rounded-full">
                  Needs Review
                </span>
              )}
```

Line 93-100 — update text colors:
```tsx
              <div className="text-[13px] font-semibold text-primary mb-2">
                Flagged Fields
              </div>
              {parsedFlags.map((flag, i) => (
                <div
                  key={i}
                  className="bg-badge-review-bg text-badge-review-text text-[12px] px-3 py-2 rounded-lg"
                >
```

Line 104 — update heading:
```tsx
              <div className="text-[13px] font-semibold text-primary mt-4 mb-2">
```

Line 110 — update label:
```tsx
                    <label className="text-[11px] text-tertiary uppercase">
```

Line 142 — update confidence label:
```tsx
            <span className="text-[12px] text-secondary">AI Confidence:</span>
```

- [ ] **Step 8: Verify build**

Run: `cd frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 9: Commit**

```bash
git add frontend/components/layout/client-sidebar.tsx frontend/components/forms/ frontend/components/returns/ frontend/components/clients/ frontend/components/documents/
git commit -m "feat(frontend): migrate sidebar, forms, returns, and modals to theme tokens"
```

---

## Task 7: Migrate page.tsx to Theme Tokens

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Replace all hardcoded colors in page.tsx**

The main changes to `frontend/app/page.tsx`:

Line 526 — main background:
```tsx
        <main className="flex-1 flex flex-col bg-surface min-w-0">
```

Line 528 — context bar border:
```tsx
          <div className="shrink-0 border-b border-divider px-5 py-3">
```

Line 532 — client name:
```tsx
                <span className="text-[14px] font-semibold text-primary">
```

Line 537 — meta text:
```tsx
                    <span className="text-[11px] text-tertiary">{activeClient.meta}</span>
```

Lines 546-551 — tracking labels:
```tsx
              <span className="text-[12px] font-semibold text-green-600 dark:text-green-400 bg-surface-secondary px-2.5 py-1 rounded-md">
                Federal: +$4,820
              </span>
              <span className="text-[12px] font-semibold text-red-500 dark:text-red-400 bg-surface-secondary px-2.5 py-1 rounded-md">
                NJ: -$1,240
              </span>
```

Line 557 — divider:
```tsx
              <div className="w-px h-4 bg-divider" />
```

Line 563 — step connector:
```tsx
                      {i > 0 && <div className="w-4 h-px bg-divider" />}
```

Line 601 — work panel aside:
```tsx
        <aside className="w-96 shrink-0 bg-surface border-l border-divider flex flex-col overflow-hidden">
```

Line 613 — flag message:
```tsx
                  <div className="bg-badge-review-bg text-badge-review-text text-[12px] px-3 py-2 rounded-lg">
```

Line 634 — doc name:
```tsx
                              <div className="text-[13px] font-medium text-primary">
```

Line 637 — doc meta:
```tsx
                              <div className="text-[11px] text-tertiary">
```

Lines 655-680 — grid labels and values:
Replace all `text-gray-400` with `text-tertiary` and all `text-[#1d1d1f]` with `text-primary`.

Lines 714-728 — filed tab:
```tsx
              <div className="flex flex-col items-center justify-center h-64 text-center">
                <div className="w-12 h-12 rounded-full bg-green-100 dark:bg-green-950/30 text-green-600 dark:text-green-400 flex items-center justify-center text-[24px] mb-3">
                  &#10003;
                </div>
                <div className="text-[15px] font-semibold text-primary mb-1">
                  Return Filed
                </div>
                <div className="text-[12px] text-secondary">
                  Submitted 04/10/2026
                </div>
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(frontend): migrate page.tsx to semantic theme tokens"
```

---

## Task 8: Responsive Layout — Panel Overlay & Bottom Tab Bar

**Files:**
- Create: `frontend/components/layout/panel-overlay.tsx`
- Create: `frontend/components/layout/bottom-tab-bar.tsx`
- Create: `frontend/lib/hooks/use-media-query.ts`
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Create useMediaQuery hook**

```tsx
// frontend/lib/hooks/use-media-query.ts
"use client";

import { useState, useEffect } from "react";

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia(query);
    setMatches(mq.matches);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [query]);

  return matches;
}

/** Breakpoint hooks matching Tailwind defaults */
export const useIsMobile = () => !useMediaQuery("(min-width: 768px)");
export const useIsTablet = () => useMediaQuery("(min-width: 768px)") && !useMediaQuery("(min-width: 1024px)");
export const useIsDesktop = () => useMediaQuery("(min-width: 1024px)");
export const useIsDesktopXL = () => useMediaQuery("(min-width: 1280px)");
```

- [ ] **Step 2: Create PanelOverlay component**

```tsx
// frontend/components/layout/panel-overlay.tsx
"use client";

import { useEffect } from "react";
import { cn } from "@/lib/utils";

interface PanelOverlayProps {
  open: boolean;
  onClose: () => void;
  side: "left" | "right";
  children: React.ReactNode;
  className?: string;
}

export function PanelOverlay({ open, onClose, side, children, className }: PanelOverlayProps) {
  // Lock body scroll when open
  useEffect(() => {
    if (open) document.body.style.overflow = "hidden";
    else document.body.style.overflow = "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30 animate-fade-in"
        onClick={onClose}
      />
      {/* Panel */}
      <div
        className={cn(
          "absolute top-0 bottom-0 bg-surface shadow-xl overflow-y-auto",
          side === "left" ? "left-0 animate-slide-in-left" : "right-0 animate-slide-in-right",
          className
        )}
      >
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create BottomTabBar component**

```tsx
// frontend/components/layout/bottom-tab-bar.tsx
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
          {/* Badge for docs tab */}
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
```

- [ ] **Step 4: Restructure page.tsx for responsive layout**

This is the largest single change. Replace the layout section of `page.tsx` (the `return` block, starting at line 510) with responsive logic. The key structural changes:

1. Import the new components at the top of page.tsx:
```tsx
import { PanelOverlay } from "@/components/layout/panel-overlay";
import { BottomTabBar, type TabId } from "@/components/layout/bottom-tab-bar";
import { useIsMobile, useIsDesktopXL } from "@/lib/hooks/use-media-query";
```

2. Add responsive state after the existing state declarations (around line 236):
```tsx
  const isMobile = useIsMobile();
  const isDesktopXL = useIsDesktopXL();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [workPanelOpen, setWorkPanelOpen] = useState(false);
  const [mobileTab, setMobileTab] = useState<TabId>("chat");
```

3. Add handler for mobile tab switch that auto-navigates:
```tsx
  const handleMobileTabChange = useCallback((tab: TabId) => {
    setMobileTab(tab);
    setSidebarOpen(false);
    setWorkPanelOpen(false);
  }, []);

  // When client is selected on mobile, switch to chat
  const handleSelectClient = useCallback((id: string) => {
    setActiveClientId(id);
    if (isMobile) {
      setMobileTab("chat");
    }
    setSidebarOpen(false);
  }, [isMobile]);
```

4. Replace the return block with the responsive layout. The full updated return block:

```tsx
  const flagCount = documents.filter((d) => d.status === "flagged" || d.status === "pending").length;
  const flagMessage = flagCount > 0 ? `${flagCount} documents need review before filing` : "";

  // Sidebar content (shared between inline and overlay)
  const sidebarContent = (
    <ClientSidebar
      clients={sidebarClients}
      activeClientId={activeClientId}
      onSelectClient={handleSelectClient}
      onNewIntake={() => setIntakeOpen(true)}
    />
  );

  // Work panel content (shared between inline and overlay)
  const workPanelContent = (
    <>
      <Tabs
        tabs={["Documents", "Tax Return", "Filed"]}
        activeTab={activeWorkTab}
        onTabChange={setActiveWorkTab}
        className="px-2 pt-1"
      />
      <div className="flex-1 overflow-y-auto p-3">
        {activeWorkTab === "Documents" && (
          <div className="space-y-3">
            {flagMessage && (
              <div className="bg-badge-review-bg text-badge-review-text text-[12px] px-3 py-2 rounded-lg">
                &#9888; {flagMessage}
              </div>
            )}
            {documents.map((doc) => {
              const data = (() => { try { return JSON.parse(doc.extracted_data); } catch { return {}; } })();
              const fmt = (v: number | undefined) => v != null ? `$${v.toLocaleString()}` : "\u2014";
              return (
                <button
                  key={doc.id}
                  onClick={() => { setViewerDoc(doc); setViewerOpen(true); }}
                  className="w-full text-left cursor-pointer"
                >
                  <Card className="p-3 hover:shadow-md transition-shadow">
                    <div className="flex items-center justify-between mb-1.5">
                      <div>
                        <div className="text-[13px] font-medium text-primary">{doc.name}</div>
                        <div className="text-[11px] text-tertiary">{doc.form_type} &middot; TY 2025</div>
                      </div>
                      <Badge variant={doc.status === "verified" ? "completed" : doc.status === "flagged" ? "review" : "pending"}>
                        {doc.confidence}%
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                      {data.wages != null && (<><span className="text-tertiary">Wages</span><span className="text-right text-primary font-medium">{fmt(data.wages)}</span></>)}
                      {data.federal_tax_withheld != null && (<><span className="text-tertiary">Fed W/H</span><span className="text-right text-primary font-medium">{fmt(data.federal_tax_withheld)}</span></>)}
                      {data.state && data.state_tax != null && (<><span className="text-tertiary">{data.state} W/H</span><span className="text-right text-primary font-medium">{fmt(data.state_tax)}</span></>)}
                      {data.interest_income != null && (<><span className="text-tertiary">Interest</span><span className="text-right text-primary font-medium">{fmt(data.interest_income)}</span></>)}
                      {data.mortgage_interest != null && (<><span className="text-tertiary">Mort. Int.</span><span className="text-right text-primary font-medium">{fmt(data.mortgage_interest)}</span></>)}
                      {data.real_estate_taxes != null && (<><span className="text-tertiary">RE Taxes</span><span className="text-right text-primary font-medium">{fmt(data.real_estate_taxes)}</span></>)}
                    </div>
                  </Card>
                </button>
              );
            })}
          </div>
        )}
        {activeWorkTab === "Tax Return" && (
          <ReturnPreview
            lines={returnDraft ? returnDraft.lines : undefined}
            refundOrOwed={returnDraft?.refund_or_owed}
            effectiveRate={returnDraft?.effective_rate}
            onViewFull={handleGenerateReturn}
          />
        )}
        {activeWorkTab === "Filed" && (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <div className="w-12 h-12 rounded-full bg-green-100 dark:bg-green-950/30 text-green-600 dark:text-green-400 flex items-center justify-center text-[24px] mb-3">&#10003;</div>
            <div className="text-[15px] font-semibold text-primary mb-1">Return Filed</div>
            <div className="text-[12px] text-secondary">Submitted 04/10/2026</div>
            <Badge variant="filed" className="mt-3">E-Filed</Badge>
          </div>
        )}
      </div>
    </>
  );

  // Chat panel content
  const chatContent = (
    <main className="flex-1 flex flex-col bg-surface min-w-0">
      {/* Context bar */}
      <div className="shrink-0 border-b border-divider px-5 max-md:px-3 py-3">
        <div className="flex items-center gap-3">
          <div className="flex-1 min-w-0 flex items-center gap-3">
            <span className="text-[14px] font-semibold text-primary">
              {activeClient?.name || "Select a client"}
            </span>
            {activeClient && (
              <>
                <span className="text-[11px] text-tertiary max-md:hidden">{activeClient.meta}</span>
                <Badge variant={activeClient.status as "pending" | "inProgress" | "review" | "completed" | "filed"}>
                  {activeClient.status === "inProgress" ? "In Progress" : activeClient.status}
                </Badge>
              </>
            )}
          </div>
          {/* Work panel toggle — when panel is not inline */}
          {!isDesktopXL && (
            <button
              onClick={() => setWorkPanelOpen(true)}
              className="hidden md:flex w-8 h-8 rounded-lg items-center justify-center text-secondary hover:bg-surface-secondary transition-colors cursor-pointer relative"
              aria-label="Show documents panel"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                <path d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {flagCount > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 bg-orange-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">{flagCount}</span>
              )}
            </button>
          )}
          {/* Tracking labels — desktop only */}
          <span className="hidden xl:inline text-[12px] font-semibold text-green-600 dark:text-green-400 bg-surface-secondary px-2.5 py-1 rounded-md">
            Federal: +$4,820
          </span>
          <span className="hidden xl:inline text-[12px] font-semibold text-red-500 dark:text-red-400 bg-surface-secondary px-2.5 py-1 rounded-md">
            NJ: -$1,240
          </span>
        </div>
        {/* Stepper — hidden on mobile */}
        <div className="hidden md:flex items-center gap-3 mt-2">
          <Badge variant="inProgress">2025 Tax Season</Badge>
          <div className="w-px h-4 bg-divider" />
          <div className="flex items-center gap-1">
            {["Intake", "Documents", "Review", "Prepare", "File"].map((step, i) => (
              <div key={step} className="flex items-center gap-1">
                {i > 0 && <div className="w-4 h-px bg-divider" />}
                <Badge variant={i < 2 ? "completed" : i === 2 ? "inProgress" : "pending"}>{step}</Badge>
              </div>
            ))}
          </div>
        </div>
      </div>
      <MessageList messages={messages} isTyping={isTyping} />
      <input type="file" ref={fileInputRef} className="hidden" accept=".pdf,.png,.jpg,.jpeg,.tiff" onChange={handleFileSelected} />
      <ChatInput onSend={handleSendMessage} onAttach={() => fileInputRef.current?.click()} />
    </main>
  );

  return (
    <div className="flex flex-col h-full">
      <TopBar
        stats={{ clients: totalClients, filed: filedCount, review: reviewCount }}
        deadline="April 15 in 4 days"
        user={{ initials: "SC" }}
        showMenu={!isDesktopXL}
        onMenuToggle={() => setSidebarOpen(!sidebarOpen)}
        clientName={isMobile ? activeClient?.name : undefined}
      />

      {/* Desktop layout */}
      {!isMobile && (
        <div className="flex flex-1 overflow-hidden">
          {/* Sidebar — inline on desktop, hidden on tablet (overlay) */}
          <div className="hidden lg:block">
            {sidebarContent}
          </div>
          {chatContent}
          {/* Work panel — inline on XL, hidden otherwise (overlay) */}
          {isDesktopXL && (
            <aside className="w-96 shrink-0 bg-surface border-l border-divider flex flex-col overflow-hidden">
              {workPanelContent}
            </aside>
          )}
        </div>
      )}

      {/* Mobile layout — single panel via tab bar */}
      {isMobile && (
        <div className="flex-1 overflow-hidden flex flex-col">
          <div className="flex-1 overflow-hidden">
            {mobileTab === "clients" && <div className="h-full overflow-y-auto">{sidebarContent}</div>}
            {mobileTab === "chat" && chatContent}
            {mobileTab === "docs" && (
              <div className="h-full overflow-y-auto bg-surface flex flex-col">
                {workPanelContent}
              </div>
            )}
            {mobileTab === "returns" && (
              <div className="h-full overflow-y-auto bg-surface p-4">
                <ReturnPreview
                  lines={returnDraft ? returnDraft.lines : undefined}
                  refundOrOwed={returnDraft?.refund_or_owed}
                  effectiveRate={returnDraft?.effective_rate}
                  onViewFull={handleGenerateReturn}
                />
              </div>
            )}
          </div>
          <BottomTabBar
            activeTab={mobileTab}
            onTabChange={handleMobileTabChange}
            docBadge={flagCount}
          />
        </div>
      )}

      {/* Sidebar overlay — tablet */}
      <PanelOverlay open={sidebarOpen && !isMobile} onClose={() => setSidebarOpen(false)} side="left" className="w-80">
        {sidebarContent}
      </PanelOverlay>

      {/* Work panel overlay — tablet/laptop */}
      <PanelOverlay open={workPanelOpen} onClose={() => setWorkPanelOpen(false)} side="right" className="w-96 max-w-[calc(100vw-48px)] flex flex-col">
        {workPanelContent}
      </PanelOverlay>

      <DocumentViewerModal open={viewerOpen} onClose={() => setViewerOpen(false)} document={viewerDoc} onApprove={handleApproveDoc} />

      <IntakeModal
        open={intakeOpen}
        onClose={() => setIntakeOpen(false)}
        onSubmit={async (data: IntakeFormData) => {
          // ... (keep existing onSubmit handler unchanged)
        }}
      />
    </div>
  );
```

Note: The `onSubmit` handler for `IntakeModal` stays exactly the same — just replace `setActiveClientId` calls with `handleSelectClient` for the mobile auto-switch behavior.

- [ ] **Step 5: Update onSelectClient references**

In page.tsx, replace the two references to `onSelectClient={setActiveClientId}` inside `ClientSidebar` with `onSelectClient={handleSelectClient}`.

- [ ] **Step 6: Verify build**

Run: `cd frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/hooks/ frontend/components/layout/panel-overlay.tsx frontend/components/layout/bottom-tab-bar.tsx frontend/app/page.tsx
git commit -m "feat(frontend): add responsive layout with panel overlays and mobile bottom tab bar"
```

---

## Task 9: Toast Notification System

**Files:**
- Create: `frontend/components/ui/toast.tsx`

- [ ] **Step 1: Create toast component and provider**

```tsx
// frontend/components/ui/toast.tsx
"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type ToastType = "success" | "error" | "info";

interface Toast {
  id: number;
  type: ToastType;
  title: string;
  description?: string;
}

interface ToastContextValue {
  toast: (type: ToastType, title: string, description?: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

const borderColors: Record<ToastType, string> = {
  success: "border-l-green-500",
  error: "border-l-red-500",
  info: "border-l-apple-blue",
};

const icons: Record<ToastType, string> = {
  success: "\u2713",
  error: "\u2717",
  info: "\u2139",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((type: ToastType, title: string, description?: string) => {
    const id = Date.now();
    setToasts((prev) => [...prev.slice(-2), { id, type, title, description }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast: addToast }}>
      {children}
      {/* Toast container */}
      <div className="fixed top-16 right-4 max-md:right-2 max-md:left-2 max-md:top-12 z-[60] flex flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "bg-surface rounded-xl shadow-lg border-l-[3px] px-4 py-3 flex items-start gap-3 animate-slide-in-right max-md:animate-fade-in min-w-[280px] max-md:min-w-0",
              borderColors[t.type]
            )}
          >
            <span className="text-[14px] mt-0.5">{icons[t.type]}</span>
            <div className="flex-1 min-w-0">
              <div className="text-[13px] font-medium text-primary">{t.title}</div>
              {t.description && <div className="text-[12px] text-secondary mt-0.5">{t.description}</div>}
            </div>
            <button
              onClick={() => removeToast(t.id)}
              className="text-tertiary hover:text-primary text-[14px] cursor-pointer shrink-0"
            >
              &times;
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
```

- [ ] **Step 2: Wire ToastProvider into providers.tsx**

In `frontend/app/providers.tsx`, add `ToastProvider` inside `ThemeProvider`:

```tsx
import { ToastProvider } from "@/components/ui/toast";

// Inside AppProvider return:
    <ThemeProvider>
      <ToastProvider>
        <AppContext.Provider value={...}>
          {children}
        </AppContext.Provider>
      </ToastProvider>
    </ThemeProvider>
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/ui/toast.tsx frontend/app/providers.tsx
git commit -m "feat(frontend): add toast notification system with auto-dismiss"
```

---

## Task 10: Skeleton Loading Components

**Files:**
- Create: `frontend/components/ui/skeleton.tsx`

- [ ] **Step 1: Create skeleton primitives**

```tsx
// frontend/components/ui/skeleton.tsx
import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div className={cn("bg-surface-tertiary rounded-lg animate-skeleton", className)} />
  );
}

export function ChatSkeleton() {
  return (
    <div className="space-y-4 px-5 py-4">
      {/* Assistant message */}
      <div className="flex gap-2.5">
        <Skeleton className="w-7 h-7 rounded-md shrink-0" />
        <Skeleton className="h-16 w-[60%] rounded-2xl" />
      </div>
      {/* User message */}
      <div className="flex gap-2.5 justify-end">
        <Skeleton className="h-10 w-[45%] rounded-2xl" />
        <Skeleton className="w-7 h-7 rounded-md shrink-0" />
      </div>
      {/* Assistant message */}
      <div className="flex gap-2.5">
        <Skeleton className="w-7 h-7 rounded-md shrink-0" />
        <Skeleton className="h-20 w-[55%] rounded-2xl" />
      </div>
    </div>
  );
}

export function ClientListSkeleton() {
  return (
    <div className="space-y-1 p-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex items-center gap-2.5 px-3 py-2.5">
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-[70%]" />
            <Skeleton className="h-2.5 w-[50%]" />
          </div>
          <Skeleton className="h-5 w-14 rounded-full" />
        </div>
      ))}
    </div>
  );
}

export function MetricCardSkeleton() {
  return (
    <div className="bg-surface-secondary rounded-xl p-5 space-y-2">
      <Skeleton className="h-8 w-16 mx-auto" />
      <Skeleton className="h-3 w-20 mx-auto" />
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/ui/skeleton.tsx
git commit -m "feat(frontend): add skeleton loading components"
```

---

## Task 11: Settings Page

**Files:**
- Create: `frontend/components/settings/settings-modal.tsx`

- [ ] **Step 1: Create the settings modal with all sections**

```tsx
// frontend/components/settings/settings-modal.tsx
"use client";

import { useState } from "react";
import { Modal, ModalHeader, ModalBody } from "@/components/ui/modal";
import { useTheme } from "@/components/providers/theme-provider";
import { cn } from "@/lib/utils";

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  onReplayTour?: () => void;
}

type Section = "profile" | "appearance" | "notifications" | "defaults" | "shortcuts" | "about";

const sections: { id: Section; label: string }[] = [
  { id: "profile", label: "Profile" },
  { id: "appearance", label: "Appearance" },
  { id: "notifications", label: "Notifications" },
  { id: "defaults", label: "Tax Defaults" },
  { id: "shortcuts", label: "Shortcuts" },
  { id: "about", label: "About" },
];

const NOTIFICATION_CATEGORIES = [
  { key: "documents", label: "Document processing", desc: "Upload complete, extraction ready" },
  { key: "messages", label: "Client messages", desc: "New chat messages from AI agent" },
  { key: "returns", label: "Return status", desc: "Return generated, filed, rejected" },
  { key: "deadlines", label: "Deadline reminders", desc: "Upcoming filing deadlines" },
  { key: "system", label: "System updates", desc: "Maintenance, new features" },
];

const SHORTCUTS = [
  { keys: "Cmd/Ctrl + K", action: "Quick client search" },
  { keys: "Cmd/Ctrl + N", action: "New intake" },
  { keys: "Escape", action: "Close overlay / modal" },
  { keys: "Tab", action: "Navigate between panels" },
];

const STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
  "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
  "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
  "VA","WA","WV","WI","WY","DC",
];

export function SettingsModal({ open, onClose, onReplayTour }: SettingsModalProps) {
  const [active, setActive] = useState<Section>("profile");
  const { theme, setTheme } = useTheme();
  const [notifPrefs, setNotifPrefs] = useState<Record<string, boolean>>(
    Object.fromEntries(NOTIFICATION_CATEGORIES.map((c) => [c.key, true]))
  );

  const inputCls = "w-full border border-divider rounded-lg px-3 py-2 text-[13px] outline-none focus:border-apple-blue transition-colors bg-surface text-primary placeholder:text-tertiary";
  const labelCls = "text-[11px] font-medium text-tertiary uppercase tracking-wider mb-1 block";

  return (
    <Modal open={open} onClose={onClose} className="max-w-2xl">
      <ModalHeader onClose={onClose}>Settings</ModalHeader>
      <ModalBody className="p-0 max-h-[70vh]">
        <div className="flex min-h-[400px]">
          {/* Section nav */}
          <nav className="w-44 shrink-0 border-r border-divider py-2 max-md:hidden">
            {sections.map((s) => (
              <button
                key={s.id}
                onClick={() => setActive(s.id)}
                className={cn(
                  "w-full text-left px-4 py-2 text-[13px] transition-colors cursor-pointer",
                  active === s.id ? "text-apple-blue bg-surface-secondary font-medium" : "text-secondary hover:bg-surface-secondary"
                )}
              >
                {s.label}
              </button>
            ))}
          </nav>

          {/* Content */}
          <div className="flex-1 p-6 overflow-y-auto space-y-5">
            {/* Mobile section picker */}
            <select
              className={cn(inputCls, "md:hidden mb-4")}
              value={active}
              onChange={(e) => setActive(e.target.value as Section)}
            >
              {sections.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>

            {active === "profile" && (
              <div className="space-y-4">
                <h3 className="text-[15px] font-semibold text-primary">Profile</h3>
                <div className="grid grid-cols-2 gap-3">
                  <div><label className={labelCls}>Name</label><input className={inputCls} defaultValue="Sarah Chen" readOnly /></div>
                  <div><label className={labelCls}>Email</label><input className={inputCls} defaultValue="sarah@taxfirm.com" readOnly /></div>
                  <div><label className={labelCls}>Firm</label><input className={inputCls} defaultValue="Chen & Associates CPA" readOnly /></div>
                  <div><label className={labelCls}>Role</label><input className={inputCls} defaultValue="Senior Tax Preparer" readOnly /></div>
                </div>
              </div>
            )}

            {active === "appearance" && (
              <div className="space-y-4">
                <h3 className="text-[15px] font-semibold text-primary">Appearance</h3>
                <div>
                  <label className={labelCls}>Theme</label>
                  <div className="flex gap-2 mt-1">
                    {(["light", "dark", "system"] as const).map((t) => (
                      <button
                        key={t}
                        onClick={() => {
                          document.documentElement.classList.add("theme-transitioning");
                          setTheme(t);
                          setTimeout(() => document.documentElement.classList.remove("theme-transitioning"), 400);
                        }}
                        className={cn(
                          "px-4 py-2 rounded-lg text-[13px] font-medium border transition-all cursor-pointer capitalize",
                          theme === t
                            ? "bg-apple-blue text-white border-apple-blue"
                            : "bg-surface text-secondary border-divider hover:border-tertiary"
                        )}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {active === "notifications" && (
              <div className="space-y-4">
                <h3 className="text-[15px] font-semibold text-primary">Notification Preferences</h3>
                <div className="space-y-3">
                  {NOTIFICATION_CATEGORIES.map((cat) => (
                    <div key={cat.key} className="flex items-center justify-between py-2 border-b border-divider last:border-0">
                      <div>
                        <div className="text-[13px] text-primary">{cat.label}</div>
                        <div className="text-[11px] text-tertiary">{cat.desc}</div>
                      </div>
                      <div className="flex items-center gap-4">
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={notifPrefs[cat.key]}
                            onChange={(e) => setNotifPrefs((p) => ({ ...p, [cat.key]: e.target.checked }))}
                            className="w-4 h-4 accent-apple-blue cursor-pointer"
                          />
                          <span className="text-[11px] text-secondary">In-app</span>
                        </label>
                        <label className="flex items-center gap-1.5 opacity-40 cursor-not-allowed" title="Coming soon">
                          <input type="checkbox" disabled className="w-4 h-4 cursor-not-allowed" />
                          <span className="text-[11px] text-tertiary">Email</span>
                        </label>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {active === "defaults" && (
              <div className="space-y-4">
                <h3 className="text-[15px] font-semibold text-primary">Tax Defaults</h3>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={labelCls}>Default Tax Year</label>
                    <select className={inputCls} defaultValue="2025">
                      {[2025, 2024, 2023, 2022].map((y) => <option key={y} value={y}>{y}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={labelCls}>Filing Status</label>
                    <select className={inputCls} defaultValue="single">
                      <option value="single">Single</option>
                      <option value="mfj">Married Filing Jointly</option>
                      <option value="mfs">Married Filing Separately</option>
                      <option value="hoh">Head of Household</option>
                      <option value="qw">Qualifying Surviving Spouse</option>
                    </select>
                  </div>
                  <div>
                    <label className={labelCls}>Default State</label>
                    <select className={inputCls} defaultValue="">
                      <option value="">None</option>
                      {STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                </div>
              </div>
            )}

            {active === "shortcuts" && (
              <div className="space-y-4">
                <h3 className="text-[15px] font-semibold text-primary">Keyboard Shortcuts</h3>
                <div className="space-y-2">
                  {SHORTCUTS.map((s) => (
                    <div key={s.keys} className="flex items-center justify-between py-2 border-b border-divider last:border-0">
                      <span className="text-[13px] text-primary">{s.action}</span>
                      <kbd className="text-[12px] font-mono bg-surface-secondary text-secondary px-2 py-1 rounded">{s.keys}</kbd>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {active === "about" && (
              <div className="space-y-4">
                <h3 className="text-[15px] font-semibold text-primary">About TaxFlow AI</h3>
                <div className="space-y-2 text-[13px]">
                  <div className="flex justify-between"><span className="text-secondary">Version</span><span className="text-primary font-medium">0.1.0</span></div>
                  <div className="flex justify-between"><span className="text-secondary">Build</span><span className="text-primary font-medium">2026.04.12</span></div>
                </div>
                <div className="flex gap-2 mt-4">
                  {onReplayTour && (
                    <button onClick={onReplayTour} className="text-[13px] text-apple-blue hover:underline cursor-pointer">
                      Replay onboarding tour
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </ModalBody>
    </Modal>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/settings/settings-modal.tsx
git commit -m "feat(frontend): add settings page with profile, appearance, notifications, defaults, shortcuts, about"
```

---

## Task 12: Notification Bell

**Files:**
- Create: `frontend/components/notifications/notification-bell.tsx`

- [ ] **Step 1: Create the notification bell dropdown**

```tsx
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
        className="w-8 h-8 rounded-lg flex items-center justify-center text-secondary hover:bg-surface-secondary transition-colors cursor-pointer relative"
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
```

- [ ] **Step 2: Wire into top bar**

In `frontend/components/layout/top-bar.tsx`, import and add between the dashboard icon and deadline:

```tsx
import { NotificationBell } from "@/components/notifications/notification-bell";
```

Add `<NotificationBell />` in the right cluster, between the dashboard button and the deadline span.

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/notifications/ frontend/components/layout/top-bar.tsx
git commit -m "feat(frontend): add notification bell with dropdown panel and mock data"
```

---

## Task 13: Onboarding Tour

**Files:**
- Create: `frontend/components/onboarding/onboarding-tour.tsx`

- [ ] **Step 1: Create the 3-step spotlight tour**

```tsx
// frontend/components/onboarding/onboarding-tour.tsx
"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";

interface OnboardingTourProps {
  active: boolean;
  onComplete: () => void;
}

const steps = [
  {
    title: "Meet your workspace",
    text: "Your clients are on the left. Chat with the AI tax agent in the center. Review documents and returns on the right.",
  },
  {
    title: "Start with a client",
    text: "Add a new client to begin. Upload their W-2s and 1099s, and the AI agent will help prepare their return.",
  },
  {
    title: "Ask anything",
    text: "Ask tax questions in plain English. The agent pulls from IRS rules, instructions, and publications to give you sourced answers.",
  },
];

export function OnboardingTour({ active, onComplete }: OnboardingTourProps) {
  const [step, setStep] = useState(0);

  // Reset step when tour becomes active
  useEffect(() => {
    if (active) setStep(0);
  }, [active]);

  if (!active) return null;

  const current = steps[step];
  const isLast = step === steps.length - 1;

  return (
    <div className="fixed inset-0 z-[60] animate-fade-in">
      {/* Dark overlay */}
      <div className="absolute inset-0 bg-black/60" />

      {/* Content card — centered */}
      <div className="absolute inset-0 flex items-center justify-center p-4">
        <div className="bg-surface rounded-2xl p-6 shadow-xl max-w-[360px] w-full relative animate-scale-in">
          {/* Step indicator */}
          <div className="flex gap-1.5 mb-4 justify-center">
            {steps.map((_, i) => (
              <div
                key={i}
                className={cn(
                  "w-2 h-2 rounded-full transition-colors",
                  i <= step ? "bg-apple-blue" : "bg-surface-tertiary"
                )}
              />
            ))}
          </div>

          <h3 className="text-[17px] font-semibold text-primary mb-2">{current.title}</h3>
          <p className="text-[14px] text-secondary leading-relaxed mb-6">{current.text}</p>

          <div className="flex items-center justify-between">
            <button
              onClick={onComplete}
              className="text-[13px] text-tertiary hover:text-secondary cursor-pointer"
            >
              Skip tour
            </button>
            <button
              onClick={() => {
                if (isLast) {
                  onComplete();
                } else {
                  setStep((s) => s + 1);
                }
              }}
              className="px-4 py-2 rounded-lg bg-apple-blue text-white text-[14px] font-medium hover:brightness-110 transition-all cursor-pointer"
            >
              {isLast ? "Get Started" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/onboarding/
git commit -m "feat(frontend): add 3-step onboarding tour with spotlight overlay"
```

---

## Task 14: Analytics Dashboard

**Files:**
- Create: `frontend/components/dashboard/analytics-dashboard.tsx`

- [ ] **Step 1: Create the full analytics dashboard with all sections**

```tsx
// frontend/components/dashboard/analytics-dashboard.tsx
"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// TODO: wire to real API — all values below are placeholder mock data

const metrics = [
  { label: "Total Clients", value: "67", trend: "+3", trendUp: true, color: "text-apple-blue" },
  { label: "Returns Filed", value: "42", trend: "63%", trendUp: true, color: "text-green-600 dark:text-green-400" },
  { label: "Pending Review", value: "12", trend: "5 urgent", trendUp: false, color: "text-orange-500" },
  { label: "Revenue", value: "$148,500", trend: "+12% YoY", trendUp: true, color: "text-green-600 dark:text-green-400" },
];

const pipeline = [
  { stage: "Intake", count: 8, color: "bg-badge-pending-bg", badge: "pending" as const },
  { stage: "Documents", count: 12, color: "bg-badge-progress-bg", badge: "inProgress" as const },
  { stage: "Review", count: 15, color: "bg-badge-review-bg", badge: "review" as const },
  { stage: "Filing", count: 18, color: "bg-badge-complete-bg", badge: "completed" as const },
  { stage: "Complete", count: 14, color: "bg-badge-filed-bg", badge: "filed" as const },
];

const deadlines = [
  { date: "Apr 15, 2026", desc: "Individual returns", clients: 8, accent: "text-red-500" },
  { date: "Jun 15, 2026", desc: "Estimated Q2 payments", clients: 3, accent: "text-orange-500" },
  { date: "Sep 15, 2026", desc: "Extension deadline", clients: 2, accent: "text-yellow-600 dark:text-yellow-400" },
  { date: "Jan 15, 2027", desc: "Estimated Q4 payments", clients: 1, accent: "text-tertiary" },
];

const activity = [
  { icon: "\u2B06", text: "Sarah Johnson's W-2 uploaded", time: "2h ago" },
  { icon: "\uD83D\uDD0D", text: "Data extracted from Mike Chen's 1099-INT", time: "5h ago" },
  { icon: "\uD83D\uDCC4", text: "Draft return generated for Lisa Park", time: "8h ago" },
  { icon: "\uD83D\uDCAC", text: "New response for David Kim's query", time: "1d ago" },
  { icon: "\uD83D\uDC64", text: "New client James Wright added", time: "1d ago" },
];

const seasonTotal = 67;
const seasonFiled = 42;
const seasonReview = 12;
const seasonPending = seasonTotal - seasonFiled - seasonReview;

export function AnalyticsDashboard() {
  return (
    <div className="p-6 max-md:p-4 space-y-6 overflow-y-auto h-full">
      <h2 className="text-[17px] font-semibold text-primary">Dashboard</h2>

      {/* Row 1: Metric cards */}
      <div className="grid grid-cols-4 max-md:grid-cols-2 gap-4 max-md:gap-3">
        {metrics.map((m) => (
          <Card key={m.label} className="p-5 max-md:p-4 text-center">
            <div className={cn("text-[28px] max-md:text-[24px] font-semibold", m.color)}>{m.value}</div>
            <div className="text-[11px] text-secondary uppercase tracking-wider mt-1">{m.label}</div>
            <div className={cn("text-[11px] mt-1", m.trendUp ? "text-green-600 dark:text-green-400" : "text-orange-500")}>
              {m.trendUp ? "\u2191" : ""} {m.trend}
            </div>
          </Card>
        ))}
      </div>

      {/* Row 2: Filing pipeline */}
      <Card className="p-5">
        <h3 className="text-[13px] font-semibold text-primary mb-4">Filing Pipeline</h3>
        <div className="flex max-md:flex-col gap-3">
          {pipeline.map((p) => (
            <div key={p.stage} className="flex-1 text-center">
              <Badge variant={p.badge}>{p.stage}</Badge>
              <div className="text-[20px] font-semibold text-primary mt-2">{p.count}</div>
              <div className="h-2 rounded-full bg-surface-tertiary mt-2 overflow-hidden">
                <div
                  className={cn("h-full rounded-full", p.color)}
                  style={{ width: `${(p.count / seasonTotal) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Row 3: Deadlines + Activity */}
      <div className="grid grid-cols-2 max-md:grid-cols-1 gap-4">
        {/* Deadline timeline */}
        <Card className="p-5">
          <h3 className="text-[13px] font-semibold text-primary mb-4">Upcoming Deadlines</h3>
          <div className="space-y-4">
            {deadlines.map((d) => (
              <div key={d.date} className="flex items-start gap-3">
                <div className="flex flex-col items-center">
                  <div className={cn("w-2.5 h-2.5 rounded-full border-2 shrink-0", d.accent.replace("text-", "border-"))} />
                  <div className="w-px h-8 bg-divider last:hidden" />
                </div>
                <div className="flex-1">
                  <div className={cn("text-[12px] font-semibold", d.accent)}>{d.date}</div>
                  <div className="text-[12px] text-primary">{d.desc}</div>
                  <div className="text-[11px] text-tertiary">{d.clients} client{d.clients > 1 ? "s" : ""}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Activity feed */}
        <Card className="p-5">
          <h3 className="text-[13px] font-semibold text-primary mb-4">Recent Activity</h3>
          <div className="space-y-3">
            {activity.map((a, i) => (
              <div key={i} className="flex items-start gap-3">
                <span className="text-[14px] mt-0.5 shrink-0">{a.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-[12px] text-primary">{a.text}</div>
                  <div className="text-[11px] text-tertiary">{a.time}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Row 4: Season progress */}
      <Card className="p-5">
        <h3 className="text-[13px] font-semibold text-primary mb-3">
          Tax Season 2025: {seasonFiled} of {seasonTotal} returns filed ({Math.round((seasonFiled / seasonTotal) * 100)}%)
        </h3>
        <div className="h-3 rounded-full bg-surface-tertiary overflow-hidden flex">
          <div className="bg-green-500 h-full" style={{ width: `${(seasonFiled / seasonTotal) * 100}%` }} />
          <div className="bg-orange-500 h-full" style={{ width: `${(seasonReview / seasonTotal) * 100}%` }} />
        </div>
        <div className="flex gap-4 mt-2 text-[11px]">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500" /> Filed ({seasonFiled})</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-orange-500" /> Review ({seasonReview})</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-surface-tertiary" /> Pending ({seasonPending})</span>
        </div>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/dashboard/analytics-dashboard.tsx
git commit -m "feat(frontend): add analytics dashboard with metrics, pipeline, deadlines, and activity feed"
```

---

## Task 15: Wire Settings, Onboarding, and Dashboard into Page

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Add imports and state**

At the top of `page.tsx`, add:
```tsx
import { SettingsModal } from "@/components/settings/settings-modal";
import { OnboardingTour } from "@/components/onboarding/onboarding-tour";
import { AnalyticsDashboard } from "@/components/dashboard/analytics-dashboard";
```

Add state (near the other useState declarations):
```tsx
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [showDashboard, setShowDashboard] = useState(false);

  // Check onboarding on mount
  useEffect(() => {
    if (!localStorage.getItem("taxflow_onboarding_complete")) {
      setShowOnboarding(true);
    }
  }, []);

  const completeOnboarding = useCallback(() => {
    localStorage.setItem("taxflow_onboarding_complete", "true");
    setShowOnboarding(false);
  }, []);

  const replayTour = useCallback(() => {
    setSettingsOpen(false);
    localStorage.removeItem("taxflow_onboarding_complete");
    setShowOnboarding(true);
  }, []);
```

- [ ] **Step 2: Pass dashboard and settings handlers to TopBar**

Update TopBar usage:
```tsx
      <TopBar
        stats={{ clients: totalClients, filed: filedCount, review: reviewCount }}
        deadline="April 15 in 4 days"
        user={{ initials: "SC" }}
        showMenu={!isDesktopXL}
        onMenuToggle={() => setSidebarOpen(!sidebarOpen)}
        clientName={isMobile ? activeClient?.name : undefined}
        onDashboard={() => setShowDashboard(!showDashboard)}
      />
```

- [ ] **Step 3: Add dashboard view in the chat area**

In the desktop layout, wrap the `chatContent` so it shows dashboard when toggled:

```tsx
          {showDashboard ? <AnalyticsDashboard /> : chatContent}
```

And in the mobile layout, add a similar conditional or give the dashboard its own way to appear (via the top bar icon). For simplicity, the dashboard replaces the chat panel when toggled:

```tsx
            {mobileTab === "chat" && (showDashboard ? <AnalyticsDashboard /> : chatContent)}
```

- [ ] **Step 4: Add the modal and tour components at the bottom of the return block**

Just before the closing `</div>` of the return:
```tsx
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onReplayTour={replayTour}
      />

      <OnboardingTour
        active={showOnboarding}
        onComplete={completeOnboarding}
      />
```

- [ ] **Step 5: Add avatar click to open settings**

In the TopBar component, add an `onAvatarClick` prop and pass `() => setSettingsOpen(true)` from page.tsx. Update `top-bar.tsx` to accept `onAvatarClick?: () => void` and add `onClick={onAvatarClick}` to the avatar wrapper div:

```tsx
        <button onClick={onAvatarClick} className="hidden md:block cursor-pointer">
          <Avatar initials={user.initials} size="sm" color="#6B7280" />
        </button>
```

- [ ] **Step 6: Verify build**

Run: `cd frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 7: Test the dev server manually**

Run: `cd frontend && npm run dev`

Check:
1. App loads in light mode by default
2. Theme toggle cycles through light → dark → system
3. Dark mode renders correctly (dark backgrounds, light text)
4. Onboarding tour appears on first visit
5. Sidebar collapses at tablet width
6. Bottom tab bar appears at mobile width
7. Settings modal opens from avatar click
8. Dashboard toggles from chart icon
9. Notification bell shows dropdown

- [ ] **Step 8: Commit**

```bash
git add frontend/app/page.tsx frontend/components/layout/top-bar.tsx
git commit -m "feat(frontend): wire settings, onboarding, analytics dashboard, and notification bell into main app"
```

---

## Summary

15 tasks producing 15 commits. Build order ensures each commit is independently functional:

1. Theme provider + CSS tokens (foundation)
2. Theme toggle component
3. UI component migration (button, card, modal, input, badge, avatar, progress, tabs)
4. Top bar redesign (glass, responsive)
5. Chat component migration
6. Layout + form component migration
7. Page.tsx token migration
8. Responsive layout (overlays, bottom tab bar, breakpoints)
9. Toast notifications
10. Skeleton loading
11. Settings page
12. Notification bell
13. Onboarding tour
14. Analytics dashboard
15. Wire everything together
