import type { CircuitGraph, CircuitLink, CircuitNode } from "@/lib/api";

/** A graph cut down for drawing: the nodes and edges kept, and how many there were. */
export type Cut = {
  nodes: CircuitNode[];
  links: CircuitLink[];
  total: { nodes: number; links: number };
};

/** Pinned nodes merged into one: circuit-tracer's supernode. */
export type Group = { name: string; nodes: string[] };

/** The smallest set of items, strongest first, whose shares reach `keep` of the total. */
function strongest<T>(items: T[], share: (t: T) => number, keep: number): T[] {
  const sorted = [...items].sort((a, b) => share(b) - share(a));
  const total = sorted.reduce((s, t) => s + share(t), 0);
  if (total <= 0) return sorted;
  const out: T[] = [];
  let sum = 0;
  for (const t of sorted) {
    if (sum >= keep * total) break;
    out.push(t);
    sum += share(t);
  }
  return out;
}

/** Prunes as circuit-tracer does: the nodes that carry `nodes` of the influence on the logits, then
 * the edges between them that carry `edges` of it. Logits stay; a node left with no edge goes. */
export function prune(g: CircuitGraph, nodes: number, edges: number): Cut {
  const logits = g.nodes.filter((n) => n.kind === "logit");
  const kept = new Set([
    ...logits.map((n) => n.id),
    ...strongest(
      g.nodes.filter((n) => n.kind !== "logit"),
      (n) => n.score,
      nodes,
    ).map((n) => n.id),
  ]);
  const among = g.links.filter((l) => kept.has(l.source) && kept.has(l.target));
  const links = strongest(among, (l) => l.share, edges);
  const linked = new Set(links.flatMap((l) => [l.source, l.target]));
  return {
    nodes: g.nodes.filter((n) => kept.has(n.id) && (n.kind === "logit" || linked.has(n.id))),
    links,
    total: { nodes: g.nodes.length, links: g.links.length },
  };
}

/** Only the pinned nodes and the edges between them, each group drawn as one node: its row and
 * position the members' highest, its score their sum, its edges theirs added up. */
export function subgraph(g: CircuitGraph, pinned: string[], groups: Group[]): Cut {
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const into = new Map<string, string>();
  const nodes: CircuitNode[] = [];
  for (const grp of groups) {
    const members = grp.nodes.map((id) => byId.get(id)).filter((n): n is CircuitNode => !!n);
    if (members.length === 0) continue;
    const id = `group:${grp.name}`;
    for (const m of members) into.set(m.id, id);
    nodes.push({
      id,
      kind: "feature",
      layer: members.reduce((a, m) => (m.row >= a.row ? m : a)).layer,
      row: Math.max(...members.map((m) => m.row)),
      position: Math.max(...members.map((m) => m.position)),
      label: grp.name,
      score: members.reduce((s, m) => s + m.score, 0),
      target: false,
    });
  }
  for (const id of pinned) {
    const n = byId.get(id);
    if (n && !into.has(id)) nodes.push(n);
  }
  const shown = new Set(nodes.map((n) => n.id));
  const merged = new Map<string, CircuitLink>();
  for (const l of g.links) {
    const source = into.get(l.source) ?? l.source;
    const target = into.get(l.target) ?? l.target;
    if (source === target || !shown.has(source) || !shown.has(target)) continue;
    const key = `${source}→${target}`;
    const was = merged.get(key);
    merged.set(key, {
      source,
      target,
      weight: (was?.weight ?? 0) + l.weight,
      share: (was?.share ?? 0) + l.share,
    });
  }
  return {
    nodes,
    links: [...merged.values()],
    total: { nodes: g.nodes.length, links: g.links.length },
  };
}

export type Placed = CircuitNode & { x: number; y: number; r: number };
export type Laid = {
  width: number;
  height: number;
  nodes: Placed[];
  /** Each row's y and its layer, bottom (embeddings) first. */
  rows: { y: number; layer: string; kind: CircuitNode["kind"] }[];
  /** Each token position's centre. */
  columns: { x: number; token: string }[];
};

export const PAD = { left: 56, right: 16, top: 32, bottom: 72 };
const ROW = 72;
const GAP = 22;
/** Logits sit wider apart: each carries its token as a label. */
const LOGIT_GAP = 64;
const EMPTY = 26;
const gap = (members: CircuitNode[]) => (members[0]?.kind === "logit" ? LOGIT_GAP : GAP);

/** Token positions across, layers up: each column as wide as its busiest cell, a cell's nodes
 * strongest first. A graph narrower than `fit` is spread out to it, rows up to 112 apart. */
export function layout(cut: Cut, tokens: string[], fit = 0): Laid {
  const rowsOf = [...new Set(cut.nodes.map((n) => n.row))].sort((a, b) => a - b);
  const positions = Math.max(tokens.length, ...cut.nodes.map((n) => n.position + 1));
  const cells = new Map<string, CircuitNode[]>();
  for (const n of [...cut.nodes].sort((a, b) => b.score - a.score)) {
    const key = `${n.row}:${n.position}`;
    cells.set(key, [...(cells.get(key) ?? []), n]);
  }
  const widths = Array.from({ length: positions }, (_, p) =>
    Math.max(
      EMPTY,
      ...rowsOf.map((r) => {
        const members = cells.get(`${r}:${p}`) ?? [];
        return members.length * gap(members) + 12;
      }),
    ),
  );
  const natural = PAD.left + PAD.right + widths.reduce((s, w) => s + w, 0);
  const extra = Math.max(0, fit - natural) / positions;
  for (let p = 0; p < positions; p++) widths[p] += extra;
  const starts = [PAD.left];
  for (let i = 1; i < positions; i++) starts[i] = starts[i - 1] + widths[i - 1];
  const step = rowsOf.length > 1 ? Math.min(112, Math.max(ROW, 360 / (rowsOf.length - 1))) : ROW;
  const height = PAD.top + PAD.bottom + Math.max(1, rowsOf.length - 1) * step;
  const yOf = (row: number) => height - PAD.bottom - rowsOf.indexOf(row) * step;
  const max = Math.max(1e-9, ...cut.nodes.filter((n) => n.kind !== "logit").map((n) => n.score));
  const nodes: Placed[] = [];
  for (const [key, members] of cells) {
    const [row, p] = key.split(":").map(Number);
    const g = gap(members);
    const left = starts[p] + (widths[p] - members.length * g) / 2 + g / 2;
    members.forEach((n, i) =>
      nodes.push({
        ...n,
        x: left + i * g,
        y: yOf(row),
        r: n.kind === "logit" ? 7 : 3 + 6 * Math.sqrt(Math.min(1, n.score / max)),
      }),
    );
  }
  const kinds = new Map(cut.nodes.map((n) => [n.row, n]));
  return {
    width: starts[positions - 1] + widths[positions - 1] + PAD.right,
    height,
    nodes,
    rows: rowsOf.map((r) => ({ y: yOf(r), layer: kinds.get(r)!.layer, kind: kinds.get(r)!.kind })),
    columns: widths.map((w, p) => ({ x: starts[p] + w / 2, token: tokens[p] ?? "" })),
  };
}

/** Every node a node reads from and writes to, through the kept edges, and the edges between. */
export function paths(
  links: CircuitLink[],
  from: string,
): { nodes: Set<string>; links: Set<CircuitLink> } {
  const up = new Map<string, CircuitLink[]>();
  const down = new Map<string, CircuitLink[]>();
  for (const l of links) {
    up.set(l.source, [...(up.get(l.source) ?? []), l]);
    down.set(l.target, [...(down.get(l.target) ?? []), l]);
  }
  const nodes = new Set([from]);
  const on = new Set<CircuitLink>();
  for (const [edges, next] of [
    [up, (l: CircuitLink) => l.target],
    [down, (l: CircuitLink) => l.source],
  ] as const) {
    const todo = [from];
    const seen = new Set([from]);
    while (todo.length) {
      for (const l of edges.get(todo.pop()!) ?? []) {
        on.add(l);
        const n = next(l);
        nodes.add(n);
        if (!seen.has(n)) {
          seen.add(n);
          todo.push(n);
        }
      }
    }
  }
  return { nodes, links: on };
}

/** A node's strongest inputs and outputs among the edges, by absolute weight. */
export function neighbours(links: CircuitLink[], id: string, n = 8) {
  const by = (a: CircuitLink, b: CircuitLink) => Math.abs(b.weight) - Math.abs(a.weight);
  return {
    inputs: links
      .filter((l) => l.target === id)
      .sort(by)
      .slice(0, n),
    outputs: links
      .filter((l) => l.source === id)
      .sort(by)
      .slice(0, n),
  };
}
