"use client";

/**
 * Account-onboarding wizard shown on first login (when ``/api/auth/me``
 * returns ``onboarding_status === "pending"``).
 *
 * Industry-standard split: Auth0 owns identity (email/password/MFA); this
 * wizard captures everything else — firm name, role, timezone — and POSTs
 * to ``/api/auth/complete-onboarding``. Only after success does the app
 * expose tenant data.
 *
 * Design choices:
 * - 4 steps with a progress rail; restart-from-1 if the tab closes (data
 *   is short enough that persistence would add complexity for little win).
 * - "Join existing firm" is visible as a radio option but disabled and
 *   labelled "Coming soon". Phase 2 will wire invite-token flow behind it.
 * - Timezone is auto-detected from the browser. The user can skip the
 *   confirmation step's fields if they want.
 */
import { useCallback, useMemo, useState } from "react";
import { api, type MeResponse, type OnboardingPayload } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

interface AccountWizardProps {
  userName: string;
  userEmail: string;
  emailVerified?: boolean;
  onComplete: (me: MeResponse) => void;
}

type Choice = "create" | "join";

export function AccountWizard({ userName, userEmail, emailVerified, onComplete }: AccountWizardProps) {
  const { toast } = useToast();
  const [step, setStep] = useState(1);
  const [choice, setChoice] = useState<Choice>("create");
  const [firmName, setFirmName] = useState("");
  const detectedTz = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch {
      return "";
    }
  }, []);
  const [timezone, setTimezone] = useState(detectedTz);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const next = () => setStep((s) => Math.min(4, s + 1));
  const back = () => setStep((s) => Math.max(1, s - 1));

  const canAdvanceFromStep3 = firmName.trim().length >= 2;

  /** Pull the meaningful detail out of the api-client's error message,
   *  which is shaped like ``API 403: {"detail":"…"}``. */
  const _humanizeError = (raw: string): string => {
    const match = raw.match(/API \d+: (.+)$/);
    if (!match) return raw;
    try {
      const parsed = JSON.parse(match[1]);
      const detail = parsed.detail || parsed.message || match[1];
      // Replace the backend's terse message with a user-friendly one
      if (detail.includes("Verify your email")) {
        return "Your email address hasn't been verified yet. Please check your inbox (and spam folder) for a verification link from Auth0, click it, then come back and try again.";
      }
      return detail;
    } catch {
      return match[1];
    }
  };

  const submit = useCallback(async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const payload: OnboardingPayload = {
        firm_name: firmName.trim(),
        role: "admin",
        timezone: timezone || null,
      };
      const me = await api.auth.completeOnboarding(payload);
      toast("success", "Welcome to TaxFlow AI", `Workspace "${me.organization?.name}" is ready.`);
      onComplete(me);
    } catch (err) {
      const raw = err instanceof Error ? err.message : "Unknown error";
      setSubmitError(_humanizeError(raw));
      setSubmitting(false);
    }
  }, [firmName, timezone, toast, onComplete]);

  return (
    <div className="h-screen w-screen flex items-center justify-center bg-surface-secondary p-4">
      <div className="w-full max-w-[520px] bg-surface rounded-2xl shadow-xl border border-divider overflow-hidden">
        <ProgressRail step={step} total={4} />

        <div className="px-8 py-8">
          {step === 1 && (
            <StepWelcome userName={userName} userEmail={userEmail} emailVerified={emailVerified} onNext={next} />
          )}
          {step === 2 && (
            <StepChoice
              choice={choice}
              onChoose={setChoice}
              onBack={back}
              onNext={next}
            />
          )}
          {step === 3 && (
            <StepFirmDetails
              firmName={firmName}
              setFirmName={setFirmName}
              timezone={timezone}
              setTimezone={setTimezone}
              detectedTz={detectedTz}
              canAdvance={canAdvanceFromStep3}
              onBack={back}
              onNext={next}
            />
          )}
          {step === 4 && (
            <StepConfirm
              firmName={firmName}
              timezone={timezone}
              userEmail={userEmail}
              emailVerified={emailVerified}
              submitting={submitting}
              error={submitError}
              onBack={back}
              onSubmit={submit}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Progress rail ────────────────────────────────────────────────────────

function ProgressRail({ step, total }: { step: number; total: number }) {
  return (
    <div className="flex gap-1 px-8 pt-6">
      {Array.from({ length: total }, (_, i) => {
        const n = i + 1;
        const active = n <= step;
        return (
          <div
            key={n}
            className={`h-1 flex-1 rounded-full transition-colors ${
              active ? "bg-apple-blue" : "bg-surface-tertiary"
            }`}
          />
        );
      })}
    </div>
  );
}

// ─── Step 1 — welcome ─────────────────────────────────────────────────────

function StepWelcome({
  userName,
  userEmail,
  emailVerified,
  onNext,
}: {
  userName: string;
  userEmail: string;
  emailVerified?: boolean;
  onNext: () => void;
}) {
  // Auth0 defaults `name` to the email when the user has no display name.
  // Pretty-print: if name looks like an email, take the local part.
  const greeting = (() => {
    if (!userName) return "";
    const cleaned = userName.includes("@") ? userName.split("@")[0] : userName;
    return cleaned.split(" ")[0];
  })();
  return (
    <div>
      <h2 className="text-[20px] font-semibold text-primary">
        Welcome{greeting ? `, ${greeting}` : ""}
      </h2>
      <p className="text-[13px] text-tertiary mt-1">
        You signed in as <span className="text-secondary">{userEmail}</span>
      </p>

      {emailVerified === false && (
        <div className="mt-5 rounded-lg border border-orange-300 bg-orange-50 dark:bg-orange-950/20 dark:border-orange-400/40 p-4">
          <div className="flex items-start gap-2.5">
            <svg className="w-5 h-5 text-orange-500 dark:text-orange-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
            </svg>
            <div>
              <div className="text-[13px] font-semibold text-orange-800 dark:text-orange-300">
                Email verification required
              </div>
              <p className="text-[12px] text-gray-800 dark:text-gray-200 mt-1 leading-relaxed">
                Check your inbox for a verification email from Auth0 and click the
                link to verify <span className="font-medium">{userEmail}</span>.
                You&apos;ll need to verify your email before you can create your workspace.
              </p>
              <p className="text-[11px] text-gray-600 dark:text-gray-400 mt-2">
                Don&apos;t see it? Check your spam folder or sign out and sign in again to resend.
              </p>
            </div>
          </div>
        </div>
      )}

      <p className="text-[14px] text-secondary mt-5 leading-relaxed">
        Let&apos;s set up your workspace. This takes about 30 seconds and can&apos;t
        be skipped — you&apos;ll need a workspace before you can add clients.
      </p>
      <div className="mt-8 flex justify-end">
        <Button variant="primary" onClick={onNext} className="text-[14px]">
          Get started
        </Button>
      </div>
    </div>
  );
}

// ─── Step 2 — create new vs join existing ────────────────────────────────

function StepChoice({
  choice,
  onChoose,
  onBack,
  onNext,
}: {
  choice: Choice;
  onChoose: (c: Choice) => void;
  onBack: () => void;
  onNext: () => void;
}) {
  return (
    <div>
      <h2 className="text-[20px] font-semibold text-primary">Create or join a firm</h2>
      <p className="text-[13px] text-tertiary mt-1">
        Each firm is its own workspace — clients, documents, and chat are scoped to it.
      </p>

      <div className="mt-6 space-y-3">
        <label
          className={`flex items-start gap-3 p-4 rounded-lg border cursor-pointer transition-colors ${
            choice === "create"
              ? "border-apple-blue bg-apple-blue/5"
              : "border-divider hover:border-tertiary"
          }`}
        >
          <input
            type="radio"
            name="onboard-choice"
            value="create"
            checked={choice === "create"}
            onChange={() => onChoose("create")}
            className="mt-1 accent-apple-blue"
          />
          <div>
            <div className="text-[14px] font-medium text-primary">
              Create a new firm
            </div>
            <div className="text-[12px] text-tertiary mt-0.5">
              You&apos;ll be the admin. Add colleagues later via invite.
            </div>
          </div>
        </label>

        <label
          className="flex items-start gap-3 p-4 rounded-lg border border-divider opacity-50 cursor-not-allowed"
          aria-disabled
        >
          <input type="radio" disabled className="mt-1" />
          <div>
            <div className="text-[14px] font-medium text-primary flex items-center gap-2">
              Join an existing firm
              <span className="text-[10px] font-medium px-1.5 py-px rounded-full bg-surface-tertiary text-secondary">
                Coming soon
              </span>
            </div>
            <div className="text-[12px] text-tertiary mt-0.5">
              Use an invite link from your firm&apos;s admin.
            </div>
          </div>
        </label>
      </div>

      <div className="mt-8 flex justify-between">
        <Button variant="ghost" onClick={onBack} className="text-[14px]">
          Back
        </Button>
        <Button
          variant="primary"
          onClick={onNext}
          disabled={choice !== "create"}
          title={choice !== "create" ? "Select 'Create a new firm' to continue" : undefined}
          className="text-[14px]"
        >
          Continue
        </Button>
      </div>
    </div>
  );
}

// ─── Step 3 — firm details ────────────────────────────────────────────────

function StepFirmDetails({
  firmName,
  setFirmName,
  timezone,
  setTimezone,
  detectedTz,
  canAdvance,
  onBack,
  onNext,
}: {
  firmName: string;
  setFirmName: (v: string) => void;
  timezone: string;
  setTimezone: (v: string) => void;
  detectedTz: string;
  canAdvance: boolean;
  onBack: () => void;
  onNext: () => void;
}) {
  return (
    <div>
      <h2 className="text-[20px] font-semibold text-primary">About your firm</h2>
      <p className="text-[13px] text-tertiary mt-1">Only the firm name is required.</p>

      <div className="mt-6 space-y-4">
        <div>
          <label className="block text-[12px] font-medium text-secondary mb-1">
            Firm name <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={firmName}
            onChange={(e) => setFirmName(e.target.value)}
            placeholder="Firm name"
            autoFocus
            className="w-full px-3 py-2 rounded-lg border border-divider bg-surface text-[14px] text-primary focus:border-apple-blue focus:ring-2 focus:ring-apple-blue/20 outline-none"
          />
          <div className="text-[11px] text-tertiary mt-1">
            Displayed to clients in generated documents and emails.
          </div>
        </div>

        <div>
          <label className="block text-[12px] font-medium text-secondary mb-1">
            Timezone
          </label>
          <input
            type="text"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            placeholder={detectedTz || "America/New_York"}
            className="w-full px-3 py-2 rounded-lg border border-divider bg-surface text-[14px] text-primary focus:border-apple-blue focus:ring-2 focus:ring-apple-blue/20 outline-none"
          />
          <div className="text-[11px] text-tertiary mt-1">
            Detected from your browser. Used for due-date reminders and timestamps.
          </div>
        </div>
      </div>

      <div className="mt-8 flex justify-between">
        <Button variant="ghost" onClick={onBack} className="text-[14px]">
          Back
        </Button>
        <Button
          variant="primary"
          onClick={onNext}
          disabled={!canAdvance}
          title={!canAdvance ? "Enter a firm name (at least 2 characters) to continue" : undefined}
          className="text-[14px]"
        >
          Continue
        </Button>
      </div>
    </div>
  );
}

// ─── Step 4 — confirm ─────────────────────────────────────────────────────

function StepConfirm({
  firmName,
  timezone,
  userEmail,
  emailVerified,
  submitting,
  error,
  onBack,
  onSubmit,
}: {
  firmName: string;
  timezone: string;
  userEmail: string;
  emailVerified?: boolean;
  submitting: boolean;
  error: string | null;
  onBack: () => void;
  onSubmit: () => void;
}) {
  return (
    <div>
      <h2 className="text-[20px] font-semibold text-primary">Review</h2>
      <p className="text-[13px] text-tertiary mt-1">
        You can change all of these later in Settings.
      </p>

      <dl className="mt-6 space-y-3 text-[13px]">
        <div className="flex justify-between gap-4 py-2 border-b border-divider">
          <dt className="text-tertiary">Workspace type</dt>
          <dd className="text-primary font-medium">New firm</dd>
        </div>
        <div className="flex justify-between gap-4 py-2 border-b border-divider">
          <dt className="text-tertiary">Firm name</dt>
          <dd className="text-primary font-medium text-right">{firmName}</dd>
        </div>
        <div className="flex justify-between gap-4 py-2 border-b border-divider">
          <dt className="text-tertiary">Your role</dt>
          <dd className="text-primary font-medium">Admin</dd>
        </div>
        <div className="flex justify-between gap-4 py-2">
          <dt className="text-tertiary">Timezone</dt>
          <dd className="text-primary font-medium text-right">
            {timezone || "Not set"}
          </dd>
        </div>
      </dl>

      {emailVerified === false && (
        <div className="mt-5 rounded-lg border border-orange-300 bg-orange-50 dark:bg-orange-950/20 dark:border-orange-400/40 p-4">
          <div className="flex items-start gap-2.5">
            <svg className="w-5 h-5 text-orange-500 dark:text-orange-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
            </svg>
            <div>
              <div className="text-[13px] font-semibold text-orange-800 dark:text-orange-300">
                Email verification required
              </div>
              <p className="text-[12px] text-gray-800 dark:text-gray-200 mt-1 leading-relaxed">
                Check your inbox for a verification email from Auth0 and click the
                link to verify <span className="font-medium">{userEmail}</span>.
                You&apos;ll need to verify your email before you can create your workspace.
              </p>
              <p className="text-[11px] text-gray-600 dark:text-gray-400 mt-2">
                Don&apos;t see it? Check your spam folder or sign out and sign in again to resend.
              </p>
            </div>
          </div>
        </div>
      )}

      {error && emailVerified !== false && (
        <div className="mt-6 rounded-lg border border-red-300 bg-red-50 dark:bg-red-950/30 dark:border-red-900 p-3">
          <div className="text-[12px] font-semibold text-red-700 dark:text-red-300 mb-0.5">
            Couldn&apos;t create your workspace
          </div>
          <div className="text-[12px] text-red-700/90 dark:text-red-300/90 leading-relaxed">
            {error}
          </div>
        </div>
      )}

      <div className="mt-8 flex justify-between">
        <Button
          variant="ghost"
          onClick={onBack}
          disabled={submitting}
          className="text-[14px]"
        >
          Back
        </Button>
        <Button
          variant="primary"
          onClick={onSubmit}
          disabled={submitting}
          className="text-[14px]"
        >
          {submitting ? "Creating workspace\u2026" : "Create workspace"}
        </Button>
      </div>
    </div>
  );
}
