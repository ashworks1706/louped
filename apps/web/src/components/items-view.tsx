"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Help } from "@/components/help";
import { arrange, part, partId, PartData, PartNote, useRules, type Rule } from "@/components/parts";
import { Term } from "@/components/term";
import { ScoreCell } from "@/components/metric";
import { RecordFields, RecordsTable } from "@/components/record-view";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cohortStats, isSnapshot, q, type PairedScore, type RunDetail } from "@/lib/api";
import {
  artifactQuery,
  asBinary,
  brief,
  defaultField,
  downloadJsonl,
  itemFolders,
  joinKey,
  parseJsonl,
  sharedFields,
  splitBy,
  splitColumns,
  stem,
  textField,
  traceShape,
  wilson,
  type Row,
} from "@/lib/artifacts";
import { cn } from "@/lib/utils";

/** Whether a run has per-item files to line up: a folder of two or more JSONL files. */
export function hasItems(run: RunDetail): boolean {
  return itemFolders(run.artifacts.map((a) => a.path)).length > 0;
}

/** A run's per-item records, one row per item and one column per condition (a JSONL file in the
 * same folder), each read against the reference condition. */
export function ItemsView({ run }: { run: RunDetail }) {
  const folders = useMemo(() => itemFolders(run.artifacts.map((a) => a.path)), [run.artifacts]);
  const [set, setSet] = useQueryState("set", parseAsString);
  const rule = useRules();
  const records = rule("items/records");
  const folder =
    folders.find((f) => f.dir === (set ?? records.default)) ??
    folders.find((f) => f.dir === set) ??
    folders[0];
  if (!folder) return <p className="text-muted-foreground text-sm">No per-item files.</p>;
  return (
    <div className="flex flex-col gap-4">
      {folders.length > 1 && !records.hidden && (
        <label className="flex items-center gap-2 text-sm" {...part("items/records")}>
          <span className="text-muted-foreground">{records.label ?? "Records"}</span>
          <NativeSelect value={folder.dir} onChange={(e) => void setSet(e.target.value)}>
            {folders.map((f) => (
              <option key={f.dir} value={f.dir}>
                {f.dir || "(top level)"} · {f.files.length} files
              </option>
            ))}
          </NativeSelect>
        </label>
      )}
      <Folder
        key={folder.dir}
        runId={run.id}
        experiment={run.experiment}
        dir={folder.dir}
        files={folder.files}
        meanings={run.artifacts.find((a) => a.path === join(folder.dir, FIELDS))?.path}
      />
    </div>
  );
}

/** What each record field means, written by the run beside its records: {"field": "meaning"}. */
const FIELDS = "fields.json";
const join = (dir: string, name: string) => (dir ? `${dir}/${name}` : name);

function Folder({
  runId,
  experiment,
  dir,
  files,
  meanings,
}: {
  runId: string;
  experiment: string | null | undefined;
  dir: string;
  files: string[];
  meanings?: string;
}) {
  const queries = useQueries({ queries: files.map((f) => artifactQuery(runId, f)) });
  const about = useQuery({ ...artifactQuery(runId, meanings ?? ""), enabled: !!meanings });
  const failed = queries.find((q) => q.error);
  if (failed) return <p className="text-negative text-sm">{String(failed.error)}</p>;
  if (queries.some((q) => q.data === undefined)) return <Skeleton className="h-64 w-full" />;
  const tables = queries.map((q) => parseJsonl(q.data!).rows);
  // a folder of traces (one request a file) is not conditions over the same items
  if (tables.every((t) => traceShape(t) !== null)) {
    const dir = files[0].includes("/") ? files[0].slice(0, files[0].lastIndexOf("/")) : "";
    return (
      <p className="text-muted-foreground text-sm">
        These files are traces, one request each, not conditions over the same items.{" "}
        <Link
          href={`?id=${encodeURIComponent(runId)}&tab=artifacts&file=${encodeURIComponent(`${dir}/*`)}`}
          className="text-foreground underline underline-offset-4"
        >
          Read them as timelines
        </Link>
        .
      </p>
    );
  }
  const meaning = about.error
    ? { meanings: {}, error: String(about.error) }
    : parseMeanings(about.data);
  return (
    <div className="flex flex-col gap-3">
      {meaning.error && (
        <p className="text-negative text-sm">
          {FIELDS} not read: {meaning.error}
        </p>
      )}
      <Aligned
        files={files}
        tables={tables}
        about={meaning.meanings}
        run={{ id: runId, experiment: experiment ?? null, folder: dir }}
      />
    </div>
  );
}

/** fields.json as {field: meaning}; anything else in it is an error to show, not to skip. */
function parseMeanings(text: string | undefined): {
  meanings: Record<string, string>;
  error?: string;
} {
  if (!text) return { meanings: {} };
  let got: unknown;
  try {
    got = JSON.parse(text);
  } catch (e) {
    return { meanings: {}, error: String(e) };
  }
  if (!got || typeof got !== "object" || Array.isArray(got))
    return { meanings: {}, error: 'expected {"field": "meaning"}' };
  const entries = Object.entries(got);
  const bad = entries.filter(([, v]) => typeof v !== "string").map(([k]) => k);
  return {
    meanings: Object.fromEntries(
      entries.filter((e): e is [string, string] => typeof e[1] === "string"),
    ),
    error: bad.length ? `not text: ${bad.join(", ")}` : undefined,
  };
}

/** A record for the agent: long text cut, so a pick of many items stays readable. */
function trim(value: unknown): unknown {
  if (typeof value === "string") return value.length > 2000 ? `${value.slice(0, 2000)}…` : value;
  if (Array.isArray(value)) return value.slice(0, 50).map(trim);
  if (value && typeof value === "object")
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, trim(v)]));
  return value;
}

type Transition = { down: number; up: number; wasOne: number; wasZero: number };

/** One file's records, as a table or, split by a column (an arm, a condition), lined up item by
 * item across its values as the Items tab lines up a folder of files. */
export function LinedUp({ rows, name }: { rows: Row[]; name: string }) {
  const columns = useMemo(() => splitColumns(rows), [rows]);
  const [by, setBy] = useQueryState("by", parseAsString);
  const split = by && columns.includes(by) ? splitBy(rows, by) : null;
  return (
    <div className="flex flex-col gap-3">
      {columns.length > 0 && (
        <label className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Line up by</span>
          <NativeSelect
            value={split ? by! : ""}
            onChange={(e) => void setBy(e.target.value || null)}
            className="font-mono text-xs"
          >
            <option value="">none: every row</option>
            {columns.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </NativeSelect>
        </label>
      )}
      {split ? (
        <Aligned files={split.names} tables={split.tables} />
      ) : (
        <RecordsTable rows={rows} name={name} />
      )}
    </div>
  );
}

/** Where lined-up records come from, when they are a run's: its cohorts apply. */
type Source = { id: string; experiment: string | null; folder: string };

function Aligned({
  files,
  tables,
  about = {},
  run,
}: {
  files: string[];
  tables: Row[][];
  about?: Record<string, string>;
  run?: Source;
}) {
  const names = files.map(stem);
  const key = useMemo(() => joinKey(tables), [tables]);
  const fields = useMemo(() => (key ? sharedFields(tables, key) : []), [tables, key]);
  const [fieldParam, setField] = useQueryState("field", parseAsString);
  const [refParam, setRef] = useQueryState("ref", parseAsString);
  const [showParam, setShow] = useQueryState("show", parseAsString);
  const [item, setItem] = useQueryState("item", parseAsString);
  const [idsParamValue, setIds] = useQueryState("ids", parseAsString);
  const [cohortName, setCohort] = useQueryState("cohort", parseAsString);
  const saved = useQuery({
    ...q.cohorts(run?.experiment ?? ""),
    enabled: !!run?.experiment,
  });
  const [search, setSearch] = useState("");
  const rule = useRules();
  // a control's value: the URL's, else the layout's default for it, else the app's
  const control = (name: string) => rule(`items/${name}`);
  const show = showParam ?? control("show").default ?? null;

  // a field with one value per file (the condition's own name) differs by construction
  const constant = useMemo(
    () =>
      new Set(
        Object.keys(tables[0]?.[0] ?? {}).filter((f) =>
          tables.every((t) => new Set(t.map((r) => JSON.stringify(r[f]))).size === 1),
        ),
      ),
    [tables],
  );
  const wanted = fieldParam ?? control("compare").default;
  const field = wanted && fields.includes(wanted) ? wanted : defaultField(tables, fields);
  const against = refParam ?? control("against").default;
  const ref = against && names.includes(against) ? names.indexOf(against) : 0;

  const every = useMemo(() => {
    if (!key) return [];
    const byKey = tables.map((t) => new Map(t.map((r) => [String(r[key]), r])));
    const order = [...new Set(tables.flatMap((t) => t.map((r) => String(r[key]))))];
    return order.map((id) => ({ id, rows: byKey.map((m) => m.get(id)) }));
  }, [tables, key]);
  // a cohort: the items picked (ids in the URL) or saved by name; every item without one
  const cohortWanted = cohortName ?? rule("items/cohort").default ?? null;
  const savedCohort = saved.data?.find((c) => c.name === cohortWanted);
  const cohortIds = useMemo(
    () =>
      idsParamValue ? idsParamValue.split(",").map(decodeURIComponent) : (savedCohort?.ids ?? null),
    [idsParamValue, savedCohort],
  );
  const items = useMemo(() => {
    if (!cohortIds) return every;
    const want = new Set(cohortIds);
    return every.filter((it) => want.has(it.id));
  }, [every, cohortIds]);
  const notHeld = cohortIds ? new Set(cohortIds).size - items.length : 0;

  // the item's own fields (its question, its answer): equal across the conditions for every item
  // that more than one file holds, and not a file's own name for itself
  const itemFields = useMemo(() => {
    const held = every.map((i) => i.rows.filter((r): r is Row => !!r)).filter((r) => r.length > 1);
    if (held.length === 0) return [];
    return Object.keys(held[0][0]).filter(
      (k) =>
        !constant.has(k) &&
        held.every((rs) => rs.every((r) => JSON.stringify(r[k]) === JSON.stringify(rs[0][k]))),
    );
  }, [every, constant]);

  // each condition's paired difference from the reference on these items, from the server,
  // whose interval is the one compare and the agent report
  const paired = useQuery({
    queryKey: ["cohort-stats", run?.id, run?.folder, field, names[ref], cohortIds],
    queryFn: () =>
      cohortStats(run!.id, { ids: cohortIds, folder: run!.folder, field, reference: names[ref] }),
    enabled: !!run && !!key && !!field && !isSnapshot(),
    retry: false,
  });

  if (!key || !field)
    return (
      <p className="text-muted-foreground text-sm">
        These files ({names.join(", ")}) share no field that names an item once in every file, so
        they cannot be lined up. Each one is under Artifacts.
      </p>
    );

  const binary = every.every((it) => it.rows.every((r) => !r || asBinary(r[field]) !== null));
  const text = textField(tables[ref], key);
  const differs = (it: (typeof items)[number], i: number) =>
    i !== ref &&
    it.rows[i] !== undefined &&
    it.rows[ref] !== undefined &&
    JSON.stringify(it.rows[i]![field]) !== JSON.stringify(it.rows[ref]![field]);

  // per condition against the reference: how many items changed, and for a 0/1 field which way
  const stats = names.map((_, i) => {
    let both = 0;
    let changed = 0;
    let k = 0;
    let n = 0;
    const t: Transition = { down: 0, up: 0, wasOne: 0, wasZero: 0 };
    for (const it of items) {
      const r = it.rows[i];
      if (!r) continue;
      const b = asBinary(r[field]);
      if (b !== null) {
        n += 1;
        k += b;
      }
      const base = it.rows[ref];
      if (!base || i === ref) continue;
      both += 1;
      if (differs(it, i)) changed += 1;
      const before = asBinary(base[field]);
      if (before === 1) {
        t.wasOne += 1;
        if (b === 0) t.down += 1;
      } else if (before === 0) {
        t.wasZero += 1;
        if (b === 1) t.up += 1;
      }
    }
    return { both, changed, k, n, t };
  });

  const pairs = new Map((paired.data?.paired ?? []).map((p) => [p.name, p]));
  const cohortLabel = idsParamValue
    ? `${cohortIds!.length} picked`
    : savedCohort
      ? `cohort ${savedCohort.name}`
      : null;

  const needle = search.toLowerCase();
  const shown = items.filter((it) => {
    if (
      needle &&
      !JSON.stringify(it.rows).toLowerCase().includes(needle) &&
      !it.id.toLowerCase().includes(needle)
    )
      return false;
    if (!show || show === "all") return true;
    if (show === "changed") return names.some((_, i) => differs(it, i));
    const [kind, cond] = show.split(":");
    const i = names.indexOf(cond);
    if (i < 0) return true;
    const before = asBinary(it.rows[ref]?.[field]);
    const after = asBinary(it.rows[i]?.[field]);
    if (kind === "changed") return differs(it, i);
    if (kind === "down") return before === 1 && after === 0;
    if (kind === "up") return before === 0 && after === 1;
    return true;
  });
  const opened = every.find((it) => it.id === item);

  // what a picked part stands for: an item's record under every condition, a condition's numbers
  const itemsData = (id: string) => {
    const [, kind, a, b] = id.split("/").map(decodeURIComponent);
    const found = every.find((it) => it.id === a);
    const records = (it: (typeof items)[number]) =>
      Object.fromEntries(names.map((n, i) => [n, trim(it.rows[i] ?? null)]));
    if (kind === "row" && found)
      return {
        [key!]: found.id,
        compared_on: field,
        reference: names[ref],
        records: records(found),
        // where it is from, so picked rows can be saved as a cohort
        ...(run
          ? { from: { run: run.id, experiment: run.experiment, folder: run.folder, key } }
          : {}),
      };
    if (kind === "cell" && found) {
      const i = names.indexOf(b);
      return {
        [key!]: found.id,
        condition: b,
        compared_on: field,
        reference: names[ref],
        differs: differs(found, i),
        record: trim(found.rows[i] ?? null),
        reference_record: trim(found.rows[ref] ?? null),
      };
    }
    if (kind === "stat") {
      const i = names.indexOf(a);
      if (i < 0) return null;
      const st = stats[i];
      const ci = binary && st.n ? wilson(st.k, st.n) : null;
      const p = pairs.get(a);
      return {
        condition: a,
        field,
        reference: names[ref],
        on: cohortLabel ?? "every item",
        ...(p
          ? {
              paired: { n: p.n, diff: p.diff, interval95: [p.low, p.high], up: p.up, down: p.down },
            }
          : {}),
        ...(binary ? { rate: st.n ? st.k / st.n : null, k: st.k, n: st.n, interval95: ci } : {}),
        ...(i === ref
          ? {}
          : binary
            ? { down: `${st.t.down}/${st.t.wasOne}`, up: `${st.t.up}/${st.t.wasZero}` }
            : { changed: `${st.changed}/${st.both}` }),
      };
    }
    if (kind === "count") return { shown: shown.length, of: items.length, show: show ?? "all" };
    if (kind === "column") return { column: a, compared_on: field };
    return null;
  };
  const itemData = (id: string) => {
    if (!opened) return null;
    const [, kind, section, name] = id.split("/").map(decodeURIComponent);
    const row = (s: string) =>
      s === "item" ? opened.rows.find(Boolean) : opened.rows[names.indexOf(s)];
    if (kind === "field")
      return {
        [key!]: opened.id,
        section,
        field: name,
        value: trim(row(section)?.[name] ?? null),
        meaning: about[name] ?? null,
      };
    if (kind === "section")
      return { [key!]: opened.id, section, record: trim(row(section) ?? null) };
    return { [key!]: opened.id };
  };

  // the table's columns as the layout orders them: the key, the text, then each condition
  const columns = arrange(
    [
      { name: key, kind: "key" as const },
      ...(text ? [{ name: text, kind: "text" as const }] : []),
      ...names.map((n) => ({ name: n, kind: "condition" as const })),
    ],
    (c) => partId("items/column", c.name),
    rule,
  );
  const columnRule = (c: string) => rule(partId("items/column", c));

  return (
    <div className="flex flex-col gap-4">
      <PartData prefix="items" resolve={itemsData} />
      <PartData prefix="item" resolve={itemData} />
      <Summary
        names={names}
        ref_={ref}
        field={field}
        binary={binary}
        stats={stats}
        rule={rule}
        pairs={pairs}
        pairedError={paired.error ? String(paired.error) : (paired.data?.unpaired ?? null)}
      />
      <div className="flex flex-wrap items-center gap-2">
        {!control("search").hidden && (
          <Input
            placeholder="Search items…"
            aria-label="Search items"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-xs"
            {...part("items/search")}
          />
        )}
        <label
          className={cn("flex items-center gap-1.5 text-xs", control("compare").hidden && "hidden")}
          {...part("items/compare")}
        >
          <span className="text-muted-foreground">{control("compare").label ?? "Compare on"}</span>
          <NativeSelect
            value={field}
            onChange={(e) => void setField(e.target.value)}
            className="font-mono text-xs"
          >
            {fields.map((f) => (
              <option key={f}>{f}</option>
            ))}
          </NativeSelect>
        </label>
        <label
          className={cn("flex items-center gap-1.5 text-xs", control("against").hidden && "hidden")}
          {...part("items/against")}
        >
          <span className="text-muted-foreground">{control("against").label ?? "against"}</span>
          <NativeSelect
            value={names[ref]}
            onChange={(e) => void setRef(e.target.value)}
            className="font-mono text-xs"
          >
            {names.map((n) => (
              <option key={n}>{n}</option>
            ))}
          </NativeSelect>
        </label>
        <label
          className={cn("flex items-center gap-1.5 text-xs", control("show").hidden && "hidden")}
          {...part("items/show")}
        >
          <span className="text-muted-foreground">{control("show").label ?? "Show"}</span>
          <NativeSelect
            value={show ?? "all"}
            onChange={(e) =>
              // "every item" is the app's own default; over a layout's it has to be said
              void setShow(
                e.target.value === "all" && !control("show").default ? null : e.target.value,
              )
            }
            className="text-xs"
          >
            <option value="all">every item</option>
            <option value="changed">changed in any condition</option>
            {names.map((n, i) =>
              i === ref ? null : binary ? (
                <optgroup key={n} label={n}>
                  <option value={`changed:${n}`}>changed in {n}</option>
                  <option value={`down:${n}`}>1 → 0 in {n}</option>
                  <option value={`up:${n}`}>0 → 1 in {n}</option>
                </optgroup>
              ) : (
                <option key={n} value={`changed:${n}`}>
                  changed in {n}
                </option>
              ),
            )}
          </NativeSelect>
        </label>
        {(idsParamValue || (saved.data?.length ?? 0) > 0) && (
          <label
            className={cn(
              "flex items-center gap-1.5 text-xs",
              control("cohort").hidden && "hidden",
            )}
            {...part("items/cohort")}
          >
            <span className="text-muted-foreground">{control("cohort").label ?? "On"}</span>
            <NativeSelect
              value={idsParamValue ? "*picked" : (cohortWanted ?? "")}
              onChange={(e) => {
                if (e.target.value === "*picked") return;
                void setIds(null);
                void setCohort(e.target.value || null);
              }}
              className="text-xs"
            >
              <option value="">every item</option>
              {idsParamValue && <option value="*picked">{cohortIds!.length} picked</option>}
              {saved.data?.map((c) => (
                <option key={c.name} value={c.name}>
                  cohort {c.name} · {c.ids.length}
                </option>
              ))}
            </NativeSelect>
          </label>
        )}
        <span className="text-muted-foreground ml-auto font-mono text-xs" {...part("items/count")}>
          {shown.length} of {items.length} items
        </span>
        <Button
          variant="outline"
          size="sm"
          className={cn(control("download").hidden && "hidden")}
          {...part("items/download")}
          title="Download the items shown, each with its record in every condition, as JSONL"
          onClick={() =>
            downloadJsonl(
              shown.map((it) => ({
                [key]: it.rows.find(Boolean)?.[key] ?? it.id,
                ...Object.fromEntries(names.map((n, i) => [n, it.rows[i] ?? null])),
              })),
              "items.shown.jsonl",
            )
          }
        >
          <Download /> Items
        </Button>
      </div>
      <CohortNote
        name={cohortWanted}
        found={!!savedCohort || !!idsParamValue}
        loading={saved.isPending && !!run?.experiment}
        note={idsParamValue ? null : (savedCohort?.note ?? null)}
        notHeld={notHeld}
      />
      <div className="overflow-x-auto rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {columns.map((c) => {
                const r = columnRule(c.name);
                const label = (
                  <>
                    {r.label ?? c.name}
                    {c.kind === "condition" && names.indexOf(c.name) === ref && (
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
                    )}
                  >
                    <span className="inline-flex items-center gap-1">{label}</span>
                  </TableHead>
                );
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((it) => (
              <TableRow
                key={it.id}
                {...part(partId("items/row", it.id))}
                className="focus-visible:ring-ring/50 cursor-pointer outline-none focus-visible:ring-[3px] focus-visible:ring-inset"
                data-state={item === it.id ? "selected" : undefined}
                tabIndex={0}
                onClick={() => void setItem(it.id)}
                onKeyDown={(e) => {
                  if (e.key !== "Enter" && e.key !== " ") return;
                  e.preventDefault();
                  void setItem(it.id);
                }}
              >
                {columns.map((c) => {
                  if (c.kind === "key")
                    return (
                      <TableCell key={c.name} className="text-muted-foreground font-mono text-xs">
                        {it.id}
                        {text && !columnRule(text).hidden && (
                          <span className="text-foreground mt-1 line-clamp-2 block font-sans text-sm whitespace-normal sm:hidden">
                            {brief(it.rows[ref]?.[text], 140)}
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
                        {brief(it.rows[ref]?.[c.name], 140)}
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
      <Sheet open={!!opened} onOpenChange={(o) => !o && void setItem(null)}>
        <SheetContent className="sm:max-w-6xl">
          {opened && (
            <ItemDetail
              id={opened.id}
              keyName={key}
              names={names}
              rows={opened.rows}
              ref_={ref}
              constant={constant}
              itemFields={itemFields}
              about={about}
            />
          )}
        </SheetContent>
      </Sheet>
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

function Summary({
  names,
  ref_,
  field,
  binary,
  stats,
  rule,
  pairs,
  pairedError,
}: {
  names: string[];
  ref_: number;
  field: string;
  binary: boolean;
  stats: { both: number; changed: number; k: number; n: number; t: Transition }[];
  rule: (id: string) => Rule;
  pairs: Map<string, PairedScore>;
  pairedError: string | null;
}) {
  const heading = rule("items/summary");
  const stat = (n: string) => partId("items/stat", n);
  return (
    <div className="flex flex-col gap-2">
      <div
        className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-medium"
        {...part("items/summary")}
      >
        {heading.label ?? "By condition"}
        {binary ? (
          <span className="text-muted-foreground flex items-center gap-3 text-xs font-normal">
            <Term k="wilson">rate, 95% interval</Term>
            <Term k="transition">1→0 · 0→1</Term>
          </span>
        ) : (
          <Help>{`How many items have a different ${field} from the reference, out of the items both files hold.`}</Help>
        )}
      </div>
      <PartNote rule={heading} />
      {pairedError && (
        <p className="text-negative text-xs">Paired differences not computed: {pairedError}</p>
      )}
      <div className="grid overflow-hidden rounded-xl border sm:grid-cols-2 lg:grid-cols-4 [&>*]:-mr-px [&>*]:-mb-px [&>*]:border-r [&>*]:border-b">
        {arrange(names, stat, rule).map((n) => {
          const i = names.indexOf(n);
          const s = stats[i];
          const r = rule(stat(n));
          const ci = binary ? wilson(s.k, s.n) : null;
          return (
            <div key={n} className="flex flex-col gap-1 p-4" {...part(stat(n))}>
              <span className="text-muted-foreground flex items-center gap-1 font-mono text-xs">
                {r.label ?? n}
                {i === ref_ && " · reference"}
                {r.about && <Help>{r.about}</Help>}
              </span>
              {binary ? (
                <>
                  <span className="font-mono text-2xl font-medium tabular-nums">
                    {s.n ? `${((s.k / s.n) * 100).toFixed(1)}%` : "—"}
                  </span>
                  <span className="text-muted-foreground font-mono text-xs tabular-nums">
                    {s.k}/{s.n}
                    {ci && ` · ${(ci[0] * 100).toFixed(0)}–${(ci[1] * 100).toFixed(0)}%`}
                  </span>
                  {i !== ref_ && (
                    <span className="font-mono text-xs tabular-nums">
                      <span className="text-negative">
                        1→0 {s.t.down}/{s.t.wasOne}
                      </span>
                      {" · "}
                      <span className="text-positive">
                        0→1 {s.t.up}/{s.t.wasZero}
                      </span>
                    </span>
                  )}
                </>
              ) : (
                <span className="font-mono text-2xl font-medium tabular-nums">
                  {i === ref_ ? "—" : `${s.changed}/${s.both}`}
                </span>
              )}
              {i !== ref_ && !binary && (
                <span className="text-muted-foreground text-xs">changed from the reference</span>
              )}
              {pairs.has(n) && <Paired p={pairs.get(n)!} binary={binary} />}
              <PartNote rule={r} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** A condition minus the reference over the items both hold, with its 95% interval: points
 * for a 0/1 field. */
function Paired({ p, binary }: { p: PairedScore; binary: boolean }) {
  const f = (x: number) =>
    binary
      ? `${x > 0 ? "+" : ""}${(x * 100).toFixed(1)}`
      : `${x > 0 ? "+" : ""}${x.toPrecision(3)}`;
  return (
    <span className="text-muted-foreground flex items-center gap-1 font-mono text-xs tabular-nums">
      Δ {f(p.diff)}
      {binary && " pts"} · {f(p.low)} to {f(p.high)}
      <Help>{`Paired difference from the reference over the ${p.n} items both hold, with its 95% bootstrap interval: the interval the agent and Compare report.`}</Help>
    </span>
  );
}

/** What the items are read on, when not every item: a saved cohort's note, ids no file holds,
 * or a cohort name the experiment does not have. */
function CohortNote({
  name,
  found,
  loading,
  note,
  notHeld,
}: {
  name: string | null;
  found: boolean;
  loading: boolean;
  note: string | null;
  notHeld: number;
}) {
  if (!found && (!name || loading)) return null;
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

/** One item: what it is (the fields the conditions share for every item, such as its question
 * and its answer), then each condition's record side by side with what differs from the reference
 * outlined. A field's ? is its meaning from the run's fields.json. */
function ItemDetail({
  id,
  keyName,
  names,
  rows,
  ref_,
  constant,
  itemFields,
  about,
}: {
  id: string;
  keyName: string;
  names: string[];
  rows: (Row | undefined)[];
  ref_: number;
  constant: Set<string>;
  itemFields: string[];
  about: Record<string, string>;
}) {
  const base = rows[ref_];
  const present = rows.filter((r): r is Row => !!r);
  const shared = itemFields.filter((k) => present[0] && k in present[0]);
  const item = Object.fromEntries(shared.map((k) => [k, present[0][k]]));
  const own = (r: Row) =>
    Object.fromEntries(Object.entries(r).filter(([k]) => !shared.includes(k) && !constant.has(k)));
  const rule = useRules();
  const section = (n: string) => partId("item/section", n);
  const fieldOf = (n: string) => (k: string) => partId("item/field", n, k);
  const itself = rule(section("item"));
  return (
    <>
      <div className="border-b px-6 py-4 pr-12">
        <SheetTitle className="font-semibold" {...part("item/title")}>
          <span className="text-muted-foreground font-mono text-sm">{keyName}</span> {id}
        </SheetTitle>
        <SheetDescription className="text-muted-foreground text-xs">
          The item, then what each condition did with it; fields that differ from {names[ref_]} are
          outlined.
        </SheetDescription>
      </div>
      <div className="flex flex-1 flex-col gap-6 overflow-auto px-6 py-5">
        {shared.length > 1 && !itself.hidden && (
          <section className="flex flex-col gap-3 rounded-xl border p-4" {...part(section("item"))}>
            <h3 className="text-sm font-medium">{itself.label ?? "The item"}</h3>
            <RecordFields row={item} about={about} partOf={fieldOf("item")} />
          </section>
        )}
        <div
          className="grid gap-6"
          style={{ gridTemplateColumns: `repeat(auto-fit, minmax(16rem, 1fr))` }}
        >
          {names.map((n, i) => {
            const r = rows[i];
            const own_ = rule(section(n));
            if (own_.hidden) return null;
            const changed = new Set(
              r && base && i !== ref_
                ? Object.keys(r).filter(
                    (k) => !constant.has(k) && JSON.stringify(r[k]) !== JSON.stringify(base[k]),
                  )
                : [],
            );
            return (
              <section key={n} className="flex min-w-0 flex-col gap-3" {...part(section(n))}>
                <h3 className="border-b pb-1 font-mono text-sm font-medium">
                  {own_.label ?? n}
                  {i === ref_ && <span className="text-muted-foreground"> · reference</span>}
                </h3>
                {r ? (
                  <RecordFields
                    row={shared.length > 1 ? own(r) : r}
                    changed={changed}
                    about={about}
                    partOf={fieldOf(n)}
                  />
                ) : (
                  <p className="text-muted-foreground text-sm">Not in this file.</p>
                )}
              </section>
            );
          })}
        </div>
      </div>
    </>
  );
}
