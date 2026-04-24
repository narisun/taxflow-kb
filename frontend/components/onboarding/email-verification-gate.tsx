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
