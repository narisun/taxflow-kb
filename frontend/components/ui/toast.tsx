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
