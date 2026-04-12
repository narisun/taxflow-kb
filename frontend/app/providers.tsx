"use client";

import { createContext, useContext, useState, ReactNode } from "react";
import { ThemeProvider } from "@/components/providers/theme-provider";
import type { Client, ChatMessage, Document } from "@/lib/api-client";

interface AppState {
  activeClientId: number | null;
  setActiveClientId: (id: number | null) => void;
  clients: Client[];
  setClients: (c: Client[]) => void;
  messages: ChatMessage[];
  setMessages: (m: ChatMessage[]) => void;
  documents: Document[];
  setDocuments: (d: Document[]) => void;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeClientId, setActiveClientId] = useState<number | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);

  return (
    <ThemeProvider>
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
    </ThemeProvider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
