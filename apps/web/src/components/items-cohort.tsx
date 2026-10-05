"use client";

import { useQuery } from "@tanstack/react-query";
import { parseAsString, useQueryState } from "nuqs";
import { useMemo } from "react";

import { part, useRules } from "@/components/parts";
import { NativeSelect } from "@/components/ui/native-select";
import { q } from "@/lib/api";
import { cn } from "@/lib/utils";

/** The items a view is read on: those picked (ids in the URL) or a cohort saved by name in the
 * experiment; every item without one. */
export function useCohort<T extends { id: string }>(
  experiment: string | null | undefined,
  every: T[],
) {
  const [picked, setIds] = useQueryState("ids", parseAsString);
  const [name, setCohort] = useQueryState("cohort", parseAsString);
  const saved = useQuery({
    ...q.cohorts(experiment ?? ""),
    enabled: !!experiment,
  });
  const rule = useRules();
  const wanted = name ?? rule("items/cohort").default ?? null;
  const found = saved.data?.find((c) => c.name === wanted);
  const ids = useMemo(
    () => (picked ? picked.split(",").map(decodeURIComponent) : (found?.ids ?? null)),
    [picked, found],
  );
  const items = useMemo(() => {
    if (!ids) return every;
    const want = new Set(ids);
    return every.filter((it) => want.has(it.id));
  }, [every, ids]);
  return {
    /** The ids in the URL, when items were picked rather than a cohort named. */
    picked,
    wanted,
    saved,
    found,
    ids,
    items,
    notHeld: ids ? new Set(ids).size - items.length : 0,
    label: picked ? `${ids!.length} picked` : found ? `cohort ${found.name}` : null,
    loading: saved.isPending && !!experiment,
    /** Read on a saved cohort by name, or on every item with none; picked ids are let go. */
    choose: (value: string) => {
      if (value === "*picked") return;
      void setIds(null);
      void setCohort(value || null);
    },
  };
}

type Cohort = ReturnType<typeof useCohort>;

/** The control choosing the cohort, shown once there are picked items or saved cohorts. */
export function CohortSelect({ cohort }: { cohort: Cohort }) {
  const control = useRules()("items/cohort");
  if (!cohort.picked && (cohort.saved.data?.length ?? 0) === 0) return null;
  return (
    <label
      className={cn("flex items-center gap-1.5 text-xs", control.hidden && "hidden")}
      {...part("items/cohort")}
    >
      <span className="text-muted-foreground">{control.label ?? "On"}</span>
      <NativeSelect
        value={cohort.picked ? "*picked" : (cohort.wanted ?? "")}
        onChange={(e) => cohort.choose(e.target.value)}
        className="text-xs"
      >
        <option value="">every item</option>
        {cohort.picked && <option value="*picked">{cohort.ids!.length} picked</option>}
        {cohort.saved.data?.map((c) => (
          <option key={c.name} value={c.name}>
            cohort {c.name} · {c.ids.length}
          </option>
        ))}
      </NativeSelect>
    </label>
  );
}

/** What the items are read on, when not every item: a saved cohort's note, ids no file holds,
 * or a cohort name the experiment does not have. */
export function CohortNote({ cohort }: { cohort: Cohort }) {
  const name = cohort.wanted;
  const found = !!cohort.found || !!cohort.picked;
  const note = cohort.picked ? null : (cohort.found?.note ?? null);
  const { notHeld } = cohort;
  if (!found && (!name || cohort.loading)) return null;
  if (found && !note && notHeld === 0) return null;
  return (
    <div className="flex flex-col gap-1 text-xs" {...part("items/cohort/note")}>
      {!found && <p className="text-negative">This experiment has no cohort {name}.</p>}
      {note && <p className="text-muted-foreground">{note}</p>}
      {notHeld > 0 && (
        <p className="text-muted-foreground">
          {notHeld} of the cohort&apos;s items are not in these files.
        </p>
      )}
    </div>
  );
}
