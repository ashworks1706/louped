"use client";

import { useMutation } from "@tanstack/react-query";
import { parseAsInteger, useQueryStates } from "nuqs";

import { kept, NumberField, type Setup, Views } from "@/components/playground-fields";
import { TabsContent } from "@/components/ui/tabs";
import { speed } from "@/lib/api";

/** The Speed tool: the reply timed base and with the intervention, over a few repeats. */
export function useSpeedTab(setup: Setup) {
  const { interventions, live, gen, label } = setup;
  const [s, set] = useQueryStates({ repeats: parseAsInteger.withDefault(3) });
  // Its errors show in the result pane it fills, so no toast.
  const timed = useMutation({ mutationFn: speed, meta: { quiet: true } });
  const repeats = Math.max(1, Math.min(10, s.repeats));
  return {
    ready: true,
    busy: timed.isPending,
    run: (prompt: string) =>
      timed.mutate({ prompt, interventions, adapters: live, ...gen, repeats }),
    keep: () => kept(timed, setup.prompt, label),
    repeats,
    setRepeats: (repeats: number) => void set({ repeats }),
    timed,
  };
}

/** The Speed tab: how many timed runs, and the timings. */
export function SpeedTab({
  tool: { repeats, setRepeats, timed },
  setup: { intervened, gen, label },
}: {
  tool: ReturnType<typeof useSpeedTab>;
  setup: Setup;
}) {
  return (
    <TabsContent value="speed" className="flex flex-col gap-4 pt-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <NumberField
          label="Repeats"
          help="Timed runs after one warm-up; the median is shown, so one slow run does not skew it."
          value={repeats}
          min={1}
          max={10}
          onChange={setRepeats}
        />
      </div>
      <Views
        state={timed}
        empty={`Run a prompt to time ${gen.max_new_tokens} tokens${intervened ? `, base and ${label}` : ""}.`}
      />
    </TabsContent>
  );
}
