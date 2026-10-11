"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, ExternalLink, KeyRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { Markdown } from "@/components/markdown";
import { Part, part, partId } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { TokenField } from "@/components/sync";
import { Term } from "@/components/term";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ApiError,
  hubAdd,
  q,
  saveHubToken,
  type HubDetail,
  type HubHit,
  type HubKind,
} from "@/lib/api";
import { jobHref, sourceHref } from "@/lib/href";

const KINDS = ["models", "embeddings", "datasets", "papers"] as const;
const SORTS = ["downloads", "likes", "recent"] as const;
const TITLES: Record<HubKind, string> = {
  models: "Models",
  embeddings: "Embeddings",
  datasets: "Datasets",
  papers: "Papers",
};
/** Pipeline tags a model search is usually narrowed by. */
const TASKS = [
  "text-generation",
  "image-text-to-text",
  "text-classification",
  "token-classification",
  "fill-mask",
  "automatic-speech-recognition",
];
const EMBEDDING_TASKS = ["sentence-similarity", "feature-extraction"];
const LIBRARIES = ["transformers", "sentence-transformers", "peft", "gguf", "mlx", "diffusers"];

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const count = (n: number | null | undefined) => (n == null ? "—" : compact.format(n));
const bytes = (n: number | null | undefined) => (n == null ? "—" : `${compact.format(n / 1e9)} GB`);
const day = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : "—");

/** Search the Hugging Face Hub and add what the project uses. */
export function HubView() {
  const me = useQuery(q.hubMe());
  if (me.isError && me.error instanceof ApiError && me.error.status === 403)
    return (
      <EmptyState
        icon={Boxes}
        title="The Hub is off"
        body="It uses this machine's Hugging Face token, so a server started with --expose turns it off. Start one without it."
        command="louped serve"
      />
    );
  return <Search />;
}

function Search() {
  const [s, set] = useQueryStates({
    kind: parseAsStringLiteral(KINDS).withDefault("models"),
    q: parseAsString.withDefault(""),
    task: parseAsString.withDefault(""),
    library: parseAsString.withDefault(""),
    sort: parseAsStringLiteral(SORTS).withDefault("downloads"),
    open: parseAsString,
  });
  const models = s.kind === "models" || s.kind === "embeddings";
  const params = {
    kind: s.kind,
    q: s.q,
    task: models ? s.task : "",
    library: models ? s.library : "",
    sort: s.sort,
  };
  const hits = useQuery(q.hubSearch(params));
  const tasks = s.kind === "embeddings" ? EMBEDDING_TASKS : TASKS;
  return (
    <>
      <Tabs
        value={s.kind}
        onValueChange={(kind) =>
          void set({ kind: kind as HubKind, task: null, library: null, open: null })
        }
      >
        <div className="flex flex-wrap items-end justify-between gap-3 border-b">
          <TabsList className="border-b-0">
            {KINDS.map((k) => (
              <TabsTrigger key={k} value={k} {...part(partId("hub/tab", k))}>
                {TITLES[k]}
              </TabsTrigger>
            ))}
          </TabsList>
          <Account />
        </div>
      </Tabs>
      <form
        key={s.kind}
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const text = String(new FormData(e.currentTarget).get("q") ?? "").trim();
          void set({ q: text || null, open: null });
        }}
      >
        <Input
          name="q"
          type="search"
          defaultValue={s.q}
          placeholder={s.kind === "papers" ? "Search papers; empty for today's" : "Search"}
          aria-label={`Search ${TITLES[s.kind].toLowerCase()} on the Hub`}
          className="max-w-md"
          {...part("hub/search")}
        />
        {models && (
          <>
            <NativeSelect
              aria-label="Task"
              value={s.task}
              onChange={(e) => void set({ task: e.target.value || null })}
              className="font-mono text-xs"
              {...part("hub/filter/task")}
            >
              <option value="">{s.kind === "embeddings" ? "both tasks" : "any task"}</option>
              {tasks.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </NativeSelect>
            <NativeSelect
              aria-label="Library"
              value={s.library}
              onChange={(e) => void set({ library: e.target.value || null })}
              className="font-mono text-xs"
              {...part("hub/filter/library")}
            >
              <option value="">any library</option>
              {LIBRARIES.map((l) => (
                <option key={l}>{l}</option>
              ))}
            </NativeSelect>
          </>
        )}
        {s.kind !== "papers" && (
          <NativeSelect
            aria-label="Sort"
            value={s.sort}
            onChange={(e) => void set({ sort: e.target.value as (typeof SORTS)[number] })}
            className="text-xs"
            {...part("hub/filter/sort")}
          >
            <option value="downloads">most downloaded</option>
            <option value="likes">most liked</option>
            <option value="recent">recently updated</option>
          </NativeSelect>
        )}
      </form>
      <QueryState query={hits} rows={8}>
        {(found) =>
          found.length === 0 ? (
            <p className="text-muted-foreground text-sm">Nothing on the Hub matches.</p>
          ) : (
            <Results hits={found} onOpen={(id) => void set({ open: id })} />
          )
        }
      </QueryState>
      <Sheet open={s.open !== null} onOpenChange={(o) => !o && void set({ open: null })}>
        <SheetContent>{s.open !== null && <Detail kind={s.kind} id={s.open} />}</SheetContent>
      </Sheet>
    </>
  );
}

function Results({ hits, onOpen }: { hits: HubHit[]; onOpen: (id: string) => void }) {
  const papers = hits[0].kind === "papers";
  const models = hits[0].kind === "models" || hits[0].kind === "embeddings";
  const col = (id: string) => partId("hub/column", id);
  const num = "text-right font-mono tabular-nums";
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead {...part(col("name"))}>{papers ? "Title" : "Id"}</TableHead>
          {models && <TableHead {...part(col("task"))}>Task</TableHead>}
          {models && (
            <TableHead className="text-right" {...part(col("params"))}>
              <Term k="params">Params</Term>
            </TableHead>
          )}
          {papers ? (
            <TableHead className="text-right" {...part(col("upvotes"))}>
              <Term k="upvotes">Upvotes</Term>
            </TableHead>
          ) : (
            <>
              <TableHead className="text-right" {...part(col("downloads"))}>
                <Term k="downloads">Downloads</Term>
              </TableHead>
              <TableHead className="text-right" {...part(col("likes"))}>
                <Term k="likes">Likes</Term>
              </TableHead>
            </>
          )}
          <TableHead {...part(col("updated"))}>{papers ? "Published" : "Updated"}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {hits.map((h) => (
          <TableRow
            key={h.id}
            className="cursor-pointer"
            tabIndex={0}
            onClick={() => onOpen(h.id)}
            onKeyDown={(e) => e.key === "Enter" && onOpen(h.id)}
            {...part(partId("hub/hit", h.kind, h.id))}
          >
            <TableCell className="max-w-md">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className={papers ? "text-sm" : "font-mono text-xs"}>
                  {papers ? h.title : h.id}
                </span>
                <Badges hit={h} />
              </div>
              {papers && h.authors.length > 0 && (
                <p className="text-muted-foreground truncate text-xs">
                  {h.authors.slice(0, 4).join(", ")}
                  {h.authors.length > 4 && " et al."}
                </p>
              )}
            </TableCell>
            {models && (
              <TableCell className="text-muted-foreground font-mono text-xs">
                {h.task ?? "—"}
              </TableCell>
            )}
            {models && <TableCell className={num}>{count(h.params)}</TableCell>}
            {papers ? (
              <TableCell className={num}>{count(h.upvotes)}</TableCell>
            ) : (
              <>
                <TableCell className={num}>{count(h.downloads)}</TableCell>
                <TableCell className={num}>{count(h.likes)}</TableCell>
              </>
            )}
            <TableCell className="text-muted-foreground font-mono text-xs">
              {day(h.updated)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function Badges({ hit }: { hit: HubHit }) {
  return (
    <>
      {hit.gated && <Badge>gated</Badge>}
      {hit.private && <Badge>private</Badge>}
    </>
  );
}

/** One result in full, with what adds it to the project. */
function Detail({ kind, id }: { kind: HubKind; id: string }) {
  const info = useQuery(q.hubInfo(kind, id));
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-6">
      <div className="flex flex-col gap-1 pr-8">
        <SheetTitle
          className={kind === "papers" ? "font-medium" : "font-mono text-sm font-medium"}
          {...part("hub/detail/title")}
        >
          {info.data?.title ?? id}
        </SheetTitle>
        <SheetDescription className="text-muted-foreground font-mono text-xs">
          {kind === "papers" ? `arXiv ${id}` : TITLES[kind].replace(/s$/, "").toLowerCase()}
        </SheetDescription>
      </div>
      <QueryState query={info} rows={6}>
        {(d) => <DetailBody detail={d} />}
      </QueryState>
    </div>
  );
}

function DetailBody({ detail: d }: { detail: HubDetail }) {
  const paper = d.kind === "papers";
  const facts: [React.ReactNode, string][] = paper
    ? [
        [
          <Term key="u" k="upvotes">
            Upvotes
          </Term>,
          count(d.upvotes),
        ],
        ["Published", day(d.updated)],
      ]
    : [
        [
          <Term key="d" k="downloads">
            Downloads
          </Term>,
          count(d.downloads),
        ],
        [
          <Term key="l" k="likes">
            Likes
          </Term>,
          count(d.likes),
        ],
        ...(d.kind === "datasets"
          ? []
          : ([
              [
                <Term key="p" k="params">
                  Params
                </Term>,
                count(d.params),
              ],
            ] as [React.ReactNode, string][])),
        [
          <Term key="s" k="hubSize">
            Size
          </Term>,
          bytes(d.size),
        ],
        ["Files", count(d.files)],
        ["License", d.license ?? "—"],
        ["Updated", day(d.updated)],
      ];
  return (
    <>
      <div className="flex flex-wrap items-center gap-2" {...part("hub/detail/actions")}>
        <Actions detail={d} />
        <Button asChild variant="ghost" size="sm" {...part("hub/detail/open")}>
          <a href={d.url} target="_blank" rel="noreferrer">
            <ExternalLink /> {d.gated ? "Ask for access" : "On the Hub"}
          </a>
        </Button>
        {d.gated && (
          <Term k="gated">
            <Badge>gated</Badge>
          </Term>
        )}
        {d.private && <Badge>private</Badge>}
      </div>
      {paper && d.authors.length > 0 && (
        <p className="text-muted-foreground text-xs" {...part("hub/detail/authors")}>
          {d.authors.join(", ")}
        </p>
      )}
      <dl
        className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm"
        {...part("hub/detail/facts")}
      >
        {facts.map(([label, value], i) => (
          <div key={i} className="contents">
            <dt className="text-muted-foreground text-xs">{label}</dt>
            <dd className="font-mono text-xs tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      {d.tags.length > 0 && (
        <div className="flex flex-wrap gap-1" {...part("hub/detail/tags")}>
          {d.tags.slice(0, 16).map((t) => (
            <Badge key={t} className="font-mono">
              {t}
            </Badge>
          ))}
        </div>
      )}
      {d.summary && (
        <p className="text-sm leading-relaxed" {...part("hub/detail/abstract")}>
          {d.summary}
        </p>
      )}
      {Object.keys(d.links).length > 0 && (
        <ul className="flex flex-wrap gap-3 text-xs" {...part("hub/detail/links")}>
          {Object.entries(d.links).map(([name, href]) => (
            <li key={name}>
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                className="underline underline-offset-4"
              >
                {name}
              </a>
            </li>
          ))}
        </ul>
      )}
      {d.card && (
        <Part id="hub/detail/card" className="prose-sm border-t pt-4 text-sm">
          <Markdown noImages>{d.card}</Markdown>
        </Part>
      )}
    </>
  );
}

/** Add to the project (louped.toml's [hub]), download as a job, or keep a paper as a source. */
function Actions({ detail: d }: { detail: HubDetail }) {
  const client = useQueryClient();
  const router = useRouter();
  const added = useQuery(q.hubAdded());
  const listed = d.kind !== "papers" && (added.data?.[d.kind] ?? []).includes(d.id);
  const add = useMutation({
    mutationFn: (download: boolean) => hubAdd({ kind: d.kind, id: d.id, download }),
    meta: { action: "Add" },
    onSuccess: (done) => {
      void client.invalidateQueries({ queryKey: ["hub", "added"] });
      if (done.job) {
        void client.invalidateQueries({ queryKey: ["jobs"] });
        router.push(jobHref(done.job.id));
      } else if (done.source) {
        void client.invalidateQueries({ queryKey: ["sources"] });
        const key = done.source.key;
        toast("Added to sources", {
          description: <span className="font-mono">{key}</span>,
          action: { label: "Open", onClick: () => router.push(sourceHref(key)) },
        });
      } else toast("Added to louped.toml", { description: d.id });
    },
  });
  if (d.kind === "papers")
    return (
      <Button
        size="sm"
        onClick={() => add.mutate(false)}
        disabled={add.isPending}
        {...part("hub/detail/source")}
      >
        {add.isPending ? "Adding" : "Add to sources"}
      </Button>
    );
  return (
    <>
      <Button
        size="sm"
        onClick={() => add.mutate(false)}
        disabled={add.isPending || listed}
        title="List it in louped.toml, so model fields offer it"
        {...part("hub/detail/add")}
      >
        {listed ? "Added" : "Add"}
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={() => add.mutate(true)}
        disabled={add.isPending}
        title="Get it into this machine's cache, as a job"
        {...part("hub/detail/download")}
      >
        Download
      </Button>
    </>
  );
}

/** The account whose token is on this machine, or Connect to give one. */
function Account() {
  const me = useQuery(q.hubMe());
  const [open, setOpen] = useState(false);
  const a = me.data;
  return (
    <Part id="hub/account" className="flex items-center gap-2 pb-2 text-xs">
      {a?.name && !a.error ? (
        <a
          href={`https://huggingface.co/${a.name}`}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2"
        >
          {a.avatar && (
            // eslint-disable-next-line @next/next/no-img-element -- a static export: no image server
            <img src={a.avatar} alt="" className="size-5 rounded-full border" />
          )}
          <span className="font-mono">{a.name}</span>
        </a>
      ) : (
        <>
          {a?.error && <span className="text-negative">Token refused</span>}
          <Button variant="outline" size="sm" onClick={() => setOpen(true)} disabled={!a}>
            <KeyRound /> Connect
          </Button>
        </>
      )}
      <TokenDialog open={open} onOpenChange={setOpen} />
    </Part>
  );
}

function TokenDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: saveHubToken,
    meta: { action: "Connect" },
    onSuccess: (done) => {
      void client.invalidateQueries({ queryKey: ["hub"] });
      onOpenChange(false);
      toast(`Signed in as ${done.name}`);
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col gap-4 p-5">
        <div className="flex flex-col gap-1">
          <DialogTitle className="text-sm font-medium">Connect Hugging Face</DialogTitle>
          <DialogDescription className="text-muted-foreground text-xs">
            Search sees the gated and private repositories your account can open. The token stays on
            this machine, where Hugging Face&apos;s own tools keep it.
          </DialogDescription>
        </div>
        <form
          className="flex flex-col gap-3"
          {...part("hub/token")}
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(String(new FormData(e.currentTarget).get("token") ?? "").trim());
          }}
        >
          <TokenField access="read access" placeholder="hf_…" required />
          <Button type="submit" size="sm" className="self-end" disabled={save.isPending}>
            Connect
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
