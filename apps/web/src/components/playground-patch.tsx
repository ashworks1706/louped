"use client";

import { useMutation } from "@tanstack/react-query";
import { parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";

import { Field, kept, type Setup, Views } from "@/components/playground-fields";
import { Input } from "@/components/ui/input";
import { TabsContent } from "@/components/ui/tabs";
import { patch } from "@/lib/api";
import { cn } from "@/lib/utils";

const METHODS = ["attribution", "residual", "heads"] as const;

/** The Patch tool: the prompt as the clean run against a corrupt one, and where copying
 * activations between them restores the answer. */
export function usePatchTab({ live, prompt }: Setup) {
  const [s, set] = useQueryStates({
    corrupt: parseAsString.withDefault(""),
    answer: parseAsString.withDefault(""),
    foil: parseAsString.withDefault(""),
    method: parseAsStringLiteral(METHODS).withDefault("attribution"),
  });
  // Its errors show in the result pane it fills, so no toast.
  const patched = useMutation({ mutationFn: patch, meta: { quiet: true } });
  return {
    ready: Boolean(s.corrupt.trim() && s.answer.trim() && s.foil.trim()),
    busy: patched.isPending,
    run: (clean: string) =>
      patched.mutate({
        clean,
        corrupt: s.corrupt,
        answer: s.answer,
        foil: s.foil,
        method: s.method,
        adapters: live,
        chat: true,
      }),
    keep: () => kept(patched, prompt, "no intervention"),
    s,
    set,
    patched,
  };
}

/** The Patch tab: the corrupt prompt, the answer and its foil, and the patching figures. */
export function PatchTab({ tool: { s, set, patched } }: { tool: ReturnType<typeof usePatchTab> }) {
  return (
    <TabsContent value="patch" className="flex flex-col gap-4 pt-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_8rem_8rem]">
        <Field
          label="Corrupt prompt, same length"
          help="The prompt with one detail changed, so the model gives the foil instead of the answer."
        >
          <Input
            aria-label="Corrupt prompt"
            value={s.corrupt}
            placeholder="The Eiffel Tower is in Rome"
            onChange={(e) => void set({ corrupt: e.target.value })}
          />
        </Field>
        <Field label="Answer">
          <Input
            aria-label="Answer"
            value={s.answer}
            placeholder="Paris"
            onChange={(e) => void set({ answer: e.target.value })}
            className="font-mono"
          />
        </Field>
        <Field label="Foil">
          <Input
            aria-label="Foil"
            value={s.foil}
            placeholder="Rome"
            onChange={(e) => void set({ foil: e.target.value })}
            className="font-mono"
          />
        </Field>
      </div>
      <Field label="Method">
        <Segmented
          label="Method"
          options={METHODS}
          value={s.method}
          onChange={(method) => void set({ method })}
        />
      </Field>
      <Views state={patched} empty="Run a clean and a corrupt prompt to patch them." />
    </TabsContent>
  );
}

function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div
      className="bg-muted grid w-fit grid-flow-col gap-1 rounded-md p-1"
      role="radiogroup"
      aria-label={label}
    >
      {options.map((o) => (
        <button
          key={o}
          type="button"
          role="radio"
          aria-checked={value === o}
          tabIndex={value === o ? 0 : -1}
          onClick={() => onChange(o)}
          onKeyDown={(e) => {
            const step =
              e.key === "ArrowRight" || e.key === "ArrowDown"
                ? 1
                : e.key === "ArrowLeft" || e.key === "ArrowUp"
                  ? -1
                  : 0;
            if (!step) return;
            e.preventDefault();
            const next = options[(options.indexOf(value) + step + options.length) % options.length];
            onChange(next);
            const group = e.currentTarget.parentElement;
            requestAnimationFrame(() =>
              group?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus(),
            );
          }}
          className={cn(
            "focus-visible:ring-ring/30 h-7 rounded-[5px] px-3 text-sm capitalize transition-colors outline-none focus-visible:ring-[3px]",
            value === o ? "bg-background" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o}
        </button>
      ))}
    </div>
  );
}
