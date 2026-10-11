"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ExternalLink, Table2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { parseAsString, useQueryStates } from "nuqs";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { Markdown } from "@/components/markdown";
import { Part, part, partId, PartData } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { Term } from "@/components/term";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ApiError,
  hubAdd,
  isSnapshot,
  q,
  type Dataset,
  type DatasetDetail,
  type Domain,
  type HubHit,
} from "@/lib/api";
import { jobHref } from "@/lib/href";

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const count = (n: number | null | undefined) => (n == null ? "—" : compact.format(n));
const bytes = (n: number | null | undefined) =>
  n == null ? "—" : n < 1e6 ? `${compact.format(n / 1e3)} KB` : `${compact.format(n / 1e6)} MB`;
const DOMAIN_TITLE: Record<Domain, string> = { behavior: "Behavior", efficiency: "Efficiency" };
/** A cell's value as text, cut so a long passage does not fill the table. */
const cell = (v: unknown) => {
  const text = typeof v === "string" ? v : JSON.stringify(v);
  return text === undefined ? "—" : text.length > 240 ? `${text.slice(0, 240)}…` : text;
};

/** The datasets this domain uses (its own and those listed under none), the Hub to add more,
 * and one dataset's rows in a side panel. */
export function DatasetsView({ domain }: { domain: Domain }) {
  const [s, set] = useQueryStates({
    q: parseAsString,
    open: parseAsString,
    config: parseAsString,
    split: parseAsString,
  });
  const all = useQuery(q.datasets());
  const mine = (all.data ?? []).filter((d) => !d.domains?.length || d.domains.includes(domain));
  const opened = mine.find((d) => d.id === s.open) ?? null;
  const openId = (id: string | null) => void set({ open: id, config: null, split: null });
  return (
    <div className="flex flex-col gap-6">
      {!isSnapshot() && <HubSearch domain={domain} q={s.q} onSearch={(t) => void set({ q: t })} />}
      <QueryState query={all}>
        {() =>
          mine.length === 0 ? (
            <EmptyState
              icon={Table2}
              title="No datasets here yet"
              body="Search the Hub above and add one to this page, or put JSONL, CSV, Parquet or JSON files in data/ at the project's root."
              action={{ href: "/hub/?kind=datasets", label: "Browse the Hub" }}
            />
          ) : (
            <DatasetsTable sets={mine} open={s.open} onOpen={openId} />
          )
        }
      </QueryState>
      <Sheet open={s.open !== null} onOpenChange={(o) => !o && openId(null)}>
        <SheetContent className="sm:max-w-4xl">
          {s.open !== null && (
            <Detail
              id={s.open}
              hub={opened ? opened.source === "hub" : !s.open.startsWith("data/")}
              listed={opened !== null}
              domain={domain}
              config={s.config}
              split={s.split}
              onPick={(config, split) => void set({ config, split })}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function DatasetsTable({
  sets,
  open,
  onOpen,
}: {
  sets: Dataset[];
  open: string | null;
  onOpen: (id: string) => void;
}) {
  const col = (id: string) => partId("datasets/column", id);
  const num = "text-right font-mono tabular-nums";
  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-muted-foreground text-xs font-medium" {...part("datasets/heading")}>
        {sets.length} {sets.length === 1 ? "dataset" : "datasets"}
      </h2>
      <PartData
        prefix="datasets/row"
        resolve={(id) => sets.find((d) => partId("datasets/row", d.id) === id) ?? null}
      />
      <div className="overflow-x-auto rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead {...part(col("name"))}>Name</TableHead>
              <TableHead {...part(col("source"))}>
                <Term k="datasetSource">Source</Term>
              </TableHead>
              <TableHead {...part(col("format"))}>Format</TableHead>
              <TableHead className="text-right" {...part(col("size"))}>
                Size
              </TableHead>
              <TableHead {...part(col("domains"))}>
                <Term k="datasetDomains">Listed under</Term>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sets.map((d) => {
              const training = d.source === "training";
              const go = () => !training && onOpen(d.id);
              return (
                <TableRow
                  key={`${d.source}:${d.id}`}
                  className={training ? undefined : "cursor-pointer"}
                  data-state={open === d.id ? "selected" : undefined}
                  tabIndex={training ? undefined : 0}
                  onClick={go}
                  onKeyDown={(e) => e.key === "Enter" && go()}
                  {...part(partId("datasets/row", d.id))}
                >
                  <TableCell className="max-w-md font-mono text-xs">
                    {training ? (
                      <Link
                        href={`/behavior/training-sets/?set=${encodeURIComponent(d.path ?? "")}`}
                        className="underline-offset-4 hover:underline"
                        title={d.path ?? undefined}
                      >
                        {d.id}
                      </Link>
                    ) : (
                      <span title={d.path ?? undefined}>{d.id}</span>
                    )}
                    {d.error && <p className="text-negative mt-1 font-sans">{d.error}</p>}
                  </TableCell>
                  <TableCell className="text-xs">{d.source}</TableCell>
                  <TableCell className="text-muted-foreground font-mono text-xs">
                    {d.format ?? "—"}
                  </TableCell>
                  <TableCell className={num}>
                    {d.rows != null ? `${count(d.rows)} rows` : bytes(d.size)}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {d.domains?.length ? d.domains.map((x) => DOMAIN_TITLE[x]).join(", ") : "both"}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

/** Search the Hub's datasets inline and add one to this domain; off when the Hub is. */
function HubSearch({
  domain,
  q: text,
  onSearch,
}: {
  domain: Domain;
  q: string | null;
  onSearch: (q: string | null) => void;
}) {
  const me = useQuery(q.hubMe());
  const off = me.isError && me.error instanceof ApiError && me.error.status === 403;
  return (
    <Part id="datasets/hub" className="flex flex-col gap-3">
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const t = String(new FormData(e.currentTarget).get("q") ?? "").trim();
          onSearch(t || null);
        }}
      >
        <Input
          name="q"
          type="search"
          defaultValue={text ?? ""}
          placeholder="Search Hugging Face datasets"
          aria-label="Search datasets on the Hub"
          className="max-w-md"
          disabled={off}
          {...part("datasets/search")}
        />
        {text && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onSearch(null)}
            {...part("datasets/clear")}
          >
            Clear
          </Button>
        )}
        {off && (
          <span className="text-muted-foreground text-xs">
            The Hub is off: this server was started with --expose.
          </span>
        )}
      </form>
      {text && !off && <Hits domain={domain} text={text} />}
    </Part>
  );
}

function Hits({ domain, text }: { domain: Domain; text: string }) {
  const hits = useQuery(
    q.hubSearch({ kind: "datasets", q: text, task: "", library: "", sort: "downloads" }),
  );
  return (
    <QueryState query={hits} rows={3}>
      {(found) =>
        found.length === 0 ? (
          <p className="text-muted-foreground text-sm">No dataset on the Hub matches.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead {...part(partId("datasets/hit-column", "id"))}>On the Hub</TableHead>
                  <TableHead
                    className="text-right"
                    {...part(partId("datasets/hit-column", "downloads"))}
                  >
                    <Term k="downloads">Downloads</Term>
                  </TableHead>
                  <TableHead
                    className="text-right"
                    {...part(partId("datasets/hit-column", "likes"))}
                  >
                    <Term k="likes">Likes</Term>
                  </TableHead>
                  <TableHead {...part(partId("datasets/hit-column", "add"))}>
                    <span className="sr-only">Add</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {found.slice(0, 10).map((h) => (
                  <Hit key={h.id} hit={h} domain={domain} />
                ))}
              </TableBody>
            </Table>
          </div>
        )
      }
    </QueryState>
  );
}

function Hit({ hit, domain }: { hit: HubHit; domain: Domain }) {
  const client = useQueryClient();
  const [, set] = useQueryStates({ open: parseAsString });
  const add = useMutation({
    mutationFn: () => hubAdd({ kind: "datasets", id: hit.id, domains: [domain] }),
    meta: { action: "Add" },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["datasets"] });
      void client.invalidateQueries({ queryKey: ["hub", "added"] });
      toast(`Added to ${DOMAIN_TITLE[domain]}`, { description: hit.id });
    },
  });
  const num = "text-right font-mono tabular-nums";
  return (
    <TableRow {...part(partId("datasets/hit", hit.id))}>
      <TableCell className="font-mono text-xs">
        <button
          type="button"
          className="underline-offset-4 hover:underline"
          onClick={() => void set({ open: hit.id })}
        >
          {hit.id}
        </button>
        {hit.gated && <Badge className="ml-1.5">gated</Badge>}
      </TableCell>
      <TableCell className={num}>{count(hit.downloads)}</TableCell>
      <TableCell className={num}>{count(hit.likes)}</TableCell>
      <TableCell className="text-right">
        <Button
          size="sm"
          variant="outline"
          onClick={() => add.mutate()}
          disabled={add.isPending || add.isSuccess}
          {...part(partId("datasets/add", hit.id))}
        >
          {add.isSuccess ? "Added" : `Add to ${DOMAIN_TITLE[domain]}`}
        </Button>
      </TableCell>
    </TableRow>
  );
}

function Detail({
  id,
  hub,
  listed,
  domain,
  config,
  split,
  onPick,
}: {
  id: string;
  hub: boolean;
  listed: boolean;
  domain: Domain;
  config: string | null;
  split: string | null;
  onPick: (config: string | null, split: string | null) => void;
}) {
  const remote = useQuery({ ...q.hubDataset(id, config, split), enabled: hub && !isSnapshot() });
  const local = useQuery({ ...q.localDataset(id), enabled: !hub && !isSnapshot() });
  const found = hub ? remote : local;
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-y-auto p-6">
      <div className="flex flex-col gap-1 pr-8">
        <SheetTitle className="font-mono text-sm font-medium" {...part("datasets/detail/title")}>
          {id}
        </SheetTitle>
        <SheetDescription className="text-muted-foreground text-xs">
          {hub ? "A dataset on the Hugging Face Hub" : "A file in the project"}
        </SheetDescription>
      </div>
      {isSnapshot() ? (
        <p className="text-muted-foreground text-sm" {...part("datasets/detail/error")}>
          A published dashboard shows the list only: rows are read from the Hub or the file by a
          running louped.
        </p>
      ) : (
        <QueryState query={found} rows={6}>
          {(d) => <DetailBody detail={d} listed={listed} domain={domain} onPick={onPick} />}
        </QueryState>
      )}
    </div>
  );
}

function DetailBody({
  detail: d,
  listed,
  domain,
  onPick,
}: {
  detail: DatasetDetail;
  listed: boolean;
  domain: Domain;
  onPick: (config: string | null, split: string | null) => void;
}) {
  const h = d.hub;
  const facts: [React.ReactNode, string][] = h
    ? [
        [
          <Term key="d" k="downloads">
            Downloads
          </Term>,
          count(h.downloads),
        ],
        [
          <Term key="s" k="hubSize">
            Size
          </Term>,
          h.size == null ? "—" : bytes(h.size),
        ],
        ["License", h.license ?? "—"],
        ["Updated", h.updated ? h.updated.slice(0, 10) : "—"],
      ]
    : [];
  if (d.total != null) facts.push(["Rows", count(d.total)]);
  const splits = d.splits ?? [];
  const columns = d.features?.length
    ? d.features.map((f) => f.name)
    : [...new Set((d.rows ?? []).flatMap((r) => Object.keys(r)))];
  return (
    <>
      {d.source === "hub" && <HubActions id={d.id} listed={listed} domain={domain} url={h?.url} />}
      {d.hub_error && (
        <p className="text-negative text-xs" {...part("datasets/detail/hub-error")}>
          {d.hub_error}
        </p>
      )}
      {facts.length > 0 && (
        <dl
          className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm"
          {...part("datasets/detail/facts")}
        >
          {facts.map(([label, value], i) => (
            <div key={i} className="contents">
              <dt className="text-muted-foreground text-xs">{label}</dt>
              <dd className="font-mono text-xs tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {splits.length > 0 && (
        <div
          className="flex flex-wrap items-center gap-2 text-xs"
          {...part("datasets/detail/split")}
        >
          <Term k="split">
            <label htmlFor="dataset-split" className="text-muted-foreground">
              Split
            </label>
          </Term>
          <NativeSelect
            id="dataset-split"
            value={`${d.config}\u0000${d.split}`}
            onChange={(e) => {
              const [config, split] = e.target.value.split("\u0000");
              onPick(config, split);
            }}
            className="font-mono text-xs"
          >
            {splits.map((s) => (
              <option key={`${s.config}/${s.split}`} value={`${s.config}\u0000${s.split}`}>
                {s.config === "default" ? s.split : `${s.config} / ${s.split}`}
                {s.rows != null ? ` · ${count(s.rows)} rows` : ""}
              </option>
            ))}
          </NativeSelect>
        </div>
      )}
      {d.error && (
        <p
          className="text-negative rounded-xl border px-4 py-3 font-mono text-xs"
          {...part("datasets/detail/error")}
        >
          {d.error}
        </p>
      )}
      {(d.features ?? []).length > 0 && (
        <div className="flex flex-col gap-2" {...part("datasets/detail/features")}>
          <h3 className="text-xs font-medium">
            <Term k="feature">Features</Term>
          </h3>
          <ul className="flex flex-wrap gap-1.5">
            {d.features!.map((f) => (
              <li key={f.name}>
                <Badge className="font-mono">
                  {f.name} <span className="text-muted-foreground">{f.type}</span>
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
      {(d.rows ?? []).length > 0 && (
        <div className="flex flex-col gap-2" {...part("datasets/detail/rows")}>
          <h3 className="text-xs font-medium">
            First {d.rows!.length} rows{d.total != null ? ` of ${count(d.total)}` : ""}
          </h3>
          <div className="overflow-x-auto rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  {columns.map((c) => (
                    <TableHead
                      key={c}
                      className="font-mono text-xs"
                      {...part(partId("datasets/field", c))}
                    >
                      {c}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {d.rows!.map((r, i) => (
                  <TableRow key={i} {...part(partId("datasets/sample", i))}>
                    {columns.map((c) => (
                      <TableCell
                        key={c}
                        className="max-w-xs align-top text-xs break-words whitespace-pre-wrap"
                      >
                        {cell(r[c])}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
      {h?.card && (
        <Part id="datasets/detail/card" className="prose-sm border-t pt-4 text-sm">
          <Markdown noImages>{h.card}</Markdown>
        </Part>
      )}
    </>
  );
}

/** Add to this domain, download as a job, open on the Hub. */
function HubActions({
  id,
  listed,
  domain,
  url,
}: {
  id: string;
  listed: boolean;
  domain: Domain;
  url?: string;
}) {
  const client = useQueryClient();
  const router = useRouter();
  const add = useMutation({
    mutationFn: (download: boolean) =>
      hubAdd({ kind: "datasets", id, download, domains: listed ? [] : [domain] }),
    meta: { action: "Add" },
    onSuccess: (done) => {
      void client.invalidateQueries({ queryKey: ["datasets"] });
      void client.invalidateQueries({ queryKey: ["hub", "added"] });
      if (done.job) {
        void client.invalidateQueries({ queryKey: ["jobs"] });
        router.push(jobHref(done.job.id));
      } else toast(`Added to ${DOMAIN_TITLE[domain]}`, { description: id });
    },
  });
  return (
    <div className="flex flex-wrap items-center gap-2" {...part("datasets/detail/actions")}>
      {!listed && (
        <Button
          size="sm"
          onClick={() => add.mutate(false)}
          disabled={add.isPending}
          {...part("datasets/detail/add")}
        >
          Add to {DOMAIN_TITLE[domain]}
        </Button>
      )}
      <Button
        variant="outline"
        size="sm"
        onClick={() => add.mutate(true)}
        disabled={add.isPending}
        title="Get it into this machine's cache, as a job (louped hub get)"
        {...part("datasets/detail/download")}
      >
        <Download /> Download
      </Button>
      <Button asChild variant="ghost" size="sm" {...part("datasets/detail/open")}>
        <a href={url ?? `https://huggingface.co/datasets/${id}`} target="_blank" rel="noreferrer">
          <ExternalLink /> On the Hub
        </a>
      </Button>
    </div>
  );
}
