# Email Verification Gate — Design Spec

**Date:** 2026-04-24
**Branch:** feat/fullstack-platform
**Status:** Approved

## Problem

When a new CPA organization signs up, email verification is a requirement to complete onboarding. However, the current implementation has three UX issues:

1. **Verification is a soft warning, not a gate.** Users can fill out the entire 4-step onboarding wizard before discovering they're blocked at submission (backend returns HTTP 403).
2. **No way to fix a mistyped email.** If the user registered with the wrong email, there's no path to correct it — they're stuck on a verification screen for an email they can't access.
3. **No advance signal about verification.** Users don't know email verification is required until they're already inside the wizard.

## Solution

Make email verification an explicit, mandatory first step by inserting an `EmailVerificationGate` component between Auth0 authentication and the onboarding wizard. Social login users (Google, GitHub, etc.) skip it entirely since Auth0 marks them as verified automatically.

## Approach

**Verification Gate Before Wizard** — a new pre-wizard screen that blocks progress until email is verified. The wizard stays unchanged (minus warning banners). Clean separation: verification screen handles identity verification, wizard handles account setup.

Alternatives considered:
- **Verification as Wizard Step 1:** Complicates wizard logic with conditional first step and dynamic step numbering. Mixes two concerns in one component.
- **Modal Overlay:** User sees the wizard behind an undismissable modal. Confusing UX.

## Flow

### Current
```
Auth0 callback → OnboardingGate (fetch /me) → if pending → AccountWizard (4 steps with warning banners)
```

### New
```
Auth0 callback → OnboardingGate (fetch /me) → if pending:
  ├── if email_verified === false → EmailVerificationGate
  └── if email_verified === true  → AccountWizard (4 steps, no warnings)
```

Social login users have `email_verified = true` set automatically by Auth0. They skip the verification gate entirely and land in the wizard — no special-case code needed.

## New Component: EmailVerificationGate

**File:** `frontend/components/onboarding/email-verification-gate.tsx`

### Props

```typescript
interface EmailVerificationGateProps {
  userEmail: string;
  onVerified: () => void;  // called when verification confirmed
}
```

### UI Layout

- Full-screen centered card (same visual style as the onboarding wizard)
- Email icon at top
- Heading: "Verify your email"
- Body: "We sent a verification link to **{email}**. Click the link in your email to continue."
- Helper text: "Check your spam folder if you don't see it."
- **Primary button:** "I've verified my email"
- **Secondary link:** "Wrong email? Sign out and register again"

### Button Behavior ("I've verified my email")

1. Button enters loading state (spinner, disabled)
2. Calls Auth0 SDK's `getAccessTokenSilently({ cacheMode: "off" })` to force a fresh token fetch, then reads the updated `user.email_verified` from the Auth0 SDK. (Note: `email_verified` lives on the Auth0 user object, not our `/me` endpoint.)
3. If verified → calls `onVerified()` callback, transitions to wizard
4. If still unverified → shows inline error: "Email not yet verified. Please click the link in your email and try again."
5. Button returns to normal state

### "Wrong email?" Flow

Calls `logout({ logoutParams: { returnTo: window.location.origin } })`. User lands on Auth0 login page and can re-register with the correct email. No backend API changes needed.

## Changes to Existing Components

### 1. OnboardingGate (`auth0-provider.tsx`, lines 111-119)

The `if (me.user.onboarding_status === "pending")` block gets a nested verification check:

- Add local `verified` boolean state, initialized from `auth0?.user?.email_verified`
- If `verified === false` → render `EmailVerificationGate` with `onVerified` callback that sets `verified = true`
- If `verified === true` → render `AccountWizard` as today (minus `emailVerified` prop)

This allows transitioning from gate to wizard without a full page reload.

### 2. AccountWizard (`account-wizard.tsx`)

Remove:
- `emailVerified` prop from `AccountWizardProps` (line 28)
- Email verification warning banner on Step 1 (lines 189-209)
- Email verification warning banner on Step 4 (lines 434-455)
- Error-handling code that humanizes "Verify your email" backend errors (line 65)

The wizard becomes purely about onboarding — firm name, timezone, confirm. No verification concerns.

### 3. Backend

No changes. The backend already enforces email verification on `POST /api/auth/complete-onboarding` (returns HTTP 403). This remains as defense-in-depth — it should never trigger in normal flow since the frontend gate blocks unverified users upstream.

## Testing

- **Unverified email/password user:** Sees verification gate, cannot proceed to wizard. Clicks "I've verified" before verifying → sees error. Verifies email, clicks again → transitions to wizard.
- **Social login user (Google):** Skips verification gate entirely, lands in wizard.
- **Wrong email flow:** Clicks "Wrong email?" → logged out, redirected to Auth0 signup.
- **Already verified user:** Skips verification gate, lands in wizard.
- **Mock mode:** Verification gate should be skippable (no Auth0 context available).
