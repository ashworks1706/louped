"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PanelsTopLeft } from "lucide-react";
import { parseAsInteger, parseAsString, useQueryState } from "nuqs";
import { useMemo, useState } from "react";

import { Help } from "@/components/help";
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
import { q, setLabel, type Label, type SampleSummary } from "@/lib/api";
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
  const judged = scoreNames.includes("b_wins");
  const rows = samples.filter(
    (s) =>
      (!failing || s.scores[failing] === 0) &&
      `${s.id} ${s.input} ${s.target}`.toLowerCase().includes(filter.toLowerCase()),
  );

  return (
    <div className="flex flex-col gap-3">
      {judged && <JudgeAgreement runId={runId} />}
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
            <SampleSheetBody
              runId={runId}
              sampleId={open}
              epoch={epoch ?? 1}
              hasLog={hasLog}
              judged={judged}
            />
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
  judged,
}: {
  runId: string;
  sampleId: string;
  epoch: number;
  hasLog: boolean;
  judged: boolean;
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
      {judged && <YourPick runId={runId} sampleId={sampleId} />}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <QueryState query={query}>{(s) => <Transcript sample={s} />}</QueryState>
      </div>
    </>
  );
}

const PICKS: [Label, string][] = [
  ["a", "A"],
  ["tie", "Tie"],
  ["b", "B"],
];

/** How far the judge agrees with the pairs a person labelled. */
function JudgeAgreement({ runId }: { runId: string }) {
  const agree = useQuery(q.agreement(runId));
  const a = agree.data;
  if (!a) return null;
  return (
    <div className="text-muted-foreground flex items-center gap-1.5 text-sm">
      {a.labelled === 0 ? (
        "Label pairs to check the judge against you."
      ) : (
        <>
          Agrees with you on <span className="text-foreground font-mono">{pct(a.agreement)}</span>{" "}
          of {a.labelled} of {a.total} pairs · κ{" "}
          <span className="text-foreground font-mono">{num(a.kappa, 2)}</span>
        </>
      )}
      <Help label="What is judge agreement?">
        Open a pair and pick the better answer yourself. Agreement is the share of your picks the
        judge matched. κ (Cohen&apos;s kappa) discounts matches expected by chance: 1 is perfect, 0
        is chance. Trust the judge&apos;s win rate only when κ is high.
      </Help>
    </div>
  );
}

/** The person's pick for this pair; picking it again clears it. */
function YourPick({ runId, sampleId }: { runId: string; sampleId: string }) {
  const client = useQueryClient();
  const labels = useQuery(q.labels(runId));
  const mine = labels.data?.[sampleId] ?? null;
  const save = useMutation({
    mutationFn: (label: Label | null) => setLabel(runId, sampleId, label),
    onSuccess: (all) => {
      client.setQueryData(["labels", runId], all);
      void client.invalidateQueries({ queryKey: ["agreement", runId] });
    },
  });
  return (
    <div className="flex flex-wrap items-center gap-2 border-b px-6 py-3">
      <span className="text-muted-foreground flex items-center gap-1 text-xs">
        Your pick
        <Help label="Which is A?">
          A is the baseline run: Answer 1 in the first prompt below, Answer 2 in the second.
        </Help>
      </span>
      <div role="group" aria-label="Your pick" className="flex gap-1">
        {PICKS.map(([value, text]) => (
          <Button
            key={value}
            size="sm"
            variant={mine === value ? "default" : "outline"}
            aria-pressed={mine === value}
            disabled={save.isPending}
            onClick={() => save.mutate(mine === value ? null : value)}
          >
            {text}
          </Button>
        ))}
      </div>
      {save.error && <span className="text-negative text-xs">{save.error.message}</span>}
    </div>
  );
}
