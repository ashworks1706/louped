"use client";

import { useMutation } from "@tanstack/react-query";
import { parseAsStringLiteral, useQueryStates } from "nuqs";

import { InspectReadout, targetOf, useReadoutState } from "@/components/inspect-readout";
import { type Setup, ViewList } from "@/components/playground-fields";
import { part } from "@/components/parts";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { inspect, type View } from "@/lib/api";

const SIDES = ["base", "intervention"] as const;

/** The Inspect tool: one forward pass read base and, with an intervention, intervened. */
export function useInspectTab(setup: Setup) {
  const { info, vectors, interventions, live, intervened, gen, label } = setup;
  const [s, set] = useQueryStates({ side: parseAsStringLiteral(SIDES).withDefault("base") });
  const [read, setRead] = useReadoutState();
  // Their errors show in the result pane they fill, so no toast.
  const looked = useMutation({ mutationFn: inspect, meta: { quiet: true } });
  const lookedEdited = useMutation({ mutationFn: inspect, meta: { quiet: true } });
  const run = (prompt: string, target = read.ltarget) => {
    const ask = {
      prompt,
      vectors: info.diffusion ? [] : vectors.map((v) => v.name),
      chat: true,
      ...targetOf(target),
    };
    lookedEdited.reset();
    // the intervened pass follows the token the base pass followed, so the two compare
    void looked
      .mutateAsync({ ...ask, ...gen, interventions: [], adapters: [] })
      .then((b) => {
        if (!intervened) return;
        const id = b.readout?.target;
        lookedEdited.mutate({
          ...ask,
          ...gen,
          ...(id == null ? {} : { target: null, target_id: id }),
          interventions,
          adapters: live,
        });
      })
      .catch(() => undefined); // the error shows in the result pane
  };
  return {
    ready: true,
    busy: looked.isPending || lookedEdited.isPending,
    run,
    /** Follows another token: every panel reads it, from a new pass. */
    follow: (target: string) => {
      void setRead({ ltarget: target });
      run(setup.prompt, target);
    },
    keep: () => {
      if (!looked.data) return null;
      const titled = (views: View[], side: string) =>
        views.map((v) => ({ ...v, title: `${side} · ${v.title}` }));
      return {
        prompt: setup.prompt,
        settings: { ...looked.variables, intervened: lookedEdited.variables ?? null },
        label,
        views: lookedEdited.data
          ? [...titled(looked.data.views, "base"), ...titled(lookedEdited.data.views, label)]
          : looked.data.views,
      };
    },
    side: s.side,
    setSide: (side: (typeof SIDES)[number]) => void set({ side }),
    // the stream read: the intervened one only while there is an intervention
    shown: s.side === "intervention" && intervened ? lookedEdited : looked,
    // the other side, which the intervened side's panels show their change from
    base: s.side === "intervention" && intervened ? (looked.data?.readout ?? null) : null,
  };
}

/** The Inspect tab: which stream to read, and what the pass showed. */
export function InspectTab({
  tool: { side, setSide, shown, base, follow },
  setup: { info, intervened, label },
}: {
  tool: ReturnType<typeof useInspectTab>;
  setup: Setup;
}) {
  return (
    <TabsContent value="inspect" className="flex flex-col gap-4 pt-4">
      {intervened && (
        <Tabs value={side} onValueChange={(side) => setSide(side as (typeof SIDES)[number])}>
          <TabsList aria-label="Which stream to read">
            <TabsTrigger value="base" {...part("playground/side/base")}>
              Base
            </TabsTrigger>
            <TabsTrigger
              value="intervention"
              {...part("playground/side/intervention")}
              className="data-[state=active]:text-intervention min-w-0 truncate"
            >
              {label}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      )}
      {shown.isPending ? (
        <span className="text-muted-foreground animate-pulse text-sm">Reading…</span>
      ) : shown.error ? (
        <span className="text-negative text-sm">{shown.error.message}</span>
      ) : shown.data?.readout ? (
        <>
          <InspectReadout
            r={shown.data.readout}
            other={base}
            label={label}
            patterns={patternsOf(shown.data.views)}
            onTarget={follow}
          />
          {/* what the readout does not draw: projections onto saved vectors */}
          <ViewList views={shown.data.views.filter(extra)} at={shown.submittedAt} />
        </>
      ) : shown.data ? (
        <ViewList views={shown.data.views} at={shown.submittedAt} />
      ) : (
        <span className="text-muted-foreground text-sm">
          Run a prompt to {info.diffusion ? "watch it denoise" : "read its layers"}.
        </span>
      )}
    </TabsContent>
  );
}

/** The attention view's weights by "layer i · head j", each [query][key]. */
function patternsOf(views: View[]): Record<string, number[][]> | null {
  const attention = views.find((v) => v.kind === "tokens" && v.pairs);
  return attention?.kind === "tokens" ? (attention.pairs ?? null) : null;
}

/** A view the readout does not already draw: not the lens, not the attention. */
const extra = (v: View) =>
  !(v.kind === "heatmap" && v.title.startsWith("Logit lens")) && !(v.kind === "tokens" && v.pairs);
