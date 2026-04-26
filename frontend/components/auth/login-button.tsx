"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { Button } from "@/components/ui/button";

/** Renders a Login button when Auth0 is configured and the user is logged out. */
export function LoginButton() {
  let auth0;
  try {
    auth0 = useAuth0();
  } catch {
    // Auth0Provider not mounted (NEXT_PUBLIC_AUTH0_DOMAIN unset) — no-op.
    return null;
  }
  const { isAuthenticated, isLoading, loginWithRedirect } = auth0;
  if (isLoading || isAuthenticated) return null;
  return (
    <Button
      variant="pill"
      onClick={() => loginWithRedirect()}
      className="text-[12px] px-3 py-1"
    >
      Log in
    </Button>
  );
}

export function LogoutButton() {
  let auth0;
  try {
    auth0 = useAuth0();
  } catch {
    return null;
  }
  const { isAuthenticated, logout, user } = auth0;
  if (!isAuthenticated) return null;
  return (
    <div className="flex items-center gap-2">
      {user?.email && (
        <span className="text-[11px] text-tertiary truncate max-w-[160px]">
          {user.email}
        </span>
      )}
      <Button
        variant="ghost"
        onClick={() =>
          logout({ logoutParams: { returnTo: window.location.origin } })
        }
        className="text-[12px]"
      >
        Log out
      </Button>
    </div>
  );
}
