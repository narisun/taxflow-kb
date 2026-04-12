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
