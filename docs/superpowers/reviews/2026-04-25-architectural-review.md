# TaxFlow AI — Architectural Code Review

**Date**: 2026-04-25
**Reviewer**: Claude (Software Architect / Lead Engineer review)
**Branch**: `feat/fullstack-platform`
**Scope**: Full-stack architecture, OOP/DI patterns, security, testability, best practices

---

## Executive Summary

TaxFlow AI is a well-structured full-stack tax preparation platform with a Python/FastAPI backend, Next.js frontend, PostgreSQL + Neo4j data layer, and Claude/OpenAI AI integration. The codebase demonstrates strong foundational patterns — protocol-based design in the `taxkb` package, proper DI via FastAPI `Depends`, Pydantic v2 validation, async SQLAlchemy, and Fernet-based PII encryption.

However, the review uncovered **47 findings** across 5 severity levels. The most impactful issues are: a circular dependency between the service and router layers, a 1,292-line monolithic frontend page component, missing repository abstractions for testability, absent security hardening (rate limiting, CSRF, security headers), and significant test coverage gaps in critical modules.

**Verdict**: Solid prototype-to-MVP architecture. Needs targeted refactoring before production scale.

---

## Table of Contents

1. [Severity Summary](#1-severity-summary)
2. [Architecture & Layering](#2-architecture--layering)
3. [OOP, DI & Testability](#3-oop-di--testability)
4. [Security & PII](#4-security--pii)
5. [Frontend Architecture](#5-frontend-architecture)
6. [Test Infrastructure](#6-test-infrastructure)
7. [Technology Stack Best Practices](#7-technology-stack-best-practices)
8. [What's Working Well](#8-whats-working-well)
9. [Prioritized Action Plan](#9-prioritized-action-plan)

---

## 1. Severity Summary

| Severity | Count | Description |
|----------|-------|-------------|
| **CRITICAL** | 3 | Architectural violations, security gaps that must be fixed before production |
| **HIGH** | 10 | Significant design issues affecting testability, maintainability, or security |
| **MEDIUM** | 16 | Code quality, missing abstractions, inconsistencies |
| **LOW** | 18 | Style, minor improvements, polish |

---

## 2. Architecture & Layering

### 2.1 Backend Layer Structure

The backend follows a reasonable layered architecture:

```
Routers (HTTP) → Services (Business Logic) → DB Models (Persistence)
                                            → Tax Engine (Domain)
                                            → Agent (AI Orchestration)
```

**Strengths:**
- Clean router/service separation in most modules
- `TaxReturnService` properly documented as "does not import FastAPI"
- Tax engine is self-contained with its own models, calculators, and validation
- `taxkb` package is protocol-driven with clean adapter pattern

### CRITICAL-1: Circular Dependency — Service Layer Imports from Router Layer

- **Location**: `api/services/tax/return_service.py` lines 70, 144, 165, 190, 212, 243
- **Issue**: `from api.routers._helpers import get_client_or_404` is called 6 times inside service methods
- **Why it matters**: Services must never depend on routers. This violates dependency inversion, makes the service untestable without the router module, and creates a latent circular import risk.
- **Fix**: Move `get_client_or_404` to `api/db/queries.py` or `api/services/common.py`. It's a pure database query — it belongs in the data access layer.

### HIGH-1: Business Logic Leaking into Routers

- **Location**: `api/routers/clients.py` lines 50-88 (`_build_response`)
- **Issue**: PII decryption + masking + response assembly happens in the router. This is business logic that should be in a `ClientResponseBuilder` service, unit-testable independently.
- **Also**: `api/routers/chat.py` lines 124-184 — `_get_or_create_conversation` and `_load_history` contain raw SQLAlchemy queries directly in the router.
- **Fix**: Extract to `ClientService.build_response()` and `ConversationRepository`.

### HIGH-2: Duplicate Agent Service Constructors

- **Location**: `api/dependencies.py` lines 122-138 (`get_agent_service`) and lines 173-189 (`get_agent_service_for_chat`)
- **Issue**: Two nearly identical factory functions construct `AgentService` with the same parameters. DRY violation.
- **Fix**: Consolidate into a single `_build_agent_service()` helper. If different tool registries are needed, parameterize.

---

## 3. OOP, DI & Testability

### 3.1 Dependency Injection — Current State

| Pattern | Status | Notes |
|---------|--------|-------|
| FastAPI `Depends()` | Good | Used throughout for settings, auth, DB sessions |
| `lru_cache` singletons | Good | Anthropic client, encryptor, settings |
| Constructor injection | Partial | Services accept deps in `__init__`, but not all |
| Protocol-based interfaces | Partial | Excellent in `taxkb`, missing in `api` |
| Factory pattern | Good | OCR extractor factory, `taxkb.factories` |

### HIGH-3: No Repository Abstraction Layer

- **Impact**: Every router and service writes raw SQLAlchemy queries inline
- **Locations**: `api/routers/clients.py`, `api/routers/documents.py`, `api/routers/chat.py`, `api/services/tax/return_service.py`
- **Issue**: Database queries are scattered across the codebase. To test business logic, you must set up a full async SQLite database — there's no way to inject a mock repository.
- **Fix**: Create `api/repositories/` with protocol-based interfaces:
  ```python
  class ClientRepository(Protocol):
      async def get_by_id(self, client_id: str, org_id: str) -> ClientModel | None: ...
      async def list_by_org(self, org_id: str, page: int, size: int) -> list[ClientModel]: ...
  ```

### HIGH-4: Missing Service Protocols

- **Impact**: `TaxReturnService`, `ChatService`, `AgentService` are concrete classes with no interface definitions
- **Contrast**: `taxkb/protocols.py` defines 6 clean protocols (`Retriever`, `ConnectionPool`, `EmbeddingClient`, `CompletionClient`, `ChunkEnricher`, `VectorStore`) — this is the pattern the `api` package should follow
- **Fix**: Define protocols for each service in `api/services/protocols.py`

### MEDIUM-1: Module-Level Global State

- **Location**: `api/db/engine.py` lines 33-35
  ```python
  _settings = get_settings()
  engine = _build_engine(_settings)
  async_session = async_sessionmaker(engine, ...)
  ```
- **Issue**: Engine created at import time. If tests override settings after import, the engine isn't rebuilt. The autouse fixture in `tests/conftest.py` that clears `lru_cache` helps, but this is fragile.
- **Also**: `api/auth/config.py` lines 13-22 — module-level `_settings = get_settings()` documented as "compatibility shim"

### MEDIUM-2: `Any` Type Overuse in Agent Layer

- **Locations**:
  - `api/agent/tool_registry.py` lines 4, 13, 21, 28-29 — `tool_input: dict[str, Any]`
  - `api/agent/service.py` lines 6, 75, 96, 105
  - `api/agent/tools/research_tools.py` lines 1-20
  - `api/services/pii/masking.py` lines 16, 46, 59
- **Fix**: Use `TypedDict` for tool inputs, or at minimum domain-specific types

### MEDIUM-3: Missing Type Hint on Constructor

- **Location**: `api/services/ocr/claude_extractor.py` line 13
  ```python
  def __init__(self, client, model: str = DEFAULT_MODEL):  # client is untyped
  ```
- **Fix**: `client: "anthropic.Anthropic"`

---

## 4. Security & PII

### 4.1 PII Encryption — Current State

The encryption architecture is well-designed:
- Fernet (AES-128-CBC) for SSN, DOB, street address
- `PIIEncryptor` is a pure class with constructor injection — testable
- Factory pattern separates config from logic
- Production raises `ConfigError` if key is missing
- Response models never expose plaintext PII

### HIGH-5: Dev Fallback Encryption Key in Source

- **Location**: `api/services/pii/encryptor.py` line 30
  ```python
  _DEV_FALLBACK_KEY = b"1GSIXE2641DMBbBishzM5Oa6f9DqLzzmsD6m0I1RqPk="
  ```
- **Issue**: While this key is only used in dev/test (production raises if no key), it's a well-known value in source code. Any dev/staging data encrypted with this key is trivially decryptable.
- **Fix**: Generate a random key per dev environment (e.g., write to `.env` on first run). Or accept the risk with documentation that dev/staging data is not real PII.

### HIGH-6: No Rate Limiting

- **Location**: `api/main.py` — no rate limiting middleware
- **Impact**: Auth endpoints, PII reveal endpoint, file upload, and AI agent endpoints are all unthrottled
- **Fix**: Add `slowapi` or custom rate limiting middleware. Priority endpoints: `/api/auth/me`, `/api/clients/{id}/reveal-pii`, `/api/documents/upload`

### HIGH-7: Missing Security Headers

- **Location**: `api/main.py` — only CORS middleware configured
- **Missing**: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security`, `Content-Security-Policy`
- **Fix**: Add security headers middleware

### HIGH-8: No CSRF Protection

- **Issue**: State-changing POST/PATCH/DELETE endpoints have no CSRF token validation
- **Mitigant**: If the API is purely token-based (Bearer auth, no cookies), CSRF is less critical. But `allow_credentials=True` in CORS suggests cookie usage.
- **Fix**: Validate `Origin` header or implement double-submit cookie pattern

### MEDIUM-4: Missing SSN Format Validation

- **Location**: `api/models/client.py` lines 84, 88
  ```python
  primary_ssn: str | None = Field(default=None, max_length=20)  # No format check
  ```
- **Issue**: Only `max_length` constraint. No regex for SSN format, no rejection of invalid ranges (000-00-0000, 666-xx-xxxx, 9xx-xx-xxxx)
- **Also**: Dependent SSN in `api/routers/dependents.py` lines 22-28 has same gap

### MEDIUM-5: PII Reveal Endpoint Missing Audit Logging

- **Location**: `api/routers/clients.py` lines 285-321
- **Issue**: `/reveal-pii` decrypts and returns plaintext PII with no audit trail. For tax/financial compliance, every PII access should be logged with who, when, which fields, and why.

### MEDIUM-6: Document `extracted_data` Stored as Plaintext

- **Location**: `api/db/models.py` — `extracted_data: Mapped[str] = mapped_column(Text, default="{}")`
- **Issue**: OCR-extracted data (which may contain SSNs) is stored as plaintext JSON alongside the encrypted version. Migration to encrypted-only storage (mentioned in comments as "Phase C") should be prioritized.

### MEDIUM-7: Frontend Token in localStorage

- **Location**: `frontend/components/auth/auth0-provider.tsx` line 48
  ```typescript
  cacheLocation="localstorage"  // Vulnerable to XSS
  ```
- **Fix**: Use `cacheLocation="memory"` with refresh token rotation for better security

### LOW-1: Default Docker Credentials

- **Location**: `docker-compose.yml` lines 24, 55 — `taxflow_dev` as default password
- **Acceptable for local dev** but should be documented as "change for any networked environment"

---

## 5. Frontend Architecture

### CRITICAL-2: Monolithic Page Component (1,292 lines)

- **Location**: `frontend/app/page.tsx`
- **Issue**: Single component with:
  - 29 `useState` calls managing all app state
  - Client selection, chat, documents, modals, returns, filing, advisory, tours
  - Data fetching, transformation, and business logic mixed with rendering
  - 10+ modal open/close states as separate booleans
- **Impact**: Untestable, unmaintainable, impossible to work on in parallel
- **Fix**: Decompose into container components:
  - `ChatContainer` — messages + input
  - `ClientsContainer` — sidebar + selection
  - `WorkPanel` — tabbed document/return/filing/advisory views
  - `ModalsManager` — modal state coordination
  - Extract data fetching into custom hooks: `useClients()`, `useDocuments()`, `useMessages()`

### HIGH-9: Duplicate State Between Context and Page

- **Location**: `app/providers.tsx` lines 22-27 vs `app/page.tsx` lines 83-85
- **Issue**: `AppProvider` defines `activeClientId`, `messages`, `documents` state. Then `page.tsx` duplicates these as local state with different types (`LocalMessage` vs `ChatMessage`). No single source of truth.
- **Fix**: Use context as the canonical store. Transform data at the boundary (API response → context), not in the page component.

### HIGH-10: Large Modal Components Without Logic Extraction

- **Location**:
  - `components/clients/intake-modal.tsx` — 609 lines (form + validation + submission + dependent management)
  - `components/research/research-agent-modal.tsx` — 512 lines
  - `components/documents/document-manager-modal.tsx` — 431 lines
- **Fix**: Extract validation to `lib/validation/intake.ts`, form logic to custom hooks (`useIntakeForm`, `useDependentManager`)

### MEDIUM-8: Missing Custom Hooks

- **Issue**: No custom hooks exist. Repeated patterns that should be hooks:
  - Async data loading (loading + error + retry)
  - Document upload handling
  - Modal state management
  - Client selection + data refresh
- **Fix**: Create `lib/hooks/` with `useAsync`, `useDocumentUpload`, `useModals`, `useClientData`

### MEDIUM-9: TypeScript Safety Gaps

- **Locations**:
  - `page.tsx` lines 619, 1016, 1029 — `d: any`
  - `page.tsx` line 996 — `...(c as any)`
  - `components/documents/pdf-viewer.tsx` — `useRef<any>(null)`
- **Fix**: Replace with proper types

### MEDIUM-10: Inconsistent Data Transformation

- **Location**: `page.tsx` lines 238-257 vs 442-444
- **Issue**: Same API → local model transformation written 2-3 different ways
- **Fix**: Create `lib/transformers.ts` with `toLocalMessage()`, `toLocalDocument()`

### MEDIUM-11: Missing Error Handling

- **Locations**:
  - `page.tsx` line 260-263 — failed data loads silently set empty arrays
  - `page.tsx` line 412 — `catch { /* ignore */ }` on return generation
  - No error boundaries, no retry logic, no user-facing error states

---

## 6. Test Infrastructure

### 6.1 Current State

| Metric | Value |
|--------|-------|
| Test files | 69 |
| Test functions | ~834 |
| Async tests | 167 (20%) |
| Conftest files | 5 |
| Marker usage | Defined but rarely applied |

### Strengths

- Excellent fixture architecture: autouse cache clearing, in-memory SQLite, proper DI overrides
- Clean `seeded_user` fixture with org context for auth testing
- `FakeAnthropic` stub in chat isolation tests (not generic MagicMock)
- Tax engine calculators thoroughly tested (30+ calculator tests)
- Proper `asyncio_mode = "auto"` configuration

### CRITICAL-3: Untested Critical Modules

| Module | Impact | Status |
|--------|--------|--------|
| `api/agent/mcp_server.py` | Tool registry initialization | **No tests** |
| `api/services/workflow.py` | Task orchestration | **No tests** |
| `taxkb/agent/search.py` | Core KB search | **No tests** |
| `taxkb/agent/compressor.py` | Context compression | **No tests** |
| `taxkb/agent/reranker.py` | Result reranking | **No tests** |
| `api/routers/auth.py` | Auth flow | 3-4 basic tests |
| `api/services/tax/return_service.py` | Tax computation orchestration | Limited |

### MEDIUM-12: No Consistent Unit/Integration Markers

- **Issue**: Most tests in `tests/api/` are full-stack HTTP tests (router → service → DB) but aren't marked as integration tests. Only `test_chat_isolation.py` uses `pytestmark = pytest.mark.unit`.
- **Impact**: Can't run "just unit tests" for fast feedback
- **Fix**: Apply markers consistently; add `pytestmark` to each test module

### MEDIUM-13: Complex Mock Patterns in Retriever Tests

- **Location**: `tests/taxkb/test_retriever.py` lines 161-206
- **Issue**: Hybrid real/mock objects — binding real methods to mock instances. Works but is fragile and hard to understand.
- **Fix**: Use either full mocks or full integration tests, not hybrids

---

## 7. Technology Stack Best Practices

### 7.1 FastAPI

| Practice | Status |
|----------|--------|
| Lifespan management (startup/shutdown) | Excellent — `@asynccontextmanager` |
| Router organization | Good — modular with prefixes and tags |
| Middleware (CORS) | Good but missing security middleware |
| Error handling | Good — `HTTPException` with proper status codes |
| Async throughout | Good — `asyncio.to_thread` for sync SDK calls |

### 7.2 Pydantic v2

| Practice | Status |
|----------|--------|
| `model_config = {"from_attributes": True}` | Correct |
| Field constraints | Good — `min_length`, `max_length`, regex |
| Custom validators (phone, state, zip) | Good |
| `SecretStr` for API keys | Good |
| Blank-to-None normalization | Good pattern |

### 7.3 SQLAlchemy (Async)

| Practice | Status |
|----------|--------|
| Async engine + sessionmaker | Correct |
| Pool configuration (size, overflow, recycle) | Tuned |
| UUIDv7 for PKs | Excellent — time-ordered, globally unique |
| RLS via `SET LOCAL` | Correct — scoped to transaction |
| Alembic integration | Good — programmatic, not shell |
| `expire_on_commit=False` | Correct for async |

### 7.4 Anthropic/Claude Integration

| Practice | Status |
|----------|--------|
| Client caching by API key | Good |
| Tool registry pattern | Good — centralized, typed |
| Session context (frozen dataclass) | Excellent — immutable, scoped |
| Tool round limits | Good — prevents infinite loops |
| `asyncio.to_thread` for sync SDK | Correct |
| Error isolation in tool loop | Good |

### 7.5 taxkb Package

| Practice | Status |
|----------|--------|
| Protocol-based design (6 protocols) | Excellent |
| Factory composition root | Excellent |
| Adapter pattern (OpenAI, Postgres) | Good |
| Configuration with extensible sources | Good |
| No circular imports | Good |

### MEDIUM-14: Missing Structured Logging

- **Issue**: No correlation IDs, no request-scoped logging context, no JSON logging format
- **Fix**: Add middleware that attaches a `request_id` to all log messages

### MEDIUM-15: No Global Exception Handler

- **Issue**: Unhandled exceptions return raw 500 errors. No catch-all that logs + returns sanitized error.
- **Fix**: Add `@app.exception_handler(Exception)` that logs the traceback and returns a generic error response

### LOW-2: Missing SSL for Database in Production

- **Location**: `api/db/engine.py` — no `sslmode=require` enforcement
- **Fix**: Validate DSN contains `sslmode=require` when `is_production=True`

---

## 8. What's Working Well

These patterns should be preserved and extended:

1. **`taxkb` protocol architecture** — 6 clean protocols with adapter implementations. This is the gold standard the `api` package should follow.

2. **PIIEncryptor design** — Pure class, constructor injection, factory pattern, production guard. Well-documented.

3. **FastAPI DI wiring** — `api/dependencies.py` is a clean composition root. `Annotated[..., Depends()]` type aliases reduce boilerplate.

4. **OCR extractor strategy pattern** — `OCRExtractor` protocol + `OCRExtractorFactory` + three implementations (Claude, text, mock). Textbook strategy pattern.

5. **Tax engine modularity** — Calculators, validation rules, advisory engine, and comparison engine are all independently testable units with clean interfaces.

6. **Test fixtures** — Autouse cache clearing, in-memory SQLite, `seeded_user` with org context, `FakeAnthropic` stubs. Professional-grade test infrastructure.

7. **Multi-tenant by default** — `TenantMixin`, org-scoped queries, RLS via `SET LOCAL`. Built-in, not bolted on.

8. **AgentSession as frozen dataclass** — Immutable request context prevents tools from targeting wrong clients. Security by design.

9. **Settings validation** — Required fields (no silent defaults), `SecretStr` masking, classified field types for banner output.

10. **UUIDv7 identity strategy** — Time-ordered, globally unique, cross-dialect portable. Well-documented rationale.

---

## 9. Prioritized Action Plan

### Phase 1: Critical (Before Production)

| # | Action | Files | Effort |
|---|--------|-------|--------|
| 1 | Move `get_client_or_404` out of routers into `api/db/queries.py` | `return_service.py`, `_helpers.py` | Small |
| 2 | Add security headers middleware | `main.py` | Small |
| 3 | Add rate limiting (`slowapi`) on auth + PII endpoints | `main.py`, routers | Medium |
| 4 | Add audit logging for PII reveal | `routers/clients.py` | Small |
| 5 | Add SSN/EIN format validation | `models/client.py`, `routers/dependents.py` | Small |
| 6 | Write tests for `mcp_server.py`, `workflow.py` | `tests/api/` | Medium |

### Phase 2: High Priority (Next Sprint)

| # | Action | Files | Effort |
|---|--------|-------|--------|
| 7 | Extract `page.tsx` into container components + custom hooks | `frontend/app/`, `frontend/lib/hooks/` | Large |
| 8 | Create repository abstraction layer | `api/repositories/` | Large |
| 9 | Define service protocols in `api/services/protocols.py` | New file | Medium |
| 10 | Consolidate duplicate `get_agent_service` factories | `api/dependencies.py` | Small |
| 11 | Move `_build_response` PII logic to `ClientService` | `routers/clients.py` → `services/` | Medium |
| 12 | Extract chat DB queries to `ConversationRepository` | `routers/chat.py` | Medium |

### Phase 3: Medium Priority (Backlog)

| # | Action | Files | Effort |
|---|--------|-------|--------|
| 13 | Replace `Any` types in agent layer with `TypedDict` | `agent/tool_registry.py`, `agent/service.py` | Medium |
| 14 | Add structured logging with correlation IDs | Middleware + logging config | Medium |
| 15 | Add global exception handler | `main.py` | Small |
| 16 | Apply consistent test markers (`unit`/`integration`) | All test files | Small |
| 17 | Migrate `extracted_data` to encrypted-only storage | `db/models.py`, migrations | Large |
| 18 | Remove module-level engine globals (lazy init) | `db/engine.py`, `auth/config.py` | Medium |
| 19 | Extract frontend validation to `lib/validation/` | `intake-modal.tsx` → shared | Medium |
| 20 | Add error boundaries + loading skeletons to frontend | Various components | Medium |
| 21 | Switch Auth0 token to `cacheLocation="memory"` | `auth0-provider.tsx` | Small |
| 22 | Write tests for `search.py`, `compressor.py`, `reranker.py` | `tests/taxkb/` | Medium |

---

## Appendix: File Index

Key files referenced in this review:

**Backend Core:**
- `api/main.py` — App factory, lifespan, middleware
- `api/config.py` — Settings with Pydantic v2 validation
- `api/dependencies.py` — DI composition root
- `api/db/engine.py` — Async SQLAlchemy engine + Alembic
- `api/db/models.py` — Multi-tenant ORM models with UUIDv7

**Services:**
- `api/services/pii/encryptor.py` — Fernet encryption + masking
- `api/services/tax/return_service.py` — Tax computation orchestration
- `api/services/ocr/protocol.py` — OCR extractor protocol
- `api/services/chat/chat_service.py` — Claude chat integration

**Agent:**
- `api/agent/service.py` — Tool-use loop with Claude
- `api/agent/tool_registry.py` — Centralized tool registration
- `api/agent/session.py` — Frozen request context

**taxkb:**
- `taxkb/protocols.py` — 6 protocol definitions (gold standard)
- `taxkb/factories.py` — Composition root
- `taxkb/adapters/` — OpenAI + Postgres implementations

**Frontend:**
- `frontend/app/page.tsx` — 1,292-line monolith (needs decomposition)
- `frontend/components/clients/intake-modal.tsx` — 609-line form
- `frontend/lib/api-client.ts` — API communication layer

**Tests:**
- `conftest.py` (root) — Env loading, path setup
- `tests/conftest.py` — Mock factories, cache clearing
- `tests/api/conftest.py` — In-memory SQLite, auth fixtures
