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
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={cn(
          "bg-white rounded-2xl shadow-2xl max-h-[calc(100vh-48px)] overflow-hidden animate-in",
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
    <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
      <div className="text-[17px] font-semibold text-[#1d1d1f]">{children}</div>
      {onClose && (
        <button
          onClick={onClose}
          className="rounded-lg border border-gray-200 px-2 py-1 text-[13px] text-gray-500 hover:bg-red-50 hover:text-red-500 transition-colors cursor-pointer"
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
    <div className={cn("px-6 py-4 border-t border-gray-100 flex justify-end gap-2", className)}>
      {children}
    </div>
  );
}

export { Modal, ModalHeader, ModalBody, ModalFooter, type ModalProps };
