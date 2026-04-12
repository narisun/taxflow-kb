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

export const useIsMobile = () => !useMediaQuery("(min-width: 768px)");
export const useIsTablet = () => useMediaQuery("(min-width: 768px)") && !useMediaQuery("(min-width: 1024px)");
export const useIsDesktop = () => useMediaQuery("(min-width: 1024px)");
export const useIsDesktopXL = () => useMediaQuery("(min-width: 1280px)");
