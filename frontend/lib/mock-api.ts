// frontend/lib/mock-api.ts
//
// Drop-in replacement for api-client.ts that returns mock data with
// simulated network delays. Used when the backend is unavailable.

import type { Client, ChatMessage, Document, TaxReturnDraft } from "./api-client";
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

// Mutable state for the session (resets on page reload)
let clients = [...mockClients];
let documents: Record<number, Document[]> = JSON.parse(JSON.stringify(mockDocuments));
let chat: Record<number, ChatMessage[]> = JSON.parse(JSON.stringify(mockChat));
let drafts: Record<number, TaxReturnDraft> = JSON.parse(JSON.stringify(mockReturnDrafts));
let nextClientId = 100;
let nextDocId = 1000;
let nextMsgId = 10000;

export const mockApi = {
  clients: {
    list: async (): Promise<Client[]> => {
      await delay(200);
      return [...clients];
    },

    get: async (id: number): Promise<Client> => {
      await delay(100);
      const c = clients.find((c) => c.id === id);
      if (!c) throw new Error("Client not found");
      return { ...c };
    },

    create: async (data: Partial<Client>): Promise<Client> => {
      await delay(300);
      const id = ++nextClientId;
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
          id: ++nextMsgId,
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
    history: async (clientId: number): Promise<ChatMessage[]> => {
      await delay(150);
      return [...(chat[clientId] || [])];
    },

    send: async (clientId: number, content: string): Promise<ChatMessage> => {
      await delay(800);
      // Store user message
      const userMsg: ChatMessage = {
        id: ++nextMsgId,
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
        id: ++nextMsgId,
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
    list: async (clientId: number): Promise<Document[]> => {
      await delay(150);
      return [...(documents[clientId] || [])];
    },

    upload: async (
      clientId: number,
      file: File,
      formType: string
    ): Promise<Document> => {
      await delay(1000);
      const template =
        mockExtractionTemplates[formType] || mockExtractionTemplates._default;

      const doc: Document = {
        id: ++nextDocId,
        client_id: clientId,
        form_type: formType,
        title: `${formType} (${file.name})`,
        status: template.flags.length > 0 || template.confidence < 0.9 ? "review" : "verified",
        confidence: template.confidence,
        extracted_data: JSON.stringify(template.data),
        flags: JSON.stringify(template.flags),
        created_at: new Date().toISOString(),
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

    approve: async (docId: number): Promise<Document> => {
      await delay(200);
      for (const clientDocs of Object.values(documents)) {
        const doc = clientDocs.find((d) => d.id === docId);
        if (doc) {
          doc.status = "approved";
          return { ...doc };
        }
      }
      throw new Error("Document not found");
    },

    fields: async (
      docId: number
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
    draft: async (clientId: number): Promise<TaxReturnDraft> => {
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
  },
};
