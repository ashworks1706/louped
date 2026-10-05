"use client";

import { useEffect, useRef, useState } from "react";

import { quoteRanges } from "@/lib/quotes";

/** A page of a PDF drawn by pdf.js, with its text laid over it to select and the words of
 * `marks` marked. `file` is the PDF's URL or its bytes; `onPages` hears how many pages it has. */
export function PdfPage({
  file,
  page,
  marks = [],
  onPages,
}: {
  file: string | Uint8Array;
  page: number;
  marks?: string[];
  onPages?: (pages: number) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [doc, setDoc] = useState<import("pdfjs-dist/legacy/build/pdf.mjs").PDFDocumentProxy | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    let done = false;
    let task: import("pdfjs-dist/legacy/build/pdf.mjs").PDFDocumentLoadingTask | null = null;
    void (async () => {
      try {
        // the legacy build: the modern one needs JavaScript newer than many browsers have
        const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/legacy/build/pdf.worker.min.mjs",
          import.meta.url,
        ).toString();
        if (done) return;
        // pdf.js takes over the bytes it is given, so it gets a copy
        task = pdfjs.getDocument(typeof file === "string" ? { url: file } : { data: file.slice() });
        const loaded = await task.promise;
        if (done) return;
        setDoc(loaded);
        onPages?.(loaded.numPages);
      } catch (e) {
        if (!done) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      done = true;
      void task?.destroy();
    };
  }, [file, onPages]);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const seen = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)));
    seen.observe(el);
    return () => seen.disconnect();
  }, []);
  const quotes = marks.join("\n");
  useEffect(() => {
    const el = box.current;
    if (!doc || !el || width === 0) return;
    let done = false;
    let cancel = () => {};
    void (async () => {
      const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
      const p = await doc.getPage(page);
      if (done) return;
      const viewport = p.getViewport({ scale: width / p.getViewport({ scale: 1 }).width });
      const ratio = window.devicePixelRatio || 1;
      const canvas = document.createElement("canvas");
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      const text = document.createElement("div");
      text.className = "textLayer";
      el.replaceChildren(canvas, text);
      el.style.height = `${viewport.height}px`;
      el.style.setProperty("--total-scale-factor", String(viewport.scale));
      const drawing = p.render({
        canvas,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
      });
      const layer = new pdfjs.TextLayer({
        textContentSource: p.streamTextContent(),
        container: text,
        viewport,
      });
      cancel = () => {
        drawing.cancel();
        layer.cancel();
      };
      try {
        await Promise.all([drawing.promise, layer.render()]);
      } catch (e) {
        if (!done && !(e instanceof Error && e.name === "RenderingCancelledException"))
          setError(e instanceof Error ? e.message : String(e));
        return;
      }
      if (done) return;
      // mark the spans a pin's words fall in
      const spans = layer.textDivs;
      const whole = spans.map((d) => d.textContent ?? "").join("");
      const starts: number[] = [];
      spans.reduce((at, d) => (starts.push(at), at + (d.textContent ?? "").length), 0);
      for (const [a, b] of quoteRanges(whole, quotes ? quotes.split("\n") : []))
        spans.forEach((d, i) => {
          const from = starts[i];
          const to = from + (d.textContent ?? "").length;
          if (from < b && to > a) d.classList.add("pinned");
        });
    })();
    return () => {
      done = true;
      cancel();
    };
  }, [doc, page, width, quotes]);
  return (
    <>
      <div
        ref={box}
        className="pdf-page relative w-full overflow-hidden rounded-xl border bg-white"
      />
      {error && <p className="text-negative text-sm">This PDF could not be drawn: {error}</p>}
    </>
  );
}
