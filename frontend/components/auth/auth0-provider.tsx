"use client";

import { Auth0Provider, useAuth0 } from "@auth0/auth0-react";
import { ReactNode, useCallback, useEffect, useState } from "react";
import {
  api,
  setAuthTokenGetter,
  USE_MOCK,
  type MeResponse,
} from "@/lib/api-client";
import { AccountWizard } from "@/components/onboarding/account-wizard";
import { MeProvider } from "@/components/auth/me-context";

const DOMAIN = process.env.NEXT_PUBLIC_AUTH0_DOMAIN || "";
const CLIENT_ID = process.env.NEXT_PUBLIC_AUTH0_CLIENT_ID || "";
const AUDIENCE = process.env.NEXT_PUBLIC_AUTH0_API_AUDIENCE || "";
const REDIRECT_URI =
  typeof window !== "undefined"
    ? window.location.origin
    : "http://localhost:3000";

/**
 * Wraps the app in Auth0's React SDK and bridges the access-token getter
 * into the api-client so every fetch automatically gets `Authorization: Bearer`.
 *
 * When NEXT_PUBLIC_AUTH0_DOMAIN is unset, becomes a no-op pass-through (lets
 * dev servers run without an Auth0 tenant configured — relies on the backend
 * AUTH0_ALLOW_DEV_BYPASS=true behavior).
 *
 * When configured, automatically redirects unauthenticated users to the Auth0
 * Universal Login page on app start.
 */
export function AppAuth0Provider({ children }: { children: ReactNode }) {
  if (!DOMAIN || !CLIENT_ID) {
    // Dev / mock mode without Auth0 — still need to load /api/auth/me so the
    // app has permissions for PiiInput's reveal gating, etc.
    return <OnboardingGate>{children}</OnboardingGate>;
  }
  return (
    <Auth0Provider
      domain={DOMAIN}
      clientId={CLIENT_ID}
      authorizationParams={{
        redirect_uri: REDIRECT_URI,
        audience: AUDIENCE || undefined,
      }}
      cacheLocation="localstorage"
    >
      <Auth0TokenBridge>
        <AuthGate>
          <OnboardingGate>{children}</OnboardingGate>
        </AuthGate>
      </Auth0TokenBridge>
    </Auth0Provider>
  );
}

/**
 * Fetches /api/auth/me after the user is authenticated. If their
 * onboarding_status is "pending", renders the AccountWizard instead of
 * the app. After the wizard POSTs and we receive a complete MeResponse,
 * unmounts the wizard and renders children.
 *
 * In USE_MOCK mode we skip this entirely — mocks always return complete.
 */
function OnboardingGate({ children }: { children: ReactNode }) {
  const auth0 = (() => { try { return useAuth0(); } catch { return null; } })();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // In mock mode we still fetch — mock-api.auth.me() returns a complete
    // MeResponse with permissions, which the rest of the app needs (e.g.
    // PiiInput's eye toggle is gated by permissions.can_view_pii).
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
    return (
      <AccountWizard
        userName={me.user.name}
        userEmail={me.user.email}
        emailVerified={auth0?.user?.email_verified ?? undefined}
        onComplete={handleComplete}
      />
    );
  }

  // Provide me + permissions to the whole app.
  return <MeProvider value={me}>{children}</MeProvider>;
}

/** Pushes Auth0's access-token getter into the api-client at mount time. */
function Auth0TokenBridge({ children }: { children: ReactNode }) {
  const { getAccessTokenSilently, isAuthenticated } = useAuth0();
  useEffect(() => {
    if (!isAuthenticated) {
      setAuthTokenGetter(null);
      return;
    }
    setAuthTokenGetter(async () => {
      try {
        return await getAccessTokenSilently();
      } catch {
        return null;
      }
    });
  }, [getAccessTokenSilently, isAuthenticated]);
  return <>{children}</>;
}

/**
 * Forces unauthenticated users through Auth0 Universal Login on app start.
 *
 * Renders a brief "Redirecting…" splash while the SDK figures out whether
 * the user is logged in (initial silent-auth attempt). After that:
 *   - authenticated → render the app
 *   - not authenticated → kick off loginWithRedirect() and show splash
 *                          until Auth0 returns the user to the app.
 */
function AuthGate({ children }: { children: ReactNode }) {
  const { isLoading, isAuthenticated, error, loginWithRedirect } = useAuth0();

  useEffect(() => {
    if (!isLoading && !isAuthenticated && !error) {
      void loginWithRedirect();
    }
  }, [isLoading, isAuthenticated, error, loginWithRedirect]);

  if (error) {
    return (
      <div className="h-screen w-screen flex items-center justify-center text-sm text-red-600 p-6 text-center">
        Auth0 error: {error.message}
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="h-screen w-screen flex flex-col items-center justify-center gap-2 text-sm text-tertiary">
        <div className="w-6 h-6 border-2 border-apple-blue border-t-transparent rounded-full animate-spin" />
        <span>Redirecting to sign-in&hellip;</span>
      </div>
    );
  }

  return <>{children}</>;
}
