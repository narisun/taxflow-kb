"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { MeResponse } from "@/lib/api-client";

interface MeContextValue {
  me: MeResponse;
  updateMe: (updated: MeResponse) => void;
}

const MeContext = createContext<MeContextValue | null>(null);

export function MeProvider({ value, onUpdate, children }: { value: MeResponse; onUpdate?: (v: MeResponse) => void; children: ReactNode }) {
  return <MeContext.Provider value={{ me: value, updateMe: onUpdate || (() => {}) }}>{children}</MeContext.Provider>;
}

export function useMe(): MeResponse {
  const v = useContext(MeContext);
  if (!v) throw new Error("useMe must be used within MeProvider");
  return v.me;
}

/** Returns a function to update the Me state after a profile change. */
export function useUpdateMe(): (updated: MeResponse) => void {
  const v = useContext(MeContext);
  return v?.updateMe || (() => {});
}

/** Convenience: returns false if there is no Me available (mock mode without provider). */
export function useCanViewPii(): boolean {
  const v = useContext(MeContext);
  return Boolean(v?.me?.permissions?.can_view_pii);
}

/** Returns the user's IANA timezone (e.g. "America/New_York") or the browser default. */
export function useTimezone(): string {
  const v = useContext(MeContext);
  return v?.me?.user?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** Safe version of useMe that returns null instead of throwing when no provider is mounted. */
export function useMeOrNull(): MeResponse | null {
  const v = useContext(MeContext);
  return v?.me ?? null;
}
