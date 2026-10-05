"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";
import Link from "next/link";
import { parseAsString, useQueryState } from "nuqs";
import { useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { Part, part, partId } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { addSource, q, type SourceHit } from "@/lib/api";
import { host, sourceHref } from "@/lib/href";

/** The project's sources: a search over their pages, and the list. */
export function SourcesView() {
  const sources = useQuery(q.sources());
  return (
    <QueryState query={sources}>
      {(all) =>
        all.length === 0 ? (
          <EmptyState
            icon={BookOpen}
            title="No sources yet"
            body="Papers, docs, slides and notebooks kept in sources/, to search, quote and cite."
          >
            <AddSource />
          </EmptyState>
        ) : (
          <>
            <Search />
            <section className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-sm font-medium" {...part("sources/heading")}>
                  <span className="font-mono tabular-nums">{all.length}</span>{" "}
                  {all.length === 1 ? "source" : "sources"}
                </h2>
                <AddSource />
              </div>
              <Part id="sources/table">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Title</TableHead>
                      <TableHead>Key</TableHead>
                      <TableHead>Kind</TableHead>
                      <TableHead className="text-right">Pages</TableHead>
                      <TableHead>From</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {all.map((s) => (
                      <TableRow key={s.key} {...part(partId("sources/source", s.key))}>
                        <TableCell className="max-w-md">
                          <Link
                            href={sourceHref(s.key)}
                            className="underline-offset-4 hover:underline"
                          >
                            {s.title}
                          </Link>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{s.key}</TableCell>
                        <TableCell className="font-mono text-xs">{s.kind}</TableCell>
                        <TableCell className="text-right font-mono tabular-nums">
                          {s.pages}
                        </TableCell>
                        <TableCell className="text-muted-foreground max-w-48 truncate text-xs">
                          {s.origin ? (
                            <a
                              href={s.origin}
                              target="_blank"
                              rel="noreferrer"
                              className="underline-offset-4 hover:underline"
                            >
                              {host(s.origin)}
                            </a>
                          ) : (
                            "a file"
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Part>
            </section>
          </>
        )
      }
    </QueryState>
  );
}

/** Every word of the query, over every page; ?q= keeps it. */
function Search() {
  const [query, setQuery] = useQueryState("q", parseAsString.withDefault(""));
  const hits = useQuery({ ...q.sourceSearch(query), enabled: query.trim() !== "" });
  return (
    <section className="flex flex-col gap-3">
      <Input
        type="search"
        placeholder="Search every page"
        aria-label="Search sources"
        value={query}
        onChange={(e) => void setQuery(e.target.value || null)}
        className="max-w-xl"
        {...part("sources/search")}
      />
      {query.trim() !== "" && (
        <QueryState query={hits}>
          {(found) =>
            found.length === 0 ? (
              <p className="text-muted-foreground text-sm">No page holds every word.</p>
            ) : (
              <ul className="flex flex-col divide-y rounded-xl border">
                {found.map((h) => (
                  <li
                    key={`${h.key}/${h.page}`}
                    {...part(partId("sources/hit", h.key, String(h.page)))}
                  >
                    <Link
                      href={sourceHref(h.key, h.page)}
                      className="hover:bg-muted/50 flex flex-col gap-1 px-4 py-3"
                    >
                      <span className="text-sm">
                        {h.title}{" "}
                        <span className="text-muted-foreground font-mono text-xs">p{h.page}</span>
                      </span>
                      <Snippet hit={h} />
                    </Link>
                  </li>
                ))}
              </ul>
            )
          }
        </QueryState>
      )}
    </section>
  );
}

/** The search's snippet, its matched words (in [brackets] from the server) marked. */
function Snippet({ hit }: { hit: SourceHit }) {
  return (
    <span className="text-muted-foreground text-xs leading-relaxed">
      {hit.snippet.split(/(\[[^\]]*\])/).map((bit, i) =>
        bit.startsWith("[") && bit.endsWith("]") ? (
          <mark key={i} className="bg-muted text-foreground rounded-sm px-0.5">
            {bit.slice(1, -1)}
          </mark>
        ) : (
          bit
        ),
      )}
    </span>
  );
}

/** A file in the project or an https URL, kept in sources/; only while launching is on. */
function AddSource() {
  const health = useQuery(q.health());
  const client = useQueryClient();
  const [location, setLocation] = useState("");
  const add = useMutation({
    mutationFn: () => addSource({ location }),
    meta: { action: "Add source" },
    onSuccess: () => {
      setLocation("");
      void client.invalidateQueries({ queryKey: ["sources"] });
    },
  });
  if (!health.data?.launching)
    return (
      <p className="text-muted-foreground font-mono text-xs">
        louped source add &lt;file or url&gt;
      </p>
    );
  return (
    <Part id="sources/add" className="flex w-full max-w-lg gap-2">
      <form
        className="flex w-full gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (location.trim()) add.mutate();
        }}
      >
        <Input
          placeholder="arXiv link, file URL or a path in the project"
          aria-label="Source to add"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
        <Button type="submit" size="sm" disabled={add.isPending || !location.trim()}>
          {add.isPending ? "Adding" : "Add"}
        </Button>
      </form>
    </Part>
  );
}
