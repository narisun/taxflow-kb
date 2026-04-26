"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { api } from "@/lib/api-client";
import { useCanViewPii } from "@/components/auth/me-context";

/**
 * Hide-by-default input for encrypted PII (SSN, DOB, street).
 *
 * Why this component exists
 * -------------------------
 * PII like SSNs and DOBs end up on the screen during client meetings, screen
 * shares, and over-the-shoulder situations. Showing the plaintext value as
 * the default contents of an edit form has caused real-world leaks. Pattern
 * here mirrors password managers (1Password, Apple Wallet):
 *
 *  - Input is empty by default; the masked snippet (``***-**-1234``) shows
 *    as a placeholder so the user knows a value is stored.
 *  - An eye icon next to the field — visible ONLY if the caller has
 *    ``can_view_pii`` permission — fetches the plaintext via
 *    ``/api/clients/{id}/reveal-pii`` and fills the input.
 *  - After ``REVEAL_TIMEOUT_MS`` the value is wiped back to empty (mask
 *    placeholder returns). Cancelled if the user starts typing — once they
 *    are actively editing, the field stays revealed indefinitely.
 *  - Save semantics: an empty field on submit is interpreted by the parent
 *    page as "leave unchanged". So a user who never reveals/types still
 *    preserves the stored value.
 *
 * Limitations
 * -----------
 *  - The ``date`` HTML input doesn't render a custom string placeholder; we
 *    show the masked DOB as a small adjacent label instead.
 *  - The reveal call is best-effort — a 403 (no permission) silently
 *    suppresses the eye button.
 */
const REVEAL_TIMEOUT_MS = 8000;

export type PiiFieldName =
  | "primary_ssn"
  | "primary_dob"
  | "spouse_ssn"
  | "spouse_dob"
  | "street";

interface PiiInputProps {
  fieldName: PiiFieldName;
  /** Undefined in create mode — eye button is hidden because there's nothing
   *  to reveal yet. */
  clientId?: string;
  /** Snippet from the API (``***-**-1234`` etc.). When present, indicates a
   *  value exists on the server. */
  maskedValue?: string;
  /** Current form value (plaintext that will be POST/PATCHed). */
  value: string;
  onChange: (next: string) => void;
  type?: "text" | "date";
  /** Placeholder used when no stored value exists (create mode, or cleared). */
  placeholder?: string;
  /** Pass-through for input attrs the form needs. */
  className?: string;
  inputMode?: "text" | "numeric" | "decimal" | "tel" | "search" | "email" | "url" | "none";
  maxLength?: number;
  hasError?: boolean;
  /** Optional style overrides for the wrapper. Most callers won't need this. */
  style?: CSSProperties;
}

/** Inline SVG icons (no new deps). */
function EyeIcon({ open }: { open: boolean }) {
  if (open) {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    );
  }
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a19.6 19.6 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A10.94 10.94 0 0 1 12 4c7 0 11 8 11 8a19.6 19.6 0 0 1-2.16 3.19" />
      <path d="M14.12 14.12a3 3 0 0 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}

export function PiiInput({
  fieldName,
  clientId,
  maskedValue,
  value,
  onChange,
  type = "text",
  placeholder,
  className,
  inputMode,
  maxLength,
  hasError,
  style,
}: PiiInputProps) {
  const canView = useCanViewPii();
  const [revealed, setRevealed] = useState(false);
  const [revealing, setRevealing] = useState(false);
  const timerRef = useRef<number | null>(null);

  // Cancel any pending auto-mask timer on unmount or field change.
  useEffect(() => () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
  }, []);

  const startMaskTimer = () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      setRevealed(false);
      onChange("");
      timerRef.current = null;
    }, REVEAL_TIMEOUT_MS);
  };

  const cancelMaskTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const handleReveal = async () => {
    if (!clientId || revealing) return;
    setRevealing(true);
    try {
      const r = await api.clients.revealPii(clientId, [fieldName]);
      const plain = r[fieldName] ?? "";
      onChange(plain);
      setRevealed(true);
      startMaskTimer();
    } catch {
      // 403 / network — silently leave masked. The user can still type a new
      // value to overwrite.
    } finally {
      setRevealing(false);
    }
  };

  const handleHide = () => {
    cancelMaskTimer();
    setRevealed(false);
    onChange("");
  };

  const handleInput = (next: string) => {
    // First user-edit after reveal cancels the auto-mask timer — they're
    // actively working with the value and probably don't want it to vanish.
    if (revealed) cancelMaskTimer();
    onChange(next);
  };

  // For text inputs, use the masked snippet as the placeholder; for date
  // inputs the browser ignores custom string placeholders, so we render a
  // small adjacent hint instead (handled by the consumer label).
  const effectivePlaceholder =
    type === "text" && !value && maskedValue
      ? maskedValue
      : placeholder;

  // Hide eye if user has no permission, or there's nothing to reveal.
  const showEye = canView && Boolean(clientId) && Boolean(maskedValue);

  return (
    <div className="relative" style={style}>
      <input
        type={type}
        value={value}
        onChange={(e) => handleInput(e.target.value)}
        placeholder={effectivePlaceholder}
        inputMode={inputMode}
        maxLength={maxLength}
        className={className}
        // Prevent browser autofill for SSN — sensitive
        autoComplete="off"
        spellCheck={false}
        style={{ paddingRight: showEye ? "1.75rem" : undefined }}
        aria-invalid={hasError ? true : undefined}
      />
      {showEye && (
        <button
          type="button"
          onClick={revealed ? handleHide : handleReveal}
          disabled={revealing}
          aria-label={revealed ? "Hide value" : "Reveal value"}
          title={revealed ? `Hides automatically in ${REVEAL_TIMEOUT_MS / 1000}s` : "Reveal"}
          className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1 rounded text-tertiary hover:text-primary hover:bg-surface-secondary transition-colors cursor-pointer disabled:opacity-40"
        >
          <EyeIcon open={revealed} />
        </button>
      )}
    </div>
  );
}
