"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Pin, PinOff, Waypoints, X } from "lucide-react";
import Link from "next/link";
import { parseAsFloat, parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";
import { useDeferredValue, useMemo, useState } from "react";
import { toast } from "sonner";

import { CircuitGraph } from "@/components/circuit-graph";
import { EmptyState } from "@/components/empty-state";
import { ExamplesButton } from "@/components/examples-button";
import { Help } from "@/components/help";
import { part, partId, PartNote, useRules } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { Stat, StatGrid } from "@/components/stat-grid";
import { Term } from "@/components/term";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
  API,
  type CircuitGraph as Graph,
  type CircuitLink,
  type CircuitNode,
  q,
  saveGraphPins,
} from "@/lib/api";
import { type Group, hasInfluence, neighbours, prune, subgraph } from "@/lib/circuit";
import { num, pct } from "@/lib/format";
import { GLOSSARY } from "@/lib/glossary";
import { cn } from "@/lib/utils";

/** The project's attribution graphs, one at a time, drawn by louped. */
export function CircuitsView() {
  const graphs = useQuery(q.graphs());
  const [slug, setSlug] = useQueryState("slug", parseAsString);
  return (
    <QueryState query={graphs}>
      {(all) => {
        if (all.length === 0) {
          return (
            <EmptyState
              icon={Waypoints}
              title="No graphs"
              body="Attribution graphs over a model's transcoders, from circuit-tracer. The examples draw one over a tiny model's neurons."
            >
              <Button asChild size="sm" variant="outline">
                <Link href="/launch/?id=circuit">Launch a circuit</Link>
              </Button>
              <ExamplesButton />
            </EmptyState>
          );
        }
        const current = all.find((g) => g.slug === slug) ?? all[all.length - 1];
        return (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <NativeSelect
                aria-label="Graph"
                {...part("circuits/graph")}
                value={current.slug}
                onChange={(e) => void setSlug(e.target.value)}
                className="max-w-full min-w-0 flex-1"
              >
                {all.map((g) => (
                  <option key={g.slug} value={g.slug}>
                    {g.slug}: {g.prompt}
                  </option>
                ))}
              </NativeSelect>
              <Button asChild size="sm" variant="ghost" {...part("circuits/viewer")}>
                <a
                  href={`${API}/circuit/?slug=${encodeURIComponent(current.slug)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink />
                  circuit-tracer viewer
                </a>
              </Button>
            </div>
            <GraphView key={current.slug} slug={current.slug} />
          </div>
        );
      }}
    </QueryState>
  );
}

const VIEWS = ["all", "pinned"] as const;

function GraphView({ slug }: { slug: string }) {
  const graph = useQuery(q.graph(slug));
  return <QueryState query={graph}>{(g) => <Loaded g={g} />}</QueryState>;
}

function Loaded({ g }: { g: Graph }) {
  const health = useQuery(q.health());
  const client = useQueryClient();
  const [node, setNode] = useQueryState("node", parseAsString);
  const [keep, setKeep] = useQueryState("keep", parseAsFloat.withDefault(0.8));
  const [edges, setEdges] = useQueryState("edges", parseAsFloat.withDefault(0.98));
  const [view, setView] = useQueryState("view", parseAsStringLiteral(VIEWS).withDefault("all"));
  const [pinned, setPinned] = useState<string[]>(g.pinned);
  const [groups, setGroups] = useState<Group[]>(g.groups);
  const dirty = JSON.stringify([pinned, groups]) !== JSON.stringify([g.pinned, g.groups]);
  const save = useMutation({
    mutationFn: () => saveGraphPins(g.slug, { pinned, groups }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["graphs", g.slug] });
      toast("Saved pins: circuit-tracer's viewer opens the same subgraph");
    },
    onError: (e) => toast.error(String(e)),
  });

  const byId = useMemo(() => new Map(g.nodes.map((n) => [n.id, n])), [g]);
  // the sliders move at once; the graph follows when it can
  const keepLate = useDeferredValue(keep);
  const edgesLate = useDeferredValue(edges);
  const cut = useMemo(
    () => (view === "pinned" ? subgraph(g, pinned, groups) : prune(g, keepLate, edgesLate)),
    [g, view, pinned, groups, keepLate, edgesLate],
  );
  // a group drawn as one node is picked like any other
  const known = useMemo(
    () => new Map([...byId, ...cut.nodes.map((n) => [n.id, n] as const)]),
    [byId, cut],
  );
  const pinSet = useMemo(() => new Set(pinned), [pinned]);
  const togglePin = (id: string) => {
    if (!pinned.includes(id)) return setPinned([...pinned, id]);
    setPinned(pinned.filter((x) => x !== id));
    // an unpinned node leaves its group; an empty group goes
    setGroups(
      groups
        .map((x) => ({ ...x, nodes: x.nodes.filter((n) => n !== id) }))
        .filter((x) => x.nodes.length > 0),
    );
  };
  const logits = g.nodes
    .filter((n) => n.kind === "logit")
    .sort((a, b) => (b.prob ?? 0) - (a.prob ?? 0));
  const target = logits.find((n) => n.target) ?? logits[0];
  const errorShare = g.nodes.filter((n) => n.kind === "error").reduce((s, n) => s + n.score, 0);
  const featureShare = g.nodes.filter((n) => n.kind === "feature").reduce((s, n) => s + n.score, 0);
  const selected = node ? (known.get(node) ?? null) : null;
  const group = selected?.id.startsWith("group:")
    ? groups.find((x) => `group:${x.name}` === selected.id)
    : undefined;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm" {...part("circuits/prompt")}>
        {g.tokens.map((t, i) => (
          <span
            key={i}
            className="bg-muted mr-0.5 rounded px-1 py-0.5 font-mono text-xs whitespace-pre"
          >
            {t}
          </span>
        ))}
      </p>
      <StatGrid>
        <Stat
          label="Output"
          part="circuits/stat/output"
          note={target && `p = ${num(target.prob, 3)}`}
        >
          {target ? target.label.replace(/^Output /, "").replace(/ \(p=.*\)$/, "") : "none"}
        </Stat>
        <Stat label="Nodes shown" part="circuits/stat/nodes" note={`of ${cut.total.nodes}`}>
          {cut.nodes.length}
        </Stat>
        <Stat label="Edges shown" part="circuits/stat/edges" note={`of ${cut.total.links}`}>
          {cut.links.length}
        </Stat>
        <Stat
          label="Unexplained"
          about={GLOSSARY.error_node}
          part="circuits/stat/errors"
          note="error nodes' share of the influence on features and errors"
        >
          {pct(errorShare / Math.max(1e-9, errorShare + featureShare))}
        </Stat>
      </StatGrid>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-sm">
        <Range
          id="keep"
          term="keep_nodes"
          label="Nodes"
          value={keep}
          min={0.3}
          max={0.99}
          onChange={(v) => void setKeep(v)}
          disabled={view === "pinned"}
        />
        <Range
          id="edges"
          term="keep_edges"
          label="Edges"
          value={edges}
          min={0.5}
          max={1}
          onChange={(v) => void setEdges(v)}
          disabled={view === "pinned"}
        />
        <div
          role="group"
          aria-label="Show"
          className="flex rounded-md border p-0.5"
          {...part("circuits/view")}
        >
          {VIEWS.map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={view === v}
              onClick={() => void setView(v)}
              className={cn(
                "focus-visible:ring-ring rounded px-2 py-0.5 text-xs outline-none focus-visible:ring-2",
                view === v ? "bg-muted text-foreground" : "text-muted-foreground",
              )}
            >
              {v === "all" ? "Pruned graph" : `Pinned (${pinned.length})`}
            </button>
          ))}
        </div>
        {health.data?.launching && dirty && (
          <Button
            size="sm"
            onClick={() => save.mutate()}
            disabled={save.isPending}
            {...part("circuits/save")}
          >
            Save pins
          </Button>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex min-w-0 flex-col gap-2">
          {cut.nodes.length === 0 ? (
            <p className="text-muted-foreground rounded-xl border p-6 text-sm">
              {view === "pinned"
                ? "Nothing pinned. Pick a node in the pruned graph and pin it (P)."
                : "No node carries influence on the output."}
            </p>
          ) : (
            <GraphFigure pruning={view === "all" && hasInfluence(g)}>
              <CircuitGraph
                cut={cut}
                tokens={g.tokens}
                selected={node}
                pinned={pinSet}
                onSelect={(id) => void setNode(id)}
                onPin={togglePin}
              />
            </GraphFigure>
          )}
          <Legend />
        </div>
        <aside className="flex flex-col gap-4" {...part("circuits/panel")}>
          {selected ? (
            <NodeDetail
              n={selected}
              members={group?.nodes}
              links={view === "pinned" && !group ? g.links : cut.links}
              byId={known}
              tokens={g.tokens}
              pinned={pinSet.has(selected.id)}
              onPin={() => togglePin(selected.id)}
              onSelect={(id) => void setNode(id)}
              onClose={() => void setNode(null)}
            />
          ) : (
            <TopNodes nodes={g.nodes} logits={logits} onSelect={(id) => void setNode(id)} />
          )}
          <Pinned
            pinned={pinned}
            groups={groups}
            byId={byId}
            onUnpin={togglePin}
            onSelect={(id) => void setNode(id)}
            onGroup={(name) => {
              const grouped = new Set(groups.flatMap((x) => x.nodes));
              const nodes = pinned.filter((id) => !grouped.has(id));
              if (nodes.length)
                setGroups([...groups.filter((x) => x.name !== name), { name, nodes }]);
            }}
            onUngroup={(name) => setGroups(groups.filter((x) => x.name !== name))}
          />
        </aside>
      </div>
    </div>
  );
}

/** The graph with its title and how to read it. */
function GraphFigure({ pruning, children }: { pruning: boolean; children: React.ReactNode }) {
  const rule = useRules()("circuits/figure");
  return (
    <figure className="flex min-w-0 flex-col gap-2" {...part("circuits/figure")}>
      <figcaption className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
        {rule.label ?? "Attribution graph"}
        <Help label="How to read the attribution graph">
          {rule.about ??
            "Tokens sit along the bottom, layers go up, the outputs are on top. Each edge is one node's direct effect on another: green raises the target, red lowers it, wider is a larger share of the influence on the outputs. Hover or pick a node to light the paths through it."}
        </Help>
        {pruning && (
          <span className="text-muted-foreground text-xs font-normal">
            Nodes pruned by circuit-tracer&apos;s own influence
          </span>
        )}
        <PartNote rule={rule} className="basis-full" />
      </figcaption>
      {children}
    </figure>
  );
}

function Range({
  id,
  term,
  label,
  value,
  min,
  max,
  onChange,
  disabled,
}: {
  id: string;
  term: "keep_nodes" | "keep_edges";
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center gap-2" {...part(partId("circuits/prune", id))}>
      <span className="text-muted-foreground inline-flex items-center gap-1 text-xs">
        <label htmlFor={`circuit-${id}`}>{label}</label>
        <Help label={`What is ${label}?`}>{GLOSSARY[term]}</Help>
      </span>
      <input
        id={`circuit-${id}`}
        type="range"
        min={min}
        max={max}
        step={0.01}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="accent-foreground w-32 disabled:opacity-40"
      />
      <span className="w-10 text-right font-mono text-xs tabular-nums">{pct(value)}</span>
    </div>
  );
}

function Legend() {
  const item = "inline-flex items-center gap-1.5";
  if (useRules()("circuits/legend").hidden) return null;
  return (
    <p
      className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs"
      {...part("circuits/legend")}
    >
      <span className={item}>
        <svg width="10" height="10" aria-hidden>
          <rect width="10" height="10" rx="2" className="fill-muted-foreground" />
        </svg>
        token
      </span>
      <span className={item}>
        <svg width="10" height="10" aria-hidden>
          <circle cx="5" cy="5" r="5" className="fill-muted-foreground" />
        </svg>
        feature, larger for more influence
      </span>
      <span className={item}>
        <svg width="12" height="12" aria-hidden>
          <rect
            x="3"
            y="3"
            width="6"
            height="6"
            transform="rotate(45 6 6)"
            fill="none"
            stroke="currentColor"
            strokeDasharray="2 2"
          />
        </svg>
        <Term k="error_node">error</Term>
      </span>
      <span className={item}>
        <span className="bg-positive inline-block h-0.5 w-4" /> pushes up
      </span>
      <span className={item}>
        <span className="bg-negative inline-block h-0.5 w-4" /> pushes down
      </span>
      <span>Arrow keys walk the graph · P pins · Esc clears</span>
    </p>
  );
}

function where(n: CircuitNode, tokens: string[]) {
  const word = tokens[n.position];
  return `${n.layer === "E" ? "embedding" : n.kind === "logit" ? "output" : `layer ${n.layer}`} · ${word !== undefined ? JSON.stringify(word) : `position ${n.position}`}`;
}

function NodeDetail({
  n,
  members,
  links,
  byId,
  tokens,
  pinned,
  onPin,
  onSelect,
  onClose,
}: {
  n: CircuitNode;
  /** A group's nodes, when n is a group drawn as one. */
  members?: string[];
  links: CircuitLink[];
  byId: Map<string, CircuitNode>;
  tokens: string[];
  pinned: boolean;
  onPin: () => void;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const { inputs, outputs } = neighbours(links, n.id);
  return (
    <section
      className="flex flex-col gap-3 rounded-xl border p-4"
      {...part(partId("circuits/node-detail", n.id))}
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-medium break-words">{n.label}</h2>
          <p className="text-muted-foreground text-xs">{where(n, tokens)}</p>
        </div>
        <Button size="icon-sm" variant="ghost" aria-label="Close" onClick={onClose}>
          <X />
        </Button>
      </div>
      <div className="flex flex-wrap gap-1">
        <Badge>{members ? "group" : n.kind}</Badge>
        {n.feature != null && n.kind !== "embedding" && (
          <Badge className="font-mono">#{n.feature}</Badge>
        )}
        {n.target && <Badge>target</Badge>}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">
          <Term k="influence">Influence</Term>
        </dt>
        <dd className="text-right font-mono tabular-nums">{pct(n.score)}</dd>
        {n.activation != null && (
          <>
            <dt className="text-muted-foreground">
              <Term k="activation">Activation</Term>
            </dt>
            <dd className="text-right font-mono tabular-nums">{num(n.activation, 3)}</dd>
          </>
        )}
        {n.prob != null && (
          <>
            <dt className="text-muted-foreground">Probability</dt>
            <dd className="text-right font-mono tabular-nums">{num(n.prob, 3)}</dd>
          </>
        )}
      </dl>
      {members ? (
        <ul className="flex flex-col" aria-label="Members">
          {members.map((id) => (
            <li key={id}>
              <button
                type="button"
                onClick={() => onSelect(id)}
                {...part(partId("circuits/member", id))}
                className="hover:bg-muted focus-visible:ring-ring w-full truncate rounded px-1 py-0.5 text-left text-xs outline-none focus-visible:ring-2"
              >
                {byId.get(id)?.label ?? id}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <Button size="sm" variant="outline" onClick={onPin} {...part("circuits/pin")}>
          {pinned ? <PinOff /> : <Pin />}
          {pinned ? "Unpin" : "Pin"}
        </Button>
      )}
      <Edges
        title="Reads from"
        edges={inputs}
        other={(l) => l.source}
        byId={byId}
        onSelect={onSelect}
      />
      <Edges
        title="Writes to"
        edges={outputs}
        other={(l) => l.target}
        byId={byId}
        onSelect={onSelect}
      />
    </section>
  );
}

function Edges({
  title,
  edges,
  other,
  byId,
  onSelect,
}: {
  title: string;
  edges: CircuitLink[];
  other: (l: CircuitLink) => string;
  byId: Map<string, CircuitNode>;
  onSelect: (id: string) => void;
}) {
  if (edges.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-muted-foreground text-xs">
        <Term k="edge_weight">{title}</Term>
      </h3>
      <ul className="flex flex-col">
        {edges.map((l) => {
          const id = other(l);
          return (
            <li key={id}>
              <button
                type="button"
                onClick={() => onSelect(id)}
                className="hover:bg-muted focus-visible:ring-ring flex w-full items-center gap-2 rounded px-1 py-0.5 text-left text-xs outline-none focus-visible:ring-2"
              >
                <span className="min-w-0 flex-1 truncate">{byId.get(id)?.label ?? id}</span>
                <span
                  className={cn(
                    "font-mono tabular-nums",
                    l.weight >= 0 ? "text-positive" : "text-negative",
                  )}
                >
                  {l.weight >= 0 ? "+" : ""}
                  {num(l.weight, 2)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function TopNodes({
  nodes,
  logits,
  onSelect,
}: {
  nodes: CircuitNode[];
  logits: CircuitNode[];
  onSelect: (id: string) => void;
}) {
  const top = nodes
    .filter((n) => n.kind === "feature")
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
  const row = (n: CircuitNode, value: string) => (
    <li key={n.id}>
      <button
        type="button"
        onClick={() => onSelect(n.id)}
        className="hover:bg-muted focus-visible:ring-ring flex w-full items-center gap-2 rounded px-1 py-0.5 text-left text-xs outline-none focus-visible:ring-2"
      >
        <span className="min-w-0 flex-1 truncate">{n.label}</span>
        <span className="text-muted-foreground font-mono">L{n.layer}</span>
        <span className="w-12 text-right font-mono tabular-nums">{value}</span>
      </button>
    </li>
  );
  return (
    <section className="flex flex-col gap-3 rounded-xl border p-4" {...part("circuits/top")}>
      <div className="flex flex-col gap-1">
        <h2 className="text-xs font-medium">Outputs</h2>
        <ul>{logits.slice(0, 5).map((n) => row(n, num(n.prob, 3)))}</ul>
      </div>
      <div className="flex flex-col gap-1">
        <h2 className="text-xs font-medium">
          <Term k="influence">Strongest features</Term>
        </h2>
        <ul>{top.map((n) => row(n, pct(n.score)))}</ul>
      </div>
      <p className="text-muted-foreground text-xs">
        Pick a node to see what it reads from and writes to.
      </p>
    </section>
  );
}

function Pinned({
  pinned,
  groups,
  byId,
  onUnpin,
  onSelect,
  onGroup,
  onUngroup,
}: {
  pinned: string[];
  groups: Group[];
  byId: Map<string, CircuitNode>;
  onUnpin: (id: string) => void;
  onSelect: (id: string) => void;
  onGroup: (name: string) => void;
  onUngroup: (name: string) => void;
}) {
  const [name, setName] = useState("");
  if (pinned.length === 0 && groups.length === 0) return null;
  const grouped = new Set(groups.flatMap((g) => g.nodes));
  const loose = pinned.filter((id) => !grouped.has(id));
  return (
    <section className="flex flex-col gap-2 rounded-xl border p-4" {...part("circuits/pinned")}>
      <h2 className="text-xs font-medium">Pinned</h2>
      {groups.map((g) => (
        <div key={g.name} className="flex items-center gap-2 text-xs">
          <Badge>{g.name}</Badge>
          <span className="text-muted-foreground flex-1">{g.nodes.length} nodes</span>
          <Button
            size="sm"
            variant="ghost"
            className="h-6 px-2 text-xs"
            onClick={() => onUngroup(g.name)}
          >
            Ungroup
          </Button>
        </div>
      ))}
      <ul>
        {loose.map((id) => (
          <li key={id} className="flex items-center gap-1 text-xs">
            <button
              type="button"
              onClick={() => onSelect(id)}
              className="hover:bg-muted focus-visible:ring-ring min-w-0 flex-1 truncate rounded px-1 py-0.5 text-left outline-none focus-visible:ring-2"
            >
              {byId.get(id)?.label ?? id}
            </button>
            <Button
              size="icon-sm"
              variant="ghost"

              aria-label={`Unpin ${byId.get(id)?.label ?? id}`}
              onClick={() => onUnpin(id)}
            >
              <X />
            </Button>
          </li>
        ))}
      </ul>
      {loose.length > 1 && (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) onGroup(name.trim());
            setName("");
          }}
        >
          <Input
            aria-label="Group name"
            placeholder="Group name"
            value={name}
            maxLength={80}
            onChange={(e) => setName(e.target.value)}
            className="h-7 text-xs"
          />
          <Button size="sm" variant="outline" className="h-7" type="submit" disabled={!name.trim()}>
            Group
          </Button>
        </form>
      )}
    </section>
  );
}
