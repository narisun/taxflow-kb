# TaxFlow AI — Agentic Layer Foundation (Sub-project A)

## Goal

Replace the current single-turn chat pass-through with a tool-calling AI agent that answers CPA queries grounded in live client data, with bulletproof tenant isolation and persistent conversation history. The agent can read and analyze but never mutate — all write actions remain user-initiated.

## Scope

This spec covers Phases 1–3 of the agentic layer:

- **P1:** Conversation model + PostgreSQL RLS tenant isolation
- **P2:** FastMCP server with 6 READ tools
- **P3:** AgentService with Claude tool-use loop

Sub-project B (P4–P7: analysis tools, RAG bridge, draft tools, context management) is a separate spec that layers on after this foundation is solid.

---

## Architecture Overview

```
Frontend Chat UI
    ↓ POST /api/clients/{cid}/conversations/{conv_id}/messages
    ↓ Auth: JWT → user_id, org_id
    ↓
ChatRouter (FastAPI)
    ├─ Validate: client belongs to user's org
    ├─ SET app.current_org_id (PostgreSQL RLS)
    ├─ Load/create conversation (scoped to org + client + user)
    ├─ Load conversation history (token-budgeted)
    └─ Dispatch to AgentService
            ↓
AgentService (Claude tool_use loop)
    ├─ System prompt (client context, rules, PII policy)
    ├─ while has_tool_calls:
    │     call MCP tools → collect results → feed back
    ├─ Persist all messages (user, assistant, tool_call, tool_result)
    └─ Return final assistant message
            ↓
FastMCP Tool Server (in-process, no network hop)
    ├─ get_client_summary()
    ├─ list_documents()
    ├─ get_document_fields(doc_id)
    ├─ get_return_draft()
    ├─ get_return_line_detail(line_number)
    └─ list_dependents()
    All tools:
      - Read client_id from AgentSession (injected, not LLM-controlled)
      - Run through RLS-protected DB session
      - Mask PII before returning to LLM
```

---

## P1: Conversation Model + RLS

### 1.1 Database Tables

**`conversations`**

| Column | Type | Constraint |
|--------|------|------------|
| `id` | `String(36)` PK | UUIDv7 via `new_uuid()` |
| `org_id` | `String(36)` FK → organizations | NOT NULL, RLS-enforced |
| `client_id` | `String(36)` FK → clients | NOT NULL |
| `user_id` | `String(36)` FK → users | NOT NULL |
| `title` | `String(200)` | Auto-generated from first user message (first 80 chars) |
| `is_active` | `Boolean` | Default `True`. Soft-close old conversations. |
| `created_at` | `DateTime` | UTC |
| `updated_at` | `DateTime` | UTC, auto-on-update |

Index: `(org_id, client_id, user_id)` for fast lookup.

**`conversation_messages`**

| Column | Type | Constraint |
|--------|------|------------|
| `id` | `String(36)` PK | UUIDv7 |
| `conversation_id` | `String(36)` FK → conversations | NOT NULL |
| `org_id` | `String(36)` FK → organizations | NOT NULL (denormalized for RLS) |
| `role` | `String(20)` | `user`, `assistant`, `tool_call`, `tool_result` |
| `content` | `Text` | The visible message text (empty for tool_call/tool_result) |
| `tool_name` | `String(100)` | Nullable. Which MCP tool was called. |
| `tool_call_id` | `String(100)` | Nullable. Claude's tool_use ID for pairing call↔result. |
| `tool_input` | `Text` | Nullable. JSON of tool call arguments. |
| `tool_output` | `Text` | Nullable. JSON of tool result (PII-masked). |
| `token_count` | `Integer` | Estimated token count for context budgeting. |
| `created_at` | `DateTime` | UTC |

Index: `(conversation_id, created_at)` for ordered history load.
Index: `(org_id)` for RLS.

### 1.2 PostgreSQL Row Level Security

RLS is defense-in-depth on top of existing app-level `WHERE org_id = ...` filters. It catches missed filters, raw SQL, and new endpoints that forget the pattern.

**Policy applied to all tenant tables:**

```sql
-- Applied per table (clients, documents, conversations,
-- conversation_messages, chat_messages, dependents,
-- tax_return_drafts, manual_entries, family_groups)
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON {table}
  USING (org_id = current_setting('app.current_org_id', true)::text);
```

`current_setting(..., true)` returns NULL if the variable is unset (rather than erroring), which means unset = no rows visible = safe default.

**Connection-level setup:**

The existing `get_session()` dependency is auth-independent (it just yields a DB session). RLS activation happens in a new dependency that composes both:

```python
async def get_rls_session(
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
) -> AsyncSession:
    """Yield a DB session with RLS tenant context set."""
    await session.execute(
        text("SET LOCAL app.current_org_id = :oid"),
        {"oid": user.org_id},
    )
    return session
```

`SET LOCAL` scopes the variable to the current transaction, preventing leakage across connection pool reuse. Endpoints that need RLS use `Depends(get_rls_session)` instead of `Depends(get_session)`. Existing endpoints can migrate incrementally.

**Database role for the application:**

The app connects as a non-superuser role (e.g., `taxflow_app`). Superusers bypass RLS. The migration creates the role and grants appropriate permissions. The `taxflow` superuser role is used only for migrations.

**Alembic migration:**

One migration that:
1. Creates the `conversations` and `conversation_messages` tables.
2. Enables RLS + creates `tenant_isolation` policy on all tenant tables.
3. Creates the `taxflow_app` database role (if not exists) with `LOGIN` and appropriate `GRANT`s.

### 1.3 Pydantic Schemas

```python
class ConversationCreate(BaseModel):
    client_id: str

class ConversationResponse(BaseModel):
    id: str
    client_id: str
    user_id: str
    title: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

class ConversationMessageResponse(BaseModel):
    id: str
    role: str  # user | assistant | tool_call | tool_result
    content: str
    tool_name: str | None = None
    created_at: datetime

class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
```

### 1.4 API Endpoints

```
POST   /api/clients/{client_id}/conversations
       → Create a new conversation. Returns ConversationResponse.

GET    /api/clients/{client_id}/conversations
       → List conversations for this client+user. Paginated.

GET    /api/conversations/{conversation_id}/messages
       → Load message history. Paginated, newest-last.

POST   /api/conversations/{conversation_id}/messages
       → Send a user message. Triggers the agent loop.
         Returns the final assistant message (+ intermediate tool
         calls are persisted but not returned in the response body;
         the frontend can poll or re-fetch history if it wants to
         show tool call details).

DELETE /api/conversations/{conversation_id}
       → Soft-delete (set is_active=false). Conversations are not
         hard-deleted because they may be needed for audit.
```

All endpoints enforce:
- Auth: `require_onboarded_user`
- Org scope: client must belong to user's org
- RLS: `SET LOCAL app.current_org_id`

### 1.5 Relationship to Existing `chat_messages` Table

The existing `chat_messages` table and `/api/clients/{client_id}/chat` endpoints continue to work unchanged during the transition. The new conversation system is additive. Once the frontend switches to the new endpoints, the old table becomes unused and can be dropped in a future cleanup.

---

## P2: FastMCP Tool Server

### 2.1 Tool Design Principles

1. **No client_id parameter on any tool.** The LLM cannot choose which client to query. `client_id` is injected from the `AgentSession` created by the router.

2. **All PII masked.** Tools call the existing `PIIEncryptor.mask_*` methods. SSN → `***-**-1234`, DOB → `**/**/1985`, street → first-5-chars + `***`. The `reveal_pii` endpoint is never exposed as a tool.

3. **Structured return values.** Tools return typed dicts, not free-text. Claude formats the data into natural language for the user.

4. **No side effects.** Every tool is a pure read. No database writes, no external calls, no state mutations.

5. **Error handling.** Tools return `{"error": "..."}` on failure rather than raising exceptions. The agent can report the error to the user gracefully.

### 2.2 AgentSession

```python
@dataclass(frozen=True)
class AgentSession:
    """Immutable context for one agent invocation.
    Created by the router, threaded through to all MCP tools.
    Frozen so it cannot be mutated mid-request."""
    org_id: str
    client_id: str
    user_id: str
    conversation_id: str
    db_session: AsyncSession  # RLS already configured
    pii_encryptor: PIIEncryptor
```

### 2.3 Tool Inventory (6 READ tools)

**`get_client_summary()`**

Returns: client name, filing status, tax year, dependents count, workflow step, email (plaintext — not PII), phone, masked SSN, masked DOB, masked street, city, state, zip, spouse info (masked), family group name, filing states.

Source: `ClientModel` + `FamilyGroupModel` via existing `_build_response` pattern.

**`list_documents()`**

Returns: list of `{form_type, file_name, title, status, confidence, flags_count, uploaded_by, uploaded_at, reviewed_by, reviewed_at}` for all documents belonging to the client.

Source: `DocumentModel` with user-name resolution (existing `_resolve_user_names` pattern).

**`get_document_fields(doc_id: str)`**

Parameters: `doc_id` — the LLM CAN specify which document to drill into (but only documents belonging to the current client are accessible thanks to RLS + app-level filter).

Returns: list of `{field_name, display_label, value, confidence, flagged, flag_reason}`. SSN values within extracted data are masked via `mask_ssns_in_payload`.

Source: `DocumentModel.extracted_data` (JSON parse) + field mapping labels.

Validation: the tool verifies `doc.client_id == session.client_id` before returning.

**`get_return_draft()`**

Returns: `{tax_year, filing_status, lines: [{number, label, value, section}], total_income, taxable_income, total_tax, refund_or_owed, effective_rate}` or `null` if no draft has been computed.

Source: `TaxReturnDraftModel` → parse `draft_json`.

**`get_return_line_detail(line_number: str)`**

Parameters: `line_number` — e.g., `"1a"`, `"25a"`.

Returns: breakdown of which documents/entries contribute to this line. For example, line 1a (wages) returns each W-2's employer name + wages amount.

Source: `TaxReturnDraftModel.draft_json` line-level detail + cross-reference with `DocumentModel` extracted data.

**`list_dependents()`**

Returns: list of `{first_name, last_name, relationship, is_qualifying_child, ssn_masked, dob_masked}`.

Source: `DependentModel` with PII masking.

### 2.4 File Structure

```
api/agent/
├── __init__.py
├── session.py          # AgentSession dataclass
├── mcp_server.py       # FastMCP tool definitions
├── tools/
│   ├── __init__.py
│   ├── client_tools.py     # get_client_summary, list_dependents
│   ├── document_tools.py   # list_documents, get_document_fields
│   └── return_tools.py     # get_return_draft, get_return_line_detail
└── service.py          # AgentService (tool-use loop)
```

Each tool file contains pure async functions that take an `AgentSession` and return a dict. The `mcp_server.py` file registers them as FastMCP tools and wires in the session.

### 2.5 FastMCP Integration

```python
from fastmcp import FastMCP

mcp = FastMCP("taxflow-agent")

@mcp.tool()
async def get_client_summary() -> dict:
    """Get the current client's profile, filing status, and masked PII."""
    session = _current_session.get()  # contextvars
    return await client_tools.get_client_summary(session)
```

The `AgentSession` is threaded via `contextvars.ContextVar` so tool functions don't need explicit parameters that the LLM could manipulate.

---

## P3: AgentService

### 3.1 Responsibilities

1. Build the system prompt with client context summary and behavioral rules.
2. Load conversation history (recent N messages, token-budgeted).
3. Run the Claude tool-use loop: send messages → receive tool_calls → execute tools → feed results back → repeat until Claude emits a final text response.
4. Persist every message (user, assistant, tool_call, tool_result) to `conversation_messages`.
5. Return the final assistant message to the router.

### 3.2 System Prompt

```
You are TaxFlow AI, an assistant for CPAs using TaxFlow to prepare tax returns.

CURRENT CONTEXT:
- CPA: {user.name} ({user.email})
- Client: {client.name} — {client.filing_status}, TY {client.tax_year}
- Workflow step: {client.workflow_step}

RULES:
1. Answer ONLY using data returned by your tools. Never fabricate numbers,
   dollar amounts, or tax figures.
2. All client data you see has PII masked (SSN, DOB, address). Do NOT
   attempt to reconstruct, guess, or display unmasked PII.
3. You can READ data and ANALYZE it. You CANNOT modify data, approve
   documents, send emails, or submit returns. If the user asks you to
   take an action, explain what they need to do in the UI.
4. When referencing specific numbers, state which tool/document they came
   from (e.g., "per the W-2 from Acme Corp").
5. All your tools are scoped to this client only. You cannot access other
   clients' data.
6. If you lack data to answer a question, say so and suggest what the user
   should upload or configure.
7. Keep responses concise and professional. Use markdown formatting for
   readability (bold key numbers, bullet lists for multi-item answers).
```

### 3.3 Tool-Use Loop

```python
async def reply(
    self,
    user_message: str,
    session: AgentSession,
    history: list[dict],  # prior conversation messages
) -> str:
    messages = [
        {"role": "system", "content": self._build_system_prompt(session)},
        *history,
        {"role": "user", "content": user_message},
    ]

    MAX_TOOL_ROUNDS = 10  # safety limit
    for _ in range(MAX_TOOL_ROUNDS):
        response = await self._call_claude(messages, tools=self.tool_definitions)

        # If Claude returns a text response (no tool calls), we're done.
        if response.stop_reason == "end_turn":
            return response.content[0].text

        # Process tool calls
        tool_results = []
        for tool_use in response.content:
            if tool_use.type == "tool_use":
                result = await self._execute_tool(tool_use, session)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(result),
                })
                # Persist tool_call + tool_result
                await self._persist_message(session, "tool_call", ...)
                await self._persist_message(session, "tool_result", ...)

        # Feed results back to Claude
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return "I wasn't able to complete the analysis within the allowed steps. Please try a more specific question."
```

### 3.4 Configuration

```python
# api/config.py additions
agent_model: str = "claude-sonnet-4-20250514"       # AGENT_MODEL env var
agent_max_tokens: int = 4096                         # AGENT_MAX_TOKENS
agent_max_tool_rounds: int = 10                      # AGENT_MAX_TOOL_ROUNDS
agent_history_token_budget: int = 8000               # AGENT_HISTORY_TOKEN_BUDGET
```

### 3.5 Token Budgeting (Simple v1)

For this sub-project, use a simple character-based estimate (`len(text) / 4` as rough token count). Load messages newest-first until the budget is exhausted, then reverse for chronological order. Tool_call and tool_result messages from prior turns are summarized to a single line: `"[Used tool: {name}]"` to save tokens.

Sub-project B (P7) replaces this with proper tiktoken counting and sliding-window summarization.

### 3.6 Error Handling

- **Tool execution failure:** Return `{"error": "Failed to load documents: ..."}` to Claude. The agent reports the error to the user and suggests a workaround.
- **Claude API failure:** Return a user-friendly error message. Do not retry automatically (user can re-send).
- **Max rounds exceeded:** Return the safety message (see 3.3).
- **RLS violation (should never happen):** If a query returns 0 rows unexpectedly, the tool returns `{"error": "Data not found"}`. The agent reports it. This is logged as a warning for investigation.

---

## Frontend Changes

### Conversation Sidebar

The chat panel gets a conversation list (similar to the Research Agent modal's thread list). Each conversation shows its title + last message timestamp. Users can switch between conversations or start a new one.

### Message Display

Tool calls are collapsed by default in the chat — the user sees the final assistant message. An expandable "Tool calls" section shows what the agent looked up (for transparency/debugging). This matches the pattern in Claude.ai and ChatGPT.

### Chip Migration

The hardcoded `handleCommand` switch statement in `page.tsx` is removed. The chips become simple suggested prompts that send their text as a regular message through the new conversation endpoint. The agent handles everything via tools.

The `handleSendMessage` function changes from:
```
1. Try handleCommand() (local JS)
2. If null, send to /api/clients/{cid}/chat (old endpoint)
```
to:
```
1. POST /api/conversations/{conv_id}/messages (new endpoint)
2. Display response
```

---

## Testing Strategy

### Backend Unit Tests

- **Conversation CRUD:** Create, list, get messages, soft-delete.
- **RLS enforcement:** Verify that a user from org A cannot see org B's conversations (even with raw SQL).
- **Tool isolation:** Verify `get_document_fields(doc_id)` rejects a doc_id belonging to a different client.
- **PII masking:** Verify every tool's return value has SSNs, DOBs, and streets masked.
- **Agent loop:** Mock Claude responses with tool_use blocks, verify correct tool dispatch and message persistence.

### Integration Tests

- **End-to-end flow:** Send a user message → agent calls tools → response contains data from the correct client.
- **Concurrent clients:** Two conversations for different clients in the same org, verify no data leakage.
- **History loading:** Verify conversation history is loaded correctly and token-budgeted.

### RLS-Specific Tests

- Directly execute SQL with mismatched `app.current_org_id` and verify 0 rows returned.
- Verify `SET LOCAL` scoping (variable does not leak across transactions).

---

## Migration Path

1. Deploy P1 (conversation model + RLS) — non-breaking, additive tables and policies.
2. Deploy P2 (MCP tools) — no API changes, internal module only.
3. Deploy P3 (AgentService + new endpoints) — new endpoints coexist with old `/chat` endpoints.
4. Switch frontend to new conversation endpoints — old chat becomes unused.
5. Future cleanup: drop `chat_messages` table and old `/chat` routes.

---

## Dependencies

- `fastmcp` — Python MCP server library (add to `requirements-api.txt`)
- `anthropic` — already present, used for tool_use API
- No new frontend dependencies

---

## Out of Scope (Sub-project B)

- Analysis tools (validate, compare, advisory, anomaly detection)
- Knowledge/RAG tools (search publications, lookup instructions, lookup rules)
- Draft tools (email, memo)
- Advanced context window management (tiktoken, summarization)
- Streaming responses
- Conversation branching/forking
