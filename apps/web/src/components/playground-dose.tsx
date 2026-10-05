"use client";

import { useMutation } from "@tanstack/react-query";
import { parseAsFloat, parseAsInteger, parseAsString, useQueryStates } from "nuqs";

import { Field, kept, NumberField, type Setup, Views } from "@/components/playground-fields";
import { Input } from "@/components/ui/input";
import { TabsContent } from "@/components/ui/tabs";
import { dose } from "@/lib/api";

/** The Dose tool: the chosen vector added at a range of strengths, the answer read at each. */
export function useDoseTab(setup: Setup) {
  const { vector, layer, live, label } = setup;
  const [s, set] = useQueryStates({
    token: parseAsString.withDefault(""),
    versus: parseAsString.withDefault(""),
    from: parseAsFloat.withDefault(-4),
    to: parseAsFloat.withDefault(4),
    points: parseAsInteger.withDefault(9),
  });
  // Its errors show in the result pane it fills, so no toast.
  const dosed = useMutation({ mutationFn: dose, meta: { quiet: true } });
  const n = Math.max(2, Math.min(41, s.points));
  const alphas: number[] = Array.from({ length: n }, (_, i) =>
    Number((s.from + ((s.to - s.from) * i) / (n - 1)).toFixed(4)),
  );
  return {
    ready: Boolean(vector && s.token.trim()),
    busy: dosed.isPending,
    run: (prompt: string) => {
      if (vector)
        dosed.mutate({
          prompt,
          vector: vector.name,
          layer,
          alphas,
          answer: s.token,
          foil: s.versus.trim() || null,
          adapters: live,
          chat: true,
        });
    },
    keep: () => kept(dosed, setup.prompt, label),
    s,
    set,
    n,
    dosed,
  };
}

/** The Dose tab: the answer and its foil, the range of strengths, and the sweep. */
export function DoseTab({
  tool: { s, set, n, dosed },
  setup: { vector, layer },
}: {
  tool: ReturnType<typeof useDoseTab>;
  setup: Setup;
}) {
  return (
    <TabsContent value="dose" className="flex flex-col gap-4 pt-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Field label="Answer">
          <Input
            aria-label="Answer"
            value={s.token}
            placeholder="Yes"
            onChange={(e) => void set({ token: e.target.value })}
            className="font-mono"
          />
        </Field>
        <Field label="Foil">
          <Input
            aria-label="Foil"
            value={s.versus}
            placeholder="No"
            onChange={(e) => void set({ versus: e.target.value })}
            className="font-mono"
          />
        </Field>
        <NumberField label="α from" value={s.from} onChange={(from) => void set({ from })} />
        <NumberField label="α to" value={s.to} onChange={(to) => void set({ to })} />
        <NumberField
          label="Points"
          help="How many strengths between the two ends, each one forward pass."
          value={n}
          min={2}
          max={41}
          onChange={(points) => void set({ points })}
        />
      </div>
      <Views
        state={dosed}
        empty={
          vector
            ? `Run a prompt to steer ${vector.name} at layer ${layer} from α ${s.from} to ${s.to}.`
            : "Save a vector for this model to sweep it."
        }
      />
    </TabsContent>
  );
}
