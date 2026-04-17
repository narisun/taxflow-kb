// frontend/components/settings/settings-modal.tsx
"use client";

import { useState } from "react";
import { Modal, ModalHeader, ModalBody } from "@/components/ui/modal";
import { useTheme } from "@/components/providers/theme-provider";
import { cn } from "@/lib/utils";
import { useMe } from "@/components/auth/me-context";

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  onReplayTour?: () => void;
}

type Section = "profile" | "appearance" | "notifications" | "shortcuts" | "about";

const sections: { id: Section; label: string }[] = [
  { id: "profile", label: "Profile" },
  { id: "appearance", label: "Appearance" },
  { id: "notifications", label: "Notifications" },
  { id: "shortcuts", label: "Shortcuts" },
  { id: "about", label: "About" },
];

const NOTIFICATION_CATEGORIES = [
  { key: "documents", label: "Document processing", desc: "Upload complete, extraction ready" },
  { key: "messages", label: "Client messages", desc: "New chat messages from AI agent" },
  { key: "returns", label: "Return status", desc: "Return generated, filed, rejected" },
  { key: "deadlines", label: "Deadline reminders", desc: "Upcoming filing deadlines" },
  { key: "system", label: "System updates", desc: "Maintenance, new features" },
];

const SHORTCUTS = [
  { keys: "Cmd/Ctrl + K", action: "Quick client search" },
  { keys: "Cmd/Ctrl + N", action: "New intake" },
  { keys: "Escape", action: "Close overlay / modal" },
  { keys: "Tab", action: "Navigate between panels" },
];

export function SettingsModal({ open, onClose, onReplayTour }: SettingsModalProps) {
  const [active, setActive] = useState<Section>("profile");
  const { theme, setTheme } = useTheme();
  let me: ReturnType<typeof useMe> | null = null;
  try { me = useMe(); } catch { /* MeProvider not mounted yet */ }
  const [notifPrefs, setNotifPrefs] = useState<Record<string, boolean>>(
    Object.fromEntries(NOTIFICATION_CATEGORIES.map((c) => [c.key, true]))
  );

  const inputCls = "w-full border border-divider rounded-lg px-3 py-2 text-[13px] outline-none focus:border-apple-blue transition-colors bg-surface text-primary placeholder:text-tertiary";
  const labelCls = "text-[11px] font-medium text-tertiary uppercase tracking-wider mb-1 block";

  return (
    <Modal open={open} onClose={onClose} className="max-w-2xl">
      <ModalHeader onClose={onClose}>Settings</ModalHeader>
      <ModalBody className="p-0 max-h-[70vh]">
        <div className="flex min-h-[400px]">
          {/* Section nav */}
          <nav className="w-44 shrink-0 border-r border-divider py-2 max-md:hidden">
            {sections.map((s) => (
              <button
                key={s.id}
                onClick={() => setActive(s.id)}
                className={cn(
                  "w-full text-left px-4 py-2 text-[13px] transition-colors cursor-pointer",
                  active === s.id ? "text-apple-blue bg-surface-secondary font-medium" : "text-secondary hover:bg-surface-secondary"
                )}
              >
                {s.label}
              </button>
            ))}
          </nav>

          {/* Content */}
          <div className="flex-1 p-6 overflow-y-auto space-y-5">
            {/* Mobile section picker */}
            <select
              className={cn(inputCls, "md:hidden mb-4")}
              value={active}
              onChange={(e) => setActive(e.target.value as Section)}
            >
              {sections.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>

            {active === "profile" && (
              <div className="space-y-4">
                <h3 className="text-[15px] font-semibold text-primary">Profile</h3>
                <div className="grid grid-cols-2 gap-3">
                  <div><label className={labelCls}>Name</label><input className={inputCls} defaultValue={me?.user?.name || ""} readOnly /></div>
                  <div><label className={labelCls}>Email</label><input className={inputCls} defaultValue={me?.user?.email || ""} readOnly /></div>
                  <div><label className={labelCls}>Firm</label><input className={inputCls} defaultValue={me?.organization?.name || ""} readOnly /></div>
                  <div><label className={labelCls}>Role</label><input className={inputCls} defaultValue={me?.user?.role || ""} readOnly /></div>
                </div>
              </div>
            )}

            {active === "appearance" && (
              <div className="space-y-4">
                <h3 className="text-[15px] font-semibold text-primary">Appearance</h3>
                <div>
                  <label className={labelCls}>Theme</label>
                  <div className="flex gap-2 mt-1">
                    {(["light", "dark", "system"] as const).map((t) => (
                      <button
                        key={t}
                        onClick={() => {
                          document.documentElement.classList.add("theme-transitioning");
                          setTheme(t);
                          setTimeout(() => document.documentElement.classList.remove("theme-transitioning"), 400);
                        }}
                        className={cn(
                          "px-4 py-2 rounded-lg text-[13px] font-medium border transition-all cursor-pointer capitalize",
                          theme === t
                            ? "bg-apple-blue text-white border-apple-blue"
                            : "bg-surface text-secondary border-divider hover:border-tertiary"
                        )}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {active === "notifications" && (
              <div className="space-y-4">
                <h3 className="text-[15px] font-semibold text-primary">Notification Preferences</h3>
                <div className="space-y-3">
                  {NOTIFICATION_CATEGORIES.map((cat) => (
                    <div key={cat.key} className="flex items-center justify-between py-2 border-b border-divider last:border-0">
                      <div>
                        <div className="text-[13px] text-primary">{cat.label}</div>
                        <div className="text-[11px] text-tertiary">{cat.desc}</div>
                      </div>
                      <div className="flex items-center gap-4">
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={notifPrefs[cat.key]}
                            onChange={(e) => setNotifPrefs((p) => ({ ...p, [cat.key]: e.target.checked }))}
                            className="w-4 h-4 accent-apple-blue cursor-pointer"
                          />
                          <span className="text-[11px] text-secondary">In-app</span>
                        </label>
                        <label className="flex items-center gap-1.5 opacity-40 cursor-not-allowed" title="Coming soon">
                          <input type="checkbox" disabled className="w-4 h-4 cursor-not-allowed" />
                          <span className="text-[11px] text-tertiary">Email</span>
                        </label>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {active === "shortcuts" && (
              <div className="space-y-4">
                <h3 className="text-[15px] font-semibold text-primary">Keyboard Shortcuts</h3>
                <div className="space-y-2">
                  {SHORTCUTS.map((s) => (
                    <div key={s.keys} className="flex items-center justify-between py-2 border-b border-divider last:border-0">
                      <span className="text-[13px] text-primary">{s.action}</span>
                      <kbd className="text-[12px] font-mono bg-surface-secondary text-secondary px-2 py-1 rounded">{s.keys}</kbd>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {active === "about" && (
              <div className="space-y-4">
                <h3 className="text-[15px] font-semibold text-primary">About TaxFlow AI</h3>
                <div className="space-y-2 text-[13px]">
                  <div className="flex justify-between"><span className="text-secondary">Version</span><span className="text-primary font-medium">0.1.0</span></div>
                  <div className="flex justify-between"><span className="text-secondary">Build</span><span className="text-primary font-medium">2026.04.12</span></div>
                </div>
                <div className="flex gap-2 mt-4">
                  {onReplayTour && (
                    <button onClick={onReplayTour} className="text-[13px] text-apple-blue hover:underline cursor-pointer">
                      Replay onboarding tour
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </ModalBody>
    </Modal>
  );
}
