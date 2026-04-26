import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Safe JSON parse with fallback */
export function parseJson<T>(json: string, fallback: T): T {
  try {
    return JSON.parse(json) as T;
  } catch {
    return fallback;
  }
}

/** Format currency */
export function fmtCurrency(v: number | undefined): string {
  return v != null ? `$${v.toLocaleString()}` : "\u2014";
}

/**
 * Ensure a timestamp string is treated as UTC.
 * Backend returns naive datetimes (no Z suffix) that are actually UTC.
 * Without this, JS parses "2026-04-18T19:51:00" as local time.
 */
function asUtc(iso: string): Date {
  // Already has timezone info (Z or +/-offset) — parse as-is
  if (/Z|[+-]\d{2}:\d{2}$/.test(iso)) return new Date(iso);
  // Naive datetime from backend — treat as UTC
  return new Date(iso + "Z");
}

/** Format timestamp for display (date + time in user timezone) */
export function fmtTimestamp(iso: string, tz?: string): string {
  const d = asUtc(iso);
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", ...(tz && { timeZone: tz }) };
  const timeOpts: Intl.DateTimeFormatOptions = { hour: "numeric", minute: "2-digit", ...(tz && { timeZone: tz }) };
  return d.toLocaleDateString("en-US", opts) + " " + d.toLocaleTimeString("en-US", timeOpts);
}

/** Format short date in user timezone */
export function fmtDate(iso: string, tz?: string): string {
  return asUtc(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", ...(tz && { timeZone: tz }) });
}

/** Format time only in user timezone */
export function fmtTime(iso: string, tz?: string): string {
  return asUtc(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", ...(tz && { timeZone: tz }) });
}

/** Derive 1-2 character initials from a name or email */
export function deriveInitials(name?: string, email?: string): string {
  const source = (name || email || "").trim();
  if (!source) return "?";
  if (source.includes("@")) return source.split("@")[0].slice(0, 2).toUpperCase();
  const parts = source.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Detect IRS form type from filename */
export function detectFormType(filename: string): string {
  const f = filename.toLowerCase();
  if (f.includes("w2") || f.includes("w-2")) return "W-2";
  if (f.includes("1099-int") || f.includes("1099int")) return "1099-INT";
  if (f.includes("1099-nec") || f.includes("1099nec")) return "1099-NEC";
  if (f.includes("1099-b") || f.includes("1099b")) return "1099-B";
  if (f.includes("1099-div") || f.includes("1099div")) return "1099-DIV";
  if (f.includes("1099")) return "1099";
  if (f.includes("1098")) return "1098";
  if (f.includes("k-1") || f.includes("k1")) return "K-1";
  return "Other";
}
