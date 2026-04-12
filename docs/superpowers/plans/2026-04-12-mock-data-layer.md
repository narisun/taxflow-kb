# Mock Data Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a rich mock data layer so the frontend can be tested end-to-end without a running backend, covering the full CPA workflow from intake through filing.

**Architecture:** Centralized mock data in `mock-data.ts`, mock API implementation in `mock-api.ts` mirroring the real `api` object shape with simulated delays, and page.tsx refactored to use the mock API instead of inline mock data.

**Tech Stack:** TypeScript, existing api-client.ts types

---

## Task 1: Create Mock Data

**Files:**
- Create: `frontend/lib/mock-data.ts`

- [ ] **Step 1: Create the mock data file with all objects**

```typescript
// frontend/lib/mock-data.ts
//
// Rich test data covering the full CPA workflow:
//   Client 1 (Smith): Review stage — W-2 + flagged 1099-INT + 1098
//   Client 2 (Johnson): Documents stage — 2 W-2s + 1099-NEC (MFJ)
//   Client 3 (Chen): Intake stage — no docs, no chat
//   Client 4 (Garcia): Filing stage — all verified, return ready (MFJ)
//   Client 5 (Patel): Filed — complete (MFJ)

import type { Client, ChatMessage, Document, TaxReturnDraft } from "./api-client";

// ── Clients ────────────────────────────────────────────────

export const mockClients: Client[] = [
  {
    id: 1,
    name: "Smith, John",
    filing_status: "single",
    tax_year: 2025,
    dependents: 1,
    workflow_step: "review",
    created_at: "2026-03-15T10:00:00Z",
  },
  {
    id: 2,
    name: "Johnson Family",
    filing_status: "mfj",
    tax_year: 2025,
    dependents: 3,
    workflow_step: "documents",
    created_at: "2026-03-20T14:00:00Z",
  },
  {
    id: 3,
    name: "Chen, Wei",
    filing_status: "single",
    tax_year: 2025,
    dependents: 0,
    workflow_step: "intake",
    created_at: "2026-04-01T09:00:00Z",
  },
  {
    id: 4,
    name: "Garcia Household",
    filing_status: "mfj",
    tax_year: 2025,
    dependents: 4,
    workflow_step: "filing",
    created_at: "2026-02-10T11:00:00Z",
  },
  {
    id: 5,
    name: "Patel Family",
    filing_status: "mfj",
    tax_year: 2025,
    dependents: 1,
    workflow_step: "filed",
    created_at: "2026-01-25T16:00:00Z",
  },
];

// ── Documents ──────────────────────────────────────────────

export const mockDocuments: Record<number, Document[]> = {
  // Client 1 — Smith: W-2, flagged 1099-INT, 1098
  1: [
    {
      id: 101,
      client_id: 1,
      form_type: "W-2",
      title: "W-2 (Acme Corporation)",
      status: "verified",
      confidence: 0.99,
      extracted_data: JSON.stringify({
        employer_name: "Acme Corporation",
        employer_ein: "12-3456789",
        employee_name: "John Smith",
        wages: 112400,
        federal_tax_withheld: 18750,
        social_security_wages: 112400,
        social_security_tax: 6968.8,
        medicare_wages: 112400,
        medicare_tax: 1629.8,
        state: "NJ",
        state_wages: 112400,
        state_tax: 5620,
      }),
      flags: "[]",
      created_at: "2026-03-15T10:05:00Z",
    },
    {
      id: 102,
      client_id: 1,
      form_type: "1099-INT",
      title: "1099-INT (First National Bank)",
      status: "review",
      confidence: 0.82,
      extracted_data: JSON.stringify({
        payer_name: "First National Bank",
        payer_tin: "**-***4521",
        recipient_name: "John Smith",
        interest_income: 2340,
        federal_tax_withheld: 0,
      }),
      flags: JSON.stringify([
        "Payer TIN mismatch \u2014 expected ending 4512, found 4521",
      ]),
      created_at: "2026-03-15T10:10:00Z",
    },
    {
      id: 103,
      client_id: 1,
      form_type: "1098",
      title: "1098 (Wells Fargo Mortgage)",
      status: "verified",
      confidence: 0.95,
      extracted_data: JSON.stringify({
        lender_name: "Wells Fargo Mortgage",
        mortgage_interest: 14200,
        outstanding_principal: 285000,
        real_estate_taxes: 6800,
      }),
      flags: "[]",
      created_at: "2026-03-16T09:00:00Z",
    },
  ],

  // Client 2 — Johnson: 2 W-2s + 1099-NEC
  2: [
    {
      id: 201,
      client_id: 2,
      form_type: "W-2",
      title: "W-2 (Robert \u2014 Microsoft Corp)",
      status: "verified",
      confidence: 0.98,
      extracted_data: JSON.stringify({
        employer_name: "Microsoft Corp",
        employer_ein: "91-1144442",
        employee_name: "Robert Johnson",
        wages: 145000,
        federal_tax_withheld: 24500,
        social_security_wages: 145000,
        social_security_tax: 8990,
        medicare_wages: 145000,
        medicare_tax: 2102.5,
        state: "WA",
        state_wages: 145000,
        state_tax: 0,
      }),
      flags: "[]",
      created_at: "2026-03-20T14:05:00Z",
    },
    {
      id: 202,
      client_id: 2,
      form_type: "W-2",
      title: "W-2 (Maria \u2014 County Hospital)",
      status: "verified",
      confidence: 0.97,
      extracted_data: JSON.stringify({
        employer_name: "County General Hospital",
        employer_ein: "36-2167891",
        employee_name: "Maria Johnson",
        wages: 78500,
        federal_tax_withheld: 11200,
        social_security_wages: 78500,
        social_security_tax: 4867,
        medicare_wages: 78500,
        medicare_tax: 1138.25,
        state: "WA",
        state_wages: 78500,
        state_tax: 0,
      }),
      flags: "[]",
      created_at: "2026-03-20T14:10:00Z",
    },
    {
      id: 203,
      client_id: 2,
      form_type: "1099-NEC",
      title: "1099-NEC (Freelance Consulting)",
      status: "verified",
      confidence: 0.96,
      extracted_data: JSON.stringify({
        payer_name: "Consulting Partners LLC",
        nonemployee_compensation: 12500,
        federal_tax_withheld: 0,
      }),
      flags: "[]",
      created_at: "2026-03-21T08:00:00Z",
    },
  ],

  // Client 3 — Chen: no docs (just started intake)
  3: [],

  // Client 4 — Garcia: W-2 + W-2 + 1099-DIV (all verified, ready to file)
  4: [
    {
      id: 401,
      client_id: 4,
      form_type: "W-2",
      title: "W-2 (Carlos \u2014 Tesla Inc)",
      status: "verified",
      confidence: 0.99,
      extracted_data: JSON.stringify({
        employer_name: "Tesla Inc",
        employer_ein: "91-2197729",
        employee_name: "Carlos Garcia",
        wages: 98000,
        federal_tax_withheld: 15200,
        social_security_wages: 98000,
        social_security_tax: 6076,
        medicare_wages: 98000,
        medicare_tax: 1421,
        state: "TX",
        state_wages: 98000,
        state_tax: 0,
      }),
      flags: "[]",
      created_at: "2026-02-10T11:05:00Z",
    },
    {
      id: 402,
      client_id: 4,
      form_type: "W-2",
      title: "W-2 (Ana \u2014 HEB Grocery)",
      status: "verified",
      confidence: 0.97,
      extracted_data: JSON.stringify({
        employer_name: "H-E-B Grocery Company",
        employer_ein: "74-1012889",
        employee_name: "Ana Garcia",
        wages: 42000,
        federal_tax_withheld: 4200,
        social_security_wages: 42000,
        social_security_tax: 2604,
        medicare_wages: 42000,
        medicare_tax: 609,
        state: "TX",
        state_wages: 42000,
        state_tax: 0,
      }),
      flags: "[]",
      created_at: "2026-02-10T11:10:00Z",
    },
    {
      id: 403,
      client_id: 4,
      form_type: "1099-DIV",
      title: "1099-DIV (Vanguard)",
      status: "verified",
      confidence: 0.97,
      extracted_data: JSON.stringify({
        payer_name: "Vanguard Group Inc",
        ordinary_dividends: 3200,
        qualified_dividends: 2800,
        capital_gain_distributions: 450,
        federal_tax_withheld: 0,
      }),
      flags: "[]",
      created_at: "2026-02-12T10:00:00Z",
    },
  ],

  // Client 5 — Patel: W-2 + W-2 (filed)
  5: [
    {
      id: 501,
      client_id: 5,
      form_type: "W-2",
      title: "W-2 (Raj \u2014 Google LLC)",
      status: "verified",
      confidence: 0.99,
      extracted_data: JSON.stringify({
        employer_name: "Google LLC",
        employer_ein: "77-0493581",
        employee_name: "Raj Patel",
        wages: 185000,
        federal_tax_withheld: 35000,
        social_security_wages: 168600,
        social_security_tax: 10453.2,
        medicare_wages: 185000,
        medicare_tax: 2682.5,
        state: "CA",
        state_wages: 185000,
        state_tax: 12950,
      }),
      flags: "[]",
      created_at: "2026-01-25T16:05:00Z",
    },
    {
      id: 502,
      client_id: 5,
      form_type: "W-2",
      title: "W-2 (Priya \u2014 Stanford Health)",
      status: "verified",
      confidence: 0.98,
      extracted_data: JSON.stringify({
        employer_name: "Stanford Health Care",
        employer_ein: "94-2735010",
        employee_name: "Priya Patel",
        wages: 125000,
        federal_tax_withheld: 22000,
        social_security_wages: 125000,
        social_security_tax: 7750,
        medicare_wages: 125000,
        medicare_tax: 1812.5,
        state: "CA",
        state_wages: 125000,
        state_tax: 8750,
      }),
      flags: "[]",
      created_at: "2026-01-25T16:10:00Z",
    },
  ],
};

// ── Chat Messages ──────────────────────────────────────────

export const mockChat: Record<number, ChatMessage[]> = {
  // Client 1 — Smith: full conversation
  1: [
    {
      id: 1001,
      role: "assistant",
      content:
        "Welcome! I\u2019ve set up the file for Smith, John (Single, TY 2025, 1 dependent). Ready to receive documents.",
      message_type: "text",
      created_at: "2026-03-15T10:00:30Z",
    },
    {
      id: 1002,
      role: "assistant",
      content:
        "<strong>W-2</strong> uploaded and processed (99% confidence).\nBox 1 \u2014 Wages: $112,400.00 \u00b7 Box 2 \u2014 Federal Tax Withheld: $18,750.00 \u00b7 Employer: ACME CORPORATION",
      message_type: "text",
      created_at: "2026-03-15T10:05:30Z",
    },
    {
      id: 1003,
      role: "assistant",
      content:
        "<strong>1099-INT</strong> uploaded and processed (82% confidence).\nBox 1 \u2014 Interest: $2,340.00\n\u26A0 1 flag(s): Payer TIN mismatch \u2014 expected ending 4512, found 4521",
      message_type: "text",
      created_at: "2026-03-15T10:10:30Z",
    },
    {
      id: 1004,
      role: "user",
      content:
        "Can you check if the 1099-INT TIN issue is a transposition error?",
      message_type: "text",
      created_at: "2026-03-15T10:12:00Z",
    },
    {
      id: 1005,
      role: "assistant",
      content:
        "The 1099-INT from First National Bank shows TIN ending in <strong>4521</strong>, but IRS records expect <strong>4512</strong>. This is likely a transposition error (digits 1 and 2 swapped). I recommend contacting the bank for a corrected form before filing.",
      message_type: "text",
      created_at: "2026-03-15T10:12:05Z",
    },
    {
      id: 1006,
      role: "assistant",
      content:
        "<strong>1098</strong> uploaded and processed (95% confidence).\nMortgage Interest: $14,200.00 \u00b7 Property Taxes: $6,800.00 \u00b7 Lender: Wells Fargo Mortgage",
      message_type: "text",
      created_at: "2026-03-16T09:00:30Z",
    },
    {
      id: 1007,
      role: "user",
      content: "What\u2019s the estimated refund looking like?",
      message_type: "text",
      created_at: "2026-03-16T09:05:00Z",
    },
    {
      id: 1008,
      role: "assistant",
      content:
        "Based on the documents received so far:\n\n\u2022 Wages: $112,400 (W-2)\n\u2022 Interest: $2,340 (1099-INT)\n\u2022 Mortgage interest deduction: $14,200 (1098)\n\u2022 Property tax deduction: $6,800 (1098)\n\nItemized deductions ($21,000) exceed the standard deduction ($15,000 for single). Using itemized.\n\nEstimated federal refund: <strong>$4,820</strong>\nEstimated NJ liability: <strong>-$1,240</strong>",
      message_type: "text",
      created_at: "2026-03-16T09:05:05Z",
    },
  ],

  // Client 2 — Johnson: document upload only
  2: [
    {
      id: 2001,
      role: "assistant",
      content:
        "Welcome! I\u2019ve set up the file for Johnson Family (MFJ, TY 2025, 3 dependents). Ready to receive documents.",
      message_type: "text",
      created_at: "2026-03-20T14:00:30Z",
    },
    {
      id: 2002,
      role: "assistant",
      content:
        "<strong>W-2</strong> (Robert) uploaded and processed (98% confidence).\nWages: $145,000.00 \u00b7 Federal W/H: $24,500.00 \u00b7 Employer: Microsoft Corp",
      message_type: "text",
      created_at: "2026-03-20T14:05:30Z",
    },
    {
      id: 2003,
      role: "assistant",
      content:
        "<strong>W-2</strong> (Maria) uploaded and processed (97% confidence).\nWages: $78,500.00 \u00b7 Federal W/H: $11,200.00 \u00b7 Employer: County General Hospital",
      message_type: "text",
      created_at: "2026-03-20T14:10:30Z",
    },
    {
      id: 2004,
      role: "assistant",
      content:
        "<strong>1099-NEC</strong> uploaded and processed (96% confidence).\nNonemployee compensation: $12,500.00 \u00b7 Payer: Consulting Partners LLC",
      message_type: "text",
      created_at: "2026-03-21T08:00:30Z",
    },
  ],

  // Client 3 — Chen: empty (just intake)
  3: [
    {
      id: 3001,
      role: "assistant",
      content:
        "Welcome! I\u2019ve set up the file for Chen, Wei (Single, TY 2025, 0 dependents). Ready to receive documents.",
      message_type: "text",
      created_at: "2026-04-01T09:00:30Z",
    },
  ],

  // Client 4 — Garcia: docs done, return prepared
  4: [
    {
      id: 4001,
      role: "assistant",
      content:
        "Welcome! I\u2019ve set up the file for Garcia Household (MFJ, TY 2025, 4 dependents). Ready to receive documents.",
      message_type: "text",
      created_at: "2026-02-10T11:00:30Z",
    },
    {
      id: 4002,
      role: "assistant",
      content:
        "<strong>W-2</strong> (Carlos) uploaded \u2014 99% confidence. Wages: $98,000.",
      message_type: "text",
      created_at: "2026-02-10T11:05:30Z",
    },
    {
      id: 4003,
      role: "assistant",
      content:
        "<strong>W-2</strong> (Ana) uploaded \u2014 97% confidence. Wages: $42,000.",
      message_type: "text",
      created_at: "2026-02-10T11:10:30Z",
    },
    {
      id: 4004,
      role: "assistant",
      content:
        "<strong>1099-DIV</strong> uploaded \u2014 97% confidence. Ordinary dividends: $3,200.",
      message_type: "text",
      created_at: "2026-02-12T10:00:30Z",
    },
    {
      id: 4005,
      role: "user",
      content: "All docs are in. Can you prepare the return?",
      message_type: "text",
      created_at: "2026-02-15T09:00:00Z",
    },
    {
      id: 4006,
      role: "assistant",
      content:
        "Return prepared. Combined wages: $140,000 \u00b7 Dividends: $3,200 \u00b7 Total income: $143,200\n\nStandard deduction (MFJ): $29,200\nChild tax credit (4 dependents): $8,000\n\nEstimated federal refund: <strong>$2,080</strong>\n\nAll documents verified. Ready to file when you approve.",
      message_type: "text",
      created_at: "2026-02-15T09:00:10Z",
    },
  ],

  // Client 5 — Patel: complete, filed
  5: [
    {
      id: 5001,
      role: "assistant",
      content:
        "Welcome! I\u2019ve set up the file for Patel Family (MFJ, TY 2025, 1 dependent).",
      message_type: "text",
      created_at: "2026-01-25T16:00:30Z",
    },
    {
      id: 5002,
      role: "assistant",
      content:
        "W-2 (Raj) \u2014 99% confidence. Wages: $185,000. W-2 (Priya) \u2014 98% confidence. Wages: $125,000.",
      message_type: "text",
      created_at: "2026-01-25T16:15:00Z",
    },
    {
      id: 5003,
      role: "assistant",
      content:
        "Return prepared and reviewed. Combined wages: $310,000 \u00b7 Standard deduction (MFJ): $29,200 \u00b7 Child tax credit: $2,000\n\nFederal refund: <strong>$1,240</strong>\nCA liability: <strong>-$4,850</strong>",
      message_type: "text",
      created_at: "2026-02-01T10:00:00Z",
    },
    {
      id: 5004,
      role: "user",
      content: "Looks good. Go ahead and file.",
      message_type: "text",
      created_at: "2026-02-05T14:00:00Z",
    },
    {
      id: 5005,
      role: "assistant",
      content:
        "\u2705 <strong>Return e-filed successfully</strong> on 02/05/2026.\n\nFederal: Accepted \u00b7 Confirmation #: 2026-FED-00482\nCalifornia: Accepted \u00b7 Confirmation #: 2026-CA-01893\n\nExpected refund deposit: 2\u20133 weeks.",
      message_type: "text",
      created_at: "2026-02-05T14:00:10Z",
    },
  ],
};

// ── Tax Return Drafts ──────────────────────────────────────

export const mockReturnDrafts: Record<number, TaxReturnDraft> = {
  // Client 1 — Smith (single, 1 dep)
  1: {
    client_id: 1,
    tax_year: 2025,
    filing_status: "single",
    lines: [
      { number: "1a", label: "Wages, salaries, tips", value: 112400, section: "Income" },
      { number: "2b", label: "Taxable interest", value: 2340, section: "Income" },
      { number: "9", label: "Total income", value: 114740, section: "Income" },
      { number: "12", label: "Standard deduction", value: 15000, section: "Deductions" },
      { number: "15", label: "Taxable income", value: 99740, section: "Deductions" },
      { number: "16", label: "Tax", value: 17412, section: "Tax & Credits" },
      { number: "19", label: "Child tax credit", value: 2000, section: "Tax & Credits" },
      { number: "24", label: "Total tax", value: 15412, section: "Tax & Credits" },
      { number: "25a", label: "W-2 withholding", value: 18750, section: "Payments" },
      { number: "33", label: "Total payments", value: 18750, section: "Payments" },
      { number: "34", label: "Overpayment / Refund", value: 3338, section: "Payments" },
    ],
    total_income: 114740,
    taxable_income: 99740,
    total_tax: 15412,
    refund_or_owed: 3338,
    effective_rate: 13.4,
  },

  // Client 4 — Garcia (MFJ, 4 dep)
  4: {
    client_id: 4,
    tax_year: 2025,
    filing_status: "mfj",
    lines: [
      { number: "1a", label: "Wages, salaries, tips", value: 140000, section: "Income" },
      { number: "3b", label: "Ordinary dividends", value: 3200, section: "Income" },
      { number: "9", label: "Total income", value: 143200, section: "Income" },
      { number: "12", label: "Standard deduction", value: 29200, section: "Deductions" },
      { number: "15", label: "Taxable income", value: 114000, section: "Deductions" },
      { number: "16", label: "Tax", value: 17520, section: "Tax & Credits" },
      { number: "19", label: "Child tax credit", value: 8000, section: "Tax & Credits" },
      { number: "24", label: "Total tax", value: 9520, section: "Tax & Credits" },
      { number: "25a", label: "W-2 withholding", value: 19400, section: "Payments" },
      { number: "33", label: "Total payments", value: 19400, section: "Payments" },
      { number: "34", label: "Overpayment / Refund", value: 9880, section: "Payments" },
    ],
    total_income: 143200,
    taxable_income: 114000,
    total_tax: 9520,
    refund_or_owed: 9880,
    effective_rate: 6.6,
  },

  // Client 5 — Patel (MFJ, 1 dep)
  5: {
    client_id: 5,
    tax_year: 2025,
    filing_status: "mfj",
    lines: [
      { number: "1a", label: "Wages, salaries, tips", value: 310000, section: "Income" },
      { number: "9", label: "Total income", value: 310000, section: "Income" },
      { number: "12", label: "Standard deduction", value: 29200, section: "Deductions" },
      { number: "15", label: "Taxable income", value: 280800, section: "Deductions" },
      { number: "16", label: "Tax", value: 55760, section: "Tax & Credits" },
      { number: "19", label: "Child tax credit", value: 2000, section: "Tax & Credits" },
      { number: "24", label: "Total tax", value: 53760, section: "Tax & Credits" },
      { number: "25a", label: "W-2 withholding", value: 57000, section: "Payments" },
      { number: "33", label: "Total payments", value: 57000, section: "Payments" },
      { number: "34", label: "Overpayment / Refund", value: 3240, section: "Payments" },
    ],
    total_income: 310000,
    taxable_income: 280800,
    total_tax: 53760,
    refund_or_owed: 3240,
    effective_rate: 17.3,
  },
};

// ── Mock upload extraction templates ───────────────────────

export const mockExtractionTemplates: Record<
  string,
  { confidence: number; flags: string[]; data: Record<string, unknown> }
> = {
  "W-2": {
    confidence: 0.99,
    flags: [],
    data: {
      employer_name: "Uploaded Employer Inc",
      employer_ein: "99-8765432",
      employee_name: "Uploaded Employee",
      wages: 75000,
      federal_tax_withheld: 11250,
      social_security_wages: 75000,
      social_security_tax: 4650,
      medicare_wages: 75000,
      medicare_tax: 1087.5,
      state: "NJ",
      state_wages: 75000,
      state_tax: 3750,
    },
  },
  "1099-INT": {
    confidence: 0.82,
    flags: ["Account number partially obscured \u2014 82% confidence"],
    data: {
      payer_name: "Uploaded Bank",
      interest_income: 1500,
      federal_tax_withheld: 0,
    },
  },
  "1099-NEC": {
    confidence: 0.96,
    flags: [],
    data: {
      payer_name: "Uploaded Payer LLC",
      nonemployee_compensation: 8500,
      federal_tax_withheld: 0,
    },
  },
  "1099-DIV": {
    confidence: 0.97,
    flags: [],
    data: {
      payer_name: "Uploaded Fund Inc",
      ordinary_dividends: 2100,
      qualified_dividends: 1800,
      federal_tax_withheld: 0,
    },
  },
  "1098": {
    confidence: 0.95,
    flags: [],
    data: {
      lender_name: "Uploaded Mortgage Co",
      mortgage_interest: 9800,
      outstanding_principal: 250000,
      real_estate_taxes: 5200,
    },
  },
  "K-1": {
    confidence: 0.9,
    flags: [],
    data: {
      partnership_name: "Uploaded Partnership",
      ordinary_income: 15000,
      guaranteed_payments: 5000,
    },
  },
  _default: {
    confidence: 0.8,
    flags: ["Unknown form type \u2014 manual review recommended"],
    data: { raw_text: "Document uploaded for manual review" },
  },
};
```

- [ ] **Step 2: Verify build**

Run: `cd /Users/admin-h26/taxflow-kb/frontend && npm run build`

Expected: Build succeeds (file is only data, no JSX).

- [ ] **Step 3: Commit**

```bash
cd /Users/admin-h26/taxflow-kb
git add frontend/lib/mock-data.ts
git commit -m "feat(frontend): add rich mock data for 5 clients across all workflow stages"
```

---

## Task 2: Create Mock API

**Files:**
- Create: `frontend/lib/mock-api.ts`

- [ ] **Step 1: Create the mock API implementation**

```typescript
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
```

- [ ] **Step 2: Verify build**

Run: `cd /Users/admin-h26/taxflow-kb/frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
cd /Users/admin-h26/taxflow-kb
git add frontend/lib/mock-api.ts
git commit -m "feat(frontend): add mock API layer with simulated delays and stateful operations"
```

---

## Task 3: Wire Mock API into Page

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Replace inline mock data with mock API**

In `frontend/app/page.tsx`, make these changes:

**A) Add import for mockApi** (near the top, after existing imports):

```typescript
import { mockApi } from "@/lib/mock-api";
```

**B) Remove the entire inline mock data block** — delete everything between the two comment banners:

```
// ────────────────────────────────────────────
// Mock data for offline / fallback mode
// ────────────────────────────────────────────
```

and

```
// ────────────────────────────────────────────
// Page component
// ────────────────────────────────────────────
```

This deletes `mockSidebarClients`, `LocalMessage` interface, `mockMessages`, `LocalDoc` interface, and `mockDocuments`. (~180 lines, lines 34-212)

**C) Add `LocalMessage` and `LocalDoc` interfaces back** (they're still needed for state typing — place them right before `export default function Home()`):

```typescript
interface LocalMessage {
  id: string | number;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  created_at?: string;
}

interface LocalDoc {
  id: number;
  form_type: string;
  title: string;
  status: string;
  confidence: number;
  extracted_data: string;
  flags: string;
  name: string;
  type: string;
}
```

**D) Update initial state** — change the initial state values that referenced mock data:

```typescript
  const [activeClientId, setActiveClientId] = useState<string | null>(null);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [documents, setDocuments] = useState<LocalDoc[]>([]);
  const [sidebarClients, setSidebarClients] = useState<SidebarClient[]>([]);
```

(Previously: `activeClientId` was `"1"`, messages was `mockMessages`, documents was `mockDocuments`, sidebarClients was `mockSidebarClients`)

**E) Replace the `loadClients` useEffect** — change the try/catch to try real API first, then fall back to mockApi:

```typescript
  // Try loading from API on mount — fallback to mock
  useEffect(() => {
    let cancelled = false;
    async function loadClients() {
      let data: ApiClient[] = [];
      try {
        data = await api.clients.list();
        if (!cancelled && Array.isArray(data) && data.length > 0) {
          setUsingApi(true);
        }
      } catch {
        // API unavailable — use mock
      }

      if (!cancelled && data.length === 0) {
        try {
          data = await mockApi.clients.list();
        } catch { /* ignore */ }
      }

      if (cancelled || !Array.isArray(data) || data.length === 0) return;

      setApiClients(data);
      const converted: SidebarClient[] = data.map((c: ApiClient) => ({
        id: String(c.id),
        name: c.name,
        meta: `${c.filing_status} \u00b7 ${c.dependents} dep. \u00b7 ${c.tax_year}`,
        status: mapWorkflowStep(c.workflow_step),
        initials: c.name
          .split(" ")
          .map((w) => w[0])
          .join("")
          .slice(0, 2)
          .toUpperCase(),
        color: hashColor(c.name),
      }));
      setSidebarClients(converted);
      if (converted.length > 0) setActiveClientId(converted[0].id);
    }
    loadClients();
    return () => { cancelled = true; };
  }, [setApiClients]);
```

**F) Replace the `loadClientData` useEffect** — use mockApi as fallback:

```typescript
  // Load chat and documents when active client changes
  useEffect(() => {
    if (!activeClientId) return;
    const numId = Number(activeClientId);
    if (isNaN(numId)) return;

    let cancelled = false;
    async function loadClientData() {
      const source = usingApi ? api : mockApi;
      try {
        const [chatData, docData] = await Promise.all([
          source.chat.history(numId),
          source.documents.list(numId),
        ]);
        if (cancelled) return;
        if (Array.isArray(chatData)) {
          setApiMessages(chatData);
          setMessages(
            chatData.map((m: ChatMessage) => ({
              id: m.id,
              role: m.role,
              content: m.content,
              timestamp: new Date(m.created_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              }),
              created_at: m.created_at,
            }))
          );
        }
        if (Array.isArray(docData)) {
          setApiDocuments(docData);
          setDocuments(
            docData.map((d: ApiDocument) => ({
              ...d,
              client_id: d.client_id,
              name: d.title,
              type: d.form_type,
            }))
          );
        }
      } catch {
        setMessages([]);
        setDocuments([]);
      }
    }
    loadClientData();
    return () => { cancelled = true; };
  }, [activeClientId, usingApi, setApiMessages, setApiDocuments]);
```

**G) Update `handleSendMessage`** — replace the mock AI fallback with mockApi:

Find the `// Mock AI response` setTimeout block and replace the entire else branch:

```typescript
      // Fallback to mock API
      try {
        const response = await mockApi.chat.send(numId, content);
        setIsTyping(false);
        setMessages((prev) => [
          ...prev,
          {
            id: response.id || Date.now() + 1,
            role: "assistant",
            content: response.content,
            timestamp: new Date(response.created_at || Date.now()).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
          },
        ]);
      } catch {
        setIsTyping(false);
      }
```

**H) Update `handleGenerateReturn`** — add mockApi fallback:

```typescript
  const handleGenerateReturn = useCallback(async () => {
    const numId = Number(activeClientId);
    if (isNaN(numId)) return;
    const source = usingApi ? api : mockApi;
    try {
      const draft = await source.returns.draft(numId);
      setReturnDraft(draft);
    } catch { /* ignore */ }
  }, [activeClientId, usingApi]);
```

**I) Update `handleFileSelected`** — use mockApi when not using real API:

In the upload handler, replace the condition `if (!isNaN(numId))` block to use the right source:

```typescript
      const numId = Number(activeClientId);
      if (isNaN(numId)) return;

      const source = usingApi ? api : mockApi;
      try {
        const doc = await source.documents.upload(numId, file, formType);
        const docData = await source.documents.list(numId);
        if (Array.isArray(docData)) {
          setDocuments(docData.map((d: ApiDocument) => ({
            ...d, client_id: d.client_id, name: d.title, type: d.form_type,
          })));
        }
        let summary = `<strong>${formType}</strong> uploaded and processed (${Math.round(doc.confidence * 100)}% confidence).`;
        try {
          const data = JSON.parse(doc.extracted_data);
          if (typeof data === "object" && data !== null) {
            const entries = Object.entries(data).slice(0, 4);
            const details = entries.map(([k, v]) => `${k.replace(/_/g, " ")}: ${typeof v === "number" ? `$${v.toLocaleString()}` : v}`).join(" \u00b7 ");
            if (details) summary += `\n${details}`;
          }
        } catch { /* ignore */ }
        const flags = JSON.parse(doc.flags || "[]");
        if (flags.length > 0) {
          summary += `\n\u26A0 ${flags.length} flag(s): ${flags.join(", ")}`;
        }
        setMessages((prev) => [
          ...prev.filter((m) => m.id !== uploadMsg.id),
          { id: Date.now() + 1, role: "assistant" as const, content: summary,
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
        ]);
      } catch (err) {
        setMessages((prev) => [
          ...prev.filter((m) => m.id !== uploadMsg.id),
          { id: Date.now() + 1, role: "assistant" as const,
            content: `Failed to upload ${file.name}: ${err instanceof Error ? err.message : "Unknown error"}`,
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
        ]);
      }
```

**J) Update IntakeModal onSubmit** — use mockApi as fallback for client creation and chat:

In the IntakeModal's `onSubmit` handler, the existing code tries `api.clients.create()` and falls back to a local-only client. Change the catch block to use `mockApi` instead:

Replace the catch block (`} catch {` around line ~790) with:

```typescript
          } catch {
            // Use mock API
            try {
              const created = await mockApi.clients.create({
                name,
                filing_status: data.filingStatus,
                tax_year: data.taxYear,
                dependents: data.dependents,
              });
              const newId = String(created.id);
              const meta = [
                data.spouseFirstName ? `${data.firstName} & ${data.spouseFirstName}` : data.firstName,
                filingLabel,
                data.dependents > 0 ? `${data.dependents} dep.` : null,
              ].filter(Boolean).join(" \u00b7 ");

              setSidebarClients((prev) => [
                {
                  id: newId, name, meta, status: "pending",
                  initials: name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase(),
                  color: hashColor(name),
                },
                ...prev,
              ]);
              handleSelectClient(newId);

              const chatData = await mockApi.chat.history(created.id);
              if (Array.isArray(chatData)) {
                setMessages(chatData.map((m: ChatMessage) => ({
                  id: m.id, role: m.role, content: m.content,
                  timestamp: new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                })));
              }
              setDocuments([]);
            } catch {
              // Last resort — local only
              const newId = String(Date.now());
              setSidebarClients((prev) => [
                { id: newId, name, meta: filingLabel, status: "pending", initials: name.slice(0, 2).toUpperCase(), color: "#6B7280" },
                ...prev,
              ]);
              handleSelectClient(newId);
              setMessages([]);
            }
          }
```

- [ ] **Step 2: Verify build**

Run: `cd /Users/admin-h26/taxflow-kb/frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
cd /Users/admin-h26/taxflow-kb
git add frontend/app/page.tsx
git commit -m "feat(frontend): wire mock API as fallback — full workflow works without backend"
```

---

## Summary

3 tasks, 3 commits:

1. **Mock data** — 5 clients, 12 documents, 25 chat messages, 3 tax return drafts, upload templates
2. **Mock API** — Stateful mock matching the real API shape, with simulated delays and dynamic responses
3. **Wire into page** — Remove inline mocks, use `mockApi` as automatic fallback when backend is unavailable
