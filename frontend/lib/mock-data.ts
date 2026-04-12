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
  {
    id: 6,
    name: "Williams, Marcus",
    filing_status: "hoh",
    tax_year: 2025,
    dependents: 2,
    workflow_step: "review",
    created_at: "2026-03-01T08:30:00Z",
  },
  {
    id: 7,
    name: "Kim, Sarah & David",
    filing_status: "mfj",
    tax_year: 2025,
    dependents: 0,
    workflow_step: "documents",
    created_at: "2026-03-25T11:00:00Z",
  },
  {
    id: 8,
    name: "O'Brien, Patrick",
    filing_status: "single",
    tax_year: 2025,
    dependents: 0,
    workflow_step: "preparation",
    created_at: "2026-02-20T15:00:00Z",
  },
  {
    id: 9,
    name: "Nguyen Family",
    filing_status: "mfj",
    tax_year: 2025,
    dependents: 2,
    workflow_step: "filed",
    created_at: "2026-01-10T09:00:00Z",
  },
  {
    id: 10,
    name: "Rivera, Sofia",
    filing_status: "single",
    tax_year: 2025,
    dependents: 1,
    workflow_step: "intake",
    created_at: "2026-04-10T13:00:00Z",
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
        "Payer TIN mismatch — expected ending 4512, found 4521",
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
      title: "W-2 (Robert — Microsoft Corp)",
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
      title: "W-2 (Maria — County Hospital)",
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
      title: "W-2 (Carlos — Tesla Inc)",
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
      title: "W-2 (Ana — HEB Grocery)",
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

  // Client 6 — Williams: W-2 + 1099-NEC + flagged 1099-B (HOH, review)
  6: [
    {
      id: 601, client_id: 6, form_type: "W-2",
      title: "W-2 (Amazon Warehouse)",
      status: "verified", confidence: 0.98,
      extracted_data: JSON.stringify({
        employer_name: "Amazon.com Services LLC",
        employer_ein: "46-0723335",
        employee_name: "Marcus Williams",
        wages: 62000, federal_tax_withheld: 8400,
        social_security_wages: 62000, social_security_tax: 3844,
        medicare_wages: 62000, medicare_tax: 899,
        state: "GA", state_wages: 62000, state_tax: 3100,
      }),
      flags: "[]", created_at: "2026-03-01T08:35:00Z",
    },
    {
      id: 602, client_id: 6, form_type: "1099-NEC",
      title: "1099-NEC (Side Gig — TaskRabbit)",
      status: "verified", confidence: 0.95,
      extracted_data: JSON.stringify({
        payer_name: "TaskRabbit Inc",
        nonemployee_compensation: 9200,
        federal_tax_withheld: 0,
      }),
      flags: "[]", created_at: "2026-03-01T08:40:00Z",
    },
    {
      id: 603, client_id: 6, form_type: "1099-B",
      title: "1099-B (Robinhood)",
      status: "review", confidence: 0.78,
      extracted_data: JSON.stringify({
        payer_name: "Robinhood Securities LLC",
        proceeds: 4500,
        cost_basis: 3200,
        date_sold: "2025-09-15",
      }),
      flags: JSON.stringify(["Date sold confidence 78% \u2014 verify against statement"]),
      created_at: "2026-03-02T10:00:00Z",
    },
  ],

  // Client 7 — Kim: 2 W-2s (documents stage, still uploading)
  7: [
    {
      id: 701, client_id: 7, form_type: "W-2",
      title: "W-2 (Sarah \u2014 Deloitte)",
      status: "verified", confidence: 0.99,
      extracted_data: JSON.stringify({
        employer_name: "Deloitte LLP",
        employer_ein: "86-1065772",
        employee_name: "Sarah Kim",
        wages: 135000, federal_tax_withheld: 25000,
        social_security_wages: 135000, social_security_tax: 8370,
        medicare_wages: 135000, medicare_tax: 1957.5,
        state: "NY", state_wages: 135000, state_tax: 8775,
      }),
      flags: "[]", created_at: "2026-03-25T11:05:00Z",
    },
    {
      id: 702, client_id: 7, form_type: "W-2",
      title: "W-2 (David \u2014 NYU Medical)",
      status: "verified", confidence: 0.97,
      extracted_data: JSON.stringify({
        employer_name: "NYU Langone Health",
        employer_ein: "13-5562308",
        employee_name: "David Kim",
        wages: 165000, federal_tax_withheld: 30000,
        social_security_wages: 165000, social_security_tax: 10230,
        medicare_wages: 165000, medicare_tax: 2392.5,
        state: "NY", state_wages: 165000, state_tax: 10725,
      }),
      flags: "[]", created_at: "2026-03-25T11:10:00Z",
    },
  ],

  // Client 8 — O'Brien: W-2 + K-1 (preparation)
  8: [
    {
      id: 801, client_id: 8, form_type: "W-2",
      title: "W-2 (Boston Consulting Group)",
      status: "verified", confidence: 0.99,
      extracted_data: JSON.stringify({
        employer_name: "Boston Consulting Group",
        employer_ein: "04-2738909",
        employee_name: "Patrick O'Brien",
        wages: 195000, federal_tax_withheld: 42000,
        social_security_wages: 168600, social_security_tax: 10453.2,
        medicare_wages: 195000, medicare_tax: 2827.5,
        state: "MA", state_wages: 195000, state_tax: 9750,
      }),
      flags: "[]", created_at: "2026-02-20T15:05:00Z",
    },
    {
      id: 802, client_id: 8, form_type: "K-1",
      title: "K-1 (Tech Ventures LP)",
      status: "verified", confidence: 0.90,
      extracted_data: JSON.stringify({
        partnership_name: "Tech Ventures LP",
        ordinary_income: 28000,
        guaranteed_payments: 0,
        capital_gains: 12500,
      }),
      flags: "[]", created_at: "2026-02-22T09:00:00Z",
    },
  ],

  // Client 9 — Nguyen: W-2 + W-2 + 1099-DIV (filed)
  9: [
    {
      id: 901, client_id: 9, form_type: "W-2",
      title: "W-2 (Tuan \u2014 Intel Corp)",
      status: "verified", confidence: 0.99,
      extracted_data: JSON.stringify({
        employer_name: "Intel Corporation",
        employer_ein: "94-1672743",
        employee_name: "Tuan Nguyen",
        wages: 155000, federal_tax_withheld: 28000,
        social_security_wages: 155000, social_security_tax: 9610,
        medicare_wages: 155000, medicare_tax: 2247.5,
        state: "OR", state_wages: 155000, state_tax: 13950,
      }),
      flags: "[]", created_at: "2026-01-10T09:05:00Z",
    },
    {
      id: 902, client_id: 9, form_type: "W-2",
      title: "W-2 (Linh \u2014 Nike Inc)",
      status: "verified", confidence: 0.98,
      extracted_data: JSON.stringify({
        employer_name: "Nike Inc",
        employer_ein: "93-0584541",
        employee_name: "Linh Nguyen",
        wages: 92000, federal_tax_withheld: 14800,
        social_security_wages: 92000, social_security_tax: 5704,
        medicare_wages: 92000, medicare_tax: 1334,
        state: "OR", state_wages: 92000, state_tax: 8280,
      }),
      flags: "[]", created_at: "2026-01-10T09:10:00Z",
    },
    {
      id: 903, client_id: 9, form_type: "1099-DIV",
      title: "1099-DIV (Fidelity)",
      status: "verified", confidence: 0.97,
      extracted_data: JSON.stringify({
        payer_name: "Fidelity Investments",
        ordinary_dividends: 4800,
        qualified_dividends: 4200,
        capital_gain_distributions: 1200,
        federal_tax_withheld: 0,
      }),
      flags: "[]", created_at: "2026-01-12T10:00:00Z",
    },
  ],

  // Client 10 — Rivera: no docs (just intake)
  10: [],

  // Client 5 — Patel: W-2 + W-2 (filed)
  5: [
    {
      id: 501,
      client_id: 5,
      form_type: "W-2",
      title: "W-2 (Raj — Google LLC)",
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
      title: "W-2 (Priya — Stanford Health)",
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

  // Client 6 — Williams: review stage
  6: [
    { id: 6001, role: "assistant", content: "Welcome! I\u2019ve set up the file for Williams, Marcus (HOH, TY 2025, 2 dependents). Ready to receive documents.", message_type: "text", created_at: "2026-03-01T08:30:30Z" },
    { id: 6002, role: "assistant", content: "<strong>W-2</strong> uploaded \u2014 98% confidence. Wages: $62,000. Employer: Amazon.com Services LLC", message_type: "text", created_at: "2026-03-01T08:35:30Z" },
    { id: 6003, role: "assistant", content: "<strong>1099-NEC</strong> uploaded \u2014 95% confidence. Nonemployee compensation: $9,200 from TaskRabbit.", message_type: "text", created_at: "2026-03-01T08:40:30Z" },
    { id: 6004, role: "assistant", content: "<strong>1099-B</strong> uploaded \u2014 78% confidence.\nProceeds: $4,500 \u00b7 Cost basis: $3,200\n\u26A0 1 flag: Date sold confidence 78% \u2014 verify against statement", message_type: "text", created_at: "2026-03-02T10:00:30Z" },
    { id: 6005, role: "user", content: "The sale date was September 15, 2025. That\u2019s correct.", message_type: "text", created_at: "2026-03-02T10:05:00Z" },
    { id: 6006, role: "assistant", content: "Got it \u2014 I\u2019ve confirmed the sale date as 09/15/2025. The 1099-B is now ready for review. Short-term capital gain: <strong>$1,300</strong> (held < 1 year).", message_type: "text", created_at: "2026-03-02T10:05:05Z" },
  ],

  // Client 7 — Kim: documents stage
  7: [
    { id: 7001, role: "assistant", content: "Welcome! I\u2019ve set up the file for Kim, Sarah & David (MFJ, TY 2025, 0 dependents). Ready to receive documents.", message_type: "text", created_at: "2026-03-25T11:00:30Z" },
    { id: 7002, role: "assistant", content: "<strong>W-2</strong> (Sarah) uploaded \u2014 99% confidence. Wages: $135,000. Employer: Deloitte LLP", message_type: "text", created_at: "2026-03-25T11:05:30Z" },
    { id: 7003, role: "assistant", content: "<strong>W-2</strong> (David) uploaded \u2014 97% confidence. Wages: $165,000. Employer: NYU Langone Health", message_type: "text", created_at: "2026-03-25T11:10:30Z" },
    { id: 7004, role: "user", content: "We also have a 1099-INT from Chase and a 1098 mortgage statement. Will upload those next.", message_type: "text", created_at: "2026-03-25T11:15:00Z" },
    { id: 7005, role: "assistant", content: "Sounds good! Combined wages so far: $300,000. With MFJ filing, the standard deduction is $29,200. I\u2019ll update the estimate once the remaining documents are uploaded.", message_type: "text", created_at: "2026-03-25T11:15:05Z" },
  ],

  // Client 8 — O'Brien: preparation
  8: [
    { id: 8001, role: "assistant", content: "Welcome! I\u2019ve set up the file for O\u2019Brien, Patrick (Single, TY 2025, 0 dependents).", message_type: "text", created_at: "2026-02-20T15:00:30Z" },
    { id: 8002, role: "assistant", content: "<strong>W-2</strong> uploaded \u2014 99% confidence. Wages: $195,000. Employer: Boston Consulting Group", message_type: "text", created_at: "2026-02-20T15:05:30Z" },
    { id: 8003, role: "assistant", content: "<strong>K-1</strong> uploaded \u2014 90% confidence. Partnership: Tech Ventures LP \u00b7 Ordinary income: $28,000 \u00b7 Capital gains: $12,500", message_type: "text", created_at: "2026-02-22T09:00:30Z" },
    { id: 8004, role: "user", content: "What\u2019s my estimated tax situation?", message_type: "text", created_at: "2026-02-25T10:00:00Z" },
    { id: 8005, role: "assistant", content: "With $195,000 in wages and $40,500 in partnership income ($28K ordinary + $12.5K capital gains), your total income is <strong>$235,500</strong>.\n\nStandard deduction: $15,000\nTaxable income: ~$220,500\nEstimated tax: ~$47,800\nWithholding: $42,000\n\nYou may owe approximately <strong>$5,800</strong>. Consider estimated payment options.", message_type: "text", created_at: "2026-02-25T10:00:10Z" },
  ],

  // Client 9 — Nguyen: filed
  9: [
    { id: 9001, role: "assistant", content: "Welcome! I\u2019ve set up the file for Nguyen Family (MFJ, TY 2025, 2 dependents).", message_type: "text", created_at: "2026-01-10T09:00:30Z" },
    { id: 9002, role: "assistant", content: "W-2 (Tuan) \u2014 99% confidence. Wages: $155,000. W-2 (Linh) \u2014 98% confidence. Wages: $92,000.", message_type: "text", created_at: "2026-01-10T09:15:00Z" },
    { id: 9003, role: "assistant", content: "1099-DIV uploaded \u2014 97% confidence. Ordinary dividends: $4,800 \u00b7 Qualified: $4,200 \u00b7 Capital gains: $1,200", message_type: "text", created_at: "2026-01-12T10:00:30Z" },
    { id: 9004, role: "assistant", content: "Return prepared. Combined wages: $247,000 \u00b7 Dividends: $4,800 \u00b7 Total income: $251,800\nStandard deduction (MFJ): $29,200 \u00b7 Child tax credit (2): $4,000\n\nEstimated federal refund: <strong>$2,460</strong>\nOR liability: <strong>-$3,120</strong>", message_type: "text", created_at: "2026-01-15T11:00:00Z" },
    { id: 9005, role: "user", content: "Approved. Please file.", message_type: "text", created_at: "2026-01-20T14:00:00Z" },
    { id: 9006, role: "assistant", content: "\u2705 <strong>Return e-filed successfully</strong> on 01/20/2026.\n\nFederal: Accepted \u00b7 Confirmation #: 2026-FED-00127\nOregon: Accepted \u00b7 Confirmation #: 2026-OR-00891\n\nExpected refund: 2\u20133 weeks.", message_type: "text", created_at: "2026-01-20T14:00:10Z" },
  ],

  // Client 10 — Rivera: just intake
  10: [
    { id: 10001, role: "assistant", content: "Welcome! I\u2019ve set up the file for Rivera, Sofia (Single, TY 2025, 1 dependent). Ready to receive documents.", message_type: "text", created_at: "2026-04-10T13:00:30Z" },
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

  // Client 8 — O'Brien (single, 0 dep, high income)
  8: {
    client_id: 8, tax_year: 2025, filing_status: "single",
    lines: [
      { number: "1a", label: "Wages, salaries, tips", value: 195000, section: "Income" },
      { number: "2b", label: "Partnership income (K-1)", value: 40500, section: "Income" },
      { number: "9", label: "Total income", value: 235500, section: "Income" },
      { number: "12", label: "Standard deduction", value: 15000, section: "Deductions" },
      { number: "15", label: "Taxable income", value: 220500, section: "Deductions" },
      { number: "16", label: "Tax", value: 47800, section: "Tax & Credits" },
      { number: "24", label: "Total tax", value: 47800, section: "Tax & Credits" },
      { number: "25a", label: "W-2 withholding", value: 42000, section: "Payments" },
      { number: "33", label: "Total payments", value: 42000, section: "Payments" },
      { number: "37", label: "Amount you owe", value: -5800, section: "Payments" },
    ],
    total_income: 235500, taxable_income: 220500,
    total_tax: 47800, refund_or_owed: -5800, effective_rate: 20.3,
  },

  // Client 9 — Nguyen (MFJ, 2 dep, filed)
  9: {
    client_id: 9, tax_year: 2025, filing_status: "mfj",
    lines: [
      { number: "1a", label: "Wages, salaries, tips", value: 247000, section: "Income" },
      { number: "3b", label: "Ordinary dividends", value: 4800, section: "Income" },
      { number: "9", label: "Total income", value: 251800, section: "Income" },
      { number: "12", label: "Standard deduction", value: 29200, section: "Deductions" },
      { number: "15", label: "Taxable income", value: 222600, section: "Deductions" },
      { number: "16", label: "Tax", value: 44340, section: "Tax & Credits" },
      { number: "19", label: "Child tax credit", value: 4000, section: "Tax & Credits" },
      { number: "24", label: "Total tax", value: 40340, section: "Tax & Credits" },
      { number: "25a", label: "W-2 withholding", value: 42800, section: "Payments" },
      { number: "33", label: "Total payments", value: 42800, section: "Payments" },
      { number: "34", label: "Overpayment / Refund", value: 2460, section: "Payments" },
    ],
    total_income: 251800, taxable_income: 222600,
    total_tax: 40340, refund_or_owed: 2460, effective_rate: 16.0,
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
