"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";

import { part, partId, useRules } from "@/components/parts";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { q, type EvalTask } from "@/lib/api";

/** Pick an Inspect task for inspect eval: the project's own first, then inspect_evals' benchmarks
 * by group, searchable by name, title and what it measures. */
export function EvalPicker({ flag, onPick }: { flag: string; onPick: (task: string) => void }) {
  const [open, setOpen] = useState(false);
  const address = partId("launch/browse", flag);
  const rule = useRules()(address);
  if (rule.hidden) return null;
  return (
    <>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="h-8 shrink-0"
        onClick={() => setOpen(true)}
        {...part(address)}
      >
        <Search /> {rule.label ?? "Browse"}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="p-0">
          <DialogTitle className="sr-only">Eval tasks</DialogTitle>
          <DialogDescription className="sr-only">
            The project&apos;s Inspect tasks and inspect_evals&apos; benchmarks.
          </DialogDescription>
          {open && (
            <Tasks
              onPick={(task) => {
                onPick(task);
                setOpen(false);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

function Tasks({ onPick }: { onPick: (task: string) => void }) {
  const tasks = useQuery(q.evalTasks());
  const rules = useRules();
  const groups = new Map<string, EvalTask[]>();
  for (const t of tasks.data ?? []) {
    if (rules(partId("launch/eval", t.task)).hidden) continue;
    const group = t.source === "project" ? `This project · ${t.group}` : t.group;
    groups.set(group, [...(groups.get(group) ?? []), t]);
  }
  return (
    <Command loop>
      <CommandInput placeholder="Search tasks: gsm8k, honesty, coding…" />
      <CommandList className="max-h-[60vh]">
        <CommandEmpty>
          {tasks.isPending
            ? "Reading tasks…"
            : tasks.error
              ? String(tasks.error)
              : "No task matches. A task.py with @task in an experiment shows here."}
        </CommandEmpty>
        {[...groups].map(([group, list]) => (
          <CommandGroup key={group} heading={group}>
            {list.map((t) => (
              <CommandItem
                key={t.task}
                value={`${t.task} ${t.title} ${t.about ?? ""}`}
                onSelect={() => onPick(t.task)}
                className="flex flex-col items-start gap-0.5"
                {...part(partId("launch/eval", t.task))}
              >
                <span className="flex w-full items-baseline gap-2">
                  <span className="truncate font-mono text-xs">{t.task}</span>
                  {t.samples != null && (
                    <span className="text-muted-foreground ml-auto font-mono text-xs">
                      {t.samples.toLocaleString()}
                    </span>
                  )}
                </span>
                {t.about && (
                  <span className="text-muted-foreground line-clamp-1 text-xs">{t.about}</span>
                )}
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </Command>
  );
}
