# Email Verification Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make email verification an explicit, mandatory gate before the onboarding wizard, with a "wrong email?" escape hatch.

**Architecture:** New `EmailVerificationGate` component renders between Auth0 auth and the onboarding wizard. `OnboardingGate` checks `email_verified` before deciding which to show. Social login users skip the gate entirely. The wizard loses all verification-related code.

**Tech Stack:** React 19, Next.js 16, Auth0 React SDK, Tailwind CSS 4

**Spec:** `docs/superpowers/specs/2026-04-24-email-verification-gate-design.md`

---

### Task 1: Create EmailVerificationGate component

**Files:**
- Create: `frontend/components/onboarding/email-verification-gate.tsx`

- [ ] **Step 1: Create the component file**

```tsx
"use client";

import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { Button } from "@/components/ui/button";

interface EmailVerificationGateProps {
  userEmail: string;
  onVerified: () => void;
}

export function EmailVerificationGate({ userEmail, onVerified }: EmailVerificationGateProps) {
  const { getAccessTokenSilently, user, logout } = useAuth0();
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCheckVerification = async () => {
    setChecking(true);
    setError(null);
    try {
      // Force a fresh token fetch so the SDK refreshes the user profile
      await getAccessTokenSilently({ cacheMode: "off" });
      // After the silent auth round-trip, the SDK's `user` object is updated.
      // But we need to re-read it after the async call, so we check via
      // a small delay to let React re-render with the updated user object.
      // A more reliable approach: re-fetch and check the claim directly.
      // The SDK updates `user` in place after getAccessTokenSilently.
      if (user?.email_verified) {
        onVerified();
      } else {
        setError("Email not yet verified. Please click the link in your email and try again.");
      }
    } catch {
      setError("Could not check verification status. Please try again.");
    } finally {
      setChecking(false);
    }
  };

  const handleWrongEmail = () => {
    logout({ logoutParams: { returnTo: window.location.origin } });
  };

  return (
    <div className="h-screen w-screen flex items-center justify-center bg-surface-secondary p-4">
      <div className="w-full max-w-[520px] bg-surface rounded-2xl shadow-xl border border-divider overflow-hidden">
        <div className="px-8 py-10">
          {/* Email icon */}
          <div className="flex justify-center mb-6">
            <div className="w-14 h-14 rounded-full bg-apple-blue/10 flex items-center justify-center">
              <svg className="w-7 h-7 text-apple-blue" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
              </svg>
            </div>
          </div>

          <h2 className="text-[20px] font-semibold text-primary text-center">
            Verify your email
          </h2>

          <p className="text-[14px] text-secondary mt-3 text-center leading-relaxed">
            We sent a verification link to{" "}
            <span className="font-medium text-primary">{userEmail}</span>.
            Click the link in your email to continue.
          </p>

          <p className="text-[12px] text-tertiary mt-2 text-center">
            Check your spam folder if you don&apos;t see it.
          </p>

          {error && (
            <div className="mt-5 rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800 p-3">
              <p className="text-[12px] text-amber-800 dark:text-amber-300 text-center leading-relaxed">
                {error}
              </p>
            </div>
          )}

          <div className="mt-8 flex flex-col items-center gap-3">
            <Button
              variant="primary"
              onClick={handleCheckVerification}
              disabled={checking}
              className="text-[14px] w-full max-w-[280px]"
            >
              {checking ? "Checking\u2026" : "I\u2019ve verified my email"}
            </Button>

            <button
              type="button"
              onClick={handleWrongEmail}
              className="text-[13px] text-tertiary hover:text-secondary hover:underline transition-colors"
            >
              Wrong email? Sign out and register again
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors related to `email-verification-gate.tsx`

- [ ] **Step 3: Commit**

```bash
git add frontend/components/onboarding/email-verification-gate.tsx
git commit -m "feat: add EmailVerificationGate component"
```

---

### Task 2: Wire EmailVerificationGate into OnboardingGate

**Files:**
- Modify: `frontend/components/auth/auth0-provider.tsx:1-124`

- [ ] **Step 1: Add the import**

At `frontend/components/auth/auth0-provider.tsx:11`, after the `AccountWizard` import, add:

```tsx
import { EmailVerificationGate } from "@/components/onboarding/email-verification-gate";
```

- [ ] **Step 2: Add verified state and gate logic**

Replace lines 66-124 of `auth0-provider.tsx` (the entire `OnboardingGate` function) with:

```tsx
function OnboardingGate({ children }: { children: ReactNode }) {
  const auth0 = (() => { try { return useAuth0(); } catch { return null; } })();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verified, setVerified] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.auth.me()
      .then((data) => {
        if (!cancelled) setMe(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load profile");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Initialize verified state from Auth0 user once available
  useEffect(() => {
    if (verified === null && auth0?.user !== undefined) {
      setVerified(auth0.user?.email_verified ?? true);
    }
  }, [auth0?.user, verified]);

  const handleComplete = useCallback((updated: MeResponse) => {
    setMe(updated);
  }, []);

  if (error) {
    return (
      <div className="h-screen w-screen flex items-center justify-center text-sm text-red-600 p-6 text-center">
        Could not load your profile: {error}
      </div>
    );
  }

  if (!me) {
    return (
      <div className="h-screen w-screen flex flex-col items-center justify-center gap-2 text-sm text-tertiary">
        <div className="w-6 h-6 border-2 border-apple-blue border-t-transparent rounded-full animate-spin" />
        <span>Loading your workspace&hellip;</span>
      </div>
    );
  }

  if (me.user.onboarding_status === "pending") {
    // Gate: email must be verified before entering the wizard
    if (verified === false) {
      return (
        <EmailVerificationGate
          userEmail={me.user.email}
          onVerified={() => setVerified(true)}
        />
      );
    }

    return (
      <AccountWizard
        userName={me.user.name}
        userEmail={me.user.email}
        onComplete={handleComplete}
      />
    );
  }

  return <MeProvider value={me} onUpdate={setMe}>{children}</MeProvider>;
}
```

Key changes:
- Added `verified` state initialized from `auth0.user.email_verified` (defaults to `true` when no Auth0 context, i.e. dev/mock mode)
- If `verified === false` and onboarding is pending, renders `EmailVerificationGate` instead of `AccountWizard`
- Removed `emailVerified` prop from `AccountWizard` render
- `onVerified` callback flips `verified` to `true`, causing re-render into the wizard

- [ ] **Step 3: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: Error — `AccountWizard` still expects `emailVerified` prop. This is expected; we fix it in Task 3.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/auth/auth0-provider.tsx
git commit -m "feat: wire EmailVerificationGate into OnboardingGate"
```

---

### Task 3: Remove email verification code from AccountWizard

**Files:**
- Modify: `frontend/components/onboarding/account-wizard.tsx`

- [ ] **Step 1: Remove `emailVerified` from props interface**

At line 25-30, change:

```tsx
interface AccountWizardProps {
  userName: string;
  userEmail: string;
  emailVerified?: boolean;
  onComplete: (me: MeResponse) => void;
}
```

to:

```tsx
interface AccountWizardProps {
  userName: string;
  userEmail: string;
  onComplete: (me: MeResponse) => void;
}
```

- [ ] **Step 2: Remove `emailVerified` from destructured props**

At line 34, change:

```tsx
export function AccountWizard({ userName, userEmail, emailVerified, onComplete }: AccountWizardProps) {
```

to:

```tsx
export function AccountWizard({ userName, userEmail, onComplete }: AccountWizardProps) {
```

- [ ] **Step 3: Remove `emailVerified` from StepWelcome render**

At line 99, change:

```tsx
<StepWelcome userName={userName} userEmail={userEmail} emailVerified={emailVerified} onNext={next} />
```

to:

```tsx
<StepWelcome userName={userName} userEmail={userEmail} onNext={next} />
```

- [ ] **Step 4: Remove `emailVerified` from StepConfirm render**

At lines 122-131, change:

```tsx
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
```

to:

```tsx
<StepConfirm
  firmName={firmName}
  timezone={timezone}
  submitting={submitting}
  error={submitError}
  onBack={back}
  onSubmit={submit}
/>
```

- [ ] **Step 5: Remove `emailVerified` from StepWelcome component**

Replace the `StepWelcome` function (lines 162-223) with:

```tsx
function StepWelcome({
  userName,
  userEmail,
  onNext,
}: {
  userName: string;
  userEmail: string;
  onNext: () => void;
}) {
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
```

- [ ] **Step 6: Remove `emailVerified` from StepConfirm component**

Replace the `StepConfirm` function (lines 387-488) with:

```tsx
function StepConfirm({
  firmName,
  timezone,
  submitting,
  error,
  onBack,
  onSubmit,
}: {
  firmName: string;
  timezone: string;
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

      {error && (
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
```

- [ ] **Step 7: Remove the "Verify your email" humanization from `_humanizeError`**

At lines 57-71, replace the `_humanizeError` function with:

```tsx
const _humanizeError = (raw: string): string => {
  const match = raw.match(/API \d+: (.+)$/);
  if (!match) return raw;
  try {
    const parsed = JSON.parse(match[1]);
    return parsed.detail || parsed.message || match[1];
  } catch {
    return match[1];
  }
};
```

- [ ] **Step 8: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No type errors.

- [ ] **Step 9: Commit**

```bash
git add frontend/components/onboarding/account-wizard.tsx
git commit -m "refactor: remove email verification warnings from AccountWizard"
```

---

### Task 4: Manual smoke test

**Files:** None (testing only)

- [ ] **Step 1: Start the dev server in mock mode**

Save the current `frontend/.env.local`, then overwrite with mock config per CLAUDE.md:

```
NEXT_PUBLIC_API_URL=http://localhost:3000
NEXT_PUBLIC_AUTH0_DOMAIN=
NEXT_PUBLIC_AUTH0_CLIENT_ID=
NEXT_PUBLIC_AUTH0_API_AUDIENCE=
NEXT_PUBLIC_USE_MOCK_DATA=true
```

Run: `cd frontend && npm run dev`

- [ ] **Step 2: Verify mock mode skips verification gate**

Open `http://localhost:3000` in browser. In mock mode, Auth0 is not configured, so `verified` defaults to `true`. The user should see the onboarding wizard directly (Step 1: Welcome) with no email verification warning banner.

Verify:
- No email verification warning on Step 1
- No email verification warning on Step 4 (Review)
- Wizard functions normally through all 4 steps

- [ ] **Step 3: Verify the EmailVerificationGate component renders**

Temporarily hardcode `setVerified(false)` in the `OnboardingGate` useEffect (replacing `auth0.user?.email_verified ?? true`) to force the gate to render. Reload the page and verify:
- Full-screen centered card appears
- "Verify your email" heading visible
- Email address displayed
- "I've verified my email" button visible
- "Wrong email? Sign out and register again" link visible

Revert the hardcode after testing.

- [ ] **Step 4: Restore `.env.local`**

Restore the original `.env.local` contents and restart the dev server.

- [ ] **Step 5: Final commit (if any fixups needed)**

```bash
git add -u
git commit -m "fix: address smoke test findings"
```

Only commit if changes were needed. Skip if everything passed clean.
