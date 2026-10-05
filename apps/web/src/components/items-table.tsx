"use client";

import { Help } from "@/components/help";
import { ScoreCell } from "@/components/metric";
import { arrange, part, partId, useRules } from "@/components/parts";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { asBinary, brief, type Row } from "@/lib/artifacts";
import { cn } from "@/lib/utils";

/** One item lined up: its record in each file, in the files' order, undefined where one lacks it. */
export type Item = { id: string; rows: (Row | undefined)[] };

/** The lined-up items, one row each and one column per condition, each cell outlined where it
 * differs from the reference; a row opens its item. */
export function AlignedTable({
  items,
  keyName,
  text,
  names,
  ref_,
  field,
  binary,
  derived,
  differs,
  opened,
  open,
}: {
  items: Item[];
  keyName: string;
  text: string | null;
  names: string[];
  ref_: number;
  field: string;
  binary: boolean;
  /** The added columns, and each item's values for them. */
  derived: { cols: string[]; of: (id: string) => Row };
  differs: (it: Item, i: number) => boolean;
  opened: string | null;
  open: (id: string) => void;
}) {
  const rule = useRules();
  const textOf = (it: Item) => it.rows[ref_]?.[text!];
  // the table's columns as the layout orders them: the key, the text, then each condition
  const columns = arrange(
    [
      { name: keyName, kind: "key" as const },
      ...(text ? [{ name: text, kind: "text" as const }] : []),
      ...names.map((n) => ({ name: n, kind: "condition" as const })),
      ...derived.cols.map((n) => ({ name: n, kind: "derived" as const })),
    ],
    (c) => partId("items/column", c.name),
    rule,
  );
  const columnRule = (c: string) => rule(partId("items/column", c));
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {columns.map((c) => {
              const r = columnRule(c.name);
              const label = (
                <>
                  {r.label ?? c.name}
                  {c.kind === "condition" && names.indexOf(c.name) === ref_ && (
                    <span className="text-muted-foreground"> · ref</span>
                  )}
                  {r.about && <Help>{r.about}</Help>}
                </>
              );
              return (
                <TableHead
                  key={c.name}
                  {...part(partId("items/column", c.name))}
                  className={cn(
                    "font-mono text-xs",
                    c.kind === "key" && "w-16",
                    c.kind === "text" && "hidden sm:table-cell",
                    c.kind === "condition" && "text-right whitespace-nowrap",
                    c.kind === "derived" && "whitespace-nowrap",
                  )}
                >
                  <span className="inline-flex items-center gap-1">{label}</span>
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((it) => (
            <TableRow
              key={it.id}
              {...part(partId("items/row", it.id))}
              className="focus-visible:ring-ring/50 cursor-pointer outline-none focus-visible:ring-[3px] focus-visible:ring-inset"
              data-state={opened === it.id ? "selected" : undefined}
              tabIndex={0}
              onClick={() => open(it.id)}
              onKeyDown={(e) => {
                if (e.key !== "Enter" && e.key !== " ") return;
                e.preventDefault();
                open(it.id);
              }}
            >
              {columns.map((c) => {
                if (c.kind === "key")
                  return (
                    <TableCell key={c.name} className="text-muted-foreground font-mono text-xs">
                      {it.id}
                      {text && !columnRule(text).hidden && (
                        <span className="text-foreground mt-1 line-clamp-2 block font-sans text-sm whitespace-normal sm:hidden">
                          {brief(textOf(it), 140)}
                        </span>
                      )}
                    </TableCell>
                  );
                if (c.kind === "text")
                  return (
                    <TableCell
                      key={c.name}
                      className="hidden max-w-md truncate text-sm sm:table-cell"
                    >
                      {brief(textOf(it), 140)}
                    </TableCell>
                  );
                if (c.kind === "derived")
                  return (
                    <TableCell
                      key={c.name}
                      className="max-w-48 truncate font-mono text-xs"
                      {...part(partId("items/cell", it.id, c.name))}
                    >
                      {brief(derived.of(it.id)[c.name] ?? "", 60)}
                    </TableCell>
                  );
                const i = names.indexOf(c.name);
                return (
                  <TableCell
                    key={c.name}
                    className="text-right"
                    {...part(partId("items/cell", it.id, c.name))}
                  >
                    <Cell
                      value={it.rows[i]?.[field]}
                      missing={!it.rows[i]}
                      binary={binary}
                      changed={differs(it, i)}
                    />
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Cell({
  value,
  missing,
  binary,
  changed,
}: {
  value: unknown;
  missing: boolean;
  binary: boolean;
  changed: boolean;
}) {
  if (missing) return <span className="text-muted-foreground font-mono text-xs">—</span>;
  const b = binary ? asBinary(value) : null;
  return (
    <span
      className={cn(
        "inline-flex min-w-7 justify-end rounded px-1.5 py-0.5",
        changed &&
          (b === 0 ? "bg-negative/10" : b === 1 ? "bg-positive/10" : "bg-muted font-medium"),
      )}
      title={changed ? "differs from the reference" : undefined}
    >
      {b !== null ? (
        <ScoreCell value={b} />
      ) : (
        <span className="font-mono text-xs">{brief(value, 30)}</span>
      )}
    </span>
  );
}
