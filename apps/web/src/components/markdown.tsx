import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { Citation } from "@/components/citation";
import { cn } from "@/lib/utils";

/** A citation of a source, [@key] or [@key p4] (its key in sources/, a page). */
const CITE = /\[@([a-z0-9][a-z0-9-]{0,63})(?: p(\d+))?\]/g;
const CITED = "louped-cite:";

type Node = { type: string; value?: string; url?: string; children?: Node[] };

/** Turns citations in text into links Citation draws; code and links are left as they are. */
function remarkCite() {
  const walk = (node: Node) => {
    if (!node.children || node.type === "link" || node.type === "linkReference") return;
    node.children = node.children.flatMap((child): Node[] => {
      if (child.type !== "text" || !child.value) {
        walk(child);
        return [child];
      }
      const out: Node[] = [];
      let at = 0;
      for (const m of child.value.matchAll(CITE)) {
        if (m.index > at) out.push({ type: "text", value: child.value.slice(at, m.index) });
        out.push({
          type: "link",
          url: `${CITED}${m[1]}${m[2] ? `#${m[2]}` : ""}`,
          children: [{ type: "text", value: m[0] }],
        });
        at = m.index + m[0].length;
      }
      if (at === 0) return [child];
      if (at < child.value.length) out.push({ type: "text", value: child.value.slice(at) });
      return out;
    });
  };
  return (tree: Node) => walk(tree);
}

/** Lets louped-cite: links through the sanitiser, which keeps only web and mail links. */
const urlTransform = (url: string) => (url.startsWith(CITED) ? url : defaultUrlTransform(url));

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
 * another site. */
export function Markdown({ children, noImages }: { children: string; noImages?: boolean }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkCite]}
      components={components}
      urlTransform={urlTransform}
      disallowedElements={noImages ? ["img"] : undefined}
    >
      {children}
    </ReactMarkdown>
  );
}
