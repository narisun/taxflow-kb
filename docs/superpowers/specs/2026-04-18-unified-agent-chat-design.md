# Unified Agent Chat with Smart Chips — Design Spec

**Date:** 2026-04-18
**Status:** Draft
**Scope:** Unify chat onto AgentService, add 5 tax tools, rewire 9 chips

## Problem

The client chat has two separate backends: `ChatService` (simple Claude call, no tools) and `AgentService` (Claude with tool-use loop). Chips are split between frontend-handled local commands (calling API endpoints directly) and LLM commands (sent to ChatService with enhanced prompts). Neither path gives Claude tool access, so the agent can't intelligently suggest next steps or chain actions.

## Decision Summary

- **Unify onto AgentService** — all chat (chips + free text) routes through AgentService with full tool use. ChatService is deprecated.
- **Report-only validation** — `validate_intake_vs_documents` lists discrepancies, does not offer to fix them.
- **Invisible conversations** — backend uses conversations for persistence but frontend hides the concept. One auto-managed conversation per client.

## Architecture

```
Frontend Chat Panel (9 chips + free text)
    ↓
POST /api/clients/{client_id}/chat
    ↓
Chat Router (auto-creates/resumes conversation per client)
    ↓
AgentService (Claude Sonnet + tool-use loop, up to 10 rounds)
    ↓
11 tools (6 existing + 5 new)
    ↓
Claude responds with results + suggested next steps
```

### Why Unify

- One system prompt, one tool registry, one persistence model
- Claude decides which tools to call — chip text is just a user message
- Follow-up suggestions work naturally (Claude has conversation history + tools)
- No more maintaining two separate LLM paths with divergent capabilities

## Tools (11 total)

### Existing Tools (6) — No Changes

| Tool | Purpose |
|------|---------|
| `get_client_summary` | Client profile, filing status, dependents, workflow step, masked PII |
| `list_dependents` | Dependent details with masked SSN/DOB |
| `list_documents` | All docs with status, confidence, flags count, audit trails |
| `get_document_fields` | Extracted fields for one document (SSNs masked) |
| `get_return_draft` | Latest computed 1040 draft if exists |
| `get_return_line_detail` | Breakdown of which documents contribute to a 1040 line |

### New Tools (5)

**validate_intake_vs_documents**
- **Purpose:** Cross-check intake form data against extracted document data to catch mismatches (wrong client's docs uploaded under another client, typos in intake)
- **Implementation:** Load client record (SSN, names, address, tax year) and all approved/verified documents' extracted fields. Compare key fields:
  - SSN (intake primary_ssn vs W-2 employee_ssn)
  - Name (intake first/last vs W-2 employee name)
  - Address (intake city/state/zip vs W-2 employee address)
  - Tax year (client tax_year vs document tax year indicators)
  - EIN consistency across multiple W-2s from same employer
- **Returns:** `{mismatches: [{field, intake_value, document_value, document_id, form_type, severity}], summary: str}`
- **Read-only.** Reports discrepancies, does not modify data.

**compute_tax_return**
- **Purpose:** Run full tax computation and save draft
- **Wraps:** `TaxReturnService.compute_and_save_draft()`
- **Returns:** `{status, tax_year, filing_status, total_income, taxable_income, total_tax, total_payments, refund_or_owed, effective_rate, line_count}`
- **Side effect:** Saves/updates TaxReturnDraftModel in DB

**run_advisory_analysis**
- **Purpose:** Run 12 advisory rules and return tax-saving recommendations
- **Wraps:** `TaxReturnService.get_advisory()`
- **Returns:** `{recommendations: [{title, detail, estimated_savings}], total_potential_savings}`
- **Sorted by estimated savings (highest first)**

**compare_prior_year**
- **Purpose:** Year-over-year comparison of key tax return lines
- **Wraps:** `TaxReturnService.compare_years()`
- **Input:** `prior_year` (optional, defaults to tax_year - 1)
- **Returns:** `{sections: [{name, rows: [{label, current, prior, change, pct_change}]}], summary: {current_refund, prior_refund, change}}`

**run_validation_rules**
- **Purpose:** Run 7 structural validation rules on the tax return
- **Wraps:** `TaxReturnService.validate()`
- **Returns:** `{results: [{rule_id, severity, message, suggestion}], has_errors: bool}`

## The 9 Chips

| # | Chip Label | User Message Sent | Tools Claude Typically Uses |
|---|------------|-------------------|---------------------------|
| 1 | Check status | "Check status" | `get_client_summary`, `list_documents`, `get_return_draft` |
| 2 | Review docs | "Review docs" | `list_documents`, `get_document_fields` (for flagged docs) |
| 3 | Run validations | "Run validations" | `validate_intake_vs_documents` |
| 4 | Compute return | "Compute return" | `compute_tax_return` |
| 5 | Analyze yoy | "Analyze yoy" | `compare_prior_year` |
| 6 | Estimate refund | "Estimate refund" | `get_return_draft` or `compute_tax_return` |
| 7 | Draft email | "Draft email" | `get_client_summary`, `list_documents`, `get_return_draft` + Claude drafts prose |
| 8 | Draft advisory | "Draft advisory" | `run_advisory_analysis` |
| 9 | Run pre-filing checks | "Run pre-filing checks" | `run_validation_rules`, `validate_intake_vs_documents`, `list_documents` |

Claude decides which tools to call based on the message — the chip text is treated identically to typed questions. The tool descriptions guide Claude's selection.

## System Prompt

```
You are TaxFlow AI, an assistant for CPAs using TaxFlow to prepare tax returns.

CURRENT CONTEXT:
- CPA: {user_name} ({user_email})
- Client: {client_name} — {filing_status}, TY {tax_year}
- Workflow step: {workflow_step}

RULES:
1. Answer ONLY using data returned by your tools. Never fabricate numbers.
2. All client PII is masked (SSN, DOB, address). Do not reconstruct or display unmasked PII.
3. You can READ and ANALYZE data. You can COMPUTE tax returns. You CANNOT modify client data, approve documents, send emails, or submit returns.
4. When referencing specific numbers, state which tool/document they came from.
5. All tools are scoped to this client only.
6. If you lack data to answer, say so and suggest what the CPA should do.

CONVERSATIONAL STYLE:
- After completing any action, summarize results concisely using markdown.
- Suggest 1-2 logical next steps as questions: "Would you like me to [action]?"
- If the user responds affirmatively (yes, sure, go ahead, do it), perform that action immediately.
- Keep context from the conversation — don't re-ask for information you already have.

CHIP BEHAVIOR GUIDELINES:
- For "Check status": summarize the return state and always suggest the next step
  (no docs → upload, unreviewed docs → review, no return → compute, etc.)
- For "Run validations": list each mismatch with field name, intake value, and
  document value side by side. Flag severity (critical for SSN, warning for address).
- For "Compute return" and "Estimate refund": prominently show refund or amount
  owed in bold. Include effective tax rate.
- For "Draft email" and "Draft advisory": produce ready-to-use text.
- For "Run pre-filing checks": run all available checks and present as a
  pass/fail checklist.

FORMAT:
- Use markdown for readability. Bold key figures.
- Structure complex responses with headers.
- Keep responses concise — CPAs are busy.
```

## Frontend Changes

### Chat Router Rewrite (`api/routers/chat.py`)

The `send_message` endpoint switches from `ChatService.reply()` to `AgentService.reply()`. Auto-conversation management:

1. On `POST /api/clients/{client_id}/chat`, check if a conversation exists for this client + user with `conversation_type='client'`
2. If not, create one (title = client name)
3. Load conversation history via `_load_history()`
4. Build `AgentSession` and call `AgentService.reply()`
5. Persist user + assistant messages to `ConversationMessageModel`
6. Return `ChatMessageResponse` (same shape as today — frontend doesn't change its response handling)

### Chat Input Chips

Update the chip array in `page.tsx`:

```typescript
["Check status", "Review docs", "Run validations", "Compute return",
 "Analyze yoy", "Estimate refund", "Draft email", "Draft advisory",
 "Run pre-filing checks"]
```

Remove "Run rules" (replaced by "Run validations"). Add "Compute return".

### Remove handleCommand

Delete the entire `handleCommand` function and all `case` handlers. The `handleSendMessage` function simplifies to:

1. Add user message to local state
2. POST to `/api/clients/{client_id}/chat` with the message content
3. Add assistant response to local state

No more frontend-side command routing. Every message (chip or typed) goes to the agent.

## Backend Changes

### New File: `api/agent/tools/tax_tools.py`

Contains 5 new tool handler functions:

- `validate_intake_vs_documents(session)` — cross-check client record vs extracted doc data
- `compute_tax_return(session)` — wraps TaxReturnService.compute_and_save_draft()
- `run_advisory_analysis(session)` — wraps TaxReturnService.get_advisory()
- `compare_prior_year(session, prior_year?)` — wraps TaxReturnService.compare_years()
- `run_validation_rules(session)` — wraps TaxReturnService.validate()

All tools receive `AgentSession` and use `session.client_id` for scoping. The PII encryptor from the session is passed to TaxReturnService where needed.

### Modified: `api/agent/mcp_server.py`

Register 5 new tools from `tax_tools.py` in `build_tool_registry()`.

### Modified: `api/agent/service.py`

Update `_SYSTEM_PROMPT` with the new conversational style and chip behavior guidelines.

### Modified: `api/routers/chat.py`

Rewrite `send_message` to use AgentService with auto-conversation management. Keep the same endpoint URL and response shape.

### Modified: `api/dependencies.py`

Update `get_chat_service` → `get_agent_service` dependency for the chat router (or add a new dependency that creates an AgentService configured for client chat).

## What Stays Unchanged

- `ChatService` code stays in codebase (not deleted, just no longer called from the chat router)
- Existing conversation endpoints (`/api/conversations/...`) — unchanged
- Research agent (`ResearchService`) — completely separate, unaffected
- Tax engine services (`TaxReturnService`, all engines) — unchanged, tools wrap them
- Document extraction, approval — unchanged
- Frontend message bubble rendering, chat input component — unchanged

## File Inventory

**New files:**
```
api/agent/tools/tax_tools.py              5 new tool handlers
tests/api/test_tax_tools.py               Tool handler tests
```

**Modified files:**
```
api/agent/mcp_server.py                   Register 5 new tools
api/agent/service.py                      Updated system prompt
api/routers/chat.py                       Switch to AgentService + auto-conversation
api/dependencies.py                       Wire agent service for chat
frontend/app/page.tsx                     Remove handleCommand, update chip array
```

## Testing Strategy

**Backend unit tests (mocked):**
- `test_tax_tools.py` — each tool handler with mock TaxReturnService, verify input/output shapes
- Existing `test_agent_service.py` — verify tool-use loop still works with new tools registered

**Integration tests:**
- Existing conversation tests pass (auto-conversation doesn't break explicit conversations)
- Chat endpoint returns agent-quality responses (tool calls visible in DB)

**Manual testing:**
- Each of the 9 chips produces a meaningful response
- Follow-up suggestions work (agent suggests next step, user says yes, agent acts)
- Free-text questions still work alongside chips

## Non-Goals

- Streaming for client chat (defer — research agent has it, client chat can add later)
- Write operations from the agent (no data modification, no document approval)
- Conversation thread UI in client chat (stays invisible)
- Migrating existing ChatMessage history to ConversationMessage (old messages stay, new ones go to conversation model)
