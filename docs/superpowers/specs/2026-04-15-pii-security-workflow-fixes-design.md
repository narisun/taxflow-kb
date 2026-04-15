# Client Data Model + PII Security + Workflow Fixes — Design Spec

**Date:** 2026-04-15
**Status:** Approved
**Scope:** PII encryption layer, expanded client/dependent data models, family groups, document field editing, validation endpoint, assembler fixes

---

## 1. Overview

Fix critical workflow gaps that block CPA tax filing: missing client SSN/address/spouse/dependent data, no validation endpoint, no document field editing. All PII (SSN, DOB, street address) is encrypted at rest using Fernet (AES-128-CBC) and masked in API responses. A reveal-on-demand pattern allows authorized users to view full PII.

### Design Principles

- **Encryption at rest** — all PII stored as Fernet-encrypted bytes (`LargeBinary` columns). Plaintext never written to disk or database.
- **Masked by default** — API responses show `***-**-1234` for SSN, `**/**/1985` for DOB. Requires explicit reveal action.
- **Permission-gated reveal** — only `admin` and `supervisor` roles can view full PII via `can_view_pii` permission.
- **Single application key** — one `PII_ENCRYPTION_KEY` env var (Fernet key). Upgradeable to per-org keys later.
- **Family group concept** — clients grouped by family with a display name and adult names for UI, all sensitive details encrypted.

---

## 2. PII Encryption Service

### 2.1 `api/services/pii/encryptor.py`

```python
class PIIEncryptor:
    def __init__(self, key: bytes):
        """key: 32-byte URL-safe base64 Fernet key."""
        self.fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a plaintext string. Returns ciphertext bytes."""

    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt ciphertext bytes. Returns plaintext string."""

    def encrypt_json(self, data: dict) -> bytes:
        """JSON-serialize and encrypt a dict."""

    def decrypt_json(self, ciphertext: bytes) -> dict:
        """Decrypt and JSON-deserialize to a dict."""

    @staticmethod
    def mask_ssn(ssn: str) -> str:
        """'123456789' → '***-**-6789'"""

    @staticmethod
    def mask_dob(dob: date) -> str:
        """date(1985,3,15) → '**/**/1985'"""

    @staticmethod
    def mask_address(street: str) -> str:
        """'123 Main St' → '123 M***'"""
```

### 2.2 Configuration

| Env Var | Required | Description |
|---------|----------|-------------|
| `PII_ENCRYPTION_KEY` | Yes (prod) | Fernet key (generate via `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) |

In dev mode (`APP_ENV != production`), a hardcoded dev key is used if `PII_ENCRYPTION_KEY` is not set. This key is NOT secure — only for local development.

### 2.3 FastAPI Dependency

```python
def get_pii_encryptor() -> PIIEncryptor:
    key = os.getenv("PII_ENCRYPTION_KEY", DEV_KEY)
    return PIIEncryptor(key.encode())
```

### 2.4 PII Field Classification

| Field | Encrypted | Masked Display | Reveal Permission |
|-------|-----------|---------------|-------------------|
| SSN (primary, spouse, dependents) | Yes | `***-**-1234` | `can_view_pii` |
| Date of birth | Yes | `**/**/1985` | `can_view_pii` |
| Street address | Yes | `123 M***` | `can_view_pii` |
| City, state, zip | No | Shown | — |
| Client/family display name | No | Shown | — |
| Person names (first, last) | No | Shown | — |
| EIN (employer) | No | Shown | — |
| Dollar amounts | No | Shown | — |
| Document extracted_data | Yes (whole blob) | N/A (internal) | Decrypted for processing |

---

## 3. Data Model Changes

### 3.1 `FamilyGroupModel` (new table: `family_groups`)

Groups family members under one display unit for the CPA's client list.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer PK | Auto-increment |
| `org_id` | FK → organizations | Tenant isolation |
| `created_by` | FK → users | Creator |
| `display_name` | String(200) | "The Smith Family" |
| `primary_first_name` | String(100) | "John" (display) |
| `primary_last_name` | String(100) | "Smith" (display) |
| `spouse_first_name` | String(100), nullable | "Jane" (display) |
| `spouse_last_name` | String(100), nullable | "Smith" (display) |
| `created_at` | DateTime | Auto |
| `updated_at` | DateTime | Auto |

### 3.2 `ClientModel` (expanded)

Add new columns to existing `clients` table:

| Column | Type | Description |
|--------|------|-------------|
| `family_group_id` | FK → family_groups, nullable | Links to family group |
| `primary_ssn_enc` | LargeBinary, nullable | Encrypted SSN |
| `primary_dob_enc` | LargeBinary, nullable | Encrypted DOB (ISO string) |
| `spouse_ssn_enc` | LargeBinary, nullable | Encrypted spouse SSN |
| `spouse_dob_enc` | LargeBinary, nullable | Encrypted spouse DOB |
| `street_enc` | LargeBinary, nullable | Encrypted street address |
| `city` | String(100), nullable | City (not PII) |
| `state` | String(2), nullable | State code (not PII) |
| `zip_code` | String(10), nullable | Zip code (not PII) |

Existing columns unchanged: `id`, `org_id`, `created_by`, `name`, `filing_status`, `tax_year`, `dependents` (int count), `workflow_step`.

### 3.3 `DependentModel` (new table: `dependents`)

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer PK | Auto-increment |
| `org_id` | FK → organizations | Tenant isolation |
| `created_by` | FK → users | Creator |
| `client_id` | FK → clients | Parent client |
| `first_name` | String(100) | Display name |
| `last_name` | String(100) | Display name |
| `ssn_enc` | LargeBinary, nullable | Encrypted SSN |
| `dob_enc` | LargeBinary, nullable | Encrypted DOB |
| `relationship` | String(30) | "son", "daughter", "parent", etc. |
| `months_lived_with` | Integer, default 12 | 0-12 |
| `is_student` | Boolean, default False | Student status |
| `is_qualifying_child` | Boolean, default True | CTC qualifying |
| `is_us_citizen` | Boolean, default True | Citizenship |
| `created_at` | DateTime | Auto |
| `updated_at` | DateTime | Auto |

Index: `(org_id, client_id)`

### 3.4 `DocumentModel.extracted_data` — Encrypt

Change `extracted_data` column from `Text` to `LargeBinary`. The JSON blob is encrypted before storage and decrypted on read.

The `flags` column remains `Text` (no PII in flags — just confidence messages).
The `confidence` column remains `Float`.

---

## 4. API Changes

### 4.1 Client Endpoints (expanded)

**`POST /api/clients`** — Create client with PII:

```json
{
  "name": "Smith Family",
  "filing_status": "mfj",
  "tax_year": 2024,
  "primary_ssn": "123456789",
  "primary_dob": "1985-03-15",
  "spouse_first_name": "Jane",
  "spouse_last_name": "Smith",
  "spouse_ssn": "987654321",
  "spouse_dob": "1987-05-10",
  "street": "123 Main St",
  "city": "Springfield",
  "state": "IL",
  "zip_code": "62701",
  "family_group_name": "The Smith Family"
}
```

All SSN/DOB/street fields are encrypted before storage. Response returns masked values.

**`GET /api/clients/{id}`** — Returns masked PII:

```json
{
  "id": 1,
  "name": "Smith Family",
  "filing_status": "mfj",
  "primary_ssn_masked": "***-**-6789",
  "primary_dob_masked": "**/**/1985",
  "spouse_first_name": "Jane",
  "spouse_last_name": "Smith",
  "spouse_ssn_masked": "***-**-4321",
  "street_masked": "123 M***",
  "city": "Springfield",
  "state": "IL",
  "zip_code": "62701"
}
```

**`POST /api/clients/{id}/reveal-pii`** — Reveal decrypted PII:

Request body specifies which fields to reveal:
```json
{"fields": ["primary_ssn", "primary_dob", "spouse_ssn", "street"]}
```

Response:
```json
{
  "primary_ssn": "123-45-6789",
  "primary_dob": "1985-03-15",
  "spouse_ssn": "987-65-4321",
  "street": "123 Main St"
}
```

Requires `can_view_pii` permission. Returns 403 if user lacks permission.

**`PATCH /api/clients/{id}`** — Update any field (PII fields re-encrypted on write).

### 4.2 Dependent Endpoints (new)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/clients/{id}/dependents` | Add dependent (SSN/DOB encrypted) |
| GET | `/api/clients/{id}/dependents` | List dependents (SSN/DOB masked) |
| PATCH | `/api/clients/{id}/dependents/{dep_id}` | Update dependent |
| DELETE | `/api/clients/{id}/dependents/{dep_id}` | Remove dependent |

**POST request:**
```json
{
  "first_name": "Emily",
  "last_name": "Smith",
  "ssn": "111223333",
  "dob": "2015-06-01",
  "relationship": "daughter",
  "is_qualifying_child": true
}
```

**GET response (masked):**
```json
[{
  "id": 1,
  "first_name": "Emily",
  "last_name": "Smith",
  "ssn_masked": "***-**-3333",
  "dob_masked": "**/**/2015",
  "relationship": "daughter",
  "is_qualifying_child": true
}]
```

### 4.3 Document Field Editing (new)

**`PATCH /api/documents/{id}/fields`**

```json
{"field_name": "box1_wages", "value": "115000.00"}
```

Process:
1. Decrypt `extracted_data` blob
2. Parse JSON dict
3. Update the specified field
4. Re-encrypt and save
5. Reset document status to `"review"` (CPA must re-approve)

Auth: admin, supervisor, preparer.

### 4.4 Validation Endpoint (new)

**`POST /api/clients/{id}/returns/validate`**

Returns validation results without computing taxes:
```json
{
  "results": [
    {"rule_id": "V003", "severity": "ERROR", "message": "MFJ requires spouse", "suggestion": "Add spouse data"},
    {"rule_id": "V001", "severity": "WARNING", "message": "S-Corp K-1 without W-2"}
  ],
  "has_errors": true,
  "skipped_documents": [
    {"document_id": 5, "form_type": "1099-B", "reason": "Failed to parse extracted data"}
  ]
}
```

### 4.5 Draft Response Enrichment

`TaxReturnDraft` response gains:
- `validation_results: list[ValidationResult]` — results from running validation engine
- `skipped_documents: list[SkippedDocument]` — documents the assembler couldn't parse

### 4.6 Permission Update

Add `can_view_pii` to ROLE_PERMISSIONS:
```python
"admin":      {"can_view_pii": True, ...},
"supervisor": {"can_view_pii": True, ...},
"preparer":   {"can_view_pii": False, ...},
"analyst":    {"can_view_pii": False, ...},
```

---

## 5. Assembler Fixes

The `DocumentAssembler` is updated to read real client data:

1. **Decrypt SSN/DOB** from `ClientModel` encrypted columns → build `Person` with real data
2. **Read address** from client → build `Address` with real city/state/zip + decrypted street
3. **Read spouse** from client encrypted fields → build spouse `Person` if present
4. **Query `DependentModel`** → decrypt SSN/DOB → build `Dependent` list
5. **Decrypt `extracted_data`** blob before parsing JSON into form models
6. **Track skipped documents** — instead of silent `except: continue`, collect errors and return them

The assembler receives `PIIEncryptor` via constructor injection.

---

## 6. Directory Structure (new/modified files)

```
api/services/pii/                  # NEW — PII encryption service
├── __init__.py
└── encryptor.py                   # PIIEncryptor class + masking functions

api/db/models.py                   # MODIFIED — add FamilyGroupModel, DependentModel, expand ClientModel
api/models/client.py               # MODIFIED — expand ClientCreate/Response with PII fields
api/models/document.py             # MODIFIED — add SkippedDocument model
api/models/tax_return.py           # MODIFIED — add validation_results + skipped_documents to draft
api/auth/models.py                 # MODIFIED — add can_view_pii to ROLE_PERMISSIONS
api/routers/clients.py             # MODIFIED — expand CRUD with PII, add reveal-pii, dependents
api/routers/documents.py           # MODIFIED — add PATCH /fields, encrypt/decrypt extracted_data
api/routers/tax_returns.py         # MODIFIED — add POST /validate, enrich draft response
api/tax_engine/assembler.py        # MODIFIED — read real client data, decrypt PII, track skipped docs
api/tax_engine/dependencies.py     # MODIFIED — add get_pii_encryptor dependency
requirements-api.txt               # MODIFIED — add cryptography>=43.0
```

---

## 7. Testing Strategy

### Unit Tests
- `test_encryptor.py` — encrypt/decrypt roundtrip, mask_ssn, mask_dob, mask_address, invalid key handling
- `test_dependent_model.py` — CRUD, encryption, decryption

### Integration Tests
- `test_client_pii.py` — create client with PII → GET returns masked → reveal returns plaintext → 403 for unauthorized
- `test_dependents.py` — CRUD dependents with encrypted SSN/DOB
- `test_document_field_edit.py` — edit extracted field, verify re-encryption, status reset
- `test_validation_endpoint.py` — run validation, verify errors returned
- `test_draft_enriched.py` — draft includes validation_results + skipped_documents
- `test_assembler_real_data.py` — assembler reads real client PII instead of placeholders

---

## 8. Scope Summary

| Component | Type | Description |
|-----------|------|-------------|
| PIIEncryptor | New service | Fernet encryption, masking, FastAPI dependency |
| FamilyGroupModel | New table | Family display group |
| DependentModel | New table | Full dependent details with encrypted SSN/DOB |
| ClientModel | Expanded | PII encrypted columns, family_group FK, address |
| DocumentModel | Modified | extracted_data encrypted (LargeBinary) |
| Client endpoints | Modified | PII create/update/mask/reveal + dependent CRUD |
| Document endpoints | Modified | Field editing with re-encryption |
| Validation endpoint | New | Pre-filing validation check |
| Draft response | Enriched | Includes validation + skipped docs |
| Assembler | Fixed | Reads real client data, decrypts PII, tracks errors |
| ROLE_PERMISSIONS | Modified | `can_view_pii` added |
| Dependencies | Modified | `cryptography>=43.0` added |

### Out of Scope
- Per-organization encryption keys
- PII audit logging (who viewed what PII when)
- Frontend PII reveal UI changes
- Data migration of existing plaintext extracted_data
- Phone/email fields (not needed for tax filing)
