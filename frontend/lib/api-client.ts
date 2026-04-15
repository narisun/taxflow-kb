const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Client {
  id: number;
  name: string;
  filing_status: string;
  tax_year: number;
  dependents: number;
  workflow_step: string;
  org_id?: string;
  created_by?: string;
  created_at: string;
  updated_at?: string;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  message_type: string;
  created_at: string;
}

export interface Document {
  id: number;
  client_id: number;
  form_type: string;
  title: string;
  status: string;
  confidence: number;
  extracted_data: string;
  flags: string;
  created_at: string;
}

export interface TaxReturnDraft {
  client_id: number;
  tax_year: number;
  filing_status: string;
  lines: { number: string; label: string; value: number; section: string }[];
  total_income: number;
  taxable_income: number;
  total_tax: number;
  refund_or_owed: number;
  effective_rate: number;
  total_deductions?: number;
  total_payments?: number;
  computed_at?: string;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`API ${resp.status}: ${text}`);
  }
  return resp.json();
}

export const api = {
  clients: {
    list: (): Promise<Client[]> =>
      fetchJson<{ items: Client[]; total: number }>(`${API_BASE}/api/clients`)
        .then((r) => r.items),
    get: (id: number): Promise<Client> =>
      fetchJson<Client>(`${API_BASE}/api/clients/${id}`),
    create: (data: Partial<Client>): Promise<Client> =>
      fetchJson<Client>(`${API_BASE}/api/clients`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
  },
  chat: {
    history: (clientId: number): Promise<ChatMessage[]> =>
      fetchJson<{ messages: ChatMessage[]; client_id: number }>(
        `${API_BASE}/api/clients/${clientId}/chat`
      ).then((r) => r.messages),
    send: (clientId: number, content: string): Promise<ChatMessage> =>
      fetchJson<ChatMessage>(`${API_BASE}/api/clients/${clientId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      }),
  },
  documents: {
    list: (clientId: number): Promise<Document[]> =>
      fetchJson<{ items: Document[]; total: number }>(
        `${API_BASE}/api/clients/${clientId}/documents`
      ).then((r) => r.items),
    upload: (clientId: number, file: File, formType: string): Promise<Document> => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("form_type", formType);
      return fetchJson<Document>(`${API_BASE}/api/clients/${clientId}/documents`, {
        method: "POST",
        body: fd,
      });
    },
    approve: (docId: number): Promise<Document> =>
      fetchJson<Document>(`${API_BASE}/api/documents/${docId}/approve`, {
        method: "PATCH",
      }),
    fields: (docId: number): Promise<{ fields: Array<{ name: string; value: string; confidence: number; flagged: boolean; flag_reason: string }> }> =>
      fetchJson(`${API_BASE}/api/documents/${docId}/fields`),
    delete: async (docId: number): Promise<void> => {
      const resp = await fetch(`${API_BASE}/api/documents/${docId}`, { method: "DELETE" });
      if (!resp.ok) throw new Error(`Delete failed: ${resp.status}`);
    },
  },
  returns: {
    draft: (clientId: number): Promise<TaxReturnDraft> =>
      fetchJson<TaxReturnDraft>(`${API_BASE}/api/clients/${clientId}/returns/draft`, {
        method: "POST",
      }),
    get: (clientId: number): Promise<TaxReturnDraft | null> =>
      fetchJson<TaxReturnDraft>(`${API_BASE}/api/clients/${clientId}/returns/draft`)
        .catch(() => null),
  },
};
