# UI Refinements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix dark mode contrast, simplify sidebar, redesign document cards, and add PDF.js document viewer.

**Architecture:** Dark mode token updates in globals.css, sidebar accordion removal, document card two-column layout in page.tsx work panel, new PdfViewer component using pdfjs-dist with sample PDFs served from public/.

**Tech Stack:** pdfjs-dist, Next.js 16, React 19, Tailwind CSS 4

**Spec:** `docs/superpowers/specs/2026-04-12-ui-refinements-design.md`

---

## Task 1: Dark Mode Contrast Fixes

**Files:**
- Modify: `frontend/app/globals.css`

- [ ] **Step 1: Update dark theme tokens**

In `frontend/app/globals.css`, replace the entire `[data-theme="dark"]` block (lines 102-130) with:

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

Key changes from current:
- `--t-bg`: `#000000` → `#161618` (softer background)
- `--t-surface`: `#1c1c1e` → `#1e1e20` (better contrast against bg)
- `--t-surface-secondary`: `#2c2c2e` → `#2a2a2c`
- `--t-text-secondary`: `#a1a1a6` → `#ababaf` (brighter)
- `--t-text-tertiary`: `#6e6e73` → `#78787e` (brighter)
- `--t-divider`: `0.08` → `0.12` opacity (visible borders)
- `--t-nav-bg`: updated to match new bg
- `--t-nav-border`: `0.08` → `0.10`
- `--t-chat-user`: `#2c2c2e` → `#2f3037` (cool-tinted distinct bubble)
- `--t-chat-assistant`: `#1c1c1e` → `#262628` (no longer identical to surface)
- `--t-shadow`: `0.4` → `0.5` opacity

- [ ] **Step 2: Verify build**

Run: `cd /Users/admin-h26/taxflow-kb/frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
cd /Users/admin-h26/taxflow-kb
git add frontend/app/globals.css
git commit -m "fix(frontend): improve dark mode contrast — softer bg, visible chat bubbles, stronger dividers"
```

---

## Task 2: Sidebar Simplification

**Files:**
- Modify: `frontend/components/layout/client-sidebar.tsx`

- [ ] **Step 1: Remove the accordion expansion block**

In `frontend/components/layout/client-sidebar.tsx`, delete lines 104-115 — the block that renders nested year/doc content when a client is active. The block to remove is:

```tsx
              {isActive && client.years && (
                <div className="bg-surface border-l-3 border-l-apple-blue px-3 pb-2">
                  {client.years.map((y) => (
                    <div key={y.year} className="mt-1">
                      <div className="text-[10px] font-semibold text-tertiary uppercase tracking-wider mb-0.5 pl-3">{y.year}</div>
                      {y.docs.map((doc) => (
                        <div key={doc} className="text-[11px] text-secondary pl-3 py-1 rounded hover:bg-surface-secondary cursor-pointer transition-colors">{doc}</div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
```

Remove this entire block. Leave the closing `</div>` for the client row's parent `<div key={client.id}>`.

After removal, the map body should look like:

```tsx
        {filtered.map((client) => {
          const isActive = client.id === activeClientId;
          return (
            <div key={client.id}>
              <div
                role="button"
                tabIndex={0}
                onClick={() => onSelectClient(client.id)}
                onKeyDown={(e) => { if (e.key === "Enter") onSelectClient(client.id); }}
                className={cn(
                  "w-full flex items-center gap-2.5 px-3 py-2.5 text-left transition-all cursor-pointer border-l-3",
                  isActive
                    ? "bg-surface border-l-apple-blue shadow-sm"
                    : "hover:bg-surface/60 border-l-transparent"
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className={cn("text-[13px] truncate transition-all", isActive ? "font-semibold text-primary" : "font-medium text-secondary")}>
                    {client.name}
                  </div>
                  <div className={cn("text-[11px] truncate", isActive ? "text-secondary" : "text-tertiary")}>
                    {client.meta}
                  </div>
                </div>
                <Badge variant={client.status as BadgeVariant}>
                  {statusLabels[client.status] ?? client.status}
                </Badge>
              </div>
            </div>
          );
        })}
```

- [ ] **Step 2: Verify build**

Run: `cd /Users/admin-h26/taxflow-kb/frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
cd /Users/admin-h26/taxflow-kb
git add frontend/components/layout/client-sidebar.tsx
git commit -m "refine(frontend): remove sidebar document accordion — cleaner client list"
```

---

## Task 3: Document Card Redesign

**Files:**
- Modify: `frontend/app/page.tsx` (work panel document rendering, lines ~577-665)

- [ ] **Step 1: Replace the document card rendering in the work panel**

In `frontend/app/page.tsx`, find the `{activeWorkTab === "Documents" && (` block inside `workPanelContent`. Replace the entire Documents tab content (from the opening `<div className="space-y-3">` through its closing `</div>`) with this new version:

```tsx
          <div className="space-y-3">
            {documents.map((doc) => {
              const data = (() => { try { return JSON.parse(doc.extracted_data); } catch { return {}; } })();
              const flags: string[] = (() => { try { return JSON.parse(doc.flags || "[]"); } catch { return []; } })();
              const fmt = (v: number | undefined) => v != null ? `$${v.toLocaleString()}` : "\u2014";

              // Determine subtitle from extracted data
              const subtitle = data.employer_name || data.payer_name || data.lender_name || doc.form_type;

              // Build key-value pairs based on form type
              const kvPairs: { label: string; value: string }[] = [];
              if (doc.form_type === "W-2") {
                if (data.wages != null) kvPairs.push({ label: "Wages", value: fmt(data.wages) });
                if (data.federal_tax_withheld != null) kvPairs.push({ label: "Fed W/H", value: fmt(data.federal_tax_withheld) });
                if (data.social_security_tax != null) kvPairs.push({ label: "SS Tax", value: fmt(data.social_security_tax) });
                if (data.medicare_tax != null) kvPairs.push({ label: "Medicare", value: fmt(data.medicare_tax) });
                if (data.state && data.state_tax != null) kvPairs.push({ label: `${data.state} Tax`, value: fmt(data.state_tax) });
              } else if (doc.form_type === "1099-INT") {
                if (data.interest_income != null) kvPairs.push({ label: "Interest", value: fmt(data.interest_income) });
                if (data.federal_tax_withheld != null) kvPairs.push({ label: "Fed W/H", value: fmt(data.federal_tax_withheld) });
              } else if (doc.form_type === "1098") {
                if (data.mortgage_interest != null) kvPairs.push({ label: "Mort. Int.", value: fmt(data.mortgage_interest) });
                if (data.real_estate_taxes != null) kvPairs.push({ label: "RE Taxes", value: fmt(data.real_estate_taxes) });
                if (data.outstanding_principal != null) kvPairs.push({ label: "Principal", value: fmt(data.outstanding_principal) });
              } else {
                // Generic: show all numeric fields
                Object.entries(data).forEach(([key, val]) => {
                  if (typeof val === "number") kvPairs.push({ label: key.replace(/_/g, " "), value: fmt(val) });
                });
              }

              const statusIcon = doc.status === "verified" ? "\u2713" : doc.status === "flagged" ? "\u26A0" : "\u2022";
              const statusColor = doc.status === "verified" ? "text-green-600 dark:text-green-400" : doc.status === "flagged" ? "text-orange-500" : "text-tertiary";

              return (
                <button
                  key={doc.id}
                  onClick={() => { setViewerDoc(doc); setViewerOpen(true); }}
                  className="w-full text-left cursor-pointer"
                >
                  <Card className="p-0 overflow-hidden hover:shadow-md transition-shadow">
                    {/* Header */}
                    <div className="flex items-center justify-between px-3 pt-3 pb-2">
                      <div className="min-w-0">
                        <div className="text-[13px] font-medium text-primary truncate">{doc.name}</div>
                        <div className="text-[11px] text-tertiary truncate">{subtitle} &middot; TY 2025</div>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0 ml-2">
                        <span className="text-[12px] font-medium text-secondary">{doc.confidence}%</span>
                        <span className={`text-[14px] ${statusColor}`}>{statusIcon}</span>
                      </div>
                    </div>

                    {/* Divider */}
                    <div className="border-t border-divider mx-3" />

                    {/* Body: two columns */}
                    <div className="flex gap-3 px-3 py-2.5">
                      {/* Left: key-value pairs */}
                      <div className="flex-1 min-w-0">
                        <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[11px]">
                          {kvPairs.map((kv) => (
                            <React.Fragment key={kv.label}>
                              <span className="text-tertiary whitespace-nowrap">{kv.label}</span>
                              <span className="text-primary font-medium text-right">{kv.value}</span>
                            </React.Fragment>
                          ))}
                        </div>
                      </div>

                      {/* Right: confidence + status + flags */}
                      <div className="w-28 shrink-0 space-y-1.5">
                        <div>
                          <div className="text-[10px] text-tertiary uppercase">Confidence</div>
                          <Progress value={doc.confidence} color={doc.confidence >= 90 ? "green" : doc.confidence >= 70 ? "orange" : "red"} className="mt-1" />
                          <div className="text-[11px] font-medium text-primary mt-0.5">{doc.confidence}%</div>
                        </div>
                        <Badge variant={doc.status === "verified" ? "completed" : doc.status === "flagged" ? "review" : "pending"}>
                          {doc.status === "verified" ? "Verified" : doc.status === "flagged" ? "Flagged" : "Pending"}
                        </Badge>
                        {flags.length > 0 && (
                          <div className="space-y-1">
                            {flags.map((flag, i) => (
                              <div key={i} className="text-[10px] text-badge-review-text leading-tight">
                                <span className="mr-0.5">&#9888;</span>{flag}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </Card>
                </button>
              );
            })}
          </div>
```

- [ ] **Step 2: Remove the top-level flag banner**

In the same `workPanelContent` block, remove the `flagMessage` banner. Find and delete:

```tsx
            {flagMessage && (
              <div className="bg-badge-review-bg text-badge-review-text text-[12px] px-3 py-2 rounded-lg">
                &#9888; {flagMessage}
              </div>
            )}
```

Also remove the `flagMessage` variable declaration (around line 551-555):

```tsx
  const flagMessage =
    documents.filter((d) => d.status === "flagged" || d.status === "pending")
      .length > 0
      ? `${documents.filter((d) => d.status === "flagged" || d.status === "pending").length} documents need review before filing`
      : "";
```

Keep the `flagCount` variable if it exists (used by the bottom tab bar badge), or ensure `flagCount` is still computed. If `flagCount` doesn't exist as a separate variable, add it where `flagMessage` was:

```tsx
  const flagCount = documents.filter((d) => d.status === "flagged" || d.status === "pending").length;
```

- [ ] **Step 3: Add React import for Fragment**

At the top of `page.tsx`, ensure `React` is available for `React.Fragment`. Add this import if not already present:

```tsx
import React from "react";
```

Or alternatively, replace `React.Fragment` in the card code with the shorthand `<>...</>` — but since we're using it inside `.map()` with a `key` prop, we need the explicit `React.Fragment` or import `Fragment`:

```tsx
import { useState, useEffect, useCallback, useRef, Fragment } from "react";
```

Then use `<Fragment key={kv.label}>` instead of `<React.Fragment key={kv.label}>`.

- [ ] **Step 4: Ensure Progress import exists**

Verify that `Progress` is imported at the top of `page.tsx`. It should already be imported from a previous task. If not, add:

```tsx
import { Progress } from "@/components/ui/progress";
```

- [ ] **Step 5: Verify build**

Run: `cd /Users/admin-h26/taxflow-kb/frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 6: Commit**

```bash
cd /Users/admin-h26/taxflow-kb
git add frontend/app/page.tsx
git commit -m "refine(frontend): redesign document cards — two-column layout with inline flags"
```

---

## Task 4: Install pdfjs-dist and Copy Sample PDFs

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/public/sample-forms/fw2.pdf` (copy)
- Create: `frontend/public/sample-forms/f1099div.pdf` (copy)
- Create: `frontend/public/sample-forms/f1099msc.pdf` (copy)
- Create: `frontend/public/sample-forms/f1065sk1.pdf` (copy)

- [ ] **Step 1: Install pdfjs-dist**

```bash
cd /Users/admin-h26/taxflow-kb/frontend && npm install pdfjs-dist
```

- [ ] **Step 2: Copy sample PDFs to public directory**

```bash
mkdir -p /Users/admin-h26/taxflow-kb/frontend/public/sample-forms
cp /Users/admin-h26/taxflow-kb/data/input-forms/fw2.pdf /Users/admin-h26/taxflow-kb/frontend/public/sample-forms/
cp /Users/admin-h26/taxflow-kb/data/input-forms/f1099div.pdf /Users/admin-h26/taxflow-kb/frontend/public/sample-forms/
cp /Users/admin-h26/taxflow-kb/data/input-forms/f1099msc.pdf /Users/admin-h26/taxflow-kb/frontend/public/sample-forms/
cp /Users/admin-h26/taxflow-kb/data/input-forms/f1065sk1.pdf /Users/admin-h26/taxflow-kb/frontend/public/sample-forms/
```

- [ ] **Step 3: Verify build**

Run: `cd /Users/admin-h26/taxflow-kb/frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
cd /Users/admin-h26/taxflow-kb
git add frontend/package.json frontend/package-lock.json frontend/public/sample-forms/
git commit -m "feat(frontend): add pdfjs-dist dependency and sample PDF forms"
```

---

## Task 5: PdfViewer Component

**Files:**
- Create: `frontend/components/documents/pdf-viewer.tsx`

- [ ] **Step 1: Create the PdfViewer component**

```tsx
// frontend/components/documents/pdf-viewer.tsx
"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Skeleton } from "@/components/ui/skeleton";

interface PdfViewerProps {
  src: string;
  className?: string;
}

export function PdfViewer({ src, className }: PdfViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [scale, setScale] = useState(1.2);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pdfDocRef = useRef<any>(null);

  const renderPage = useCallback(async (pageNum: number, renderScale: number) => {
    const pdfDoc = pdfDocRef.current;
    if (!pdfDoc || !canvasRef.current) return;

    try {
      const page = await pdfDoc.getPage(pageNum);
      const viewport = page.getViewport({ scale: renderScale });
      const canvas = canvasRef.current;
      const context = canvas.getContext("2d");
      if (!context) return;

      canvas.height = viewport.height;
      canvas.width = viewport.width;

      await page.render({ canvasContext: context, viewport }).promise;
    } catch (err) {
      console.error("Error rendering page:", err);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadPdf() {
      setLoading(true);
      setError(null);

      try {
        const pdfjsLib = await import("pdfjs-dist");
        pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.mjs`;

        const loadingTask = pdfjsLib.getDocument(src);
        const pdfDoc = await loadingTask.promise;

        if (cancelled) return;

        pdfDocRef.current = pdfDoc;
        setNumPages(pdfDoc.numPages);
        setCurrentPage(1);
        setLoading(false);

        await renderPage(1, scale);
      } catch (err) {
        if (!cancelled) {
          setError("Unable to load document preview");
          setLoading(false);
          console.error("PDF load error:", err);
        }
      }
    }

    loadPdf();
    return () => { cancelled = true; };
  }, [src]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!loading && pdfDocRef.current) {
      renderPage(currentPage, scale);
    }
  }, [currentPage, scale, loading, renderPage]);

  const prevPage = () => setCurrentPage((p) => Math.max(1, p - 1));
  const nextPage = () => setCurrentPage((p) => Math.min(numPages, p + 1));
  const zoomIn = () => setScale((s) => Math.min(3, s + 0.2));
  const zoomOut = () => setScale((s) => Math.max(0.5, s - 0.2));

  if (error) {
    return (
      <div className={`flex items-center justify-center h-64 text-secondary text-[13px] ${className || ""}`}>
        {error}
      </div>
    );
  }

  return (
    <div className={className}>
      {/* Controls */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1">
          <button onClick={prevPage} disabled={currentPage <= 1} className="w-7 h-7 rounded-lg flex items-center justify-center text-secondary hover:bg-surface-secondary disabled:opacity-30 transition-colors cursor-pointer text-[12px]" aria-label="Previous page">
            &larr;
          </button>
          <span className="text-[11px] text-secondary min-w-[60px] text-center">
            {loading ? "\u2014" : `${currentPage} / ${numPages}`}
          </span>
          <button onClick={nextPage} disabled={currentPage >= numPages} className="w-7 h-7 rounded-lg flex items-center justify-center text-secondary hover:bg-surface-secondary disabled:opacity-30 transition-colors cursor-pointer text-[12px]" aria-label="Next page">
            &rarr;
          </button>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={zoomOut} className="w-7 h-7 rounded-lg flex items-center justify-center text-secondary hover:bg-surface-secondary transition-colors cursor-pointer text-[13px]" aria-label="Zoom out">
            &minus;
          </button>
          <span className="text-[11px] text-tertiary min-w-[36px] text-center">{Math.round(scale * 100)}%</span>
          <button onClick={zoomIn} className="w-7 h-7 rounded-lg flex items-center justify-center text-secondary hover:bg-surface-secondary transition-colors cursor-pointer text-[13px]" aria-label="Zoom in">
            +
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div className="overflow-auto rounded-lg border border-divider bg-surface-tertiary max-h-[55vh]">
        {loading ? (
          <div className="p-4 space-y-3">
            <Skeleton className="h-6 w-[80%]" />
            <Skeleton className="h-4 w-[60%]" />
            <Skeleton className="h-4 w-[70%]" />
            <Skeleton className="h-64 w-full" />
          </div>
        ) : (
          <canvas ref={canvasRef} className="mx-auto block" />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd /Users/admin-h26/taxflow-kb/frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
cd /Users/admin-h26/taxflow-kb
git add frontend/components/documents/pdf-viewer.tsx
git commit -m "feat(frontend): add PdfViewer component using pdfjs-dist"
```

---

## Task 6: Rewrite Document Viewer Modal with PDF.js

**Files:**
- Modify: `frontend/components/documents/document-viewer-modal.tsx`

- [ ] **Step 1: Replace the entire document-viewer-modal.tsx**

```tsx
// frontend/components/documents/document-viewer-modal.tsx
"use client";

import { useState, Fragment } from "react";
import { Modal, ModalHeader, ModalBody, ModalFooter } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { PdfViewer } from "@/components/documents/pdf-viewer";

interface DocumentData {
  id: number;
  form_type: string;
  title: string;
  status: string;
  confidence: number;
  extracted_data: string;
  flags: string;
}

interface DocumentViewerModalProps {
  open: boolean;
  onClose: () => void;
  document: DocumentData | null;
  onApprove?: (docId: number) => void;
}

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

export function DocumentViewerModal({
  open,
  onClose,
  document: doc,
  onApprove,
}: DocumentViewerModalProps) {
  const [editedFields, setEditedFields] = useState<Record<string, string>>({});

  if (!doc) return null;

  let parsedData: Record<string, unknown> = {};
  try {
    parsedData = doc.extracted_data ? JSON.parse(doc.extracted_data) : {};
  } catch {
    parsedData = {};
  }

  let parsedFlags: string[] = [];
  try {
    parsedFlags = doc.flags ? JSON.parse(doc.flags) : [];
  } catch {
    parsedFlags = doc.flags ? [doc.flags] : [];
  }

  const handleFieldEdit = (key: string, value: string) => {
    setEditedFields((prev) => ({ ...prev, [key]: value }));
  };

  const isFlagged = (key: string) =>
    parsedFlags.some((f) => f.toLowerCase().includes(key.toLowerCase().replace(/_/g, " ")));

  const fmt = (val: unknown) => {
    if (typeof val === "number") return `$${val.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
    return String(val ?? "");
  };

  return (
    <Modal open={open} onClose={onClose} className="max-w-5xl">
      <ModalHeader onClose={onClose}>
        <div className="flex items-center gap-3">
          <span>{doc.title}</span>
          <Badge
            variant={doc.status === "verified" ? "completed" : doc.status === "flagged" ? "review" : "pending"}
          >
            {doc.status}
          </Badge>
        </div>
      </ModalHeader>

      <ModalBody className="max-h-[65vh] p-0">
        <div className="grid grid-cols-2 max-md:grid-cols-1 h-full">
          {/* Left: PDF viewer */}
          <div className="p-4 border-r border-divider max-md:border-r-0 max-md:border-b">
            <PdfViewer src={getPdfUrl(doc.form_type)} />
          </div>

          {/* Right: Extracted fields */}
          <div className="p-4 overflow-y-auto">
            <div className="text-[13px] font-semibold text-primary mb-3">
              Extracted Fields
            </div>

            <div className="space-y-2.5">
              {Object.entries(parsedData).map(([key, value]) => {
                const flagged = isFlagged(key);
                const fieldFlag = flagged ? parsedFlags.find((f) => f.toLowerCase().includes(key.toLowerCase().replace(/_/g, " "))) : null;

                return (
                  <div key={key}>
                    <div className="flex items-center justify-between mb-0.5">
                      <label className="text-[11px] text-tertiary uppercase">
                        {key.replace(/_/g, " ")}
                      </label>
                      {flagged && (
                        <span className="text-[10px] text-badge-review-text">&#9888;</span>
                      )}
                    </div>
                    {flagged ? (
                      <>
                        <Input
                          value={editedFields[key] !== undefined ? editedFields[key] : fmt(value)}
                          onChange={(e) => handleFieldEdit(key, e.target.value)}
                          validation="warning"
                        />
                        {fieldFlag && (
                          <div className="text-[10px] text-badge-review-text mt-0.5 leading-tight">
                            &#9888; {fieldFlag}
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-[13px] text-primary font-medium px-1">
                        {fmt(value)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </ModalBody>

      <ModalFooter>
        <div className="flex items-center gap-3 w-full">
          <div className="flex items-center gap-2 flex-1">
            <span className="text-[12px] text-secondary">AI Confidence:</span>
            <Progress
              value={doc.confidence}
              color={doc.confidence >= 90 ? "green" : doc.confidence >= 70 ? "orange" : "red"}
              className="w-24"
            />
            <span className="text-[12px] font-medium text-primary">{doc.confidence}%</span>
          </div>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              if (onApprove) onApprove(doc.id);
              onClose();
            }}
          >
            Approve
          </Button>
        </div>
      </ModalFooter>
    </Modal>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd /Users/admin-h26/taxflow-kb/frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
cd /Users/admin-h26/taxflow-kb
git add frontend/components/documents/document-viewer-modal.tsx
git commit -m "feat(frontend): replace form renderer with PDF.js viewer in document modal"
```

---

## Summary

6 tasks, 6 commits:

1. **Dark mode contrast** — token updates in globals.css
2. **Sidebar simplification** — remove accordion
3. **Document card redesign** — two-column layout with inline flags
4. **pdfjs-dist + sample PDFs** — dependency + static files
5. **PdfViewer component** — canvas-based PDF renderer
6. **Document viewer modal** — PDF.js left, extracted fields right
