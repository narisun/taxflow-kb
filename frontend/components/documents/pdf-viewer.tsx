"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { authHeaders } from "@/lib/api-client";

type FitMode = "page-width" | "page-fit" | "custom";

interface PdfViewerProps {
  src: string;
  className?: string;
  /** Jump to this page (scrolls into view in continuous mode). */
  goToPage?: number;
}

/* ── Toolbar icons (inline SVG, 16x16) ──────────────────────────────── */

function FitWidthIcon({ className }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className={className}>
      {/* Left arrow */}
      <path d="M1 8h4M1 8l2-2M1 8l2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      {/* Right arrow */}
      <path d="M15 8h-4M15 8l-2-2M15 8l-2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      {/* Page outline */}
      <rect x="5" y="3" width="6" height="10" rx="1" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function FitPageIcon({ className }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className={className}>
      {/* Outer frame */}
      <rect x="1" y="1" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.2" />
      {/* Inner page */}
      <rect x="4" y="3" width="8" height="10" rx="1" stroke="currentColor" strokeWidth="1.2" />
      {/* Corner arrows (top-left) */}
      <path d="M1.5 4.5V1.5h3" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
      {/* Corner arrows (bottom-right) */}
      <path d="M14.5 11.5v3h-3" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}

export function PdfViewer({ src, className, goToPage }: PdfViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRefs = useRef<Map<number, HTMLCanvasElement>>(new Map());
  const [numPages, setNumPages] = useState(0);
  const [scale, setScale] = useState(1.0);
  const [fitMode, setFitMode] = useState<FitMode>("page-fit");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pdfDocRef = useRef<any>(null);
  const [currentPage, setCurrentPage] = useState(1);
  // Bumped to force recalc even when fitMode value doesn't change
  const [fitSeq, setFitSeq] = useState(0);

  // ── Render a single page onto its canvas ────────────────────────────
  const renderPage = useCallback(
    async (pageNum: number, renderScale: number) => {
      const pdfDoc = pdfDocRef.current;
      const canvas = canvasRefs.current.get(pageNum);
      if (!pdfDoc || !canvas) return;

      try {
        const page = await pdfDoc.getPage(pageNum);
        const viewport = page.getViewport({ scale: renderScale });
        const context = canvas.getContext("2d");
        if (!context) return;

        canvas.height = viewport.height;
        canvas.width = viewport.width;

        await page.render({ canvasContext: context, viewport }).promise;
      } catch (err) {
        console.error("Error rendering page:", err);
      }
    },
    [],
  );

  // ── Compute scale for fit modes ─────────────────────────────────────
  const computeFitScale = useCallback(
    async (mode: FitMode) => {
      const pdfDoc = pdfDocRef.current;
      const container = containerRef.current;
      if (!pdfDoc || !container || container.clientWidth === 0) return null;

      const page = await pdfDoc.getPage(1);
      const baseViewport = page.getViewport({ scale: 1 });
      const availableWidth = container.clientWidth - 40;
      const availableHeight = container.clientHeight - 24;

      if (mode === "page-width") {
        return availableWidth / baseViewport.width;
      }
      if (mode === "page-fit") {
        const scaleW = availableWidth / baseViewport.width;
        const scaleH = availableHeight / baseViewport.height;
        return Math.min(scaleW, scaleH);
      }
      return null;
    },
    [],
  );

  // ── Apply fit scale (shared logic) ──────────────────────────────────
  const applyFit = useCallback(async () => {
    if (loading || !pdfDocRef.current || fitMode === "custom") return;
    const s = await computeFitScale(fitMode);
    if (s !== null) setScale(s);
  }, [loading, fitMode, computeFitScale]);

  // ── Load the PDF document ───────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    async function loadPdf() {
      setLoading(true);
      setError(null);

      try {
        const pdfjsLib = await import("pdfjs-dist");
        pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

        const headers = await authHeaders();
        const loadingTask = pdfjsLib.getDocument({
          url: src,
          httpHeaders: headers,
          withCredentials: false,
        });
        const pdfDoc = await loadingTask.promise;

        if (cancelled) return;

        pdfDocRef.current = pdfDoc;
        setNumPages(pdfDoc.numPages);
        setCurrentPage(1);
        setLoading(false);
      } catch (err) {
        if (!cancelled) {
          setError("Unable to load document preview");
          setLoading(false);
          console.error("PDF load error:", err);
        }
      }
    }

    loadPdf();
    return () => {
      cancelled = true;
    };
  }, [src]);

  // ── Recalculate scale when fit mode, fitSeq, or loading changes ─────
  useEffect(() => {
    applyFit();
  }, [fitMode, fitSeq, loading, applyFit]);

  // ── ResizeObserver — recalculate fit when container resizes ──────────
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(() => {
      // Only recalc if we're in a fit mode (not custom zoom)
      if (fitMode !== "custom" && pdfDocRef.current && !loading) {
        applyFit();
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [fitMode, loading, applyFit]);

  // ── Render all pages when scale changes ─────────────────────────────
  useEffect(() => {
    if (loading || !pdfDocRef.current) return;

    for (let i = 1; i <= numPages; i++) {
      renderPage(i, scale);
    }
  }, [scale, numPages, loading, renderPage]);

  // ── Scroll to goToPage ──────────────────────────────────────────────
  useEffect(() => {
    if (goToPage && goToPage >= 1 && goToPage <= numPages) {
      const canvas = canvasRefs.current.get(goToPage);
      if (canvas) {
        canvas.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  }, [goToPage, numPages, scale]);

  // ── Track current page from scroll position ─────────────────────────
  useEffect(() => {
    const container = containerRef.current;
    if (!container || loading) return;

    function onScroll() {
      const scrollTop = container!.scrollTop + container!.clientHeight / 3;
      let page = 1;
      for (const [pageNum, canvas] of canvasRefs.current.entries()) {
        if (canvas.offsetTop <= scrollTop) {
          page = pageNum;
        }
      }
      setCurrentPage(page);
    }

    container.addEventListener("scroll", onScroll, { passive: true });
    return () => container.removeEventListener("scroll", onScroll);
  }, [loading, numPages]);

  // ── Zoom controls ───────────────────────────────────────────────────
  const zoomIn = () => {
    setFitMode("custom");
    setScale((s) => Math.min(4, +(s + 0.25).toFixed(2)));
  };
  const zoomOut = () => {
    setFitMode("custom");
    setScale((s) => Math.max(0.25, +(s - 0.25).toFixed(2)));
  };
  const requestFit = (mode: FitMode) => {
    setFitMode(mode);
    // Bump sequence so the effect re-runs even if mode is the same value
    setFitSeq((n) => n + 1);
  };

  // ── Register canvas ref for a page ──────────────────────────────────
  const setCanvasRef = useCallback(
    (pageNum: number) => (el: HTMLCanvasElement | null) => {
      if (el) {
        canvasRefs.current.set(pageNum, el);
      } else {
        canvasRefs.current.delete(pageNum);
      }
    },
    [],
  );

  if (error) {
    return (
      <div
        className={`flex items-center justify-center h-64 text-secondary text-[13px] ${className || ""}`}
      >
        {error}
      </div>
    );
  }

  const pctLabel = Math.round(scale * 100);

  return (
    <div className={`flex flex-col h-full ${className || ""}`}>
      {/* ── Toolbar ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-1.5 shrink-0 px-1">
        {/* Page indicator */}
        <span className="text-[11px] text-secondary min-w-[60px]">
          {loading ? "\u2014" : `Page ${currentPage} of ${numPages}`}
        </span>

        {/* Fit mode + zoom controls */}
        <div className="flex items-center gap-0.5">
          <button
            onClick={() => requestFit("page-width")}
            className={`h-7 w-7 rounded-md flex items-center justify-center transition-colors cursor-pointer ${fitMode === "page-width" ? "bg-brand/10 text-brand" : "text-secondary hover:bg-surface-secondary"}`}
            title="Fit to width"
            aria-label="Fit to width"
          >
            <FitWidthIcon />
          </button>
          <button
            onClick={() => requestFit("page-fit")}
            className={`h-7 w-7 rounded-md flex items-center justify-center transition-colors cursor-pointer ${fitMode === "page-fit" ? "bg-brand/10 text-brand" : "text-secondary hover:bg-surface-secondary"}`}
            title="Fit whole page"
            aria-label="Fit whole page"
          >
            <FitPageIcon />
          </button>

          <div className="w-px h-4 bg-divider mx-1" />

          <button
            onClick={zoomOut}
            className="w-7 h-7 rounded-md flex items-center justify-center text-secondary hover:bg-surface-secondary transition-colors cursor-pointer text-[13px]"
            aria-label="Zoom out"
          >
            &minus;
          </button>
          <span className="text-[11px] text-tertiary min-w-[36px] text-center">
            {pctLabel}%
          </span>
          <button
            onClick={zoomIn}
            className="w-7 h-7 rounded-md flex items-center justify-center text-secondary hover:bg-surface-secondary transition-colors cursor-pointer text-[13px]"
            aria-label="Zoom in"
          >
            +
          </button>
        </div>
      </div>

      {/* ── Scroll container (fixed height, both-axis overflow) ───── */}
      <div
        ref={containerRef}
        className="overflow-auto rounded-lg border border-divider bg-surface-tertiary flex-1 min-h-0"
      >
        {loading ? (
          <div className="p-4 space-y-3">
            <Skeleton className="h-6 w-[80%]" />
            <Skeleton className="h-4 w-[60%]" />
            <Skeleton className="h-4 w-[70%]" />
            <Skeleton className="h-64 w-full" />
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 py-3 min-w-fit">
            {Array.from({ length: numPages }, (_, i) => i + 1).map(
              (pageNum) => (
                <canvas
                  key={pageNum}
                  ref={setCanvasRef(pageNum)}
                  className="shadow-md bg-white block"
                />
              ),
            )}
          </div>
        )}
      </div>
    </div>
  );
}
