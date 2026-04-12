# TaxFlow AI — UI Refinements Design Spec

**Date:** 2026-04-12
**Status:** Approved
**Scope:** Sidebar simplification, document card redesign, PDF.js viewer, dark mode contrast fixes

---

## 1. Sidebar Simplification

Remove the accordion document expansion from the client sidebar. When a client is selected, the sidebar no longer shows nested year headers and document names.

**Before:** Active client expands to show `years[].docs[]` — a nested list of "2025: W-2 (John), W-2 (Jane), 1099-INT, 1098".

**After:** Active client shows only the client row (name, meta, badge) with the blue left border and white/surface background. No expansion. No nested content.

**Changes:**
- `components/layout/client-sidebar.tsx`: Remove the entire `{isActive && client.years && (...)}` accordion block (lines 104-115 in current file).
- The `Client` interface keeps the optional `years` field for backward compatibility — it's simply not rendered.

---

## 2. Document Card Redesign (Work Panel)

### Remove Top-Level Flag Banner

The `flagMessage` warning div at the top of the Documents tab is removed. Issues are shown inline within each document card.

### New Card Layout

Each document card uses a two-column layout:

**Left column:** Grid of key-value pairs from extracted data. Labels on left, values on right. Uses the existing extracted data parsing logic.

**Right column:** 
- Confidence: progress bar + percentage
- Status badge (verified/flagged/pending)
- Flags inline: orange warning icon + flag text, shown only if the document has flags

**Card header:** 
- Left: Document name (bold) + subtitle line (employer/payer name from extracted data + "TY 2025")
- Right: Confidence percentage + status icon (green checkmark for verified, orange warning for flagged, gray dot for pending)

**Divider:** A thin `border-divider` line separates the header from the body.

### Data Display Rules

Key-value pairs to show, by form type:

**W-2:** wages, federal_tax_withheld, social_security_wages, social_security_tax, medicare_wages, medicare_tax, state + state_tax

**1099-INT:** interest_income, federal_tax_withheld, early_withdrawal_penalty

**1098:** mortgage_interest, real_estate_taxes, outstanding_principal

**Fallback:** Show all non-null extracted fields as key-value pairs.

Currency values formatted as `$XX,XXX`.

---

## 3. PDF.js Document Viewer Modal

### Architecture

Replace the form renderer (W2Form, Form1099Int, GenericForm) in the document viewer modal with a PDF.js-powered viewer. The modal becomes a two-column layout: PDF on the left, extracted fields on the right.

### PDF Source Mapping

Sample PDFs from `data/input-forms/` are copied to `frontend/public/sample-forms/` for static serving:

| form_type | PDF file |
|---|---|
| `W-2` | `/sample-forms/fw2.pdf` |
| `1099-INT`, `1099-DIV` | `/sample-forms/f1099div.pdf` |
| `1099-NEC`, `1099-MISC` | `/sample-forms/f1099msc.pdf` |
| `1098`, `K-1`, fallback | `/sample-forms/f1065sk1.pdf` |

### PdfViewer Component

**File:** `components/documents/pdf-viewer.tsx`

**Props:**
```typescript
interface PdfViewerProps {
  src: string;        // URL to the PDF file
  className?: string;
}
```

**Behavior:**
- Uses `pdfjs-dist` to load and render PDF pages onto `<canvas>`
- Renders one page at a time
- Page navigation: prev/next buttons + "Page X of Y" label
- Zoom: +/- buttons, default scale fits the container width
- Loading state: skeleton placeholder while PDF loads
- Error state: "Unable to load document preview" fallback message
- The canvas is wrapped in a scrollable container

**Dependencies:**
- `pdfjs-dist` — add to `package.json`
- PDF.js worker: configure via `pdfjs.GlobalWorkerOptions.workerSrc` pointing to the CDN worker or bundled worker

### Updated DocumentViewerModal Layout

```
┌──────────────────────────────────────────────────────┐
│  [Title]  [Status Badge]                     [Close] │
├──────────────────────────┬───────────────────────────┤
│                          │  Extracted Fields          │
│   PdfViewer              │                           │
│   (src mapped by         │  key: value               │
│    form_type)            │  key: value               │
│                          │  key: value               │
│   [< Page 1/3 >]        │  ...                      │
│   [- zoom +]             │                           │
│                          │  ⚠ Flag text (if any)     │
├──────────────────────────┴───────────────────────────┤
│  AI Confidence: [====] 97%          [Close] [Approve]│
└──────────────────────────────────────────────────────┘
```

**Right column (Extracted Fields):** Always shown for all documents (not just flagged ones). Each field is a read-only label + value pair. Flagged fields get an orange warning icon + flag description below them. Editable inputs only for flagged fields (existing behavior preserved).

**The FormRenderer, W2Form, Form1099Int, GenericForm components remain in the codebase** but are no longer imported by the document viewer modal. They may be used elsewhere or removed in a future cleanup pass.

### PDF file serving

Helper function to map form_type to PDF path:

```typescript
function getPdfUrl(formType: string): string {
  switch (formType) {
    case "W-2": return "/sample-forms/fw2.pdf";
    case "1099-INT":
    case "1099-DIV": return "/sample-forms/f1099div.pdf";
    case "1099-NEC":
    case "1099-MISC": return "/sample-forms/f1099msc.pdf";
    default: return "/sample-forms/f1065sk1.pdf";
  }
}
```

---

## 4. Dark Mode Contrast Fixes

### Problem Summary

1. Chat assistant bubble (`#1c1c1e`) is identical to surface (`#1c1c1e`) — invisible bubble
2. Chat user bubble (`#2c2c2e`) is barely distinguishable from background
3. Pure black background (`#000000`) is harsh for a productivity app
4. Text secondary (`#a1a1a6`) is too dim for extended reading
5. Dividers (`rgba(255,255,255,0.08)`) are nearly invisible

### Updated Dark Theme Tokens

Replace the `[data-theme="dark"]` block in `globals.css`:

```css
[data-theme="dark"] {
  --t-bg: #161618;
  --t-surface: #1e1e20;
  --t-surface-secondary: #2a2a2c;
  --t-surface-tertiary: #3a3a3c;
  --t-text: #f5f5f7;
  --t-text-secondary: #ababaf;
  --t-text-tertiary: #78787e;
  --t-divider: rgba(255, 255, 255, 0.12);
  --t-nav-bg: rgba(22, 22, 24, 0.72);
  --t-nav-border: rgba(255, 255, 255, 0.10);
  --t-chat-user: #2f3037;
  --t-chat-assistant: #262628;
  --t-form-header: #2a4a6f;
  --t-shadow: rgba(0, 0, 0, 0.5);

  /* Badge tokens — unchanged */
  --t-badge-pending-bg: rgba(142, 142, 147, 0.2);
  --t-badge-pending-text: #a1a1a6;
  --t-badge-progress-bg: rgba(10, 132, 255, 0.2);
  --t-badge-progress-text: #64d2ff;
  --t-badge-review-bg: rgba(255, 159, 10, 0.2);
  --t-badge-review-text: #ffd60a;
  --t-badge-complete-bg: rgba(48, 209, 88, 0.2);
  --t-badge-complete-text: #30d158;
  --t-badge-filed-bg: rgba(191, 90, 242, 0.2);
  --t-badge-filed-text: #bf5af2;

  color-scheme: dark;
}
```

### Token Change Summary

| Token | Old | New | Reason |
|---|---|---|---|
| `--t-bg` | `#000000` | `#161618` | Softer, matches GitHub/Linear dark |
| `--t-surface` | `#1c1c1e` | `#1e1e20` | Better contrast against bg |
| `--t-surface-secondary` | `#2c2c2e` | `#2a2a2c` | Stays distinct |
| `--t-text-secondary` | `#a1a1a6` | `#ababaf` | More readable |
| `--t-text-tertiary` | `#6e6e73` | `#78787e` | Labels were too dim |
| `--t-divider` | `rgba(255,255,255,0.08)` | `rgba(255,255,255,0.12)` | Borders now visible |
| `--t-nav-bg` | `rgba(29,29,31,0.72)` | `rgba(22,22,24,0.72)` | Matches new bg |
| `--t-nav-border` | `rgba(255,255,255,0.08)` | `rgba(255,255,255,0.10)` | Slightly stronger |
| `--t-chat-user` | `#2c2c2e` | `#2f3037` | Cool-tinted, distinct bubble |
| `--t-chat-assistant` | `#1c1c1e` | `#262628` | No longer invisible — elevated from surface |
| `--t-shadow` | `rgba(0,0,0,0.4)` | `rgba(0,0,0,0.5)` | Stronger shadows on darker bg |

---

## 5. New File Inventory

### New Files

| File | Purpose |
|---|---|
| `components/documents/pdf-viewer.tsx` | PDF.js canvas renderer with page nav + zoom |
| `public/sample-forms/fw2.pdf` | Sample W-2 PDF (copied from data/input-forms/) |
| `public/sample-forms/f1099div.pdf` | Sample 1099-DIV PDF |
| `public/sample-forms/f1099msc.pdf` | Sample 1099-MISC PDF |
| `public/sample-forms/f1065sk1.pdf` | Sample K-1 PDF (fallback) |

### Modified Files

| File | Changes |
|---|---|
| `app/globals.css` | Dark theme token values updated |
| `components/layout/client-sidebar.tsx` | Remove accordion expansion block |
| `components/documents/document-viewer-modal.tsx` | Replace FormRenderer with PdfViewer + extracted fields layout |
| `app/page.tsx` | Redesign document cards in work panel, remove top flag banner |
| `package.json` | Add `pdfjs-dist` dependency |

---

## 6. Implementation Priority

1. **Dark mode contrast fixes** — globals.css token update (smallest change, biggest visual impact)
2. **Sidebar simplification** — remove accordion block
3. **Document card redesign** — new two-column card layout in page.tsx work panel
4. **PDF.js viewer** — new component + modal rewrite + static PDF files
