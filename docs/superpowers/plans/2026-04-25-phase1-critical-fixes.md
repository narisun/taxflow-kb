# Phase 1: Critical Architecture Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 6 critical/high-priority issues identified in the 2026-04-25 architectural review — circular dependency, security headers, rate limiting, PII audit logging, SSN validation, and missing tests.

**Architecture:** Move shared DB queries out of the router layer into a new `api/db/queries.py` module. Add security middleware to `api/main.py`. Add field validators to Pydantic models. Write tests for untested modules.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, SQLAlchemy (async), pytest, pytest-asyncio

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `api/db/queries.py` | Shared tenant-scoped DB query helpers (moved from routers) |
| Create | `api/middleware/security_headers.py` | Security headers middleware |
| Create | `tests/api/test_security_headers.py` | Tests for security headers |
| Create | `tests/api/test_workflow.py` | Tests for workflow service |
| Create | `tests/api/test_mcp_server.py` | Tests for tool registry builder |
| Create | `tests/api/test_ssn_validation.py` | Tests for SSN/DOB validators |
| Modify | `api/routers/_helpers.py` | Re-export from new location for backwards compat |
| Modify | `api/services/tax/return_service.py` | Import from `api.db.queries` instead of `api.routers._helpers` |
| Modify | `api/main.py` | Add security headers middleware |
| Modify | `api/routers/clients.py` | Add audit logging to `reveal_pii` |
| Modify | `api/models/client.py` | Add SSN/DOB validators |
| Modify | `api/routers/dependents.py` | Add SSN/DOB validators + Field constraints |
| Modify | `api/dependencies.py` | Remove duplicate `get_agent_service_for_chat` |
| Modify | `api/routers/chat.py` | Update import to use `get_agent_service` |

---

### Task 1: Move `get_client_or_404` Out of Router Layer

Fixes CRITICAL-1: Service layer (`return_service.py`) imports from router layer (`_helpers.py`), violating dependency inversion.

**Files:**
- Create: `api/db/queries.py`
- Modify: `api/routers/_helpers.py`
- Modify: `api/services/tax/return_service.py`

- [ ] **Step 1: Create `api/db/queries.py` with the moved function**

```python
"""Tenant-scoped DB query helpers.

Shared between routers and services — lives in the data-access layer so
neither routers nor services create a circular import.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import ClientModel
from api.auth.models import UserModel


async def get_client_or_404(
    client_id: str, session: AsyncSession, user: UserModel
) -> ClientModel:
    """Load a client scoped to the user's org, or raise 404."""
    result = await session.execute(
        select(ClientModel).where(
            ClientModel.id == client_id,
            ClientModel.org_id == user.org_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client
```

- [ ] **Step 2: Update `api/routers/_helpers.py` to re-export from new location**

Replace the entire file with:

```python
"""Shared router helpers.

The canonical implementation of :func:`get_client_or_404` now lives in
:mod:`api.db.queries` (data-access layer). This module re-exports it so
existing router imports keep working without a mass-rename.
"""
from api.db.queries import get_client_or_404  # noqa: F401
```

- [ ] **Step 3: Update all 6 imports in `api/services/tax/return_service.py`**

Replace every occurrence of:
```python
from api.routers._helpers import get_client_or_404
```
with:
```python
from api.db.queries import get_client_or_404
```

These are inline imports at lines 70, 144, 165, 190, 212, 243. Change each one. The inline import pattern stays (it avoids top-level circular imports in the module).

- [ ] **Step 4: Run existing tests to confirm nothing breaks**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_clients.py tests/api/test_dependents.py tests/api/test_tax_returns.py -v --timeout=30`

Expected: All tests PASS (no import changes for routers, only the service now imports from the correct layer).

- [ ] **Step 5: Commit**

```bash
git add api/db/queries.py api/routers/_helpers.py api/services/tax/return_service.py
git commit -m "refactor: move get_client_or_404 to api.db.queries — fix circular dependency

The service layer was importing from the router layer (api.routers._helpers),
violating dependency inversion. Moved the canonical implementation to
api.db.queries and made _helpers a thin re-export shim.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Add Security Headers Middleware

Fixes HIGH-7: No `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`, or `Content-Security-Policy` headers.

**Files:**
- Create: `api/middleware/security_headers.py`
- Create: `tests/api/test_security_headers.py`
- Modify: `api/main.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_security_headers.py`:

```python
"""Tests for security headers middleware."""
import pytest
from httpx import ASGITransport, AsyncClient

from api.main import create_app


@pytest.fixture
async def raw_client():
    """Minimal client — no DB, just checks middleware on the health endpoint."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_security_headers_present(raw_client):
    resp = await raw_client.get("/api/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "max-age=" in resp.headers["strict-transport-security"]
    assert resp.headers["x-xss-protection"] == "0"
    assert "default-src" in resp.headers["content-security-policy"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_security_headers.py -v --timeout=30`

Expected: FAIL — headers are not present yet.

- [ ] **Step 3: Create the middleware**

Create `api/middleware/__init__.py` (empty file).

Create `api/middleware/security_headers.py`:

```python
"""Security headers middleware — adds OWASP-recommended response headers."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
```

- [ ] **Step 4: Wire middleware into `api/main.py`**

Add the import and middleware registration in `create_app()`. After the CORS middleware block (line 37), add:

```python
    from api.middleware.security_headers import SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)
```

The full middleware section of `create_app()` becomes:

```python
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    from api.middleware.security_headers import SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_security_headers.py -v --timeout=30`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add api/middleware/__init__.py api/middleware/security_headers.py tests/api/test_security_headers.py api/main.py
git commit -m "feat: add security headers middleware (X-Frame-Options, HSTS, CSP, etc.)

Adds OWASP-recommended response headers to all responses: X-Content-Type-Options,
X-Frame-Options, Strict-Transport-Security, Content-Security-Policy, Referrer-Policy.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Add Audit Logging for PII Reveal Endpoint

Fixes MEDIUM-5: `/reveal-pii` decrypts and returns plaintext PII with no audit trail.

**Files:**
- Modify: `api/routers/clients.py:285-321`

- [ ] **Step 1: Add logging to the `reveal_pii` endpoint**

In `api/routers/clients.py`, add a `logger` import at the top of the file (after line 2):

```python
import logging

logger = logging.getLogger(__name__)
```

Then modify the `reveal_pii` function. After the `revealed` dict is built (after the for loop, before the return on line 321), add audit logging:

```python
    logger.info(
        "PII_REVEAL user=%s org=%s client=%s fields=%s",
        user.id,
        user.org_id,
        client_id,
        sorted(req.fields),
    )
```

The full endpoint becomes:

```python
@router.post("/{client_id}/reveal-pii")
async def reveal_pii(
    client_id: str,
    req: PIIRevealRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_onboarded_user),
):
    perms = ROLE_PERMISSIONS.get(user.role, {})
    if not perms.get("can_view_pii"):
        raise HTTPException(status_code=403, detail="Not authorized to view PII")

    result = await session.execute(
        _client_query(user).where(ClientModel.id == client_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    enc = get_pii_encryptor()

    field_map = {
        "primary_ssn": client.primary_ssn_enc,
        "primary_dob": client.primary_dob_enc,
        "spouse_ssn": client.spouse_ssn_enc,
        "spouse_dob": client.spouse_dob_enc,
        "street": client.street_enc,
    }

    valid_fields = set(field_map.keys())
    revealed = {}
    for f in req.fields:
        if f not in valid_fields:
            raise HTTPException(status_code=400, detail=f"Invalid PII field: {f}")
        enc_value = field_map[f]
        revealed[f] = enc.decrypt(enc_value) if enc_value else None

    logger.info(
        "PII_REVEAL user=%s org=%s client=%s fields=%s",
        user.id,
        user.org_id,
        client_id,
        sorted(req.fields),
    )

    return revealed
```

- [ ] **Step 2: Verify existing reveal-pii test still passes**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_client_pii.py -v --timeout=30`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add api/routers/clients.py
git commit -m "feat: add audit logging for PII reveal endpoint

Every PII reveal now logs user ID, org ID, client ID, and which fields were
accessed. Supports compliance auditing and insider threat detection.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Add SSN and DOB Format Validators

Fixes MEDIUM-4: SSN fields accept any string up to 20 chars. No format validation, no rejection of invalid ranges.

**Files:**
- Modify: `api/models/client.py`
- Modify: `api/routers/dependents.py`
- Create: `tests/api/test_ssn_validation.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_ssn_validation.py`:

```python
"""Tests for SSN and DOB field validators."""
import pytest
from pydantic import ValidationError

from api.models.client import ClientCreate, ClientUpdate


class TestSSNValidation:
    def test_valid_ssn_with_dashes(self):
        c = ClientCreate(name="Test", primary_ssn="123-45-6789")
        assert c.primary_ssn == "123-45-6789"

    def test_valid_ssn_digits_only(self):
        c = ClientCreate(name="Test", primary_ssn="123456789")
        assert c.primary_ssn == "123456789"

    def test_none_ssn_allowed(self):
        c = ClientCreate(name="Test", primary_ssn=None)
        assert c.primary_ssn is None

    def test_blank_ssn_becomes_none(self):
        c = ClientCreate(name="Test", primary_ssn="   ")
        assert c.primary_ssn is None

    def test_invalid_ssn_too_short(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientCreate(name="Test", primary_ssn="12345")

    def test_invalid_ssn_letters(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientCreate(name="Test", primary_ssn="abc-de-fghi")

    def test_invalid_ssn_all_zeros(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientCreate(name="Test", primary_ssn="000-00-0000")

    def test_invalid_ssn_area_666(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientCreate(name="Test", primary_ssn="666-12-3456")

    def test_invalid_ssn_area_900_plus(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientCreate(name="Test", primary_ssn="900-12-3456")

    def test_spouse_ssn_validated_too(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientCreate(name="Test", spouse_ssn="bad")

    def test_update_model_validates_ssn(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientUpdate(primary_ssn="bad")


class TestDOBValidation:
    def test_valid_dob_iso(self):
        c = ClientCreate(name="Test", primary_dob="1990-06-15")
        assert c.primary_dob == "1990-06-15"

    def test_none_dob_allowed(self):
        c = ClientCreate(name="Test", primary_dob=None)
        assert c.primary_dob is None

    def test_invalid_dob_format(self):
        with pytest.raises(ValidationError, match="DOB"):
            ClientCreate(name="Test", primary_dob="06/15/1990")

    def test_invalid_dob_not_a_date(self):
        with pytest.raises(ValidationError, match="DOB"):
            ClientCreate(name="Test", primary_dob="not-a-date")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_ssn_validation.py -v --timeout=30`

Expected: Multiple FAIL — validators don't exist yet.

- [ ] **Step 3: Add validators to `api/models/client.py`**

Add two new validation helpers after the existing `_validate_zip` function (after line 70):

```python
def _validate_ssn(v: str | None) -> str | None:
    """Validate SSN format: NNN-NN-NNNN or NNNNNNNNN. Reject invalid IRS ranges."""
    v = _normalize_optional(v)
    if v is None:
        return None
    import re
    # Accept 9 digits with optional dashes
    if not re.fullmatch(r"\d{3}-?\d{2}-?\d{4}", v):
        raise ValueError("SSN must be 9 digits, optionally formatted as NNN-NN-NNNN")
    digits = v.replace("-", "")
    area, group, serial = digits[:3], digits[3:5], digits[5:]
    if area == "000" or group == "00" or serial == "0000":
        raise ValueError("SSN contains an invalid zero segment")
    if area == "666" or int(area) >= 900:
        raise ValueError("SSN area number is in a reserved/invalid range")
    return v


def _validate_dob(v: str | None) -> str | None:
    """Validate DOB is a valid ISO date (YYYY-MM-DD)."""
    v = _normalize_optional(v)
    if v is None:
        return None
    import re
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        raise ValueError("DOB must be in ISO format: YYYY-MM-DD")
    from datetime import date
    try:
        date.fromisoformat(v)
    except ValueError:
        raise ValueError("DOB must be a valid date in YYYY-MM-DD format")
    return v
```

Then add field validators to `ClientCreate` (after the existing `_v_filing_states` validator, around line 127):

```python
    @field_validator("primary_ssn", "spouse_ssn")
    @classmethod
    def _v_ssn(cls, v: str | None) -> str | None:
        return _validate_ssn(v)

    @field_validator("primary_dob", "spouse_dob")
    @classmethod
    def _v_dob(cls, v: str | None) -> str | None:
        return _validate_dob(v)
```

Add identical validators to `ClientUpdate` (after its `_v_filing_states`, around line 179):

```python
    @field_validator("primary_ssn", "spouse_ssn")
    @classmethod
    def _v_ssn(cls, v: str | None) -> str | None:
        return _validate_ssn(v)

    @field_validator("primary_dob", "spouse_dob")
    @classmethod
    def _v_dob(cls, v: str | None) -> str | None:
        return _validate_dob(v)
```

- [ ] **Step 4: Add validators to `DependentCreate` and `DependentUpdate` in `api/routers/dependents.py`**

Add imports at the top of the file (after line 4):

```python
from pydantic import Field, field_validator
```

Update `DependentCreate` (lines 19-28) to add field constraints and validators:

```python
class DependentCreate(BaseModel):
    first_name: str
    last_name: str
    ssn: str | None = Field(default=None, max_length=20)
    dob: str | None = Field(default=None, max_length=20)
    relationship: str
    months_lived_with: int = 12
    is_student: bool = False
    is_qualifying_child: bool = True
    is_us_citizen: bool = True

    @field_validator("ssn")
    @classmethod
    def _v_ssn(cls, v: str | None) -> str | None:
        from api.models.client import _validate_ssn
        return _validate_ssn(v)

    @field_validator("dob")
    @classmethod
    def _v_dob(cls, v: str | None) -> str | None:
        from api.models.client import _validate_dob
        return _validate_dob(v)
```

Update `DependentUpdate` (lines 31-40) similarly:

```python
class DependentUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    ssn: str | None = Field(default=None, max_length=20)
    dob: str | None = Field(default=None, max_length=20)
    relationship: str | None = None
    months_lived_with: int | None = None
    is_student: bool | None = None
    is_qualifying_child: bool | None = None
    is_us_citizen: bool | None = None

    @field_validator("ssn")
    @classmethod
    def _v_ssn(cls, v: str | None) -> str | None:
        from api.models.client import _validate_ssn
        return _validate_ssn(v)

    @field_validator("dob")
    @classmethod
    def _v_dob(cls, v: str | None) -> str | None:
        from api.models.client import _validate_dob
        return _validate_dob(v)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_ssn_validation.py -v --timeout=30`

Expected: All PASS

- [ ] **Step 6: Run full client/dependent test suite to check for regressions**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_clients.py tests/api/test_dependents.py tests/api/test_client_pii.py -v --timeout=30`

Expected: All PASS. If any test supplies an SSN that doesn't match the new format, update the test fixture data to use a valid SSN like `"123-45-6789"`.

- [ ] **Step 7: Commit**

```bash
git add api/models/client.py api/routers/dependents.py tests/api/test_ssn_validation.py
git commit -m "feat: add SSN and DOB format validators to client and dependent models

SSN: validates 9-digit format, rejects IRS-invalid ranges (000, 666, 900+).
DOB: validates ISO YYYY-MM-DD format with date parsing.
Applied to ClientCreate, ClientUpdate, DependentCreate, DependentUpdate.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Write Tests for Workflow Service

Fixes CRITICAL-3 (partial): `api/services/workflow.py` has zero tests despite containing complex gating and cascade logic.

**Files:**
- Create: `tests/api/test_workflow.py`

- [ ] **Step 1: Write the tests**

Create `tests/api/test_workflow.py`:

```python
"""Tests for the workflow step management service."""
import pytest

from api.services.workflow import (
    STEPS,
    can_complete_step,
    mark_step_complete,
    mark_step_incomplete,
    get_workflow_status,
    _step_index,
    _build_step_status,
)


# ── Pure function tests (no DB) ──────────────────────────────────────────────


class TestStepIndex:
    def test_valid_steps(self):
        assert _step_index("intake") == 0
        assert _step_index("documents") == 1
        assert _step_index("tax_return") == 2
        assert _step_index("filed") == 3

    def test_invalid_step_returns_zero(self):
        assert _step_index("bogus") == 0


class TestCanCompleteStep:
    def test_intake_always_completable(self):
        assert can_complete_step("intake", has_documents=False, has_return_draft=False, current_step="intake")

    def test_documents_requires_documents(self):
        assert not can_complete_step("documents", has_documents=False, has_return_draft=False, current_step="intake")

    def test_documents_completable_with_docs(self):
        assert can_complete_step("documents", has_documents=True, has_return_draft=False, current_step="intake")

    def test_tax_return_requires_draft(self):
        assert not can_complete_step("tax_return", has_documents=True, has_return_draft=False, current_step="documents")

    def test_tax_return_completable_with_draft(self):
        assert can_complete_step("tax_return", has_documents=True, has_return_draft=True, current_step="documents")

    def test_cannot_skip_steps(self):
        # Can't complete tax_return when current is intake (skips documents)
        assert not can_complete_step("tax_return", has_documents=True, has_return_draft=True, current_step="intake")

    def test_filed_requires_tax_return_complete(self):
        assert not can_complete_step("filed", has_documents=True, has_return_draft=True, current_step="documents")
        assert can_complete_step("filed", has_documents=True, has_return_draft=True, current_step="tax_return")


class TestBuildStepStatus:
    def test_intake_step(self):
        steps = _build_step_status("intake")
        assert len(steps) == 4
        assert steps[0] == {"id": "intake", "label": "Intake", "complete": True}
        assert steps[1] == {"id": "documents", "label": "Documents", "complete": False}

    def test_documents_step(self):
        steps = _build_step_status("documents")
        assert steps[0]["complete"] is True
        assert steps[1]["complete"] is True
        assert steps[2]["complete"] is False

    def test_filed_step(self):
        steps = _build_step_status("filed")
        assert all(s["complete"] for s in steps)


# ── Async tests (require DB) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_invalid_step(authenticated_client, app):
    """mark_step_complete with bogus step returns error dict."""
    from api.services.workflow import mark_step_complete

    session_factory = app.state.test_session_factory
    async with session_factory() as session:
        result = await mark_step_complete(session, "nonexistent-id", "org-1", "bogus")
        assert "error" in result


@pytest.mark.asyncio
async def test_mark_step_client_not_found(authenticated_client, app):
    """mark_step_complete with nonexistent client returns error."""
    from api.services.workflow import mark_step_complete

    session_factory = app.state.test_session_factory
    async with session_factory() as session:
        result = await mark_step_complete(session, "no-such-id", "org-1", "documents")
        assert result == {"error": "Client not found"}


@pytest.mark.asyncio
async def test_mark_incomplete_intake_rejected(authenticated_client, app):
    """Cannot unmark intake — it's always the baseline."""
    from api.services.workflow import mark_step_incomplete

    session_factory = app.state.test_session_factory
    async with session_factory() as session:
        result = await mark_step_incomplete(session, "any-id", "org-1", "intake")
        assert "error" in result
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_workflow.py -v --timeout=30`

Expected: All PASS (pure function tests don't need DB; async tests use the fixture infrastructure).

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_workflow.py
git commit -m "test: add unit tests for workflow service (gating, cascade, edge cases)

Tests can_complete_step gating logic, _build_step_status output,
step index mapping, invalid step handling, and client-not-found paths.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Write Tests for MCP Tool Registry

Fixes CRITICAL-3 (partial): `api/agent/mcp_server.py` has zero tests despite being the central tool wiring module.

**Files:**
- Create: `tests/api/test_mcp_server.py`

- [ ] **Step 1: Write the tests**

Create `tests/api/test_mcp_server.py`:

```python
"""Tests for the MCP tool registry builder."""
import pytest

from api.agent.mcp_server import build_tool_registry


EXPECTED_TOOLS = [
    "get_client_summary",
    "list_dependents",
    "list_documents",
    "get_document_fields",
    "get_return_draft",
    "get_return_line_detail",
    "validate_intake_vs_documents",
    "compute_tax_return",
    "run_advisory_analysis",
    "compare_prior_year",
    "run_validation_rules",
]


class TestBuildToolRegistry:
    def test_returns_registry_with_all_tools(self):
        registry = build_tool_registry()
        registered_names = {d["name"] for d in registry.tool_definitions}
        for tool in EXPECTED_TOOLS:
            assert tool in registered_names, f"Missing tool: {tool}"

    def test_tool_count(self):
        registry = build_tool_registry()
        assert len(registry.tool_definitions) == len(EXPECTED_TOOLS)

    def test_each_tool_has_handler(self):
        registry = build_tool_registry()
        for name in EXPECTED_TOOLS:
            assert name in registry._handlers, f"No handler for: {name}"

    def test_each_tool_has_description(self):
        registry = build_tool_registry()
        for defn in registry.tool_definitions:
            assert defn["description"], f"Empty description for: {defn['name']}"

    def test_each_tool_has_input_schema(self):
        registry = build_tool_registry()
        for defn in registry.tool_definitions:
            schema = defn["input_schema"]
            assert "type" in schema, f"Missing type in schema for: {defn['name']}"
            assert schema["type"] == "object"

    def test_get_document_fields_requires_doc_id(self):
        registry = build_tool_registry()
        defn = next(d for d in registry.tool_definitions if d["name"] == "get_document_fields")
        assert "doc_id" in defn["input_schema"]["properties"]
        assert "doc_id" in defn["input_schema"]["required"]

    def test_compare_prior_year_has_optional_prior_year(self):
        registry = build_tool_registry()
        defn = next(d for d in registry.tool_definitions if d["name"] == "compare_prior_year")
        assert "prior_year" in defn["input_schema"]["properties"]
        assert defn["input_schema"]["required"] == []

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        from unittest.mock import MagicMock
        registry = build_tool_registry()
        result = await registry.execute("nonexistent_tool", {}, MagicMock())
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_fresh_instance_each_call(self):
        """Each call to build_tool_registry returns an independent instance."""
        r1 = build_tool_registry()
        r2 = build_tool_registry()
        assert r1 is not r2
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_mcp_server.py -v --timeout=30`

Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_mcp_server.py
git commit -m "test: add unit tests for MCP tool registry builder

Verifies all 11 tools are registered with handlers, descriptions, and valid
input schemas. Tests unknown tool error path and instance independence.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Consolidate Duplicate Agent Service Factories

Fixes HIGH-2: `get_agent_service` and `get_agent_service_for_chat` in `api/dependencies.py` are identical.

**Files:**
- Modify: `api/dependencies.py`
- Modify: `api/routers/chat.py`

- [ ] **Step 1: Remove `get_agent_service_for_chat` from `api/dependencies.py`**

Delete lines 173-189 (the entire `get_agent_service_for_chat` function).

- [ ] **Step 2: Update `api/routers/chat.py` to use `get_agent_service`**

Change the import on line 14:

```python
# Before:
from api.dependencies import get_agent_service_for_chat, get_pii_encryptor_dep

# After:
from api.dependencies import get_agent_service, get_pii_encryptor_dep
```

Change the dependency on line 57:

```python
# Before:
    agent: AgentService = Depends(get_agent_service_for_chat),

# After:
    agent: AgentService = Depends(get_agent_service),
```

- [ ] **Step 3: Run tests to confirm nothing breaks**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/test_chat.py tests/api/test_chat_isolation.py -v --timeout=30`

Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add api/dependencies.py api/routers/chat.py
git commit -m "refactor: remove duplicate get_agent_service_for_chat factory

The function was identical to get_agent_service. Chat router now uses the
shared factory. DRY.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Final Verification

- [ ] **Step 1: Run the full test suite**

Run: `cd /Users/admin-h26/taxflow-kb && python -m pytest tests/api/ -v --timeout=60`

Expected: All PASS. If any test fails due to SSN validation (existing tests that use unformatted SSNs), update the test fixture data to use valid SSNs like `"123-45-6789"`.

- [ ] **Step 2: Verify no import cycles**

Run: `cd /Users/admin-h26/taxflow-kb && python -c "from api.main import create_app; print('OK')" && python -c "from api.services.tax.return_service import TaxReturnService; print('OK')" && python -c "from api.db.queries import get_client_or_404; print('OK')"`

Expected: All print `OK` with no ImportError.
