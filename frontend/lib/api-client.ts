const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Mock-data toggle — read once at module load.
 *
 * When ``NEXT_PUBLIC_USE_MOCK_DATA=true`` the exported ``api`` is the
 * deterministic in-memory mock implementation. Otherwise it talks to the
 * real backend at ``NEXT_PUBLIC_API_URL``. There is NO silent fallback —
 * if the backend errors, callers see the error and surface it (typically
 * via the toast provider). Mocks are opt-in only.
 */
export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK_DATA === "true";

// ─── Auth token bridge ────────────────────────────────────────────────────
// Set by AppAuth0Provider once the user has logged in. When null, requests
// are sent without an Authorization header (backend dev-bypass kicks in
// when AUTH0_ALLOW_DEV_BYPASS=true).
type TokenGetter = () => Promise<string | null>;
let _tokenGetter: TokenGetter | null = null;

export function setAuthTokenGetter(getter: TokenGetter | null): void {
  _tokenGetter = getter;
}

/**
 * Build the Authorization header for an outbound API request.
 *
 * Exported so code paths outside the ``api`` object (raw `fetch` calls in
 * page.tsx, third-party libraries like PDF.js) can carry the bearer token.
 */
export async function authHeaders(): Promise<Record<string, string>> {
  if (!_tokenGetter) return {};
  const token = await _tokenGetter();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export interface Client {
  id: string;
  name: string;
  primary_first_name?: string | null;
  primary_last_name?: string | null;
  filing_status: string;
  tax_year: number;
  dependents: number;
  workflow_step: string;
  primary_ssn?: string;
  primary_ssn_masked?: string;
  primary_dob?: string;
  primary_dob_masked?: string;
  spouse_first_name?: string;
  spouse_last_name?: string;
  spouse_ssn?: string;
  spouse_ssn_masked?: string;
  spouse_dob?: string;
  spouse_dob_masked?: string;
  street?: string;
  street_masked?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  email?: string | null;
  phone?: string | null;
  spouse_email?: string | null;
  spouse_phone?: string | null;
  family_group_name?: string;
  filing_federal?: boolean;
  filing_states?: string[];
  org_id?: string;
  created_by?: string;
  created_at: string;
  updated_at?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  message_type: string;
  created_at: string;
}

export interface Document {
  id: string;
  client_id: string;
  form_type: string;
  title: string;
  status: string;
  confidence: number;
  extracted_data: string;
  flags: string;
  file_name?: string;
  created_at: string;
  created_by?: string | null;
  created_by_name?: string | null;
  // Review audit — populated by /approve.
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  reviewed_by_name?: string | null;
}

export interface TaxReturnDraft {
  client_id: string;
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

export interface ValidationResult {
  rule_id: string;
  severity: "ERROR" | "WARNING" | "INFO";
  message: string;
  suggestion?: string;
}

export interface ValidationResponse {
  has_errors: boolean;
  results: ValidationResult[];
}

export interface ComparisonRow {
  label: string;
  current: number;
  prior: number;
  change: number;
  pct_change: number;
}

export interface ComparisonSection {
  title: string;
  rows: ComparisonRow[];
}

export interface ComparisonReport {
  client_id: string;
  current_year: number;
  prior_year: number;
  sections: ComparisonSection[];
  summary: { current: number; prior: number; change: number };
}

export interface FormManifestEntry {
  id: string;
  label: string;
  active: boolean;
  start_page: number | null;
  page_count: number;
}

export interface ReturnManifest {
  total_pages: number;
  forms: FormManifestEntry[];
}

export interface Dependent {
  id: string;
  client_id: string;
  first_name: string;
  last_name: string;
  ssn?: string;
  ssn_masked?: string;
  date_of_birth?: string;
  relationship: string;
  months_lived_with?: number;
  is_student?: boolean;
  is_qualifying_child?: boolean;
  is_us_citizen?: boolean;
}

export interface DependentCreate {
  first_name: string;
  last_name: string;
  ssn?: string;
  date_of_birth?: string;
  relationship: string;
  months_lived_with?: number;
  is_student?: boolean;
  is_qualifying_child?: boolean;
  is_us_citizen?: boolean;
}

// ─── Auth / onboarding ────────────────────────────────────────────────────

export interface UserMe {
  id: string;
  org_id: string | null;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  onboarding_status: "pending" | "complete";
  timezone: string | null;
  last_login_at: string | null;
  created_at: string;
}

export interface OrganizationMe {
  id: string;
  name: string;
  slug: string;
  plan: string;
  is_active: boolean;
  created_at: string;
}

export interface MeResponse {
  user: UserMe;
  organization: OrganizationMe | null;
  permissions: Record<string, boolean>;
}

export interface OnboardingPayload {
  firm_name: string;
  role?: "admin" | "supervisor" | "preparer" | "analyst";
  timezone?: string | null;
  invite_token?: string | null;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const auth = await authHeaders();
  const headers = { ...(init?.headers || {}), ...auth };
  const resp = await fetch(url, { ...init, headers });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`API ${resp.status}: ${text}`);
  }
  return resp.json();
}

const realApi = {
  clients: {
    list: (): Promise<Client[]> =>
      fetchJson<{ items: Client[]; total: number }>(`${API_BASE}/api/clients`)
        .then((r) => r.items),
    get: (id: string): Promise<Client> =>
      fetchJson<Client>(`${API_BASE}/api/clients/${id}`),
    create: (data: Partial<Client>): Promise<Client> =>
      fetchJson<Client>(`${API_BASE}/api/clients`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
    update: (id: string, data: Partial<Client>): Promise<Client> =>
      fetchJson<Client>(`${API_BASE}/api/clients/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
    /**
     * Reveal plaintext for selected encrypted PII fields. Backend returns
     * ``{[field]: string | null}``. Requires the caller to have
     * ``can_view_pii`` (admin/supervisor); other roles get HTTP 403, which
     * we surface as a rejected promise so callers can fall back gracefully.
     */
    revealPii: (
      id: string,
      fields: Array<"primary_ssn" | "primary_dob" | "spouse_ssn" | "spouse_dob" | "street">,
    ): Promise<Record<string, string | null>> =>
      fetchJson<Record<string, string | null>>(
        `${API_BASE}/api/clients/${id}/reveal-pii`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ fields }),
        },
      ),
    getWorkflow: (id: string) =>
      fetchJson<{ workflow_step: string; steps: Array<{ id: string; label: string; complete: boolean; can_complete?: boolean }> }>(`${API_BASE}/api/clients/${id}/workflow`),
    completeStep: (id: string, step: string) =>
      fetchJson<{ workflow_step: string; steps: Array<{ id: string; label: string; complete: boolean }> }>(`${API_BASE}/api/clients/${id}/workflow/${step}/complete`, { method: "POST" }),
    incompleteStep: (id: string, step: string) =>
      fetchJson<{ workflow_step: string; steps: Array<{ id: string; label: string; complete: boolean }> }>(`${API_BASE}/api/clients/${id}/workflow/${step}/incomplete`, { method: "POST" }),
  },
  chat: {
    history: (clientId: string): Promise<ChatMessage[]> =>
      fetchJson<{ messages: ChatMessage[]; client_id: string }>(
        `${API_BASE}/api/clients/${clientId}/chat`
      ).then((r) => r.messages),
    send: (clientId: string, content: string): Promise<ChatMessage> =>
      fetchJson<ChatMessage>(`${API_BASE}/api/clients/${clientId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      }),
  },
  documents: {
    list: (clientId: string): Promise<Document[]> =>
      fetchJson<{ items: Document[]; total: number }>(
        `${API_BASE}/api/clients/${clientId}/documents`
      ).then((r) => r.items),
    upload: (clientId: string, file: File, formType: string): Promise<Document> => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("form_type", formType);
      return fetchJson<Document>(`${API_BASE}/api/clients/${clientId}/documents`, {
        method: "POST",
        body: fd,
      });
    },
    approve: (docId: string): Promise<Document> =>
      fetchJson<Document>(`${API_BASE}/api/documents/${docId}/approve`, {
        method: "PATCH",
      }),
    fields: (docId: string): Promise<{ fields: Array<{ name: string; value: string; confidence: number; flagged: boolean; flag_reason: string }> }> =>
      fetchJson(`${API_BASE}/api/documents/${docId}/fields`),
    delete: async (docId: string): Promise<void> => {
      const auth = await authHeaders();
      const resp = await fetch(`${API_BASE}/api/documents/${docId}`, {
        method: "DELETE",
        headers: auth,
      });
      if (!resp.ok) throw new Error(`Delete failed: ${resp.status}`);
    },
  },
  returns: {
    draft: (clientId: string): Promise<TaxReturnDraft> =>
      fetchJson<TaxReturnDraft>(`${API_BASE}/api/clients/${clientId}/returns/draft`, {
        method: "POST",
      }),
    get: (clientId: string): Promise<TaxReturnDraft | null> =>
      fetchJson<TaxReturnDraft>(`${API_BASE}/api/clients/${clientId}/returns/draft`)
        .catch(() => null),
    advisory: (clientId: string): Promise<AdvisoryItem[]> =>
      fetchJson<AdvisoryItem[]>(`${API_BASE}/api/clients/${clientId}/returns/advisory`),
    validate: (clientId: string): Promise<ValidationResponse> =>
      fetchJson<ValidationResponse>(
        `${API_BASE}/api/clients/${clientId}/returns/validate`,
        { method: "POST" },
      ),
    compare: (clientId: string, priorYear: number): Promise<ComparisonReport> =>
      fetchJson<ComparisonReport>(
        `${API_BASE}/api/clients/${clientId}/returns/compare?prior_year=${priorYear}`,
      ),
    manifest: (clientId: string): Promise<ReturnManifest> =>
      fetchJson<ReturnManifest>(`${API_BASE}/api/clients/${clientId}/returns/manifest`),
    pdfUrl: (clientId: string, disposition: "inline" | "attachment" = "inline"): string =>
      `${API_BASE}/api/clients/${clientId}/returns/pdf?disposition=${disposition}`,
  },
  dependents: {
    list: (clientId: string): Promise<Dependent[]> =>
      fetchJson<Dependent[]>(`${API_BASE}/api/clients/${clientId}/dependents`),
    create: (clientId: string, data: DependentCreate): Promise<Dependent> =>
      fetchJson<Dependent>(`${API_BASE}/api/clients/${clientId}/dependents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
  },
  auth: {
    me: (): Promise<MeResponse> =>
      fetchJson<MeResponse>(`${API_BASE}/api/auth/me`),
    completeOnboarding: (payload: OnboardingPayload): Promise<MeResponse> =>
      fetchJson<MeResponse>(`${API_BASE}/api/auth/complete-onboarding`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    updateProfile: (data: { timezone?: string | null }): Promise<MeResponse> =>
      fetchJson<MeResponse>(`${API_BASE}/api/auth/profile`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
  },
  research: {
    createThread: (): Promise<{ id: string; title: string; conversation_type: string; created_at: string; updated_at: string }> =>
      fetchJson(`${API_BASE}/api/research/conversations`, { method: "POST" }),
    listThreads: (page = 1): Promise<{ items: Array<{ id: string; title: string; conversation_type: string; created_at: string; updated_at: string }>; total: number }> =>
      fetchJson(`${API_BASE}/api/research/conversations?page=${page}`),
    getMessages: (threadId: string): Promise<{ messages: Array<{ id: string; role: string; content: string; created_at: string }>; conversation_id: string }> =>
      fetchJson(`${API_BASE}/api/research/conversations/${threadId}/messages`),
    sendMessage: async (threadId: string, content: string): Promise<Response> => {
      const auth = await authHeaders();
      const resp = await fetch(`${API_BASE}/api/research/conversations/${threadId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ content }),
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new Error(`API ${resp.status}: ${text}`);
      }
      return resp;
    },
    deleteThread: async (threadId: string): Promise<void> => {
      const auth = await authHeaders();
      const resp = await fetch(`${API_BASE}/api/research/conversations/${threadId}`, {
        method: "DELETE",
        headers: auth,
      });
      if (!resp.ok) throw new Error(`Delete failed: ${resp.status}`);
    },
  },
};

// Single source of truth: callers always import { api } from "@/lib/api-client".
// The choice between real HTTP and the in-memory mock happens here, once,
// based on NEXT_PUBLIC_USE_MOCK_DATA. There is no per-request fallback.
//
// The dynamic require keeps mock-api out of the production bundle when the
// flag is off (Next.js tree-shakes the unused branch).
export const api: typeof realApi = USE_MOCK
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  ? (require("./mock-api").mockApi as typeof realApi)
  : realApi;

export interface AdvisoryItem {
  id: string;
  category: "deduction" | "credit" | "retirement" | "planning" | "compliance";
  title: string;
  detail: string;
  savings?: string | null;
  estimated_savings?: string | number | null;
  selected: boolean;
}
