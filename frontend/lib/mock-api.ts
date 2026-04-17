// frontend/lib/mock-api.ts
//
// Drop-in replacement for api-client.ts that returns mock data with
// simulated network delays. Used when the backend is unavailable.

import type {
  AdvisoryItem,
  ChatMessage,
  Client,
  ComparisonReport,
  Dependent,
  DependentCreate,
  Document,
  MeResponse,
  OnboardingPayload,
  TaxReturnDraft,
  ValidationResponse,
} from "./api-client";
import {
  mockClients,
  mockDocuments,
  mockChat,
  mockReturnDrafts,
  mockExtractionTemplates,
} from "./mock-data";

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Mutable state for the session (resets on page reload). Indexed by string
// IDs to match the real backend's UUID-shaped identifiers.
let clients = [...mockClients];
let documents: Record<string, Document[]> = JSON.parse(JSON.stringify(mockDocuments));
let chat: Record<string, ChatMessage[]> = JSON.parse(JSON.stringify(mockChat));
let drafts: Record<string, TaxReturnDraft> = JSON.parse(JSON.stringify(mockReturnDrafts));
let nextClientId = 100;
let nextDocId = 1000;
let nextMsgId = 10000;

export const mockApi = {
  clients: {
    list: async (): Promise<Client[]> => {
      await delay(200);
      return [...clients];
    },

    get: async (id: string): Promise<Client> => {
      await delay(100);
      const c = clients.find((c) => c.id === id);
      if (!c) throw new Error("Client not found");
      return { ...c };
    },

    revealPii: async (
      id: string,
      fields: string[],
    ): Promise<Record<string, string | null>> => {
      await delay(50);
      const c = clients.find((cl) => cl.id === id);
      if (!c) throw new Error("Client not found");
      // Mock data is plaintext already; just echo back what we have for the
      // requested fields so the UI's reveal flow exercises the same code path.
      const out: Record<string, string | null> = {};
      for (const f of fields) {
        out[f] = (c as unknown as Record<string, unknown>)[f] as string | null ?? null;
      }
      return out;
    },

    create: async (data: Partial<Client>): Promise<Client> => {
      await delay(300);
      const id = `mock-${++nextClientId}`;
      const client: Client = {
        id,
        name: data.name || "New Client",
        filing_status: data.filing_status || "single",
        tax_year: data.tax_year || 2025,
        dependents: data.dependents || 0,
        workflow_step: "intake",
        created_at: new Date().toISOString(),
      };
      clients = [client, ...clients];
      documents[id] = [];
      chat[id] = [
        {
          id: `mock-${++nextMsgId}`,
          role: "assistant",
          content: `Welcome! I\u2019ve set up the file for ${client.name} (${client.filing_status.toUpperCase()}, TY ${client.tax_year}, ${client.dependents} dependent${client.dependents !== 1 ? "s" : ""}). Ready to receive documents.`,
          message_type: "text",
          created_at: new Date().toISOString(),
        },
      ];
      return client;
    },
  },

  chat: {
    history: async (clientId: string): Promise<ChatMessage[]> => {
      await delay(150);
      return [...(chat[clientId] || [])];
    },

    send: async (clientId: string, content: string): Promise<ChatMessage> => {
      await delay(800);
      // Store user message
      const userMsg: ChatMessage = {
        id: `mock-${++nextMsgId}`,
        role: "user",
        content,
        message_type: "text",
        created_at: new Date().toISOString(),
      };
      if (!chat[clientId]) chat[clientId] = [];
      chat[clientId].push(userMsg);

      // Generate AI response
      const client = clients.find((c) => c.id === clientId);
      const clientDocs = documents[clientId] || [];
      const docSummary = clientDocs.length > 0
        ? `I see ${clientDocs.length} document${clientDocs.length > 1 ? "s" : ""} on file (${clientDocs.map((d) => d.form_type).join(", ")}).`
        : "No documents uploaded yet.";

      const aiMsg: ChatMessage = {
        id: `mock-${++nextMsgId}`,
        role: "assistant",
        content: `I\u2019ll look into that for ${client?.name || "this client"}. ${docSummary}\n\nRegarding your question about \u201c${content.slice(0, 80)}${content.length > 80 ? "\u2026" : ""}\u201d \u2014 based on my analysis of the uploaded documents and IRS guidelines, here is what I found. Please let me know if you need more detail.`,
        message_type: "text",
        created_at: new Date().toISOString(),
      };
      chat[clientId].push(aiMsg);
      return aiMsg;
    },
  },

  documents: {
    list: async (clientId: string): Promise<Document[]> => {
      await delay(150);
      return [...(documents[clientId] || [])];
    },

    upload: async (
      clientId: string,
      file: File,
      formType: string
    ): Promise<Document> => {
      await delay(1000);
      const template =
        mockExtractionTemplates[formType] || mockExtractionTemplates._default;

      const doc: Document = {
        id: `mock-${++nextDocId}`,
        client_id: clientId,
        form_type: formType,
        title: `${formType} (${file.name})`,
        status: template.flags.length > 0 || template.confidence < 0.9 ? "review" : "verified",
        confidence: template.confidence,
        extracted_data: JSON.stringify(template.data),
        flags: JSON.stringify(template.flags),
        file_name: file.name,
        created_at: new Date().toISOString(),
        created_by: "mock-user-1",
        created_by_name: "Mock Admin",
        reviewed_at: null,
        reviewed_by: null,
        reviewed_by_name: null,
      };

      if (!documents[clientId]) documents[clientId] = [];
      documents[clientId].push(doc);

      // Update workflow step if still at intake
      const client = clients.find((c) => c.id === clientId);
      if (client && client.workflow_step === "intake") {
        client.workflow_step = "documents";
      }

      return doc;
    },

    approve: async (docId: string): Promise<Document> => {
      await delay(200);
      for (const clientDocs of Object.values(documents)) {
        const doc = clientDocs.find((d) => d.id === docId);
        if (doc) {
          doc.reviewed_at = new Date().toISOString();
          doc.reviewed_by = "mock-user-1";
          doc.reviewed_by_name = "Mock Admin";
          doc.status = "approved";
          return { ...doc };
        }
      }
      throw new Error("Document not found");
    },

    fields: async (
      docId: string
    ): Promise<{
      fields: Array<{
        name: string;
        value: string;
        confidence: number;
        flagged: boolean;
        flag_reason: string;
      }>;
    }> => {
      await delay(100);
      for (const clientDocs of Object.values(documents)) {
        const doc = clientDocs.find((d) => d.id === docId);
        if (doc) {
          try {
            return { fields: JSON.parse(doc.extracted_data) };
          } catch {
            return { fields: [] };
          }
        }
      }
      throw new Error("Document not found");
    },
  },

  returns: {
    draft: async (clientId: string): Promise<TaxReturnDraft> => {
      await delay(500);
      if (drafts[clientId]) return { ...drafts[clientId] };

      // Generate a simple draft from documents
      const client = clients.find((c) => c.id === clientId);
      if (!client) throw new Error("Client not found");

      const clientDocs = documents[clientId] || [];
      let totalWages = 0;
      let totalWithholding = 0;
      let totalInterest = 0;

      for (const doc of clientDocs) {
        try {
          const data = JSON.parse(doc.extracted_data);
          if (data.wages) totalWages += data.wages;
          if (data.federal_tax_withheld) totalWithholding += data.federal_tax_withheld;
          if (data.interest_income) totalInterest += data.interest_income;
          if (data.nonemployee_compensation) totalWages += data.nonemployee_compensation;
          if (data.ordinary_dividends) totalInterest += data.ordinary_dividends;
        } catch { /* skip */ }
      }

      const totalIncome = totalWages + totalInterest;
      const stdDeduction = client.filing_status === "mfj" ? 29200 : 15000;
      const taxableIncome = Math.max(0, totalIncome - stdDeduction);
      const childCredit = client.dependents * 2000;
      // Simplified tax calc
      const roughTax = Math.max(0, taxableIncome * 0.18 - childCredit);
      const refund = totalWithholding - roughTax;

      const draft: TaxReturnDraft = {
        client_id: clientId,
        tax_year: client.tax_year,
        filing_status: client.filing_status,
        lines: [
          { number: "1a", label: "Wages, salaries, tips", value: totalWages, section: "Income" },
          { number: "2b", label: "Taxable interest / dividends", value: totalInterest, section: "Income" },
          { number: "9", label: "Total income", value: totalIncome, section: "Income" },
          { number: "12", label: "Standard deduction", value: stdDeduction, section: "Deductions" },
          { number: "15", label: "Taxable income", value: taxableIncome, section: "Deductions" },
          { number: "16", label: "Tax", value: roughTax + childCredit, section: "Tax & Credits" },
          { number: "19", label: "Child tax credit", value: childCredit, section: "Tax & Credits" },
          { number: "24", label: "Total tax", value: roughTax, section: "Tax & Credits" },
          { number: "25a", label: "W-2 withholding", value: totalWithholding, section: "Payments" },
          { number: "33", label: "Total payments", value: totalWithholding, section: "Payments" },
          { number: "34", label: "Overpayment / Refund", value: refund, section: "Payments" },
        ],
        total_income: totalIncome,
        taxable_income: taxableIncome,
        total_tax: roughTax,
        refund_or_owed: refund,
        effective_rate: totalIncome > 0 ? Math.round((roughTax / totalIncome) * 1000) / 10 : 0,
      };

      drafts[clientId] = draft;

      // Update workflow
      const c = clients.find((cl) => cl.id === clientId);
      if (c && (c.workflow_step === "documents" || c.workflow_step === "review")) {
        c.workflow_step = "filing";
      }

      return draft;
    },

    get: async (clientId: string): Promise<TaxReturnDraft | null> => {
      await delay(150);
      return drafts[clientId] ? { ...drafts[clientId] } : null;
    },

    advisory: async (clientId: string): Promise<AdvisoryItem[]> => {
      await delay(300);
      void clientId;
      return [
        {
          id: "mock-hsa",
          category: "deduction",
          title: "Maximize HSA contributions",
          detail: "Mock advisory: contribute up to the IRS limit pre-tax.",
          savings: "Up to $1,500/yr",
          estimated_savings: 1500,
          selected: true,
        },
        {
          id: "mock-401k",
          category: "retirement",
          title: "Increase 401(k) contributions",
          detail: "Mock advisory: bump deferral by 2% to capture employer match.",
          savings: "Up to $5,000/yr",
          estimated_savings: 5000,
          selected: true,
        },
      ];
    },

    validate: async (clientId: string): Promise<ValidationResponse> => {
      await delay(200);
      void clientId;
      return { has_errors: false, results: [] };
    },

    compare: async (
      clientId: string,
      priorYear: number,
    ): Promise<ComparisonReport> => {
      await delay(300);
      const client = clients.find((c) => c.id === clientId);
      const currentYear = client?.tax_year || 2025;
      return {
        client_id: clientId,
        current_year: currentYear,
        prior_year: priorYear,
        sections: [
          {
            title: "Income",
            rows: [
              {
                label: "Total income",
                current: 90000,
                prior: 85000,
                change: 5000,
                pct_change: 5.9,
              },
            ],
          },
        ],
        summary: { current: 1200, prior: 800, change: 400 },
      };
    },
  },

  dependents: {
    list: async (clientId: string): Promise<Dependent[]> => {
      await delay(100);
      void clientId;
      return [];
    },
    create: async (
      clientId: string,
      data: DependentCreate,
    ): Promise<Dependent> => {
      await delay(150);
      return {
        id: `mock-${Date.now()}`,
        client_id: clientId,
        ...data,
        ssn_masked: data.ssn
          ? `***-**-${data.ssn.slice(-4)}`
          : undefined,
      };
    },
  },

  research: {
    createThread: async () => {
      await delay(200);
      const id = `mock-research-${Date.now()}`;
      return {
        id,
        title: "New research",
        conversation_type: "research",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
    },
    listThreads: async (page = 1) => {
      await delay(150);
      void page;
      return {
        items: [
          {
            id: "mock-r1",
            title: "SALT deduction cap for 2025",
            conversation_type: "research",
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
          {
            id: "mock-r2",
            title: "Qualified business income deduction",
            conversation_type: "research",
            created_at: new Date(Date.now() - 86400000).toISOString(),
            updated_at: new Date(Date.now() - 86400000).toISOString(),
          },
        ],
        total: 2,
      };
    },
    getMessages: async (threadId: string) => {
      await delay(150);
      return {
        conversation_id: threadId,
        messages: [
          {
            id: `${threadId}-m1`,
            role: "assistant",
            content: "How can I help with your tax research today? I can look up IRS rules, analyze tax scenarios, compare filing strategies, or explain specific code sections.",
            created_at: new Date().toISOString(),
          },
        ],
      };
    },
    sendMessage: async (_threadId: string, content: string): Promise<Response> => {
      await delay(300);
      const responseText = `Based on my research of IRS publications and tax code, here is what I found regarding your question about "${content.slice(0, 60)}":\n\nThis is a mock response. In production, the research agent would search the tax knowledge base and provide detailed, sourced answers.`;

      const encoder = new TextEncoder();
      const events = [
        `data: ${JSON.stringify({ event: "step_start", tool: "search_tax_code", description: "Searching tax knowledge base..." })}\n\n`,
        `data: ${JSON.stringify({ event: "step_complete", tool: "search_tax_code", summary: "Found 3 relevant sections" })}\n\n`,
        ...responseText.split(" ").map((word, i) =>
          `data: ${JSON.stringify({ event: "text_delta", text: (i === 0 ? "" : " ") + word })}\n\n`
        ),
        `data: ${JSON.stringify({ event: "done" })}\n\n`,
      ];

      const stream = new ReadableStream({
        async start(controller) {
          for (const event of events) {
            await new Promise((r) => setTimeout(r, 30));
            controller.enqueue(encoder.encode(event));
          }
          controller.close();
        },
      });

      return new Response(stream, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    },
    deleteThread: async (_threadId: string): Promise<void> => {
      await delay(100);
    },
  },

  auth: {
    me: async (): Promise<MeResponse> => {
      await delay(50);
      return {
        user: {
          id: "mock-user-1",
          org_id: "mock-org-1",
          email: "mock@taxflow.local",
          name: "Mock Admin",
          role: "admin",
          is_active: true,
          onboarding_status: "complete",
          timezone: "America/Los_Angeles",
          last_login_at: new Date().toISOString(),
          created_at: new Date().toISOString(),
        },
        organization: {
          id: "mock-org-1",
          name: "Mock CPA Firm",
          slug: "mock-cpa",
          plan: "starter",
          is_active: true,
          created_at: new Date().toISOString(),
        },
        permissions: {
          can_view_all_clients: true,
          can_manage_users: true,
        },
      };
    },
    completeOnboarding: async (
      payload: OnboardingPayload,
    ): Promise<MeResponse> => {
      await delay(150);
      return {
        user: {
          id: "mock-user-1",
          org_id: "mock-org-1",
          email: "mock@taxflow.local",
          name: "Mock Admin",
          role: payload.role || "admin",
          is_active: true,
          onboarding_status: "complete",
          timezone: payload.timezone || null,
          last_login_at: new Date().toISOString(),
          created_at: new Date().toISOString(),
        },
        organization: {
          id: "mock-org-1",
          name: payload.firm_name,
          slug: payload.firm_name.toLowerCase().replace(/\s+/g, "-"),
          plan: "starter",
          is_active: true,
          created_at: new Date().toISOString(),
        },
        permissions: {},
      };
    },
  },
};
