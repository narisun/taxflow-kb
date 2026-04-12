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
  useEffect(() => {
    if (open) document.body.style.overflow = "hidden";
    else document.body.style.overflow = "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-black/30 animate-fade-in" onClick={onClose} />
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
