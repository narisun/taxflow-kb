const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Client {
  id: number;
  name: string;
  filing_status: string;
  tax_year: number;
  dependents: number;
  workflow_step: string;
  created_at: string;
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
}

export const api = {
  clients: {
    list: (): Promise<Client[]> =>
      fetch(`${API_BASE}/api/clients`).then((r) => r.json()),
    get: (id: number): Promise<Client> =>
      fetch(`${API_BASE}/api/clients/${id}`).then((r) => r.json()),
    create: (data: Partial<Client>): Promise<Client> =>
      fetch(`${API_BASE}/api/clients`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }).then((r) => r.json()),
  },
  chat: {
    history: (clientId: number): Promise<ChatMessage[]> =>
      fetch(`${API_BASE}/api/clients/${clientId}/chat`).then((r) => r.json()),
    send: (clientId: number, content: string): Promise<ChatMessage> =>
      fetch(`${API_BASE}/api/clients/${clientId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      }).then((r) => r.json()),
  },
  documents: {
    list: (clientId: number): Promise<Document[]> =>
      fetch(`${API_BASE}/api/clients/${clientId}/documents`).then((r) =>
        r.json()
      ),
    upload: (
      clientId: number,
      file: File,
      formType: string
    ): Promise<Document> => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("form_type", formType);
      return fetch(`${API_BASE}/api/clients/${clientId}/documents`, {
        method: "POST",
        body: fd,
      }).then((r) => r.json());
    },
    approve: (docId: number): Promise<Document> =>
      fetch(`${API_BASE}/api/documents/${docId}/approve`, {
        method: "PATCH",
      }).then((r) => r.json()),
  },
  returns: {
    draft: (clientId: number): Promise<TaxReturnDraft> =>
      fetch(`${API_BASE}/api/clients/${clientId}/returns/draft`, {
        method: "POST",
      }).then((r) => r.json()),
  },
};
