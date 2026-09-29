"use client";

import { useQuery } from "@tanstack/react-query";
import { PanelsTopLeft } from "lucide-react";
import { parseAsInteger, parseAsString, useQueryState } from "nuqs";
import { useMemo, useState } from "react";

import { ScoreCell } from "@/components/metric";
import { QueryState } from "@/components/query-state";
import { Transcript } from "@/components/transcript";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { q, type SampleSummary } from "@/lib/api";
import { num, pct } from "@/lib/format";

/** Every sample of an eval run, one column per score; a row opens its transcript. */
export function SamplesTable({
  runId,
  samples,
  hasLog = false,
}: {
  runId: string;
  samples: SampleSummary[];
  hasLog?: boolean;
}) {
  const [open, setOpen] = useQueryState("sample", parseAsString);
  const [epoch, setEpoch] = useQueryState("epoch", parseAsInteger);
  const [failing, setFailing] = useQueryState("fails", parseAsString);
  const [filter, setFilter] = useState("");

  const scoreNames = useMemo(
    () => [...new Set(samples.flatMap((s) => Object.keys(s.scores)))],
    [samples],
  );
  const rows = samples.filter(
    (s) =>
      (!failing || s.scores[failing] === 0) &&
      `${s.id} ${s.input} ${s.target}`.toLowerCase().includes(filter.toLowerCase()),
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Filter samples…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="max-w-xs"
        />
        {scoreNames.map((name) => {
          const values = samples.map((s) => s.scores[name]).filter((v) => v != null) as number[];
          const mean = values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
          const active = failing === name;
          return (
            <Button
              key={name}
              size="sm"
              variant={active ? "default" : "outline"}
              onClick={() => setFailing(active ? null : name)}
              title={`Show only samples that failed ${name}`}
            >
              {name}
              <span className="font-mono text-xs opacity-70">
                {values.every((v) => v === 0 || v === 1) ? pct(mean) : num(mean)}
              </span>
            </Button>
          );
        })}
        <span className="text-muted-foreground ml-auto text-xs">
          {rows.length} of {samples.length}
        </span>
      </div>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-12">#</TableHead>
            <TableHead>Input</TableHead>
            <TableHead>Target</TableHead>
            {scoreNames.map((n) => (
              <TableHead key={n} className="text-center">
                {n}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((s) => (
            <TableRow
              key={`${s.id}:${s.epoch}`}
              className="cursor-pointer"
              data-state={open === s.id && (epoch ?? 1) === s.epoch ? "selected" : undefined}
              onClick={() => {
                void setOpen(s.id);
                void setEpoch(s.epoch === 1 ? null : s.epoch);
              }}
            >
              <TableCell className="text-muted-foreground font-mono text-xs whitespace-nowrap">
                {s.id}
              </TableCell>
              <TableCell className="max-w-md truncate">{s.input}</TableCell>
              <TableCell className="max-w-40 truncate font-mono text-xs">{s.target}</TableCell>
              {scoreNames.map((n) => (
                <TableCell key={n} className="text-center">
                  <ScoreCell value={s.scores[n]} />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Sheet
        open={open !== null}
        onOpenChange={(o) => {
          if (o) return;
          void setOpen(null);
          void setEpoch(null);
        }}
      >
        <SheetContent>
          {open !== null && (
            <SampleSheetBody runId={runId} sampleId={open} epoch={epoch ?? 1} hasLog={hasLog} />
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function SampleSheetBody({
  runId,
  sampleId,
  epoch,
  hasLog,
}: {
  runId: string;
  sampleId: string;
  epoch: number;
  hasLog: boolean;
}) {
  const query = useQuery(q.sample(runId, sampleId, epoch));
  const [, setTab] = useQueryState("tab", parseAsString);
  return (
    <>
      <div className="flex items-center justify-between gap-4 border-b px-6 py-4 pr-12">
        <SheetTitle className="font-semibold">Sample {sampleId}</SheetTitle>
        <SheetDescription className="sr-only">Conversation and scores</SheetDescription>
        {hasLog && (
          <Button variant="ghost" size="sm" onClick={() => void setTab("log")}>
            <PanelsTopLeft /> Log
          </Button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <QueryState query={query}>{(s) => <Transcript sample={s} />}</QueryState>
      </div>
    </>
  );
}
