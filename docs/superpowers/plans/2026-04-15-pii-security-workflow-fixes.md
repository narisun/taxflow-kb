# PII Security + Workflow Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PII encryption (Fernet) for SSN/DOB/address, expand client data model with family groups and dependents, add document field editing, validation endpoint, and fix the assembler to use real client data.

**Architecture:** A `PIIEncryptor` service encrypts PII before DB writes and decrypts on reads. Encrypted columns use `LargeBinary`. API responses mask PII by default; a reveal endpoint requires `can_view_pii` permission. The assembler reads real encrypted client data instead of hardcoded placeholders.

**Tech Stack:** Python 3.12, cryptography (Fernet), Pydantic v2, FastAPI, SQLAlchemy async, pytest

**Spec:** `docs/superpowers/specs/2026-04-15-pii-security-workflow-fixes-design.md`

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `api/services/pii/__init__.py` | Package init |
| `api/services/pii/encryptor.py` | PIIEncryptor class (encrypt, decrypt, mask functions) |
| `api/routers/dependents.py` | Dependent CRUD endpoints |
| `tests/api/services/pii/__init__.py` | Test package |
| `tests/api/services/pii/test_encryptor.py` | Encryptor unit tests |
| `tests/api/test_client_pii.py` | Client PII create/mask/reveal integration tests |
| `tests/api/test_dependents.py` | Dependent CRUD integration tests |
| `tests/api/test_document_field_edit.py` | Document field editing tests |
| `tests/api/test_validation_endpoint.py` | Validation endpoint tests |

### Modified Files

| File | Change |
|------|--------|
| `api/db/models.py` | Add FamilyGroupModel, DependentModel, expand ClientModel, encrypt extracted_data |
| `api/models/client.py` | Expand ClientCreate/Update/Response with PII + masked fields |
| `api/models/document.py` | Add SkippedDocument model |
| `api/models/tax_return.py` | Add validation_results + skipped_documents to TaxReturnDraft |
| `api/auth/models.py` | Add can_view_pii to ROLE_PERMISSIONS |
| `api/routers/clients.py` | Expand CRUD with PII encryption, add reveal-pii endpoint |
| `api/routers/documents.py` | Add PATCH /fields, encrypt/decrypt extracted_data |
| `api/routers/tax_returns.py` | Add POST /validate, enrich draft response |
| `api/tax_engine/assembler.py` | Read real client data, decrypt PII, track skipped docs |
| `api/tax_engine/dependencies.py` | Add get_pii_encryptor dependency |
| `api/main.py` | Register dependents router |
| `tests/api/conftest.py` | Import new models (FamilyGroupModel, DependentModel) |
| `requirements-api.txt` | Add cryptography>=43.0 |

---

## Task 1: PIIEncryptor Service

**Files:**
- Create: `api/services/pii/__init__.py`
- Create: `api/services/pii/encryptor.py`
- Create: `tests/api/services/pii/__init__.py`
- Create: `tests/api/services/pii/test_encryptor.py`
- Modify: `requirements-api.txt`

- [ ] **Step 1: Add cryptography dependency**

Append to `requirements-api.txt`:
```
# PII encryption
cryptography>=43.0
```

Install: `pip install "cryptography>=43.0"`

- [ ] **Step 2: Create test package**

```bash
mkdir -p api/services/pii
touch api/services/pii/__init__.py
mkdir -p tests/api/services/pii
touch tests/api/services/pii/__init__.py
```

- [ ] **Step 3: Write failing tests**

Create `tests/api/services/pii/test_encryptor.py`:

```python
"""Tests for PII encryption service."""
import pytest
from datetime import date
from cryptography.fernet import Fernet


@pytest.fixture
def encryptor():
    from api.services.pii.encryptor import PIIEncryptor
    key = Fernet.generate_key()
    return PIIEncryptor(key)


class TestEncryptDecrypt:
    def test_roundtrip(self, encryptor):
        plaintext = "123456789"
        encrypted = encryptor.encrypt(plaintext)
        assert isinstance(encrypted, bytes)
        assert encrypted != plaintext.encode()
        assert encryptor.decrypt(encrypted) == plaintext

    def test_different_encryptions_differ(self, encryptor):
        """Fernet includes a timestamp, so same plaintext produces different ciphertext."""
        a = encryptor.encrypt("test")
        b = encryptor.encrypt("test")
        assert a != b  # Different due to timestamp/IV

    def test_empty_string(self, encryptor):
        encrypted = encryptor.encrypt("")
        assert encryptor.decrypt(encrypted) == ""

    def test_json_roundtrip(self, encryptor):
        data = {"box1_wages": "85000", "employer_name": "ACME"}
        encrypted = encryptor.encrypt_json(data)
        assert isinstance(encrypted, bytes)
        result = encryptor.decrypt_json(encrypted)
        assert result == data

    def test_json_empty_dict(self, encryptor):
        encrypted = encryptor.encrypt_json({})
        assert encryptor.decrypt_json(encrypted) == {}

    def test_wrong_key_fails(self):
        from api.services.pii.encryptor import PIIEncryptor
        key1 = Fernet.generate_key()
        key2 = Fernet.generate_key()
        enc1 = PIIEncryptor(key1)
        enc2 = PIIEncryptor(key2)
        encrypted = enc1.encrypt("secret")
        with pytest.raises(Exception):
            enc2.decrypt(encrypted)


class TestMasking:
    def test_mask_ssn(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_ssn("123456789") == "***-**-6789"

    def test_mask_ssn_short(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_ssn("1234") == "***-**-1234"

    def test_mask_ssn_none(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_ssn(None) == ""

    def test_mask_dob(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_dob(date(1985, 3, 15)) == "**/**/1985"

    def test_mask_dob_none(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_dob(None) == ""

    def test_mask_address(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_address("123 Main St") == "123 M***"

    def test_mask_address_short(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_address("A") == "A***"

    def test_mask_address_none(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_address(None) == ""


class TestGetEncryptor:
    def test_dev_key_used_when_no_env(self):
        from api.services.pii.encryptor import get_pii_encryptor
        enc = get_pii_encryptor()
        # Should work without PII_ENCRYPTION_KEY set (uses dev key)
        encrypted = enc.encrypt("test")
        assert enc.decrypt(encrypted) == "test"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/api/services/pii/test_encryptor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 5: Implement encryptor.py**

Create `api/services/pii/encryptor.py`:

```python
"""PII encryption service using Fernet (AES-128-CBC).

All PII (SSN, DOB, street address) is encrypted before storage
and decrypted only when needed. API responses show masked values.
"""
import json
import os
from datetime import date

from cryptography.fernet import Fernet

# Dev-only key — NOT SECURE. Used when PII_ENCRYPTION_KEY is not set.
_DEV_KEY = b"ZGV2LW9ubHkta2V5LXRoaXMtaXMtbm90LXNlY3VyZS0hIQ=="
# Generate a real key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"


class PIIEncryptor:
    """Encrypts and decrypts PII fields using Fernet symmetric encryption."""

    def __init__(self, key: bytes):
        self.fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a plaintext string. Returns ciphertext bytes."""
        return self.fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt ciphertext bytes. Returns plaintext string."""
        return self.fernet.decrypt(ciphertext).decode("utf-8")

    def encrypt_json(self, data: dict) -> bytes:
        """JSON-serialize a dict and encrypt it."""
        return self.encrypt(json.dumps(data))

    def decrypt_json(self, ciphertext: bytes) -> dict:
        """Decrypt and JSON-deserialize to a dict."""
        return json.loads(self.decrypt(ciphertext))

    @staticmethod
    def mask_ssn(ssn: str | None) -> str:
        """Mask SSN: '123456789' → '***-**-6789'."""
        if not ssn:
            return ""
        last4 = ssn[-4:] if len(ssn) >= 4 else ssn
        return f"***-**-{last4}"

    @staticmethod
    def mask_dob(dob: date | None) -> str:
        """Mask DOB: date(1985,3,15) → '**/**/1985'."""
        if not dob:
            return ""
        return f"**/**/{dob.year}"

    @staticmethod
    def mask_address(street: str | None) -> str:
        """Mask street: '123 Main St' → '123 M***'."""
        if not street:
            return ""
        visible = street[:5] if len(street) >= 5 else street
        return f"{visible}***"


def get_pii_encryptor() -> PIIEncryptor:
    """Get a PIIEncryptor instance. Uses dev key if PII_ENCRYPTION_KEY not set."""
    key_str = os.getenv("PII_ENCRYPTION_KEY")
    if key_str:
        key = key_str.encode()
    else:
        key = _DEV_KEY
    return PIIEncryptor(key)
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/api/services/pii/test_encryptor.py -v`
Expected: All 14 tests PASS

- [ ] **Step 7: Commit**

```bash
git add api/services/pii/ tests/api/services/pii/ requirements-api.txt
git commit -m "feat(pii): add PIIEncryptor service with Fernet encryption and masking"
```

---

## Task 2: Database Model Changes (FamilyGroup, Dependent, Client expansion)

**Files:**
- Modify: `api/db/models.py`
- Modify: `api/auth/models.py`
- Modify: `tests/api/conftest.py`

- [ ] **Step 1: Add can_view_pii to ROLE_PERMISSIONS**

In `api/auth/models.py`, add `"can_view_pii": True` to admin and supervisor, `"can_view_pii": False` to preparer and analyst. Add it as the last entry in each role's dict.

- [ ] **Step 2: Add FamilyGroupModel, DependentModel, expand ClientModel**

Add to `api/db/models.py` (before the existing `ClientModel`):

```python
class FamilyGroupModel(TenantMixin, Base):
    __tablename__ = "family_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    primary_first_name: Mapped[str] = mapped_column(String(100), default="")
    primary_last_name: Mapped[str] = mapped_column(String(100), default="")
    spouse_first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    spouse_last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

Add new columns to `ClientModel` (after existing columns, before `documents` relationship):

```python
    family_group_id: Mapped[int | None] = mapped_column(ForeignKey("family_groups.id"), nullable=True)
    primary_ssn_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    primary_dob_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    spouse_ssn_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    spouse_dob_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    street_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
```

Add `LargeBinary` to the imports at the top of `api/db/models.py`:
```python
from sqlalchemy import String, Integer, Text, Float, ForeignKey, Index, UniqueConstraint, LargeBinary
```

Add `DependentModel` after `ClientModel`:

```python
class DependentModel(TenantMixin, Base):
    __tablename__ = "dependents"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    ssn_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    dob_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    relationship: Mapped[str] = mapped_column(String(30))
    months_lived_with: Mapped[int] = mapped_column(Integer, default=12)
    is_student: Mapped[bool] = mapped_column(default=False)
    is_qualifying_child: Mapped[bool] = mapped_column(default=True)
    is_us_citizen: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        Index("ix_dependents_org_client", "org_id", "client_id"),
    )
```

- [ ] **Step 3: Update conftest.py imports**

In `tests/api/conftest.py`, update the import to include new models:

```python
from api.db.models import ClientModel, DocumentModel, ChatMessageModel, TaxReturnDraftModel, ManualEntryModel, FamilyGroupModel, DependentModel  # noqa: F401
```

- [ ] **Step 4: Run existing tests to verify no regressions**

Run: `python -m pytest tests/api/ -v --tb=short -x`
Expected: All tests PASS (new columns are nullable, so existing data still works)

- [ ] **Step 5: Commit**

```bash
git add api/db/models.py api/auth/models.py tests/api/conftest.py
git commit -m "feat(pii): add FamilyGroupModel, DependentModel, expand ClientModel with encrypted PII columns"
```

---

## Task 3: Client API — PII Create, Mask, Reveal

**Files:**
- Modify: `api/models/client.py`
- Modify: `api/routers/clients.py`
- Create: `tests/api/test_client_pii.py`

- [ ] **Step 1: Expand Pydantic schemas**

Rewrite `api/models/client.py`:

```python
"""Client Pydantic schemas with PII support."""
from pydantic import BaseModel, Field
from datetime import datetime

from api.models.enums import FilingStatus, WorkflowStep


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    filing_status: FilingStatus = "single"
    tax_year: int = Field(default=2025, ge=2000, le=2100)
    dependents: int = Field(default=0, ge=0, le=99)
    # PII fields (encrypted before storage)
    primary_ssn: str | None = None
    primary_dob: str | None = None  # ISO format: "1985-03-15"
    spouse_first_name: str | None = None
    spouse_last_name: str | None = None
    spouse_ssn: str | None = None
    spouse_dob: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    family_group_name: str | None = None


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    filing_status: FilingStatus | None = None
    workflow_step: WorkflowStep | None = None
    dependents: int | None = Field(default=None, ge=0, le=99)
    primary_ssn: str | None = None
    primary_dob: str | None = None
    spouse_first_name: str | None = None
    spouse_last_name: str | None = None
    spouse_ssn: str | None = None
    spouse_dob: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None


class ClientResponse(BaseModel):
    id: int
    name: str
    filing_status: str
    tax_year: int
    dependents: int
    workflow_step: str
    # Masked PII
    primary_ssn_masked: str = ""
    primary_dob_masked: str = ""
    spouse_first_name: str | None = None
    spouse_last_name: str | None = None
    spouse_ssn_masked: str = ""
    spouse_dob_masked: str = ""
    street_masked: str = ""
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    family_group_name: str | None = None
    # Metadata
    org_id: str
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ClientListResponse(BaseModel):
    items: list[ClientResponse]
    total: int
    page: int = 1
    page_size: int = 50


class PIIRevealRequest(BaseModel):
    fields: list[str]  # ["primary_ssn", "primary_dob", "spouse_ssn", "street"]
```

- [ ] **Step 2: Rewrite clients router with PII encryption**

Rewrite `api/routers/clients.py` to encrypt PII on create/update and mask on read. The router uses `get_pii_encryptor()` to get the encryptor. Key changes:

- `create_client`: encrypt SSN/DOB/street before saving, optionally create FamilyGroupModel
- `get_client` / `list_clients`: decrypt + mask PII in response
- `update_client`: re-encrypt PII fields on update
- New `reveal_pii` endpoint: decrypt requested fields, requires `can_view_pii`

The complete code is long — the implementer should:
1. Read the current `api/routers/clients.py` 
2. Add PII encryption/masking logic following the spec
3. Add `POST /{client_id}/reveal-pii` endpoint
4. Build `ClientResponse` manually instead of returning ORM object directly (since masked fields are computed)

- [ ] **Step 3: Write integration tests**

Create `tests/api/test_client_pii.py`:

```python
"""Tests for client PII encryption, masking, and reveal."""
import pytest


@pytest.mark.asyncio
async def test_create_client_with_pii(client):
    resp = await client.post("/api/clients", json={
        "name": "Smith Family", "filing_status": "mfj", "tax_year": 2024,
        "primary_ssn": "123456789", "primary_dob": "1985-03-15",
        "spouse_first_name": "Jane", "spouse_last_name": "Smith",
        "spouse_ssn": "987654321", "spouse_dob": "1987-05-10",
        "street": "123 Main St", "city": "Springfield", "state": "IL", "zip_code": "62701",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["primary_ssn_masked"] == "***-**-6789"
    assert body["primary_dob_masked"] == "**/**/1985"
    assert body["spouse_ssn_masked"] == "***-**-4321"
    assert body["street_masked"] == "123 M***"
    assert body["city"] == "Springfield"
    assert body["state"] == "IL"


@pytest.mark.asyncio
async def test_get_client_returns_masked(client):
    c = await client.post("/api/clients", json={
        "name": "Test", "primary_ssn": "111223333", "street": "456 Oak Ave",
        "city": "Portland", "state": "OR", "zip_code": "97201",
    })
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["primary_ssn_masked"] == "***-**-3333"
    assert body["street_masked"] == "456 O***"
    assert "111223333" not in str(body)  # Full SSN never in response


@pytest.mark.asyncio
async def test_reveal_pii(client):
    c = await client.post("/api/clients", json={
        "name": "Test", "primary_ssn": "123456789", "street": "123 Main St",
        "primary_dob": "1985-03-15",
    })
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/reveal-pii", json={
        "fields": ["primary_ssn", "primary_dob", "street"],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["primary_ssn"] == "123456789"
    assert body["primary_dob"] == "1985-03-15"
    assert body["street"] == "123 Main St"


@pytest.mark.asyncio
async def test_update_client_pii(client):
    c = await client.post("/api/clients", json={
        "name": "Test", "primary_ssn": "111111111",
    })
    cid = c.json()["id"]
    resp = await client.patch(f"/api/clients/{cid}", json={
        "primary_ssn": "999888777",
    })
    assert resp.status_code == 200
    assert resp.json()["primary_ssn_masked"] == "***-**-8777"


@pytest.mark.asyncio
async def test_create_client_without_pii_still_works(client):
    """Backward compatibility — PII fields are optional."""
    resp = await client.post("/api/clients", json={
        "name": "Simple Client", "filing_status": "single", "tax_year": 2024,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["primary_ssn_masked"] == ""
    assert body["city"] is None


@pytest.mark.asyncio
async def test_list_clients_masked(client):
    await client.post("/api/clients", json={
        "name": "A", "primary_ssn": "111111111",
    })
    await client.post("/api/clients", json={
        "name": "B", "primary_ssn": "222222222",
    })
    resp = await client.get("/api/clients")
    assert resp.status_code == 200
    items = resp.json()["items"]
    for item in items:
        if item.get("primary_ssn_masked"):
            assert "***-**-" in item["primary_ssn_masked"]
```

- [ ] **Step 4: Implement the router changes**

The implementer should rewrite `api/routers/clients.py` following the spec and tests above. Key implementation notes:
- Import `get_pii_encryptor` from `api.services.pii.encryptor`
- Import `FamilyGroupModel` from `api.db.models`
- Build `ClientResponse` manually with masked fields (don't use `from_attributes` for PII fields)
- The `reveal_pii` endpoint checks `ROLE_PERMISSIONS[user.role].get("can_view_pii")` and returns 403 if False

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/api/test_client_pii.py tests/api/test_clients.py -v`
Expected: All tests PASS (both new PII tests and existing client CRUD tests)

- [ ] **Step 6: Commit**

```bash
git add api/models/client.py api/routers/clients.py tests/api/test_client_pii.py
git commit -m "feat(pii): client CRUD with encrypted SSN/DOB/address, masked responses, reveal endpoint"
```

---

## Task 4: Dependent CRUD Endpoints

**Files:**
- Create: `api/routers/dependents.py`
- Modify: `api/main.py`
- Create: `tests/api/test_dependents.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/test_dependents.py`:

```python
"""Tests for dependent CRUD endpoints with PII encryption."""
import pytest


@pytest.mark.asyncio
async def test_add_dependent(client):
    c = await client.post("/api/clients", json={"name": "Smith", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/dependents", json={
        "first_name": "Emily", "last_name": "Smith",
        "ssn": "111223333", "dob": "2015-06-01",
        "relationship": "daughter", "is_qualifying_child": True,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["first_name"] == "Emily"
    assert body["ssn_masked"] == "***-**-3333"
    assert body["dob_masked"] == "**/**/2015"


@pytest.mark.asyncio
async def test_list_dependents_masked(client):
    c = await client.post("/api/clients", json={"name": "Smith", "tax_year": 2024})
    cid = c.json()["id"]
    await client.post(f"/api/clients/{cid}/dependents", json={
        "first_name": "A", "last_name": "S", "ssn": "111111111",
        "dob": "2015-01-01", "relationship": "son",
    })
    await client.post(f"/api/clients/{cid}/dependents", json={
        "first_name": "B", "last_name": "S", "ssn": "222222222",
        "dob": "2018-06-01", "relationship": "daughter",
    })
    resp = await client.get(f"/api/clients/{cid}/dependents")
    assert resp.status_code == 200
    deps = resp.json()
    assert len(deps) == 2
    assert deps[0]["ssn_masked"] == "***-**-1111"
    assert "111111111" not in str(deps)


@pytest.mark.asyncio
async def test_update_dependent(client):
    c = await client.post("/api/clients", json={"name": "Smith", "tax_year": 2024})
    cid = c.json()["id"]
    dep = await client.post(f"/api/clients/{cid}/dependents", json={
        "first_name": "Emily", "last_name": "Smith",
        "ssn": "111223333", "dob": "2015-06-01", "relationship": "daughter",
    })
    dep_id = dep.json()["id"]
    resp = await client.patch(f"/api/clients/{cid}/dependents/{dep_id}", json={
        "relationship": "stepdaughter",
    })
    assert resp.status_code == 200
    assert resp.json()["relationship"] == "stepdaughter"


@pytest.mark.asyncio
async def test_delete_dependent(client):
    c = await client.post("/api/clients", json={"name": "Smith", "tax_year": 2024})
    cid = c.json()["id"]
    dep = await client.post(f"/api/clients/{cid}/dependents", json={
        "first_name": "Emily", "last_name": "Smith",
        "ssn": "111223333", "dob": "2015-06-01", "relationship": "daughter",
    })
    dep_id = dep.json()["id"]
    resp = await client.delete(f"/api/clients/{cid}/dependents/{dep_id}")
    assert resp.status_code == 204
    resp = await client.get(f"/api/clients/{cid}/dependents")
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_dependent_nonexistent_client(client):
    resp = await client.post("/api/clients/9999/dependents", json={
        "first_name": "A", "last_name": "B", "ssn": "111111111",
        "dob": "2015-01-01", "relationship": "son",
    })
    assert resp.status_code == 404
```

- [ ] **Step 2: Implement dependents router**

Create `api/routers/dependents.py` with CRUD for dependents. SSN and DOB are encrypted on create/update using `get_pii_encryptor()`. Responses mask SSN/DOB. Register the router in `api/main.py`.

- [ ] **Step 3: Register router in main.py**

Add to `api/main.py` imports and `create_app()`:
```python
from api.routers import dependents
app.include_router(dependents.router)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/api/test_dependents.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/routers/dependents.py api/main.py tests/api/test_dependents.py
git commit -m "feat(pii): add dependent CRUD endpoints with encrypted SSN/DOB"
```

---

## Task 5: Document Field Editing + Encrypted extracted_data

**Files:**
- Modify: `api/routers/documents.py`
- Create: `tests/api/test_document_field_edit.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/test_document_field_edit.py`:

```python
"""Tests for document field editing with encrypted extracted_data."""
import json
import pytest


@pytest.mark.asyncio
async def test_edit_extracted_field(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"}, files={"file": ("w2.pdf", b"fake", "application/pdf")})
    did = doc.json()["id"]

    # Edit a field
    resp = await client.patch(f"/api/documents/{did}/fields", json={
        "field_name": "box1_wages", "value": "115000.00",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "review"  # Reset to review after edit

    # Verify the field was updated
    fields_resp = await client.get(f"/api/documents/{did}/fields")
    fields = fields_resp.json()
    wages = next((f for f in fields if f["name"] == "box1_wages"), None)
    assert wages is not None
    assert wages["value"] == "115000.00"


@pytest.mark.asyncio
async def test_edit_nonexistent_document(client):
    resp = await client.patch("/api/documents/9999/fields", json={
        "field_name": "box1_wages", "value": "100000",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_edit_resets_status_to_review(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"}, files={"file": ("w2.pdf", b"fake", "application/pdf")})
    did = doc.json()["id"]

    # Approve first
    await client.patch(f"/api/documents/{did}/approve")
    detail = await client.get(f"/api/documents/{did}")
    assert detail.json()["status"] == "approved"

    # Edit resets to review
    await client.patch(f"/api/documents/{did}/fields", json={
        "field_name": "employer_name", "value": "NEW CORP",
    })
    detail = await client.get(f"/api/documents/{did}")
    assert detail.json()["status"] == "review"
```

- [ ] **Step 2: Add PATCH /fields endpoint to documents router**

Add to `api/routers/documents.py`:
- Import `get_pii_encryptor`
- Update upload endpoint to encrypt `extracted_data` before storage
- Update fields endpoint to decrypt `extracted_data` before reading
- Add `PATCH /documents/{doc_id}/fields` endpoint that decrypts, updates field, re-encrypts, resets status

The implementer should also update the existing upload and fields endpoints to handle encrypted `extracted_data` (LargeBinary).

**Important note:** The `DocumentModel.extracted_data` column type changes from `Text` to `LargeBinary`. However, since tests use in-memory SQLite with `create_all`, and the column is nullable, this should work without migration issues in tests. For existing data, a migration would be needed (out of scope for this task).

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/api/test_document_field_edit.py tests/api/test_documents.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add api/routers/documents.py api/db/models.py tests/api/test_document_field_edit.py
git commit -m "feat(pii): add document field editing, encrypt extracted_data at rest"
```

---

## Task 6: Validation Endpoint + Draft Enrichment

**Files:**
- Modify: `api/models/tax_return.py`
- Modify: `api/models/document.py`
- Modify: `api/routers/tax_returns.py`
- Create: `tests/api/test_validation_endpoint.py`

- [ ] **Step 1: Add SkippedDocument model and enrich TaxReturnDraft**

Add to `api/models/document.py`:
```python
class SkippedDocument(BaseModel):
    document_id: int
    form_type: str
    reason: str
```

Add to `api/models/tax_return.py` (expand `TaxReturnDraft`):
```python
from api.tax_engine.validation.base import ValidationResult

class TaxReturnDraft(BaseModel):
    client_id: int
    tax_year: int
    filing_status: str
    lines: list[ReturnLine]
    total_income: float
    total_deductions: float
    taxable_income: float
    total_tax: float
    total_payments: float
    refund_or_owed: float
    effective_rate: float
    validation_results: list[dict] = []
    skipped_documents: list[dict] = []
```

- [ ] **Step 2: Write failing tests**

Create `tests/api/test_validation_endpoint.py`:

```python
"""Tests for validation endpoint."""
import pytest


@pytest.mark.asyncio
async def test_validate_returns_results(client):
    c = await client.post("/api/clients", json={
        "name": "Test", "filing_status": "mfj", "tax_year": 2024,
    })
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/returns/validate")
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert "has_errors" in body
    # MFJ without spouse should produce V003 error
    assert body["has_errors"] is True
    assert any(r["rule_id"] == "V003" for r in body["results"])


@pytest.mark.asyncio
async def test_validate_valid_return(client):
    c = await client.post("/api/clients", json={
        "name": "Test", "filing_status": "single", "tax_year": 2024,
    })
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/returns/validate")
    assert resp.status_code == 200
    assert resp.json()["has_errors"] is False


@pytest.mark.asyncio
async def test_validate_nonexistent_client(client):
    resp = await client.post("/api/clients/9999/returns/validate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_draft_includes_validation(client):
    c = await client.post("/api/clients", json={
        "name": "Test", "filing_status": "mfj", "tax_year": 2024,
    })
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert "validation_results" in body
```

- [ ] **Step 3: Add validation endpoint and enrich draft**

Add to `api/routers/tax_returns.py`:

```python
from api.tax_engine.validation.engine import ValidationEngine

@router.post("/validate")
async def validate_return(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    """Run validation without computing taxes."""
    client = await get_client_or_404(client_id, session, user)
    assembler = DocumentAssembler()
    tax_return = await assembler.assemble(client_id, session)

    validator = ValidationEngine()
    results = validator.validate(tax_return)

    return {
        "results": [r.model_dump() for r in results],
        "has_errors": any(r.severity == "ERROR" for r in results),
        "skipped_documents": assembler.skipped_documents if hasattr(assembler, 'skipped_documents') else [],
    }
```

Also modify the existing `generate_draft` endpoint to include `validation_results` and `skipped_documents` in the response.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/api/test_validation_endpoint.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/models/tax_return.py api/models/document.py api/routers/tax_returns.py tests/api/test_validation_endpoint.py
git commit -m "feat: add validation endpoint and enrich draft with validation results"
```

---

## Task 7: Assembler Fixes — Real Client Data + Error Tracking

**Files:**
- Modify: `api/tax_engine/assembler.py`
- Modify: `tests/api/tax_engine/test_assembler.py`

- [ ] **Step 1: Write failing tests for real client data**

Add to `tests/api/tax_engine/test_assembler.py`:

```python
@pytest.mark.asyncio
async def test_assemble_with_real_client_pii(db_session):
    """Verify assembler reads encrypted SSN/DOB/address from client."""
    session, client_id, org_id, user_id = db_session
    from api.services.pii.encryptor import get_pii_encryptor
    enc = get_pii_encryptor()

    # Update client with encrypted PII
    from sqlalchemy import select
    from api.db.models import ClientModel
    result = await session.execute(select(ClientModel).where(ClientModel.id == client_id))
    client = result.scalar_one()
    client.primary_ssn_enc = enc.encrypt("123456789")
    client.primary_dob_enc = enc.encrypt("1985-03-15")
    client.street_enc = enc.encrypt("123 Main St")
    client.city = "Springfield"
    client.state = "IL"
    client.zip_code = "62701"
    await session.commit()

    assembler = DocumentAssembler()
    tr = await assembler.assemble(client_id, session)
    assert tr.primary.ssn == "123456789"
    assert str(tr.primary.date_of_birth) == "1985-03-15"
    assert tr.address.street == "123 Main St"
    assert tr.address.city == "Springfield"


@pytest.mark.asyncio
async def test_assemble_tracks_skipped_documents(db_session):
    """Verify assembler reports documents that failed to parse."""
    session, client_id, org_id, user_id = db_session
    from api.services.pii.encryptor import get_pii_encryptor
    enc = get_pii_encryptor()

    # Add a document with invalid extracted data
    doc = DocumentModel(
        org_id=org_id, created_by=user_id, client_id=client_id,
        form_type="W-2", title="Bad W-2", status="approved", confidence=0.95,
        extracted_data=enc.encrypt_json({"invalid_field": "bad data"}),
    )
    session.add(doc)
    await session.commit()

    assembler = DocumentAssembler()
    tr = await assembler.assemble(client_id, session)
    assert len(assembler.skipped_documents) >= 1
```

- [ ] **Step 2: Update assembler to read real client data and track errors**

Rewrite `api/tax_engine/assembler.py` to:
1. Import and use `get_pii_encryptor()` to decrypt SSN/DOB/address from `ClientModel`
2. Query `DependentModel` and decrypt SSN/DOB for each dependent
3. Decrypt `extracted_data` blob (LargeBinary → JSON dict)
4. Track skipped documents in `self.skipped_documents` instead of silent `continue`
5. Fall back to placeholder values only if encrypted fields are None (backward compat)

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/api/tax_engine/test_assembler.py -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 4: Run full suite**

Run: `python -m pytest tests/api/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/assembler.py tests/api/tax_engine/test_assembler.py
git commit -m "fix(assembler): read real encrypted client data, track skipped documents"
```

---

## Task 8: Final Integration Test

**Files:**
- Run full test suite

- [ ] **Step 1: Run complete test suite**

Run: `python -m pytest tests/api/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Commit if any remaining changes**

```bash
git add -A && git status
git commit -m "feat(pii): PII security + workflow fixes complete — encrypted SSN/DOB/address, dependents, validation, field editing"
```
