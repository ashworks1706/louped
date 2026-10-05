"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Pin as PinIcon } from "lucide-react";
import Link from "next/link";
import { parseAsInteger, parseAsString, useQueryState } from "nuqs";
import { useEffect, useRef, useState } from "react";

import { CopyButton } from "@/components/copy-button";
import { DeleteButton } from "@/components/delete-button";
import { Part, part, partId } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { addPin, deletePin, q, sourceFile, type Pin, type Source } from "@/lib/api";
import { host, sourceHref } from "@/lib/href";
import { quoteRanges } from "@/lib/quotes";
import { cn } from "@/lib/utils";

/** One source, a page at a time: a PDF drawn as it prints, anything else as its text. Select
 * words on the page and Pin them; the pins of the page are marked, and all of the source's are
 * listed beside it with their citation. */
export function SourceView() {
  const [key] = useQueryState("key", parseAsString);
  const sources = useQuery(q.sources());
  return (
    <QueryState query={sources}>
      {(all) => {
        const found = all.find((s) => s.key === key);
        return found ? (
          <Viewer source={found} />
        ) : (
          <p className="text-muted-foreground mx-auto max-w-6xl px-6 py-8 text-sm">
            No source {key ? <span className="font-mono">{key}</span> : "named"}.{" "}
            <Link href="/sources/" className="underline underline-offset-4">
              All sources
            </Link>
          </p>
        );
      }}
    </QueryState>
  );
}

function Viewer({ source: s }: { source: Source }) {
  const [asked, setPage] = useQueryState("page", parseAsInteger.withDefault(1));
  const page = Math.min(Math.max(asked, 1), s.pages);
  const pins = useQuery(q.pins(s.key));
  const onPage = (pins.data ?? []).filter((p) => p.page === page);
  const [selected, setSelected] = useState({ page, text: "" });
  const picked = selected.page === page ? selected.text : "";
  const area = useRef<HTMLDivElement>(null);
  // the words selected on the page, and only on it; kept while the note is typed
  useEffect(() => {
    const read = () => {
      const sel = document.getSelection();
      if (!sel?.anchorNode) return setSelected({ page, text: "" });
      if (area.current?.contains(sel.anchorNode))
        setSelected({ page, text: sel.toString().trim() });
    };
    document.addEventListener("selectionchange", read);
    return () => document.removeEventListener("selectionchange", read);
  }, [page]);
  return (
    <>
      <header className="border-b">
        <div className="mx-auto flex max-w-6xl flex-col gap-1 px-6 py-8" {...part("source/header")}>
          <Link href="/sources/" className="text-muted-foreground text-xs hover:underline">
            Sources
          </Link>
          <h1 className="text-xl font-semibold tracking-tight">{s.title}</h1>
          <p className="text-muted-foreground text-sm">
            What this source says, and the passages pinned from it.
          </p>
          <p className="text-muted-foreground flex flex-wrap gap-x-4 font-mono text-xs">
            <span>{s.key}</span>
            <span>{s.kind}</span>
            <span>{s.pages} pages</span>
            {s.origin && (
              <a href={s.origin} target="_blank" rel="noreferrer" className="hover:underline">
                {host(s.origin)}
              </a>
            )}
          </p>
        </div>
      </header>
      <div className="mx-auto grid max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2" {...part("source/controls")}>
            <Button
              size="sm"
              variant="ghost"
              disabled={page <= 1}
              onClick={() => void setPage(page - 1)}
              aria-label="Previous page"
            >
              <ChevronLeft />
            </Button>
            <span className="font-mono text-xs tabular-nums">
              {page} / {s.pages}
            </span>
            <Button
              size="sm"
              variant="ghost"
              disabled={page >= s.pages}
              onClick={() => void setPage(page + 1)}
              aria-label="Next page"
            >
              <ChevronRight />
            </Button>
            <PinButton source={s} page={page} quote={picked} />
          </div>
          <div ref={area} {...part("source/page")}>
            {s.kind === "pdf" ? (
              <PdfPage source={s} page={page} pins={onPage} />
            ) : (
              <TextPage source={s} page={page} pins={onPage} />
            )}
          </div>
        </div>
        <Pins source={s} pins={pins.data ?? []} />
      </div>
    </>
  );
}

/** Pins the selected words, with an optional note; the server refuses words not on the page. */
function PinButton({ source: s, page, quote }: { source: Source; page: number; quote: string }) {
  const health = useQuery(q.health());
  const client = useQueryClient();
  const [note, setNote] = useState("");
  const pin = useMutation({
    mutationFn: () => addPin({ key: s.key, page, quote, note: note || null, links: [] }),
    meta: { action: "Pin" },
    onSuccess: () => {
      setNote("");
      document.getSelection()?.removeAllRanges();
      void client.invalidateQueries({ queryKey: ["pins"] });
    },
  });
  if (!health.data?.launching) return null;
  return (
    <form
      className="ml-auto flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        pin.mutate();
      }}
    >
      {quote && (
        <Input
          placeholder="Note (optional)"
          aria-label="Note for the pin"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className="h-8 w-48"
        />
      )}
      <Button
        type="submit"
        size="sm"
        variant="outline"
        disabled={!quote || pin.isPending}
        aria-describedby={quote ? undefined : "pin-hint"}
        {...part("source/pin-selection")}
      >
        <PinIcon /> Pin
      </Button>
      {!quote && (
        <span id="pin-hint" className="text-muted-foreground text-xs">
          Select words on the page to pin them
        </span>
      )}
    </form>
  );
}

/** A non-PDF page (a slide, a notebook cell, a document) as its text, pins marked. */
function TextPage({ source: s, page, pins }: { source: Source; page: number; pins: Pin[] }) {
  const text = useQuery(q.sourcePage(s.key, page));
  return (
    <QueryState query={text}>
      {(p) => {
        const ranges = quoteRanges(
          p.text,
          pins.map((x) => x.exact),
        );
        const bits: React.ReactNode[] = [];
        let at = 0;
        for (const [a, b] of ranges) {
          bits.push(p.text.slice(at, a));
          bits.push(
            <mark key={a} className="pinned text-foreground">
              {p.text.slice(a, b)}
            </mark>,
          );
          at = b;
        }
        bits.push(p.text.slice(at));
        return (
          <div
            className={cn(
              "rounded-xl border p-6 text-sm leading-relaxed whitespace-pre-wrap",
              s.kind === "ipynb" && "font-mono text-xs",
            )}
          >
            {p.text ? bits : <span className="text-muted-foreground">This page has no text.</span>}
          </div>
        );
      }}
    </QueryState>
  );
}

/** A PDF page drawn by pdf.js, with its text laid over it to select, pins marked. */
function PdfPage({ source: s, page, pins }: { source: Source; page: number; pins: Pin[] }) {
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
        task = pdfjs.getDocument({ url: sourceFile(s.key) });
        const loaded = await task.promise;
        if (!done) setDoc(loaded);
      } catch (e) {
        if (!done) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      done = true;
      void task?.destroy();
    };
  }, [s.key, s.sha256]);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const seen = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)));
    seen.observe(el);
    return () => seen.disconnect();
  }, []);
  const quotes = pins.map((p) => p.exact).join("\n");
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

/** The source's pins: each quote, its page, its note, and the citation that names it. */
function Pins({ source: s, pins }: { source: Source; pins: Pin[] }) {
  return (
    <Part id="source/pins" as="section" className="flex flex-col gap-3">
      <h2 className="text-sm font-medium">Pins</h2>
      {pins.length === 0 ? (
        <p className="text-muted-foreground text-xs">
          Select words on the page and press Pin. Your agent pins with the pin tool and cites a pin
          as [@{s.key} p&lt;page&gt;].
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {pins.map((p) => (
            <li
              key={p.id}
              className="flex flex-col gap-1.5 rounded-lg border p-3"
              {...part(partId("source/pin", p.id))}
            >
              <div className="flex items-center gap-2">
                <Link
                  href={sourceHref(s.key, p.page)}
                  className="font-mono text-xs underline-offset-4 hover:underline"
                >
                  p{p.page}
                </Link>
                <span className="text-muted-foreground ml-auto font-mono text-xs">
                  [@{s.key} p{p.page}]
                </span>
                <CopyButton text={`[@${s.key} p${p.page}]`} />
                <DeleteButton
                  what="pin"
                  name={`the pin on p${p.page}`}
                  undo="sources/pins.jsonl is committed: git brings it back."
                  remove={() => deletePin(p.id)}
                  then={sourceHref(s.key, p.page)}
                />
              </div>
              <blockquote className="line-clamp-6 border-l-2 pl-2 text-xs leading-relaxed">
                {p.exact}
              </blockquote>
              {p.note && <p className="text-muted-foreground text-xs">{p.note}</p>}
              {p.links.length > 0 && (
                <p className="text-muted-foreground truncate font-mono text-[11px]">
                  {p.links.join(" · ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </Part>
  );
}
