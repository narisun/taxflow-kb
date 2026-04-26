# Tax Brain Full-Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production CPA tax preparation platform with a Next.js frontend (Apple design system), FastAPI backend (REST + SSE streaming), OCR document pipeline, and TaxBrain RAG integration — all with clean separation of concerns and full testability.

**Architecture:** Three-tier: Next.js 14 App Router frontend communicates with a FastAPI backend via REST/SSE. The backend exposes domain services (clients, documents, tax returns, chat) that delegate to TaxBrain for AI queries, an OCR pipeline for document extraction, and a calc engine for tax computation. All state lives in PostgreSQL. The frontend is a three-panel layout (client sidebar, chat center, work panel) following Apple's design system from DESIGN.md.

**Tech Stack:**
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, Radix UI primitives
- **Backend:** FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), PostgreSQL
- **Streaming:** Server-Sent Events (SSE) for chat responses
- **OCR:** pdf2image + Tesseract (self-hosted) or OpenAI Vision API
- **Testing:** Vitest + Testing Library (frontend), pytest + httpx (backend), Playwright (e2e)

---

## Subsystem Breakdown

This is a large project spanning 5 independent subsystems. Each can be developed and tested independently:

| # | Subsystem | Scope | Dependency |
|---|-----------|-------|------------|
| **Plan A** | Backend API Layer | FastAPI app, domain models, REST endpoints, SSE streaming | Existing `taxkb` package |
| **Plan B** | Design System & Shell | Tailwind config, Apple tokens, layout shell, shared components | None |
| **Plan C** | Frontend Features | Client management, chat, document panel, dashboard | Plan A + B |
| **Plan D** | OCR & Document Pipeline | Upload, extraction, confidence scoring, form rendering | Plan A |
| **Plan E** | Tax Calc Engine & Filing | 1040 assembly, deduction analysis, e-file preparation | Plan A |

**Recommendation:** Start with Plan A (backend) and Plan B (design system) in parallel since they have no dependencies on each other. Then Plans C/D/E can proceed once A+B are stable.

---

## Plan A: Backend API Layer

### A.1 File Structure

```
api/
├── __init__.py
├── main.py                    # FastAPI app factory, CORS, lifespan
├── config.py                  # API-specific settings (port, origins, etc.)
├── dependencies.py            # FastAPI Depends() providers (pool, agent, etc.)
├── models/
│   ├── __init__.py
│   ├── client.py              # Client, TaxYear Pydantic schemas
│   ├── document.py            # Document, ExtractedField, OCRResult schemas
│   ├── chat.py                # ChatMessage, ChatEvent schemas
│   ├── tax_return.py          # TaxReturn, ReturnLine schemas
│   └── common.py              # Pagination, ErrorResponse, etc.
├── routers/
│   ├── __init__.py
│   ├── clients.py             # CRUD /api/clients
│   ├── documents.py           # Upload, list, approve /api/clients/{id}/documents
│   ├── chat.py                # POST message, GET /stream SSE
│   ├── tax_returns.py         # Draft, preview, approve /api/clients/{id}/returns
│   └── health.py              # GET /health
├── services/
│   ├── __init__.py
│   ├── client_service.py      # Client business logic
│   ├── document_service.py    # Document + OCR orchestration
│   ├── chat_service.py        # Chat + TaxBrain integration
│   ├── tax_return_service.py  # Return assembly + calc engine
│   └── audit_service.py       # Audit trail logging
├── repositories/
│   ├── __init__.py
│   ├── client_repo.py         # Client DB access
│   ├── document_repo.py       # Document DB access
│   ├── chat_repo.py           # Chat history DB access
│   └── tax_return_repo.py     # Return DB access
└── db/
    ├── __init__.py
    ├── engine.py              # Async SQLAlchemy engine + session factory
    ├── models.py              # SQLAlchemy ORM models (clients, documents, etc.)
    └── migrations/            # Alembic migrations
        ├── env.py
        └── versions/
tests/
├── api/
│   ├── conftest.py            # Test client, DB fixtures
│   ├── test_clients.py
│   ├── test_documents.py
│   ├── test_chat.py
│   └── test_tax_returns.py
```

**Key design decisions:**
- **Router → Service → Repository** layering. Routers handle HTTP, services handle business logic, repositories handle DB queries.
- **Services receive dependencies via FastAPI's `Depends()`** — no global singletons.
- **Chat service wraps TaxBrain agent** — the `taxkb` package is consumed as a library, not modified.
- **All actions logged to audit trail** — the chat history IS the audit trail.

### A.2 Tasks

#### Task A.1: FastAPI App Skeleton

**Files:**
- Create: `api/__init__.py`, `api/main.py`, `api/config.py`, `api/dependencies.py`
- Create: `api/routers/__init__.py`, `api/routers/health.py`
- Create: `tests/api/conftest.py`, `tests/api/test_health.py`
- Create: `requirements-api.txt`

- [ ] **Step 1: Write the health endpoint test**

```python
# tests/api/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport

from api.main import create_app

@pytest.fixture
def app():
    return create_app()

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_health.py -v`
Expected: FAIL — no module `api.main`

- [ ] **Step 3: Create requirements-api.txt**

```
fastapi>=0.115
uvicorn[standard]>=0.32
httpx>=0.27
pydantic>=2.10
pydantic-settings>=2.6
sqlalchemy[asyncio]>=2.0
asyncpg>=0.30
alembic>=1.14
python-multipart>=0.0.12
sse-starlette>=2.0
pytest-asyncio>=0.24
```

- [ ] **Step 4: Implement app factory and health endpoint**

```python
# api/main.py
"""FastAPI application factory for Tax Brain API."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize DB pool, TaxBrain agent
    yield
    # Shutdown: close pools

def create_app() -> FastAPI:
    app = FastAPI(
        title="Tax Brain API",
        description="CPA tax preparation platform backend",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from api.routers import health
    app.include_router(health.router)
    return app
```

```python
# api/routers/health.py
from fastapi import APIRouter

router = APIRouter(tags=["system"])

@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "tax-brain-api"}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/api/test_health.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add api/ tests/api/ requirements-api.txt
git commit -m "feat(api): FastAPI app skeleton with health endpoint"
```

#### Task A.2: Database Models and Client CRUD

**Files:**
- Create: `api/db/__init__.py`, `api/db/engine.py`, `api/db/models.py`
- Create: `api/models/common.py`, `api/models/client.py`
- Create: `api/repositories/client_repo.py`
- Create: `api/services/client_service.py`
- Create: `api/routers/clients.py`
- Create: `tests/api/test_clients.py`

- [ ] **Step 1: Write client list test**

```python
# tests/api/test_clients.py
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import create_app

@pytest.fixture
def app():
    return create_app()

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_list_clients_empty(client):
    resp = await client.get("/api/clients")
    assert resp.status_code == 200
    assert resp.json()["items"] == []

@pytest.mark.asyncio
async def test_create_and_get_client(client):
    create_resp = await client.post("/api/clients", json={
        "name": "Smith Family",
        "filing_status": "mfj",
        "tax_year": 2024,
        "dependents": 2,
    })
    assert create_resp.status_code == 201
    client_id = create_resp.json()["id"]

    get_resp = await client.get(f"/api/clients/{client_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Smith Family"
```

- [ ] **Step 2: Define SQLAlchemy ORM models**

```python
# api/db/models.py
"""SQLAlchemy ORM models for Tax Brain platform."""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, Float, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum

class Base(DeclarativeBase):
    pass

class FilingStatus(str, enum.Enum):
    SINGLE = "single"
    MFJ = "mfj"
    MFS = "mfs"
    HOH = "hoh"
    QW = "qw"

class WorkflowStep(str, enum.Enum):
    INTAKE = "intake"
    EXTRACTION = "extraction"
    TAX_PROFILE = "tax_profile"
    PREPARATION = "preparation"
    REVIEW = "review"
    FILED = "filed"

class ClientModel(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    filing_status: Mapped[str] = mapped_column(String(10))
    tax_year: Mapped[int] = mapped_column(Integer)
    dependents: Mapped[int] = mapped_column(Integer, default=0)
    workflow_step: Mapped[str] = mapped_column(String(20), default="intake")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    documents: Mapped[list["DocumentModel"]] = relationship(back_populates="client")
    chat_messages: Mapped[list["ChatMessageModel"]] = relationship(back_populates="client")

class DocumentModel(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    form_type: Mapped[str] = mapped_column(String(20))  # "W-2", "1099-INT", etc.
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, review, approved
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    extracted_data: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    file_path: Mapped[str] = mapped_column(String(500), default="")
    flags: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of flag objects
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    client: Mapped["ClientModel"] = relationship(back_populates="documents")

class ChatMessageModel(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    role: Mapped[str] = mapped_column(String(10))  # "user" | "assistant" | "system"
    content: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(30), default="text")  # "text" | "card" | "action_log"
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    client: Mapped["ClientModel"] = relationship(back_populates="chat_messages")
```

- [ ] **Step 3: Implement client repository, service, router**

```python
# api/repositories/client_repo.py
"""Client data access layer."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.db.models import ClientModel

class ClientRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self) -> list[ClientModel]:
        result = await self._session.execute(select(ClientModel).order_by(ClientModel.name))
        return list(result.scalars().all())

    async def get_by_id(self, client_id: int) -> ClientModel | None:
        return await self._session.get(ClientModel, client_id)

    async def create(self, **kwargs) -> ClientModel:
        client = ClientModel(**kwargs)
        self._session.add(client)
        await self._session.flush()
        return client
```

```python
# api/models/client.py
"""Client API schemas."""
from pydantic import BaseModel
from datetime import datetime

class ClientCreate(BaseModel):
    name: str
    filing_status: str = "single"
    tax_year: int = 2024
    dependents: int = 0

class ClientResponse(BaseModel):
    id: int
    name: str
    filing_status: str
    tax_year: int
    dependents: int
    workflow_step: str
    created_at: datetime

    model_config = {"from_attributes": True}

class ClientListResponse(BaseModel):
    items: list[ClientResponse]
    total: int
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/api/test_clients.py -v`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(api): client CRUD with repository pattern"
```

#### Task A.3: Chat Endpoint with SSE Streaming

**Files:**
- Create: `api/models/chat.py`
- Create: `api/services/chat_service.py`
- Create: `api/routers/chat.py`
- Create: `tests/api/test_chat.py`

- [ ] **Step 1: Write chat message test**

```python
# tests/api/test_chat.py
@pytest.mark.asyncio
async def test_post_message_returns_response(client):
    # Create a client first
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    client_id = c.json()["id"]

    resp = await client.post(f"/api/clients/{client_id}/chat", json={
        "content": "What is the standard deduction for MFJ?",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "assistant"
    assert len(body["content"]) > 0

@pytest.mark.asyncio
async def test_chat_history_persists(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    client_id = c.json()["id"]

    await client.post(f"/api/clients/{client_id}/chat", json={"content": "Hello"})
    history = await client.get(f"/api/clients/{client_id}/chat")
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert len(messages) >= 2  # user + assistant
```

- [ ] **Step 2: Implement chat service wrapping TaxBrain**

```python
# api/services/chat_service.py
"""Chat service — bridges user messages to TaxBrain agent."""
from taxkb.agent.classifier import classify_query

class ChatService:
    def __init__(self, agent, session):
        self._agent = agent
        self._session = session

    async def handle_message(self, client_id: int, content: str) -> dict:
        # Classify to determine if this needs TaxBrain or is a simple action
        meta = classify_query(content)

        # Query TaxBrain
        result = self._agent.query(content)

        # Persist both user and assistant messages
        # ... (repository calls)

        return {
            "role": "assistant",
            "content": result.answer,
            "sources": result.sources,
            "query_intent": result.query_intent,
        }
```

- [ ] **Step 3: Implement SSE streaming endpoint**

```python
# api/routers/chat.py
from sse_starlette.sse import EventSourceResponse

@router.get("/api/clients/{client_id}/chat/stream")
async def stream_chat(client_id: int, q: str):
    """SSE endpoint for streaming AI responses."""
    async def event_generator():
        yield {"event": "start", "data": "{}"}
        # Stream chunks from TaxBrain
        result = agent.query(q)
        yield {"event": "message", "data": json.dumps({"content": result.answer})}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())
```

- [ ] **Step 4: Run tests, commit**

#### Task A.4: Document Upload and Extraction Endpoints

**Files:**
- Create: `api/models/document.py`
- Create: `api/services/document_service.py`
- Create: `api/routers/documents.py`
- Create: `tests/api/test_documents.py`

- [ ] **Step 1: Write document upload test**

```python
# tests/api/test_documents.py
@pytest.mark.asyncio
async def test_upload_document(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    client_id = c.json()["id"]

    # Simulate file upload
    resp = await client.post(
        f"/api/clients/{client_id}/documents",
        files={"file": ("w2.pdf", b"fake-pdf-content", "application/pdf")},
        data={"form_type": "W-2"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["form_type"] == "W-2"
    assert body["status"] == "pending"
```

- [ ] **Step 2: Implement document service with OCR stub**

```python
# api/services/document_service.py
"""Document upload and OCR extraction service."""

class DocumentService:
    def __init__(self, session, ocr_client=None):
        self._session = session
        self._ocr = ocr_client  # Injected — None in tests

    async def upload(self, client_id: int, file, form_type: str) -> dict:
        # Save file to storage
        file_path = await self._save_file(file)
        # Create DB record
        doc = await self._repo.create(
            client_id=client_id, form_type=form_type,
            file_path=file_path, status="pending",
        )
        # Trigger async OCR extraction (if ocr_client available)
        if self._ocr:
            extracted = await self._ocr.extract(file_path, form_type)
            doc.extracted_data = json.dumps(extracted.fields)
            doc.confidence = extracted.overall_confidence
            doc.status = "review" if extracted.has_flags else "approved"
        return doc

    async def approve(self, doc_id: int) -> dict:
        # Mark document as approved, log to audit trail
        ...

    async def get_extracted_fields(self, doc_id: int) -> list[dict]:
        # Return extracted fields with confidence scores
        ...
```

- [ ] **Step 3: Run tests, commit**

#### Task A.5: Tax Return Preview Endpoint

**Files:**
- Create: `api/models/tax_return.py`
- Create: `api/services/tax_return_service.py`
- Create: `api/routers/tax_returns.py`
- Create: `tests/api/test_tax_returns.py`

- [ ] **Step 1: Write return preview test**

```python
@pytest.mark.asyncio
async def test_generate_draft_return(client):
    # Setup: client with approved documents
    c = await client.post("/api/clients", json={
        "name": "Smith Family", "filing_status": "mfj", "tax_year": 2024,
    })
    client_id = c.json()["id"]

    resp = await client.post(f"/api/clients/{client_id}/returns/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert "lines" in body
    assert any(l["number"] == "1a" for l in body["lines"])
```

- [ ] **Step 2: Implement return service with calc engine stub**

- [ ] **Step 3: Run tests, commit**

---

## Plan B: Design System & Frontend Shell

### B.1 File Structure

```
frontend/
├── package.json
├── tsconfig.json
├── tailwind.config.ts         # Apple design tokens
├── next.config.ts
├── app/
│   ├── layout.tsx             # Root layout with font loading
│   ├── page.tsx               # Main three-panel layout
│   ├── globals.css            # CSS custom properties from DESIGN.md
│   └── providers.tsx          # React context providers
├── components/
│   ├── ui/                    # Design system primitives
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── badge.tsx
│   │   ├── input.tsx
│   │   ├── modal.tsx
│   │   ├── tabs.tsx
│   │   ├── avatar.tsx
│   │   ├── progress.tsx
│   │   └── tooltip.tsx
│   ├── layout/
│   │   ├── top-bar.tsx        # Glass nav bar (Apple style)
│   │   ├── client-sidebar.tsx # Left panel
│   │   ├── chat-panel.tsx     # Center panel
│   │   ├── work-panel.tsx     # Right panel
│   │   └── three-panel.tsx    # Layout orchestrator
│   ├── chat/
│   │   ├── message-list.tsx
│   │   ├── message-bubble.tsx
│   │   ├── chat-input.tsx
│   │   ├── ai-card.tsx        # Tax profile / data cards in chat
│   │   ├── action-chips.tsx   # Suggested action buttons
│   │   └── typing-indicator.tsx
│   ├── clients/
│   │   ├── client-list.tsx
│   │   ├── client-item.tsx
│   │   ├── client-search.tsx
│   │   └── workflow-stepper.tsx
│   ├── documents/
│   │   ├── document-list.tsx
│   │   ├── document-card.tsx
│   │   ├── flag-banner.tsx
│   │   ├── missing-doc-alert.tsx
│   │   └── document-viewer-modal.tsx
│   ├── forms/                 # IRS form renderers
│   │   ├── form-renderer.tsx  # Dynamic form factory
│   │   ├── w2-form.tsx
│   │   ├── form-1099-int.tsx
│   │   ├── form-1099-b.tsx
│   │   ├── form-1098.tsx
│   │   ├── schedule-k1.tsx
│   │   ├── form-1040.tsx
│   │   └── field-editor.tsx   # Editable field with confidence
│   ├── returns/
│   │   ├── return-preview.tsx
│   │   ├── return-line.tsx
│   │   └── refund-summary.tsx
│   └── dashboard/
│       ├── dashboard.tsx
│       ├── metrics-row.tsx
│       └── kanban-board.tsx
├── lib/
│   ├── api-client.ts          # Typed fetch wrapper for backend
│   ├── use-sse.ts             # SSE hook for streaming chat
│   └── types.ts               # Shared TypeScript types
└── __tests__/
    ├── components/
    │   ├── button.test.tsx
    │   ├── chat-input.test.tsx
    │   └── client-item.test.tsx
    └── lib/
        └── api-client.test.ts
```

### B.2 Tasks

#### Task B.1: Next.js Project with Apple Design Tokens

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/tailwind.config.ts`
- Create: `frontend/app/globals.css`, `frontend/app/layout.tsx`

- [ ] **Step 1: Initialize Next.js project**

```bash
cd /Users/admin-h26/taxflow-kb
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir=false --no-import-alias
```

- [ ] **Step 2: Configure Tailwind with Apple design tokens**

```typescript
// frontend/tailwind.config.ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        apple: {
          blue: "#0071e3",
          "link-blue": "#0066cc",
          "bright-blue": "#2997ff",
          "near-black": "#1d1d1f",
          "light-gray": "#f5f5f7",
          "surface-1": "#272729",
          "surface-2": "#262628",
        },
      },
      fontFamily: {
        display: ['"SF Pro Display"', '"Helvetica Neue"', "Helvetica", "Arial", "sans-serif"],
        body: ['"SF Pro Text"', '"Helvetica Neue"', "Helvetica", "Arial", "sans-serif"],
      },
      letterSpacing: {
        "apple-tight": "-0.374px",
        "apple-display": "-0.28px",
        "apple-caption": "-0.224px",
      },
      borderRadius: {
        pill: "980px",
      },
      boxShadow: {
        apple: "3px 5px 30px rgba(0, 0, 0, 0.22)",
      },
      backdropBlur: {
        apple: "20px",
      },
    },
  },
  plugins: [],
};
export default config;
```

- [ ] **Step 3: Create globals.css with Apple CSS custom properties**

```css
/* frontend/app/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  /* Apple palette */
  --color-bg: #f5f5f7;
  --color-surface: #ffffff;
  --color-text: #1d1d1f;
  --color-text-secondary: rgba(0, 0, 0, 0.8);
  --color-text-tertiary: rgba(0, 0, 0, 0.48);
  --color-accent: #0071e3;
  --color-link: #0066cc;
  --color-focus: #0071e3;

  /* Status colors (functional — not part of Apple's accent palette) */
  --color-success: #30d158;
  --color-warning: #ff9f0a;
  --color-error: #ff3b30;

  /* Nav glass */
  --nav-bg: rgba(0, 0, 0, 0.8);
  --nav-blur: saturate(180%) blur(20px);
}

/* SF Pro optical sizing: Display at 20px+, Text below */
@layer base {
  body {
    font-family: "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 17px;
    line-height: 1.47;
    letter-spacing: -0.374px;
    color: var(--color-text);
    background: var(--color-bg);
    -webkit-font-smoothing: antialiased;
  }

  h1, h2, h3 {
    font-family: "SF Pro Display", "Helvetica Neue", Helvetica, Arial, sans-serif;
  }
}
```

- [ ] **Step 4: Create root layout with font loading**

```tsx
// frontend/app/layout.tsx
import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Tax Brain — CPA Platform",
  description: "AI-powered tax preparation for CPAs",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-screen overflow-hidden flex flex-col">
        {children}
      </body>
    </html>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(frontend): Next.js with Apple design tokens"
```

#### Task B.2: UI Primitives (Button, Card, Badge, Input, Modal)

**Files:**
- Create: `frontend/components/ui/button.tsx` through `modal.tsx`
- Create: `frontend/__tests__/components/button.test.tsx`

- [ ] **Step 1: Write button component test**

```tsx
// frontend/__tests__/components/button.test.tsx
import { render, screen } from "@testing-library/react";
import { Button } from "@/components/ui/button";

test("renders primary button with Apple Blue", () => {
  render(<Button variant="primary">Buy</Button>);
  const btn = screen.getByRole("button", { name: "Buy" });
  expect(btn).toHaveClass("bg-apple-blue");
});

test("renders pill link variant", () => {
  render(<Button variant="pill">Learn more</Button>);
  const btn = screen.getByRole("button", { name: "Learn more" });
  expect(btn).toHaveClass("rounded-pill");
});
```

- [ ] **Step 2: Implement Button component following DESIGN.md**

```tsx
// frontend/components/ui/button.tsx
import { ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "pill" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const variants: Record<Variant, string> = {
  primary: "bg-apple-blue text-white px-4 py-2 rounded-lg text-[17px] font-normal hover:brightness-110 focus:outline-2 focus:outline-apple-blue",
  secondary: "bg-apple-near-black text-white px-4 py-2 rounded-lg text-[17px]",
  pill: "bg-transparent text-apple-link-blue border border-apple-link-blue rounded-pill px-4 py-2 text-[14px] hover:underline",
  ghost: "bg-transparent text-apple-link-blue text-[14px] hover:underline",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", className, ...props }, ref) => (
    <button ref={ref} className={cn(variants[variant], className)} {...props} />
  ),
);
Button.displayName = "Button";
```

- [ ] **Step 3: Implement remaining primitives (Card, Badge, Input, Modal, Avatar, Progress, Tabs)**

Each follows the Apple design system tokens from DESIGN.md. Cards use `#f5f5f7` background, 8px radius, no borders. Modal uses glass overlay backdrop.

- [ ] **Step 4: Run tests, commit**

#### Task B.3: Three-Panel Layout Shell

**Files:**
- Create: `frontend/components/layout/top-bar.tsx`
- Create: `frontend/components/layout/three-panel.tsx`
- Create: `frontend/app/page.tsx`

- [ ] **Step 1: Implement glass top bar (Apple nav style)**

```tsx
// frontend/components/layout/top-bar.tsx
export function TopBar() {
  return (
    <nav className="h-12 flex items-center px-4 gap-3 shrink-0 z-50"
         style={{
           background: "rgba(0, 0, 0, 0.8)",
           backdropFilter: "saturate(180%) blur(20px)",
         }}>
      <div className="w-8 h-8 bg-apple-blue rounded-md flex items-center justify-center text-white text-sm font-bold">
        T
      </div>
      <span className="text-white text-base font-semibold tracking-tight">Tax Brain</span>
      {/* Season badge, stats, deadline, avatar */}
    </nav>
  );
}
```

- [ ] **Step 2: Implement three-panel layout**

```tsx
// frontend/components/layout/three-panel.tsx
export function ThreePanel() {
  return (
    <div className="flex flex-1 overflow-hidden">
      <aside className="w-72 shrink-0 bg-apple-light-gray border-r border-gray-200 flex flex-col overflow-hidden">
        {/* Client sidebar */}
      </aside>
      <main className="flex-1 flex flex-col overflow-hidden bg-white">
        {/* Chat panel */}
      </main>
      <aside className="w-96 shrink-0 bg-white border-l border-gray-200 flex flex-col overflow-hidden">
        {/* Work panel */}
      </aside>
    </div>
  );
}
```

- [ ] **Step 3: Wire into page.tsx, verify layout renders**

- [ ] **Step 4: Commit**

---

## Plan C: Frontend Features (depends on A + B)

Detailed tasks for: client sidebar, chat interface, document panel, workflow stepper, dashboard. Each feature connects to the backend API via typed fetch client.

*(Tasks C.1–C.8 follow the same TDD pattern: write test → implement component → wire to API → commit)*

---

## Plan D: OCR & Document Pipeline (depends on A)

#### Task D.1: OCR Service Protocol

```python
# api/services/ocr/protocol.py
from typing import Protocol

class OCRExtractor(Protocol):
    async def extract(self, file_path: str, form_type: str) -> "ExtractionResult": ...

class ExtractionResult:
    fields: list[ExtractedField]
    overall_confidence: float
    has_flags: bool
    flags: list[str]

class ExtractedField:
    name: str           # "Box 1 — Wages"
    value: str          # "$112,400.00"
    confidence: float   # 0.99
    flagged: bool       # False
    flag_reason: str    # ""
```

#### Task D.2: OpenAI Vision OCR Adapter

Implements the OCR protocol using OpenAI's GPT-4o vision API to extract structured fields from tax form images.

#### Task D.3: Form-Specific Field Mappings

Maps OCR output to structured form schemas (W-2 fields, 1099-INT fields, etc.) with confidence thresholds and cross-year comparison flags.

---

## Plan E: Tax Calc Engine & Filing (depends on A)

#### Task E.1: Tax Calculator Protocol and 1040 Assembly

```python
# api/services/calc/protocol.py
class TaxCalculator(Protocol):
    def compute_return(self, profile: TaxProfile) -> TaxReturn: ...

class TaxProfile:
    filing_status: str
    tax_year: int
    wages: Decimal
    interest_income: Decimal
    # ... all income/deduction fields

class TaxReturn:
    lines: list[ReturnLine]   # [{number: "1a", label: "Total wages", value: 185200}, ...]
    total_tax: Decimal
    total_payments: Decimal
    refund_or_owed: Decimal
```

---

## Execution Order

```
Week 1:  A.1 + B.1 + B.2 (API skeleton + design system — parallel)
Week 2:  A.2 + B.3 (client CRUD + layout shell)
Week 3:  A.3 + C.1–C.3 (chat streaming + frontend chat/sidebar)
Week 4:  A.4 + D.1–D.3 (document endpoints + OCR pipeline)
Week 5:  A.5 + E.1 + C.4–C.6 (tax returns + remaining frontend features)
Week 6:  C.7–C.8 + integration testing + polish
```

Each week produces a deployable increment with working tests.
