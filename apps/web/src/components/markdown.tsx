import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

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
  a: ({ children, href }) => (
    <a href={href} className="underline underline-offset-4 hover:no-underline">
      {children}
    </a>
  ),
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

export function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </ReactMarkdown>
  );
}
