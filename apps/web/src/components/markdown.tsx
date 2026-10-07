"use client";

import { useQuery } from "@tanstack/react-query";
import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { Citation } from "@/components/citation";
import { isFigure, LIVE, LiveRef, LiveRefs } from "@/components/live-ref";
import { q } from "@/lib/api";
import { cn } from "@/lib/utils";

/** A citation of a source, [@key] or [@key p4] (its key in sources/, a page). */
const CITE = /\[@([a-z0-9][a-z0-9-]{0,63})(?: p(\d+))?\]/g;
const CITED = "louped-cite:";
const LIVED = "louped-live:";

type Node = {
  type: string;
  value?: string;
  url?: string;
  children?: Node[];
  data?: { hName?: string; hProperties?: Record<string, unknown> };
};

/** Turns citations and live refs in text into links Citation and LiveRef draw; code and links
 * are left as they are. A paragraph holding a live figure becomes a div, which a figure may sit
 * in. */
function remarkRefs() {
  const walk = (node: Node) => {
    if (!node.children || node.type === "link" || node.type === "linkReference") return;
    node.children = node.children.flatMap((child): Node[] => {
      if (child.type !== "text" || !child.value) {
        walk(child);
        return [child];
      }
      const found = [
        ...[...child.value.matchAll(CITE)].map((m) => ({
          m,
          url: `${CITED}${m[1]}${m[2] ? `#${m[2]}` : ""}`,
        })),
        ...[...child.value.matchAll(LIVE)].map((m) => ({
          m,
          url: `${LIVED}${encodeURIComponent(m[1])}`,
        })),
      ].sort((a, b) => a.m.index - b.m.index);
      const out: Node[] = [];
      let at = 0;
      for (const { m, url } of found) {
        if (m.index < at) continue;
        if (m.index > at) out.push({ type: "text", value: child.value.slice(at, m.index) });
        out.push({ type: "link", url, children: [{ type: "text", value: m[0] }] });
        at = m.index + m[0].length;
      }
      if (at === 0) return [child];
      if (at < child.value.length) out.push({ type: "text", value: child.value.slice(at) });
      return out;
    });
    const figure = (c: Node) =>
      c.url?.startsWith(LIVED) && isFigure(decodeURIComponent(c.url.slice(LIVED.length)));
    if (node.type === "paragraph" && node.children.some(figure))
      node.data = { hName: "div", hProperties: { className: ["my-3", "text-sm"] } };
  };
  return (tree: Node) => walk(tree);
}

/** Lets louped-cite: and louped-live: links through the sanitiser, which keeps only web and
 * mail links. */
const urlTransform = (url: string) =>
  url.startsWith(CITED) || url.startsWith(LIVED) ? url : defaultUrlTransform(url);

/** Markdown in louped's type: Geist for prose, mono for code, tables like the app's. The first
 * heading is left out, since the page header already names the document. */
const components: Components = {
  h1: () => null,
  h2: ({ children }) => (
    <h2 className="mt-8 mb-2 border-b pb-2 text-base font-semibold tracking-tight first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => <h3 className="mt-6 mb-2 text-sm font-semibold">{children}</h3>,
  p: ({ children }) => <p className="my-3 text-sm leading-relaxed">{children}</p>,
  a: ({ children, href }) => {
    if (href?.startsWith(CITED)) {
      const [cite, page] = href.slice(CITED.length).split("#");
      return <Citation cite={cite} page={page ? Number(page) : null} />;
    }
    if (href?.startsWith(LIVED))
      return <LiveRef text={decodeURIComponent(href.slice(LIVED.length))} />;
    return (
      <a href={href} className="underline underline-offset-4 hover:no-underline">
        {children}
      </a>
    );
  },
  ul: ({ children }) => <ul className="my-3 list-disc space-y-1 pl-5 text-sm">{children}</ul>,
  ol: ({ children }) => <ol className="my-3 list-decimal space-y-1 pl-5 text-sm">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  code: ({ children, className }) =>
    className ? (
      <code className={className}>{children}</code>
    ) : (
      <code className="bg-muted rounded px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
    ),
  pre: ({ children }) => (
    <pre className="bg-muted/50 my-3 overflow-x-auto rounded-lg border p-3 font-mono text-xs leading-relaxed">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">{children}</table>
    </div>
  ),
  // Alignment from |---:| arrives as style; a right-aligned column is numbers, so mono.
  th: ({ children, style }) => (
    <th
      style={style}
      className="text-muted-foreground border-b px-3 py-2 text-left text-xs font-medium"
    >
      {children}
    </th>
  ),
  td: ({ children, style }) => (
    <td
      style={style}
      className={cn(
        "border-b px-3 py-2 text-xs tabular-nums",
        style?.textAlign === "right" && "font-mono",
      )}
    >
      {children}
    </td>
  ),
};

/** noImages: for text from a layout or an agent, which should not make the browser fetch from
 * another site. Live refs ({{run:<id> <metric>}}, {{<ref to a figure>}}) are read from the
 * server in one request and drawn in place. */
export function Markdown({ children, noImages }: { children: string; noImages?: boolean }) {
  const refs = [...new Set([...children.matchAll(LIVE)].map((m) => m[1]))].sort();
  const live = useQuery({ ...q.live(refs), enabled: refs.length > 0 });
  return (
    <LiveRefs.Provider value={live}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkRefs]}
        components={components}
        urlTransform={urlTransform}
        disallowedElements={noImages ? ["img"] : undefined}
      >
        {children}
      </ReactMarkdown>
    </LiveRefs.Provider>
  );
}
