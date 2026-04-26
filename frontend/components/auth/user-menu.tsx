"use client";

/**
 * Avatar + click-to-open profile dropdown for the top bar.
 *
 * Source of truth for the displayed identity is Auth0's React SDK (the user
 * object decoded from the ID token), not the backend ``/me`` endpoint —
 * Auth0 already has name/email/picture from the OIDC scopes we requested,
 * no extra round-trip needed.
 *
 * When NEXT_PUBLIC_AUTH0_DOMAIN is unset the SDK isn't mounted; we render
 * the avatar with a placeholder and the dropdown still works for Settings,
 * but Log out is hidden.
 */
import { useAuth0 } from "@auth0/auth0-react";
import { useEffect, useRef, useState } from "react";
import { Avatar } from "@/components/ui/avatar";
import { deriveInitials } from "@/lib/utils";

interface UserMenuProps {
  onSettings?: () => void;
  /** Color seed if Auth0 doesn't supply a picture. */
  fallbackColor?: string;
}

function safeUseAuth0() {
  // Wrap because useAuth0 throws when no Auth0Provider is mounted.
  try {
    return useAuth0();
  } catch {
    return null;
  }
}

export function UserMenu({ onSettings, fallbackColor = "#6B7280" }: UserMenuProps) {
  const auth0 = safeUseAuth0();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const name = auth0?.user?.name;
  const email = auth0?.user?.email;
  const picture = auth0?.user?.picture;
  const initials = deriveInitials(name, email);
  const isAuthenticated = Boolean(auth0?.isAuthenticated);

  const handleLogout = () => {
    if (!auth0) return;
    setOpen(false);
    auth0.logout({
      logoutParams: { returnTo: window.location.origin },
    });
  };

  const handleSettings = () => {
    setOpen(false);
    onSettings?.();
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="hidden md:block cursor-pointer rounded-full focus-visible:outline-2 focus-visible:outline-apple-blue focus-visible:outline-offset-2"
        aria-label="Open profile menu"
        aria-expanded={open}
        aria-haspopup="true"
      >
        {picture ? (
          // Browser-only image; Next/Image is overkill here (32×32 cached).
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={picture}
            alt={name || email || "User avatar"}
            className="w-7 h-7 rounded-full object-cover"
          />
        ) : (
          <Avatar initials={initials} size="sm" color={fallbackColor} />
        )}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-10 w-64 bg-surface rounded-xl shadow-xl border border-divider overflow-hidden z-50 animate-scale-in"
        >
          {/* Identity header */}
          <div className="px-4 py-3 border-b border-divider">
            <div className="text-[13px] font-semibold text-primary truncate">
              {name || "Signed-in user"}
            </div>
            {email && (
              <div className="text-[11px] text-tertiary truncate mt-0.5">
                {email}
              </div>
            )}
            {!isAuthenticated && (
              <div className="text-[10px] text-tertiary mt-1 italic">
                Auth0 not configured — using dev bypass
              </div>
            )}
          </div>

          {/* Actions */}
          {onSettings && (
            <button
              onClick={handleSettings}
              role="menuitem"
              className="w-full flex items-center gap-2 px-4 py-2.5 text-[13px] text-primary hover:bg-surface-secondary transition-colors text-left cursor-pointer"
            >
              <svg className="w-4 h-4 text-tertiary" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a6.759 6.759 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <span>Settings</span>
            </button>
          )}

          {isAuthenticated && (
            <button
              onClick={handleLogout}
              role="menuitem"
              className="w-full flex items-center gap-2 px-4 py-2.5 text-[13px] text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors text-left border-t border-divider cursor-pointer"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
              </svg>
              <span>Log out</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
