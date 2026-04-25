# Multi-Year Draft Storage & YoY Comparison — Design Spec

## Goal

Enable real year-over-year tax return comparison by storing drafts per year and allowing import of prior-year 1040 PDFs. CPAs can verify YoY changes with provenance tracking back to the source document.

## Architecture

The current `TaxReturnDraftModel` stores one draft per client (upsert overwrites). This change makes it one draft per client per year, adds source tracking (computed vs imported), and wires the existing YoY UI to real data instead of mock data.

Two data paths feed prior-year drafts:
1. **Computed** — when the system computes a return, the draft is archived by year automatically.
2. **Imported** — CPA uploads a prior-year 1040 PDF, OCR extracts line items, system creates an archived draft linked to the source document.

---

## 1. Database Schema

### TaxReturnDraftModel changes

**New columns:**
- `source_type: str` — `"computed"` or `"imported"`. Default `"computed"`. NOT NULL.
- `source_document_id: str | None` — FK to `documents.id`. NULL for computed drafts. Links imported drafts to the uploaded 1040 PDF.

**Unique constraint change:**
- Drop: `UNIQUE(org_id, client_id)`
- Add: `UNIQUE(org_id, client_id, tax_year)`

**Alembic migration:**
- Add `source_type` column with default `"computed"` (backfills existing rows)
- Add `source_document_id` column, nullable
- Drop old unique constraint, create new one including `tax_year`

### New form type

Add `"1040-Prior"` to the recognized form types for document uploads. This is a display/classification label — no new DB table needed.

---

## 2. Service Layer

### TaxReturnService changes

**`compute_and_save_draft()`** — modify upsert WHERE clause:
- Current: `WHERE org_id = ? AND client_id = ?`
- New: `WHERE org_id = ? AND client_id = ? AND tax_year = ?`
- Set `source_type = "computed"`, `source_document_id = NULL`

**`get_draft(tax_year: int | None)`** — add optional `tax_year` parameter:
- If provided, fetch draft for that year
- If omitted, default to `client.tax_year`

**`get_prior_year_draft(client_id, session, user)`** — new method:
- Fetch draft WHERE `tax_year = client.tax_year - 1`
- Return the draft plus source metadata (`source_type`, `source_document_id`)
- Return `None` if no prior-year draft exists

**`import_prior_year(client_id, document_id, tax_year, lines, session, user)`** — new method:
- Accept extracted 1040 line data as a list of `ReturnLine`
- Build a `TaxReturnDraft` from the lines (compute totals: total_income, total_deductions, taxable_income, total_tax, total_payments, refund_or_owed, effective_rate)
- Save as `TaxReturnDraftModel` with `source_type="imported"`, `source_document_id=document_id`
- Upsert by `(org_id, client_id, tax_year)` so re-importing overwrites

### Comparison engine changes

**`compare_years()`** — modify to use stored prior-year draft when available:
- Try loading stored draft for `prior_year` from DB
- If found: deserialize `draft_json` → build `TaxResult`-compatible structure for comparison
- If not found: fall back to current synthetic comparison (assemble + recompute with prior-year constants)

---

## 3. Prior-Year 1040 Extraction

### OCR extraction for "1040-Prior"

Use the existing Claude OCR extractor with a new prompt targeting prior-year 1040 fields. Extract these Form 1040 lines:

| Line | Label | Field key |
|------|-------|-----------|
| 1a | Wages, salaries, tips | `line_1a` |
| 2b | Taxable interest | `line_2b` |
| 3b | Qualified dividends | `line_3b` |
| 7 | Capital gain/loss | `line_7` |
| 8 | Other income | `line_8` |
| 9 | Total income | `line_9` |
| 12 | Standard/itemized deduction | `line_12` |
| 13a | Qualified business income deduction | `line_13a` |
| 15 | Taxable income | `line_15` |
| 16 | Tax | `line_16` |
| 24 | Total tax | `line_24` |
| 25a | W-2 withholding | `line_25a` |
| 25b | 1099 withholding | `line_25b` |
| 25c | Other withholding | `line_25c` |
| 26 | Estimated tax payments | `line_26` |
| 33 | Total payments | `line_33` |
| 35a | Refund | `line_35a` |
| 37 | Amount owed | `line_37` |

Also extract: `tax_year` from the 1040 header, `filing_status` from the checkbox section.

### Field mapping

Add a `map_prior_1040_to_draft()` function in a new module `api/tax_engine/prior_year_import.py`:
- Takes extracted field dict → builds `TaxReturnDraft` with `ReturnLine` entries
- Computes `effective_rate = total_tax / total_income * 100` (if total_income > 0)
- Sets section labels (income, deductions, tax_credits, payments) matching the current `_extract_lines` logic

---

## 4. API Endpoints

### Modified

**`GET /api/clients/{id}/returns/draft`**
- Add optional query param: `?tax_year=N`
- Default: client's current tax year

### New

**`GET /api/clients/{id}/returns/prior-year`**
- Returns: `{ draft: TaxReturnDraft | null, source_type: str, source_document_id: str | null }`
- Fetches draft for `client.tax_year - 1`

**`POST /api/clients/{id}/returns/import-prior`**
- Body: `{ document_id: str, tax_year: int }`
- Triggers extraction from the referenced document, then creates/upserts the archived draft
- Returns the created `TaxReturnDraft`
- Validates: document exists, belongs to client, is form_type "1040-Prior"

---

## 5. Frontend Changes

### Tax Return tab (`return-preview.tsx`)

- Replace mock prior-year data with real API call to `GET /prior-year`
- If prior-year draft exists: show inline YoY deltas (existing UI) + source badge
- Source badge: "Computed" (checkmark icon) or "Imported" (document icon, clickable → opens source PDF in document viewer)
- If no prior-year draft: hide YoY badges, show subtle "No prior year data" note

### Page.tsx wiring

- Replace `mockPriorYearDrafts[numId]` lookup with `api.returns.priorYear(clientId)` call
- Store `priorYearDraft` and `priorYearSource` in state
- Pass to `ReturnPreview` as props

### api-client.ts

- Add `priorYear(clientId): Promise<PriorYearResponse>` method
- Add `importPrior(clientId, documentId, taxYear): Promise<TaxReturnDraft>` method
- Add `PriorYearResponse` type: `{ draft: TaxReturnDraft | null, source_type: string, source_document_id: string | null }`

### Document upload (document-manager-modal.tsx)

- Add "1040-Prior" to form type dropdown options
- After successful upload + extraction of a 1040-Prior document: auto-call `POST /import-prior` with the document ID and extracted tax year
- Show toast: "Prior year return imported — YoY comparison is now available"

---

## 6. Provenance & Cross-Verification

Every `TaxReturnDraftModel` row carries:
- `source_type` — tells the CPA whether the number is system-computed or imported
- `source_document_id` — for imported drafts, links directly to the uploaded 1040 PDF

The frontend surfaces this as a clickable badge. Clicking opens the source document in the existing document viewer modal, allowing the CPA to cross-verify any line value against the original filing.

---

## 7. Testing

- **Schema migration**: test that existing single-year drafts survive the migration with `source_type="computed"`
- **Multi-year upsert**: test that computing drafts for 2024 and 2025 for the same client creates two rows
- **Prior-year import**: test extraction → draft creation pipeline with a sample 1040 PDF
- **Comparison fallback**: test that comparison uses stored draft when available, falls back to synthetic when not
- **API endpoints**: test GET /prior-year returns null when no prior, returns draft when exists
- **Frontend**: verify YoY badges show/hide based on prior-year data availability; verify source badge click opens document

---

## Out of Scope

- Schedule-level extraction from prior-year returns (only Form 1040 lines)
- Multi-year comparison beyond adjacent years (e.g., 2025 vs 2023)
- Importing prior-year data from third-party tax software formats (only IRS 1040 PDF)
- Editing imported prior-year line values (re-upload to correct)
