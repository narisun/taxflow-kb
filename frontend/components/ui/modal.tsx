"use client";

import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}

function Modal({ open, onClose, children, className }: ModalProps) {
  // Deliberately NOT closing on Escape or backdrop click — modals only
  // dismiss via the explicit Close button so accidental clicks don't drop
  // half-filled forms. ``onClose`` is held by the consumer for that button.
  void onClose;

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center animate-fade-in"
      role="dialog"
      aria-modal="true"
    >
      <div
        className={cn(
          "bg-surface rounded-2xl shadow-2xl max-h-[calc(100vh-48px)] overflow-hidden animate-scale-in w-full mx-4 flex flex-col",
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
