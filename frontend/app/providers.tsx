"use client";

import { createContext, useContext, useState, type SetStateAction, type ReactNode } from "react";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { ToastProvider } from "@/components/ui/toast";
import { AppAuth0Provider } from "@/components/auth/auth0-provider";
import type { Client, ChatMessage, Document } from "@/lib/api-client";

interface AppState {
  activeClientId: string | null;
  setActiveClientId: (id: string | null) => void;
  clients: Client[];
  setClients: (c: SetStateAction<Client[]>) => void;
  messages: ChatMessage[];
  setMessages: (m: ChatMessage[]) => void;
  documents: Document[];
  setDocuments: (d: Document[]) => void;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeClientId, setActiveClientId] = useState<string | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);

  // Order matters: ThemeProvider + ToastProvider must wrap AppAuth0Provider
  // because the OnboardingGate rendered inside AppAuth0Provider mounts the
  // AccountWizard, which uses useToast() and Tailwind theme tokens.
  return (
    <ThemeProvider>
      <ToastProvider>
        <AppAuth0Provider>
          <AppContext.Provider
            value={{
              activeClientId, setActiveClientId,
              clients, setClients,
              messages, setMessages,
              documents, setDocuments,
            }}
          >
            {children}
          </AppContext.Provider>
        </AppAuth0Provider>
      </ToastProvider>
    </ThemeProvider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
