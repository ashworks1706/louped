"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Pin as PinIcon } from "lucide-react";
import Link from "next/link";
import { parseAsInteger, parseAsString, useQueryState } from "nuqs";
import { useEffect, useRef, useState } from "react";

import { CopyButton } from "@/components/copy-button";
import { DeleteButton } from "@/components/delete-button";
import { Help } from "@/components/help";
import { NotebookFrame } from "@/components/notebook-frame";
import { Part, part, partId } from "@/components/parts";
import { PdfPage } from "@/components/pdf-page";
import { QueryState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { addPin, deletePin, q, sourceFile, sourceNotebook, type Pin, type Source } from "@/lib/api";
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
              <PdfPage
                file={`${sourceFile(s.key)}?sha=${s.sha256}`}
                page={page}
                marks={onPage.map((p) => p.exact)}
              />
            ) : (
              <TextPage source={s} page={page} pins={onPage} />
            )}
          </div>
          {s.kind === "ipynb" && (
            <Part id="source/notebook" as="section" className="flex flex-col gap-2">
              <h2 className="flex items-center gap-1.5 text-sm font-medium">
                The whole notebook, with its outputs
                <Help label="How to read the whole notebook">
                  The notebook as Jupyter shows it, with the outputs it was saved with. Nothing in
                  it runs here: math shows as TeX, and an interactive chart shows only if the
                  notebook saved a static copy. Pin from the cells above.
                </Help>
              </h2>
              <NotebookFrame url={sourceNotebook(s.key)} version={s.sha256} title={s.title} />
            </Part>
          )}
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
